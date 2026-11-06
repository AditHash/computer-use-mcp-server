"""No real input: verify recipient ownership and human-interruption guards."""
import contextlib
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.backends import physical
from src.core.errors import ComputerError
from src.core.stop import StopState


@pytest.mark.parametrize('position,hit', [((1000, 1000), 7), ((20, 20), 99)])
def test_no_click_when_cursor_moves_or_another_window_covers_the_point(position, hit):
    class FailSafe(Exception):
        pass
    gui = SimpleNamespace(FAILSAFE=True, FailSafeException=FailSafe, moveTo=Mock(), click=Mock(),
        doubleClick=Mock(), mouseDown=Mock(), position=lambda: SimpleNamespace(x=position[0], y=position[1]))
    windows = SimpleNamespace(GetForegroundWindow=lambda: 7, WindowFromPoint=lambda point: hit,
                              IsChild=lambda parent, child: False)
    api = SimpleNamespace(mouse_event=Mock(), GetAsyncKeyState=lambda key: 0)
    constants = SimpleNamespace(MOUSEEVENTF_LEFTUP=4, VK_CONTROL=17, VK_MENU=18, VK_SHIFT=16, VK_LWIN=91, VK_RWIN=92, VK_LBUTTON=1)
    processes = SimpleNamespace(GetWindowThreadProcessId=lambda handle: (1, 42 if handle == 7 else 99))
    with patch.dict('sys.modules', {'pyautogui': gui, 'win32gui': windows, 'win32api': api,
                                  'win32con': constants, 'win32process': processes}), patch.object(
        physical, 'physical_pixels', contextlib.nullcontext), patch.object(physical, 'window_bounds',
            return_value={'left': 0, 'top': 0, 'width': 100, 'height': 100}), pytest.raises(ComputerError):
        physical.apply_input(7, 'double_click', [(20, 20)], StopState(), duration=0)
    gui.click.assert_not_called()
    gui.doubleClick.assert_not_called()
    gui.mouseDown.assert_not_called()
