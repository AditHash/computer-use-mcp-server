"""Deterministic tests for authorization, stale refs, and coordinate maps."""
import pytest

from src.core.errors import ComputerError
from src.core.observations import ElementRecord, ObservationStore
from src.core.operator import OperatorPolicy, origin_of


def test_policy_defaults_deny_writes_and_navigation():
    policy = OperatorPolicy()
    assert not policy.permissions.interact
    assert not policy.permissions.screenshot
    assert not policy.permissions.navigate
    assert not policy.permissions.fallback
    assert not policy.permissions.focus
    assert not policy.grants


def test_origin_validation_blocks_credentials_and_non_http():
    assert origin_of('https://example.test/a?q=1') == 'https://example.test'
    for url in ('file:///x', 'javascript:alert(1)', 'https://user:pass@example.test/', 'data:text/html,x'):
        with pytest.raises(ComputerError):
            origin_of(url)


def test_controls_need_exact_local_grants_and_protected_names_still_fail():
    policy = OperatorPolicy.model_validate({'permissions': {'interact': True}, 'grants': [
        {'target': 'http://example.test', 'role': 'button', 'name': 'Increment', 'actions': ['click']},
        {'target': 'http://example.test', 'role': 'button', 'name': 'Delete', 'actions': ['click']},
    ]})
    policy.check_control('http://example.test', 'button', 'Increment', 'click')
    for name in ('Other', 'Delete'):
        with pytest.raises(ComputerError, match='PERMISSION_DENIED'):
            policy.check_control('http://example.test', 'button', name, 'click')


def element(name='Increment'):
    return ElementRecord(role='button', name=name, enabled=True, visible=True,
                         rect={'left': 0, 'top': 0, 'width': 100, 'height': 20}, locator='native-1')


def test_observations_invalidate_previous_and_cross_target_refs():
    store = ObservationStore()
    first = store.create('target-a', 'fingerprint', [element()])
    ref = first.elements[0].ref
    assert store.resolve('target-a', first.snapshot_id, ref).name == 'Increment'
    with pytest.raises(ComputerError, match='STALE_REF'):
        store.resolve('target-b', first.snapshot_id, ref)
    newest = store.create('target-a', 'new', [element()])
    with pytest.raises(ComputerError, match='STALE_REF'):
        store.resolve('target-a', first.snapshot_id, ref)
    assert store.resolve('target-a', newest.snapshot_id, newest.elements[0].ref).name == 'Increment'


def test_expired_refs_and_protected_fields_are_rejected():
    now = [0.0]
    store = ObservationStore(clock=lambda: now[0])
    observation = store.create('a', 'f', [element('Password')])
    assert observation.elements[0].name == '[protected]'
    with pytest.raises(ComputerError, match='PERMISSION_DENIED'):
        store.resolve('a', observation.snapshot_id, observation.elements[0].ref)
    now[0] = 31.0
    with pytest.raises(ComputerError, match='STALE_REF'):
        store.snapshot('a', observation.snapshot_id)


def test_coordinate_maps_are_target_and_snapshot_scoped():
    store = ObservationStore()
    observation = store.create('a', 'f', [element()])
    image_map = store.add_map('a', observation.snapshot_id,
                              {'left': -1920, 'top': 20, 'width': 1920, 'height': 1080}, 960, 540)
    assert store.map_point('a', observation.snapshot_id, image_map.map_id, 100, 100) == (-1720, 220)
    for point in ((-1, 0), (960, 0), (0, 540)):
        with pytest.raises(ComputerError, match='OUT_OF_BOUNDS'):
            store.map_point('a', observation.snapshot_id, image_map.map_id, *point)
    with pytest.raises(ComputerError, match='STALE_REF'):
        store.map_point('b', observation.snapshot_id, image_map.map_id, 0, 0)
