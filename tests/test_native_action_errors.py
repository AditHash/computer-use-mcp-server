"""Distinguish absent patterns from errors after native actions start."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.backends.accessibility import DesktopAdapter
from src.core.errors import ComputerError
from src.core.observations import ElementRecord
from src.core.stop import StopState


class NoPattern(Exception):
    pass


@pytest.mark.parametrize('missing', [False, True])
def test_native_pattern_absence_and_uncertain_execution_are_distinct(missing):
    invoked = Mock(side_effect=OSError('private provider diagnostic'))
    class Control:
        @property
        def iface_invoke(self):
            if missing:
                raise NoPattern()
            return SimpleNamespace(Invoke=invoked)
    record = ElementRecord('Button', 'Increment', True, True, None, ('uia', (1,)))
    adapter = DesktopAdapter(None, StopState())
    adapter._elements = Mock(return_value=[(record, Control())])
    with (
        patch.dict('sys.modules', {'pywinauto.uia_defines': SimpleNamespace(NoPatternInterfaceError=NoPattern)}),
        pytest.raises(ComputerError) as caught,
    ):
        adapter._perform(None, record, 'click', {}, None)
    assert caught.value.code == ('UNSUPPORTED' if missing else 'BACKEND_UNAVAILABLE')
    assert 'private provider' not in str(caught.value)
    assert invoked.call_count == (0 if missing else 1)


def test_legacy_handles_are_observation_only():
    record = ElementRecord('Button', 'Increment', True, True, None, ('win32', 123))
    adapter = DesktopAdapter(None, StopState())
    adapter._elements = Mock(return_value=[(record, Mock())])
    with pytest.raises(ComputerError, match='UNSUPPORTED'):
        adapter._perform(None, record, 'click', {}, None)
