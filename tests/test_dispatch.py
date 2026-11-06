"""Permission and stale-reference checks around deterministic adapter actions."""
import asyncio
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from src.core.errors import ComputerError
from src.core.observations import ElementRecord
from src.core.operator import OperatorPolicy
from src.core.runtime import ComputerRuntime


class Banner:
    def __init__(self, stop):
        self.stop = stop
    def start(self):
        pass
    def close(self):
        pass


class Source:
    def __init__(self, policy):
        self.policy = policy
    def load(self):
        return self.policy


class Browser:
    def __init__(self, name='Increment', role='button'):
        self.pages = {'t': SimpleNamespace(scope='http://fixture.test')}
        self.fingerprint = 'same'
        self.elements = [ElementRecord(role, name, True, True,
            {'left': 0, 'top': 0, 'width': 100, 'height': 50}, 'native', scope='http://fixture.test')]
        self.calls = 0
    def ensure(self, target):
        if target not in self.pages:
            raise ComputerError('TARGET_NOT_FOUND', 'Unknown fixture target.')
        return self.pages[target]
    async def observe(self, target, *options):
        return self.fingerprint, self.elements
    async def perform(self, *args):
        self.calls += 1
        return True
    async def capture(self, target):
        buffer = io.BytesIO()
        Image.new('RGB', (100, 50), 'green').save(buffer, format='PNG')
        return buffer.getvalue(), {'left': 0, 'top': 0, 'width': 100, 'height': 50}
    async def close(self):
        self.pages.clear()


def runtime(name='Increment', role='button', **permissions):
    policy = OperatorPolicy.model_validate({'permissions': permissions,
        'grants': [{'target': 'http://fixture.test', 'role': role, 'name': name,
                    'actions': ['click', 'type', 'press_keys', 'scroll', 'double_click', 'drag']}]})
    browser = Browser(name, role)
    return ComputerRuntime(Source(policy), browser=browser, banner_factory=Banner), browser


async def test_default_permissions_deny_before_dispatch():
    engine, backend = runtime()
    observation = await engine.observe('t')
    with pytest.raises(ComputerError, match='PERMISSION_DENIED'):
        await engine.action('t', observation.snapshot_id, observation.elements[0].ref, 'click')
    assert backend.calls == 0


async def test_changed_observation_and_revoked_permission_do_not_act():
    engine, backend = runtime(interact=True)
    observation = await engine.observe('t')
    backend.fingerprint = 'changed'
    with pytest.raises(ComputerError, match='STALE_REF'):
        await engine.action('t', observation.snapshot_id, observation.elements[0].ref, 'click')
    backend.fingerprint = 'same'
    observation = await engine.observe('t')
    engine.source.policy.permissions.interact = False
    with pytest.raises(ComputerError, match='PERMISSION_DENIED'):
        await engine.action('t', observation.snapshot_id, observation.elements[0].ref, 'click')
    assert backend.calls == 0


async def test_verified_type_invalidates_refs_and_audit_excludes_text(capsys):
    engine, backend = runtime(name='Name', role='textbox', interact=True)
    observation = await engine.observe('t')
    result = await engine.action('t', observation.snapshot_id, observation.elements[0].ref, 'type', text='private-user-text')
    assert result.status == 'verified'
    assert backend.calls == 1
    with pytest.raises(ComputerError, match='STALE_REF'):
        engine.observations.snapshot('t', observation.snapshot_id)
    audit = capsys.readouterr().err
    assert '"action":"type"' in audit
    assert 'private-user-text' not in audit


async def test_protected_control_and_unsafe_keys_are_denied():
    engine, backend = runtime(name='Delete everything', interact=True)
    observation = await engine.observe('t')
    with pytest.raises(ComputerError, match='PERMISSION_DENIED'):
        await engine.action('t', observation.snapshot_id, observation.elements[0].ref, 'click')
    assert backend.calls == 0
    engine, backend = runtime(interact=True)
    observation = await engine.observe('t')
    with pytest.raises(ComputerError, match='INVALID_ARGUMENT'):
        await engine.action('t', observation.snapshot_id, observation.elements[0].ref, 'press_keys', keys=['CTRL', 'ENTER'])
    assert backend.calls == 0


