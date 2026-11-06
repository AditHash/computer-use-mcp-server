"""Authorization and dispatch shared by native and managed-browser tools."""
import asyncio
import io
from pathlib import Path
from typing import Literal

from PIL import Image as PILImage
from pydantic import BaseModel

from src.backends.banner import EmergencyBanner

from . import audit
from .errors import ComputerError
from .observations import ObservationStore
from .operator import SAFE_KEYS, PolicySource
from .stop import StopState


class ActionResult(BaseModel):
    target_id: str
    action: str
    status: Literal['verified', 'executed_unverified']
    observation_invalidated: bool = True


class ComputerRuntime:
    def __init__(self, source=None, desktop=None, browser=None, banner_factory=EmergencyBanner):
        self.source = source or PolicySource()
        self.observations = ObservationStore()
        self.options = {}
        self.stop = StopState()
        self.banner = banner_factory(self.stop)
        self.lock = asyncio.Lock()
        self.desktop = desktop
        self.worker = None
        self.browser = browser
        self.active = False

    def browser_targets(self):
        return self.browser.targets() if self.browser else []

    async def _desktop(self):
        if self.desktop is None:
            from src.backends.accessibility import DesktopAdapter
            from src.backends.worker import WindowsWorker
            self.worker = await WindowsWorker.create(self.stop)
            self.desktop = DesktopAdapter(self.worker, self.stop)
            self.active = True
        return self.desktop

    def _browser(self):
        if self.browser is None:
            from src.backends.browser import BrowserAdapter
            self.browser = BrowserAdapter(self.source.load, self.observations.invalidate)
            loop = asyncio.get_running_loop()
            def abort_context():
                if not loop.is_closed():
                    loop.call_soon_threadsafe(lambda: asyncio.create_task(self._abort_browser_context()))
            self.stop.on_stop(abort_context)
        self.active = True
        return self.browser

    async def _abort_browser_context(self):
        context = self.browser.context if self.browser else None
        if context is not None:
            from playwright.async_api import Error as PlaywrightError
            try:
                await context.close()
            except PlaywrightError:
                # The normal shutdown path may already have closed this context.
                return

    async def _watch_browser_policy(self, revision):
        """Abort auto-waiting input when trusted rules change during dispatch."""
        while True:
            await asyncio.sleep(0.05)
            try:
                unchanged = self.source.load().revision() == revision
            except ComputerError:
                unchanged = False
            if not unchanged:
                # Cancelling an awaiting Playwright call alone does not retract
                # its pending browser-side input. The stop callback closes the
                # entire owned context, so delayed input cannot later fire.
                self.stop.stop()
                return

    def _target(self, target_id, policy):
        if self.browser and target_id in self.browser.pages:
            item = self.browser.ensure(target_id)
            return 'browser', item, item.scope
        from src.tools.targets import registry
        window = registry.resolve(target_id, policy.apps())
        return 'desktop', window, window.executable

    async def open_browser(self, url):
        async with self.lock:
            try:
                self.stop.check()
                with self.stop.track():
                    target = await self._browser().open(url)
                audit.emit('browser_open', target['target_id'], 'allowed', 'verified')
                return target
            except asyncio.CancelledError:
                self.stop.stop()
                if self.browser:
                    await self.browser.close()
                audit.emit('browser_open', '-', 'allowed', 'CANCELLED')
                raise ComputerError('CANCELLED', 'Managed browser navigation was cancelled.') from None
            except ComputerError as error:
                audit.emit('browser_open', '-', 'denied', error.code)
                raise

    async def _observe(self, target_id, max_depth):
        policy = self.source.load()
        revision = policy.revision()
        if not policy.permissions.inspect:
            raise ComputerError('PERMISSION_DENIED', 'Inspection is disabled by local policy.')
        self.stop.check()
        if policy.permissions.interact:
            await self._begin_interaction(policy)
        kind, target, _ = self._target(target_id, policy)
        depth = min(max_depth, policy.limits.max_depth)
        count = policy.limits.max_elements
        if kind == 'desktop':
            adapter = await self._desktop()
            fingerprint, records = await adapter.observe(target, depth, count, policy.limits.timeout_seconds)
        else:
            fingerprint, records = await self.browser.observe(target_id, depth, count)
        # Permission may have changed while the backend was reading.
        current = self.source.load()
        self._target(target_id, current)
        if not current.permissions.inspect:
            raise ComputerError('PERMISSION_DENIED', 'Inspection permission was revoked.')
        if current.revision() != revision:
            raise ComputerError('STALE_REF', 'Local policy changed during observation; observe again.')
        self.options[target_id] = (depth, count)
        return self.observations.create(target_id, fingerprint, records, kind, revision)

    async def observe(self, target_id, max_depth=6):
        async with self.lock:
            try:
                return await self._observe(target_id, max_depth)
            except BaseException:
                self.observations.invalidate(target_id)
                raise

    async def _fresh(self, target_id, snapshot_id, policy):
        self.stop.check()
        snapshot = self.observations.snapshot(target_id, snapshot_id)
        if snapshot.policy_revision != policy.revision():
            self.observations.invalidate(target_id)
            raise ComputerError('STALE_REF', 'Local policy changed; obtain a new observation.')
        kind, target, scope = self._target(target_id, policy)
        depth, count = self.options[target_id]
        if kind == 'desktop':
            adapter = await self._desktop()
            fingerprint, _ = await adapter.observe(target, depth, count, policy.limits.timeout_seconds)
        else:
            fingerprint, _ = await self.browser.observe(target_id, depth, count)
        if fingerprint != snapshot.fingerprint:
            self.observations.invalidate(target_id)
            raise ComputerError('STALE_REF', 'The target changed; observe again before acting.')
        self.stop.check()
        self.observations.snapshot(target_id, snapshot_id)
        current = self.source.load()
        if current.revision() != snapshot.policy_revision:
            self.observations.invalidate(target_id)
            raise ComputerError('STALE_REF', 'Local policy changed while validating the target.')
        self._target(target_id, current)
        return kind, target, scope, snapshot

    def _control(self, target_id, snapshot_id, ref, policy, scope, action):
        record = self.observations.resolve(target_id, snapshot_id, ref)
        snapshot = self.observations.snapshot(target_id, snapshot_id)
        if sum(entry.role == record.role and entry.name == record.name for entry in snapshot.records.values()) > 1:
            raise ComputerError('PERMISSION_DENIED', 'The local control grant is ambiguous in this observation.')
        policy.check_control(record.scope or scope, record.role, record.name, action)
        return record

    async def _begin_interaction(self, policy):
        self.stop.check()
        if not policy.permissions.interact:
            raise ComputerError('PERMISSION_DENIED', 'Interaction is disabled by local policy.')
        await asyncio.to_thread(self.banner.start)
        self.stop.check()

    async def action(self, target_id, snapshot_id, ref, action, **arguments):
        async with self.lock:
            decision = 'denied'
            try:
                policy = self.source.load()
                if not policy.permissions.interact:
                    raise ComputerError('PERMISSION_DENIED', 'Interaction is disabled by local policy.')
                kind, target, scope, snapshot = await self._fresh(target_id, snapshot_id, policy)
                record = self._control(target_id, snapshot_id, ref, policy, scope, action)
                if action == 'type' and len(arguments['text']) > policy.limits.max_text_length:
                    raise ComputerError('INVALID_ARGUMENT', 'Text exceeds the local operator limit.')
                if action == 'press_keys' and not set(arguments['keys']) <= SAFE_KEYS:
                    raise ComputerError('INVALID_ARGUMENT', 'Only bounded navigation keys are supported.')
                if (action == 'focus' or (kind == 'desktop' and action == 'press_keys')) and not policy.permissions.focus:
                    raise ComputerError('PERMISSION_DENIED', 'Local policy does not allow focus disruption.')
                if action == 'drag':
                    arguments['destination_record'] = self._control(target_id, snapshot_id,
                        arguments['destination_ref'], policy, scope, action)
                    image_points = arguments.get('image_points')
                    if image_points is not None:
                        if not policy.permissions.fallback:
                            raise ComputerError('PERMISSION_DENIED', 'Mapped drag endpoints require local fallback permission.')
                        points = [self.observations.map_point(target_id, snapshot_id, image_points['map_id'],
                            image_points[prefix + '_x'], image_points[prefix + '_y']) for prefix in ('source', 'destination')]
                        for entry, point in zip((record, arguments['destination_record']), points, strict=True):
                            bounds = entry.rect
                            if bounds is None or not (bounds['left'] <= point[0] < bounds['left'] + bounds['width'] and
                                bounds['top'] <= point[1] < bounds['top'] + bounds['height']):
                                raise ComputerError('OUT_OF_BOUNDS', 'Mapped drag endpoints must lie inside their permitted elements.')
                        arguments['points'] = points
                # Reload policy immediately before dispatch, after all awaits.
                current = self.source.load()
                self._target(target_id, current)
                current.check_control(record.scope or scope, record.role, record.name, action)
                await self._begin_interaction(current)
                # Showing the operator banner is an await boundary. Check policy
                # and target state again before any actual input is dispatched.
                current = self.source.load()
                kind, target, scope, snapshot = await self._fresh(target_id, snapshot_id, current)
                self._control(target_id, snapshot_id, ref, current, scope, action)
                def authorize(entry=record):
                    live = self.source.load()
                    if live.revision() != snapshot.policy_revision:
                        raise ComputerError('STALE_REF', 'Local policy changed before native dispatch.')
                    self._target(target_id, live)
                    self.stop.check()
                    live.check_control(entry.scope or scope, entry.role, entry.name, action)
                    if (action == 'focus' or (kind == 'desktop' and action in ('press_keys', 'double_click', 'drag'))) and not live.permissions.focus:
                        raise ComputerError('PERMISSION_DENIED', 'Focus permission was revoked.')
                    if kind == 'desktop' and action in ('double_click', 'drag') and not live.permissions.fallback:
                        raise ComputerError('PERMISSION_DENIED', 'Physical fallback permission was revoked.')
                    if arguments.get('image_points') is not None and not live.permissions.fallback:
                        raise ComputerError('PERMISSION_DENIED', 'Mapped drag permission was revoked.')
                authorize()
                decision = 'allowed'
                with self.stop.track():
                    if kind == 'browser':
                        watcher = asyncio.create_task(self._watch_browser_policy(snapshot.policy_revision))
                        try:
                            verified = await self.browser.perform(target_id, record, action, arguments, snapshot.fingerprint)
                        finally:
                            watcher.cancel()
                            await asyncio.gather(watcher, return_exceptions=True)
                    elif action in ('double_click', 'drag'):
                        if not current.permissions.fallback or not current.permissions.focus:
                            raise ComputerError('PERMISSION_DENIED', 'Physical fallback and focus disruption must both be enabled locally.')
                        records = [record]
                        if action == 'drag':
                            records.append(arguments['destination_record'])
                        if any(entry.rect is None for entry in records):
                            raise ComputerError('OUT_OF_BOUNDS', 'Fresh element bounds are required for physical fallback.')
                        points = arguments.get('points') or [(entry.rect['left'] + entry.rect['width'] // 2,
                                   entry.rect['top'] + entry.rect['height'] // 2) for entry in records]
                        verified = await self.desktop.physical(target, action, points, arguments.get('duration', 0.5), current.limits.timeout_seconds,
                            authorize=authorize, records=records)
                    else:
                        verified = await self.desktop.perform(target, record, action, arguments, current.limits.timeout_seconds, authorize=authorize)
                self.observations.invalidate(target_id)
                result = ActionResult(target_id=target_id, action=action,
                    status='verified' if verified else 'executed_unverified')
                audit.emit(action, target_id, decision, result.status)
                return result
            except asyncio.CancelledError:
                self.stop.stop()
                self.observations.invalidate(target_id)
                audit.emit(action, target_id, decision, 'CANCELLED')
                raise ComputerError('CANCELLED', 'The operation was cancelled; observe again after an operator restart.') from None
            except ComputerError as error:
                current_snapshot = self.observations.snapshots.get(target_id)
                if decision == 'allowed' or error.code in ('TARGET_NOT_FOUND', 'TARGET_NOT_ALLOWED', 'PERMISSION_DENIED', 'OS_PERMISSION_BOUNDARY') or (
                    error.code == 'STALE_REF' and current_snapshot and current_snapshot.snapshot_id == snapshot_id):
                    self.observations.invalidate(target_id)
                audit.emit(action, target_id, decision, error.code)
                raise

    async def screenshot(self, target_id, snapshot_id, crop=None, max_dimension=1280):
        async with self.lock:
            policy = self.source.load()
            if not policy.permissions.screenshot:
                raise ComputerError('PERMISSION_DENIED', 'Screenshot permission is disabled.')
            kind, target, _, snapshot = await self._fresh(target_id, snapshot_id, policy)
            if kind == 'browser':
                png, bounds = await self.browser.capture(target_id)
            else:
                png, bounds = await self.desktop.capture(target, policy.limits.timeout_seconds)
            current = self.source.load()
            self._target(target_id, current)
            if not current.permissions.screenshot:
                raise ComputerError('PERMISSION_DENIED', 'Screenshot permission was revoked.')
            # Bind the image to the same live target and revision after capture.
            await self._fresh(target_id, snapshot_id, current)
            with PILImage.open(io.BytesIO(png)) as original:
                if original.width * original.height > 16_000_000:
                    raise ComputerError('OUT_OF_BOUNDS', 'Screenshot is too large.')
                image = original.convert('RGB')
                if crop is not None:
                    if crop.left < 0 or crop.top < 0 or crop.left + crop.width > image.width or crop.top + crop.height > image.height:
                        raise ComputerError('OUT_OF_BOUNDS', 'Crop must stay inside the target image.')
                    image = image.crop((crop.left, crop.top, crop.left + crop.width, crop.top + crop.height))
                    bounds = {'left': bounds['left'] + crop.left, 'top': bounds['top'] + crop.top,
                              'width': crop.width, 'height': crop.height}
                image.thumbnail((max_dimension, max_dimension), PILImage.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format='PNG')
                data = output.getvalue()
                if len(data) > 10 * 1024 * 1024:
                    raise ComputerError('OUT_OF_BOUNDS', 'Encoded screenshot is too large.')
                current = self.source.load()
                self.stop.check()
                self._target(target_id, current)
                if not current.permissions.screenshot or current.revision() != snapshot.policy_revision:
                    self.observations.invalidate(target_id)
                    raise ComputerError('PERMISSION_DENIED', 'Screenshot policy changed before image disclosure.')
                image_map = self.observations.add_map(target_id, snapshot_id, bounds, image.width, image.height)
            return data, {**image_map.model_dump(), 'coordinate_space':
                'browser_css_pixels' if kind == 'browser' else 'screen_physical_pixels',
                'scale_x': image_map.image_width / image_map.source.width,
                'scale_y': image_map.image_height / image_map.source.height, 'expires_in_seconds':
                max(0, snapshot.expires - self.observations.clock())}

    async def move(self, target_id, snapshot_id, map_id, x, y, duration=0.5):
        async with self.lock:
            decision = 'denied'
            try:
                policy = self.source.load()
                if not policy.permissions.interact or not policy.permissions.fallback:
                    raise ComputerError('PERMISSION_DENIED', 'Interaction and coordinate fallback must be enabled locally.')
                kind, target, _, _ = await self._fresh(target_id, snapshot_id, policy)
                point = self.observations.map_point(target_id, snapshot_id, map_id, x, y)
                if kind == 'desktop' and not policy.permissions.focus:
                    raise ComputerError('PERMISSION_DENIED', 'Physical pointer movement requires local focus permission.')
                await self._begin_interaction(self.source.load())
                live = self.source.load()
                kind, target, _, snapshot = await self._fresh(target_id, snapshot_id, live)
                def authorize(entry=None):
                    policy = self.source.load()
                    if policy.revision() != snapshot.policy_revision:
                        raise ComputerError('STALE_REF', 'Local policy changed before pointer dispatch.')
                    self._target(target_id, policy)
                    self.stop.check()
                    if not policy.permissions.interact or not policy.permissions.fallback or (kind == 'desktop' and not policy.permissions.focus):
                        raise ComputerError('PERMISSION_DENIED', 'Pointer permissions were revoked.')
                authorize()
                decision = 'allowed'
                with self.stop.track():
                    if kind == 'browser':
                        await self.browser.move(target_id, point)
                    else:
                        await self.desktop.physical(target, 'move', [point], duration, policy.limits.timeout_seconds, authorize=authorize)
                self.observations.invalidate(target_id)
                audit.emit('move', target_id, decision, 'executed_unverified')
                return ActionResult(target_id=target_id, action='move', status='executed_unverified')
            except asyncio.CancelledError:
                self.stop.stop()
                self.observations.invalidate(target_id)
                audit.emit('move', target_id, decision, 'CANCELLED')
                raise ComputerError('CANCELLED', 'Pointer movement was cancelled.') from None
            except ComputerError as error:
                audit.emit('move', target_id, decision, error.code)
                raise

    async def close(self):
        self.stop.stop()
        cleanup = [asyncio.to_thread(self.banner.close)]
        if self.browser:
            cleanup.append(self.browser.close())
        if self.worker:
            cleanup.append(asyncio.to_thread(self.worker.close))
        try:
            results = await asyncio.gather(*(asyncio.wait_for(item, 5) for item in cleanup), return_exceptions=True)
        finally:
            self.observations.snapshots.clear()
            self.observations.maps.clear()
            self.options.clear()
        if any(isinstance(result, BaseException) for result in results):
            raise ComputerError('BACKEND_UNAVAILABLE', 'One owned automation resource could not shut down cleanly.')


_runtime = None
_source = PolicySource()


def configure_runtime(path: Path | None = None):
    global _source, _runtime
    if _runtime is not None and _runtime.active:
        raise ComputerError('INVALID_POLICY', 'Stop the server before changing its policy source.')
    source = PolicySource(path)
    source.load()
    _source = source
    _runtime = None


def get_runtime() -> ComputerRuntime:
    global _runtime
    if _runtime is None:
        _runtime = ComputerRuntime(_source)
    return _runtime


async def close_runtime():
    global _runtime
    current, _runtime = _runtime, None
    if current is not None:
        await current.close()
