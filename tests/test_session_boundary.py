"""Secure-desktop protection without switching or inspecting any real desktop."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.backends.desktop_session import require_interactive_session
from src.core.errors import ComputerError


@pytest.mark.parametrize('name', ['Winlogon', 'Screen-saver', 'unknown'])
def test_secure_desktop_names_are_denied_and_handles_closed(name):
    native_error = type('NativeError', (Exception,), {})
    handle = SimpleNamespace(CloseDesktop=Mock())
    service = SimpleNamespace(OpenInputDesktop=lambda *args: handle, GetUserObjectInformation=lambda *args: name)
    with patch.dict('sys.modules', {'pywintypes': SimpleNamespace(error=native_error),
        'win32con': SimpleNamespace(DESKTOP_READOBJECTS=1, UOI_NAME=2), 'win32service': service}), pytest.raises(ComputerError, match='OS_PERMISSION_BOUNDARY'):
        require_interactive_session()
    handle.CloseDesktop.assert_called_once()