async def test_target_screenshot_requires_permission_and_returns_a_scoped_map():
    engine, _ = runtime()
    observation = await engine.observe('t')
    with pytest.raises(ComputerError, match='PERMISSION_DENIED'):
        await engine.screenshot('t', observation.snapshot_id)
    engine.source.policy.permissions.screenshot = True
    observation = await engine.observe('t')
    png, metadata = await engine.screenshot('t', observation.snapshot_id, max_dimension=50)
    assert png[:8] == b'\x89PNG\r\n\x1a\n'
    assert metadata['image_width'] == 50
    assert metadata['image_height'] == 25
    assert engine.observations.map_point('t', observation.snapshot_id, metadata['map_id'], 10, 10) == (20, 20)


async def test_cancellation_sets_the_stop_and_rejects_future_actions():
    engine, backend = runtime(interact=True)
    entered = asyncio.Event()
    async def slow(*args):
        entered.set()
        await asyncio.sleep(10)
    backend.perform = slow
    observation = await engine.observe('t')
    task = asyncio.create_task(engine.action('t', observation.snapshot_id, observation.elements[0].ref, 'click'))
    await entered.wait()
    task.cancel()
    with pytest.raises(ComputerError, match='CANCELLED'):
        await task
    assert engine.stop.event.is_set()


async def test_policy_revision_change_invalidates_old_refs_even_when_grant_remains():
    engine, backend = runtime(interact=True)
    observation = await engine.observe('t')
    engine.source.policy.limits.max_text_length = 100
    with pytest.raises(ComputerError, match='STALE_REF'):
        await engine.action('t', observation.snapshot_id, observation.elements[0].ref, 'click')
    assert backend.calls == 0
    observation = await engine.observe('t')
    result = await engine.action('t', observation.snapshot_id, observation.elements[0].ref, 'click')
    assert result.status == 'verified'


async def test_cleanup_closes_all_owned_resources_if_browser_close_fails():
    engine, backend = runtime()
    async def broken():
        raise OSError('fixture cleanup failure')
    backend.close = broken
    engine.worker = SimpleNamespace(close=Mock())
    engine.banner.close = Mock()
    with pytest.raises(ComputerError, match='BACKEND_UNAVAILABLE'):
        await engine.close()
    engine.worker.close.assert_called_once()
    engine.banner.close.assert_called_once()
    assert not engine.observations.snapshots


@pytest.mark.parametrize('failure', ['permission', 'bounds', 'stale', 'none'])
async def test_mapped_drag_requires_fresh_map_permission_and_granted_element_bounds(failure):
    engine, backend = runtime(interact=True, screenshot=True, fallback=failure != 'permission')
    observation = await engine.observe('t')
    _, metadata = await engine.screenshot('t', observation.snapshot_id, max_dimension=50)
    points = {'map_id': metadata['map_id'], 'source_x': 5, 'source_y': 5,
              'destination_x': 10, 'destination_y': 10}
    if failure == 'bounds':
        # Valid image point that is outside the now narrower granted element.
        engine.observations.snapshots['t'].records[observation.elements[0].ref].rect = {
            'left': 0, 'top': 0, 'width': 2, 'height': 2}
    if failure == 'stale':
        observation = await engine.observe('t')
    arguments = {'destination_ref': observation.elements[0].ref, 'image_points': points}
    if failure != 'none':
        code = {'permission': 'PERMISSION_DENIED', 'bounds': 'OUT_OF_BOUNDS', 'stale': 'STALE_REF'}[failure]
        with pytest.raises(ComputerError, match=code):
            await engine.action('t', observation.snapshot_id, observation.elements[0].ref, 'drag', **arguments)
        assert backend.calls == 0
    else:
        result = await engine.action('t', observation.snapshot_id, observation.elements[0].ref, 'drag', **arguments)
        assert result.status == 'verified'
        assert backend.calls == 1


async def test_screenshot_revocation_during_final_observation_never_returns_image():
    engine, backend = runtime(screenshot=True)
    observation = await engine.observe('t')
    original = backend.observe
    calls = 0
    async def revoke_during_final_observe(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            engine.source.policy.permissions.screenshot = False
        return await original(*args)
    backend.observe = revoke_during_final_observe
    with pytest.raises(ComputerError, match='STALE_REF|PERMISSION_DENIED'):
        await engine.screenshot('t', observation.snapshot_id)
    assert not engine.observations.maps
