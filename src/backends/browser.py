"""Server-owned Playwright contexts with origin guards and AI ARIA references."""
import asyncio
import hashlib
import json
import logging
import math
import re
import threading
import uuid
from contextlib import suppress
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from playwright.async_api import Error as PlaywrightError

from src.core.errors import ComputerError
from src.core.observations import ElementRecord
from src.core.operator import SAFE_KEYS, origin_of, protected

NODE = re.compile(r'^\s*-\s+([\w-]+)(?:\s+"((?:\\.|[^"\\])*)")?.*?\[ref=([^\]]+)\]')
logger = logging.getLogger(__name__)


@dataclass
class BrowserTarget:
    target_id: str
    page: object
    name: str
    scope: str


class BrowserAdapter:
    def __init__(self, policy, invalidate):
        self.policy = policy
        self.invalidate = invalidate
        self.playwright = None
        self.browser = None
        self.context = None
        self.pages: dict[str, BrowserTarget] = {}
        self.lock = threading.Lock()
        self.options = {}
        self.redirects = {}
        self.opening = set()
        self.epochs = {}

    def targets(self):
        policy = self.policy()
        if not policy.permissions.inspect:
            return []
        with self.lock:
            return [{'target_id': item.target_id, 'name': item.name, 'kind': 'browser'}
                    for item in self.pages.values() if item.scope in policy.browser.allowed_origins]

    def _owned(self, page):
        with self.lock:
            return any(item.page is page for item in self.pages.values())

    async def _route(self, route):
        response = None
        try:
            request = route.request
            policy = self.policy()
            if (not self._owned(request.frame.page) or origin_of(request.url) not in policy.browser.allowed_origins or
                request.method not in ('GET', 'HEAD', 'OPTIONS') or
                (request.is_navigation_request() and (not policy.permissions.navigate or protected(urlsplit(request.url).path)))):
                await route.abort('blockedbyclient')
                return
            # Route.continue_ follows redirects without re-running the handler.
            # Fetch exactly one approved hop instead, so no redirect can escape
            # the origin guard, including image/iframe/subresource redirects.
            response = await route.fetch(max_redirects=0, timeout=policy.limits.timeout_seconds * 1000)
            if 300 <= response.status < 400 and 'location' in response.headers:
                destination = urljoin(request.url, response.headers['location'])
                page = request.frame.page
                is_open = any(item.page is page and key in self.opening for key, item in self.pages.items())
                if (is_open and request.is_navigation_request() and request.frame is page.main_frame and
                    origin_of(destination) in self.policy().browser.allowed_origins and not protected(urlsplit(destination).path)):
                    self.redirects[page] = destination
                    # Commit an inert response, then let open() issue the next
                    # separately validated navigation. Aborting an approved hop
                    # races Chromium's error-page navigation with the next goto.
                    await route.fulfill(status=200, content_type='text/html', body='<!doctype html><title>Managed navigation</title>')
                    return
                await route.abort('blockedbyclient')
                return
            if int(response.headers.get('content-length', '0')) > 10 * 1024 * 1024:
                await route.abort('blockedbyclient')
                return
            await route.fulfill(response=response)
        except (PlaywrightError, ComputerError, ValueError):
            logger.info('Blocked a managed browser request that could not be validated')
            with suppress(PlaywrightError):
                await route.abort('blockedbyclient')
        finally:
            if response:
                await response.dispose()

    async def _start(self):
        if self.browser is not None:
            return
        from playwright.async_api import async_playwright
        try:
            manager = async_playwright()
            startup = asyncio.create_task(manager.start())
            try:
                self.playwright = await asyncio.wait_for(asyncio.shield(startup), 5)
            finally:
                if self.playwright is None:
                    # Playwright starts its driver before start() returns an
                    # object. Retain the manager so cancellation cannot orphan
                    # that partially initialized connection.
                    try:
                        with suppress(PlaywrightError, OSError, TimeoutError, AttributeError):
                            await asyncio.wait_for(manager.__aexit__(), 5)
                    finally:
                        startup.cancel()
                        await asyncio.gather(startup, return_exceptions=True)
            self.browser = await self.playwright.chromium.launch(headless=self.policy().browser.headless)
            self.context = await self.browser.new_context(accept_downloads=False,
                service_workers='block', viewport={'width': 1280, 'height': 720})
            await self.context.route('**/*', self._route)
            async def block_socket(route):
                await route.close()
            await self.context.route_web_socket('**/*', block_socket)
        except (PlaywrightError, OSError, TimeoutError):
            await self.close()
            raise ComputerError('BACKEND_UNAVAILABLE', 'Managed Chromium could not start; install it with playwright install chromium.') from None

    def _drop(self, target_id):
        with self.lock:
            self.pages.pop(target_id, None)
        self.options.pop(target_id, None)
        self.epochs.pop(target_id, None)
        self.invalidate(target_id)

    async def _navigated(self, target_id, frame):
        if target_id in self.opening:
            return
        with self.lock:
            item = self.pages.get(target_id)
        if item is None:
            return
        try:
            scope = self._frame_origin(item.page, frame)
            if scope not in self.policy().browser.allowed_origins:
                await item.page.close()
                return
            if frame is item.page.main_frame:
                item.scope = scope
                if self.policy().permissions.inspect:
                    item.name = (await item.page.title())[:200]
        except (PlaywrightError, ComputerError):
            await item.page.close()

    def _frame_origin(self, page, frame):
        while frame.url in ('about:blank', 'about:srcdoc') and frame.parent_frame is not None:
            frame = frame.parent_frame
        return origin_of(frame.url if frame.url not in ('about:blank', 'about:srcdoc') else page.url)

    async def open(self, url):
        policy = self.policy()
        if not policy.permissions.navigate:
            raise ComputerError('PERMISSION_DENIED', 'Browser navigation is disabled by local policy.')
        if len(url) > 2048 or origin_of(url) not in policy.browser.allowed_origins:
            raise ComputerError('TARGET_NOT_ALLOWED', 'The URL origin is not locally approved.')
        await self._start()
        if len(self.pages) >= 16:
            raise ComputerError('OUT_OF_BOUNDS', 'At most 16 managed pages may be open.')
        page = await self.context.new_page()
        target_id = 't_' + uuid.uuid4().hex
        item = BrowserTarget(target_id, page, 'Managed browser', origin_of(url))
        with self.lock:
            self.pages[target_id] = item
        self.opening.add(target_id)
        self.epochs[target_id] = 0
        page.set_default_timeout(policy.limits.timeout_seconds * 1000)
        page.set_default_navigation_timeout(policy.limits.timeout_seconds * 1000)
        page.on('close', lambda: self._drop(target_id))
        def navigated(frame):
            self.epochs[target_id] = self.epochs.get(target_id, 0) + 1
            self.invalidate(target_id)
            asyncio.create_task(self._navigated(target_id, frame))
        page.on('framenavigated', navigated)
        page.on('popup', lambda popup: asyncio.create_task(popup.close()))
        page.on('download', lambda download: asyncio.create_task(download.cancel()))
        try:
            destination = url
            for hop in range(6):
                current = self.policy()
                if not current.permissions.navigate or origin_of(destination) not in current.browser.allowed_origins:
                    raise ComputerError('TARGET_NOT_ALLOWED', 'Navigation permission was revoked.')
                await page.goto(destination, wait_until='domcontentloaded')
                redirect = self.redirects.pop(page, None)
                if redirect is None:
                    break
                if hop == 5:
                    raise ComputerError('TARGET_NOT_ALLOWED', 'The approved navigation exceeded its redirect limit.')
                destination = redirect
            self.ensure(target_id)
            item.scope = origin_of(page.url)
            if self.policy().permissions.inspect:
                item.name = (await page.title())[:200]
            return {'target_id': target_id, 'name': item.name, 'kind': 'browser'}
        except ComputerError:
            await page.close()
            raise
        except PlaywrightError:
            await page.close()
            raise ComputerError('TARGET_NOT_ALLOWED', 'Navigation failed or left the approved origins.') from None
        finally:
            self.opening.discard(target_id)
            self.redirects.pop(page, None)

    def ensure(self, target_id):
        with self.lock:
            item = self.pages.get(target_id)
        if item is None or item.page.is_closed():
            self._drop(target_id)
            raise ComputerError('TARGET_NOT_FOUND', 'The managed page was closed or is unknown.')
        policy = self.policy()
        if origin_of(item.page.url) not in policy.browser.allowed_origins:
            raise ComputerError('TARGET_NOT_ALLOWED', 'The page origin is no longer approved.')
        item.page.set_default_timeout(policy.limits.timeout_seconds * 1000)
        return item

    async def observe(self, target_id, depth, limit):
        item = self.ensure(target_id)
        policy = self.policy()
        if not policy.permissions.inspect:
            raise ComputerError('PERMISSION_DENIED', 'Inspection is disabled by local policy.')
        records = []
        seen = set()
        sources = [str(self.epochs.get(target_id, 0))]
        if len(item.page.frames) > 16:
            raise ComputerError('OUT_OF_BOUNDS', 'The page has too many frames to inspect safely.')
        try:
            # Page snapshots may already include child-frame nodes. Validate
            # every frame first, then deduplicate native refs and obtain each
            # element's actual owning frame rather than inheriting parent scope.
            for frame in item.page.frames:
                if self._frame_origin(item.page, frame) not in policy.browser.allowed_origins:
                    raise ComputerError('TARGET_NOT_ALLOWED', 'A frame origin is not approved.')
            for frame in item.page.frames:
                scope = self._frame_origin(item.page, frame)
                if scope not in policy.browser.allowed_origins:
                    raise ComputerError('TARGET_NOT_ALLOWED', 'A frame origin is not approved.')
                root = item.page if frame is item.page.main_frame else frame.locator('body')
                raw = await root.aria_snapshot(mode='ai', boxes=True, depth=depth)
                if len(raw) > 200_000:
                    raise ComputerError('OUT_OF_BOUNDS', 'The accessibility snapshot is too large.')
                # The raw snapshot can include input values. Only parsed roles,
                # labels and refs are returned; trailing values are never copied.
                sources.extend([frame.url, raw])
                for line in raw.splitlines():
                    match = NODE.match(line)
                    if not match or len(records) >= limit:
                        continue
                    role, encoded_name, native_ref = match.groups()
                    if native_ref in seen:
                        continue
                    try:
                        name = json.loads('"' + encoded_name + '"') if encoded_name else ''
                    except ValueError:
                        name = ''
                    locator = item.page.get_by_ref(native_ref)
                    if await locator.count() != 1:
                        continue
                    handle = await locator.element_handle()
                    if handle is None:
                        raise ComputerError('STALE_REF', 'A frame element was replaced during observation.')
                    try:
                        owner = await handle.owner_frame()
                    finally:
                        await handle.dispose()
                    if owner is None:
                        raise ComputerError('STALE_REF', 'The owning frame was detached.')
                    element_scope = self._frame_origin(item.page, owner)
                    if element_scope not in policy.browser.allowed_origins:
                        raise ComputerError('TARGET_NOT_ALLOWED', 'The element frame origin is not approved.')
                    input_type = (await locator.get_attribute('type') or '').lower()
                    autocomplete = (await locator.get_attribute('autocomplete') or '').lower()
                    sensitive = input_type in ('password', 'file') or protected(name, role) or any(
                        part in autocomplete for part in ('password', 'cc-', 'one-time-code'))
                    box = await locator.bounding_box()
                    rect = None
                    if box and box['width'] > 0 and box['height'] > 0:
                        left, top = math.floor(box['x']), math.floor(box['y'])
                        rect = {'left': left, 'top': top, 'width': max(1, math.ceil(box['x'] + box['width']) - left),
                                'height': max(1, math.ceil(box['y'] + box['height']) - top)}
                    records.append(ElementRecord(role, '[protected]' if sensitive else name[:200],
                        await locator.is_enabled(), await locator.is_visible(), rect, native_ref, sensitive, element_scope))
                    seen.add(native_ref)
            self.options[target_id] = (depth, limit)
            return hashlib.sha256('\n'.join(sources).encode()).hexdigest(), records
        except ComputerError:
            raise
        except PlaywrightError:
            raise ComputerError('STALE_REF', 'Page accessibility changed; observe again.') from None

    async def perform(self, target_id, record, action, args, fingerprint):
        item = self.ensure(target_id)
        current, records = await self.observe(target_id, *self.options[target_id])
        if current != fingerprint:
            raise ComputerError('STALE_REF', 'The page changed since observation.')
        match = next((entry for entry in records if entry.locator == record.locator), None)
        if match is None or match.sensitive or not match.visible or not match.enabled:
            raise ComputerError('STALE_REF', 'The accessible element was replaced or protected.')
        live_policy = self.policy()
        live_policy.check_control(match.scope, match.role, match.name, action)
        if action == 'focus' and not live_policy.permissions.focus:
            raise ComputerError('PERMISSION_DENIED', 'Focus permission was revoked.')
        locator = item.page.get_by_ref(record.locator)
        try:
            if action == 'click':
                await locator.click()
            elif action == 'double_click':
                await locator.dblclick()
            elif action == 'type':
                if match.role not in ('textbox', 'searchbox'):
                    raise ComputerError('PERMISSION_DENIED', 'Typing requires an ordinary editable field.')
                await locator.fill(args['text'])
                return await locator.evaluate('''(el, expected) =>
                    (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement
                        ? el.value : el.isContentEditable ? el.textContent : null) === expected
                ''', args['text'])
            elif action == 'scroll':
                return await locator.evaluate('''(el, args) => {
                    const before = [el.scrollLeft, el.scrollTop];
                    el.scrollBy(args.x, args.y);
                    return el.scrollLeft !== before[0] || el.scrollTop !== before[1];
                }''', {'x': (1 if args['direction'] == 'right' else -1 if args['direction'] == 'left' else 0) * args['amount'] * 40,
                        'y': (1 if args['direction'] == 'down' else -1 if args['direction'] == 'up' else 0) * args['amount'] * 40})
            elif action == 'press_keys':
                if not set(args['keys']) <= SAFE_KEYS:
                    raise ComputerError('INVALID_ARGUMENT', 'Only bounded navigation keys are supported.')
                names = {'TAB': 'Tab', 'SHIFT+TAB': 'Shift+Tab', 'ARROWUP': 'ArrowUp', 'ARROWDOWN': 'ArrowDown',
                         'ARROWLEFT': 'ArrowLeft', 'ARROWRIGHT': 'ArrowRight', 'HOME': 'Home', 'END': 'End',
                         'PAGEUP': 'PageUp', 'PAGEDOWN': 'PageDown', 'ESCAPE': 'Escape'}
                await locator.focus()
                for key in args['keys']:
                    self.ensure(target_id)
                    self.policy().check_control(match.scope, match.role, match.name, action)
                    if not await locator.evaluate('(el) => el.getRootNode().activeElement === el'):
                        raise ComputerError('ELEMENT_NOT_INTERACTABLE', 'Key input moved focus outside the granted control.')
                    if (await locator.get_attribute('type') or '').lower() in ('password', 'file'):
                        raise ComputerError('PERMISSION_DENIED', 'The field became protected.')
                    self.policy().check_control(match.scope, match.role, match.name, action)
                    await locator.press(names[key])
            elif action == 'focus':
                await item.page.bring_to_front()
                await locator.focus()
            elif action == 'drag':
                destination = args['destination_record']
                self.policy().check_control(destination.scope, destination.role, destination.name, 'drag')
                options = {}
                if args.get('points') is not None:
                    if not self.policy().permissions.fallback:
                        raise ComputerError('PERMISSION_DENIED', 'Mapped drag permission was revoked.')
                    source_point, destination_point = args['points']
                    options = {'source_position': {'x': source_point[0] - match.rect['left'], 'y': source_point[1] - match.rect['top']},
                               'target_position': {'x': destination_point[0] - destination.rect['left'], 'y': destination_point[1] - destination.rect['top']}}
                await locator.drag_to(item.page.get_by_ref(destination.locator), **options)
            else:
                raise ComputerError('UNSUPPORTED', 'Unsupported semantic browser operation.')
            return False
        except ComputerError:
            raise
        except PlaywrightError:
            raise ComputerError('BACKEND_UNAVAILABLE', 'The action outcome is uncertain; observe again before deciding what to do.') from None

    async def capture(self, target_id):
        item = self.ensure(target_id)
        try:
            png = await item.page.screenshot(type='png', scale='css', animations='disabled', timeout=5000)
            viewport = item.page.viewport_size
            return png, {'left': 0, 'top': 0, 'width': viewport['width'], 'height': viewport['height']}
        except PlaywrightError:
            raise ComputerError('BACKEND_UNAVAILABLE', 'The managed page could not be captured.') from None

    async def move(self, target_id, point):
        item = self.ensure(target_id)
        policy = self.policy()
        if not policy.permissions.interact or not policy.permissions.fallback:
            raise ComputerError('PERMISSION_DENIED', 'Pointer permissions were revoked.')
        try:
            await item.page.mouse.move(*point)
        except PlaywrightError:
            raise ComputerError('BACKEND_UNAVAILABLE', 'Managed pointer movement failed.') from None

    async def close(self):
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
        finally:
            if self.playwright:
                await self.playwright.stop()
            for target_id in list(self.pages):
                self._drop(target_id)
            self.browser = self.context = self.playwright = None
