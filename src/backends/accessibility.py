"""UIA-first observation and semantic actions on the owned Windows worker."""
import hashlib
import json
import time

import psutil

from src.core.errors import ComputerError
from src.core.observations import ElementRecord
from src.core.operator import protected
from src.core.policy import normalize_executable

from .desktop_session import require_interactive_session
from .physical import apply_input, capture_window, window_bounds


def validate_window(window):
    require_interactive_session()
    import win32api
    import win32con
    import win32gui
    import win32process
    import win32security
    try:
        if not win32gui.IsWindow(window.handle):
            raise ComputerError('TARGET_NOT_FOUND', 'The window was closed.')
        _, pid = win32process.GetWindowThreadProcessId(window.handle)
        process = psutil.Process(pid)
        if (pid != window.process_id or process.create_time() != window.process_started or
                normalize_executable(process.exe()) != normalize_executable(window.executable) or
                win32gui.GetClassName(window.handle) != window.window_class):
            raise ComputerError('TARGET_NOT_FOUND', 'The process or window identity changed.')
        handle = win32api.OpenProcess(0x1000, False, pid)
        token = own_token = None
        try:
            token = win32security.OpenProcessToken(handle, win32con.TOKEN_QUERY)
            own_token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
            integrity = win32security.GetTokenInformation(token, win32security.TokenIntegrityLevel)[0]
            owner = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
            own_owner = win32security.GetTokenInformation(own_token, win32security.TokenUser)[0]
            if integrity.GetSubAuthority(integrity.GetSubAuthorityCount() - 1) > 0x2000 or owner != own_owner:
                raise ComputerError('OS_PERMISSION_BOUNDARY', 'Elevated or other-user windows are unsupported.')
        finally:
            if own_token:
                own_token.Close()
            if token:
                token.Close()
            handle.Close()
        if not process.is_running():
            raise ComputerError('TARGET_NOT_FOUND', 'The target process was replaced.')
    except ComputerError:
        raise
    except Exception:  # noqa: BLE001 - sanitize heterogeneous native security API failures.
        raise ComputerError('OS_PERMISSION_BOUNDARY', 'Windows did not permit target identity validation.') from None


def digest(records):
    values = [(r.role, r.name, r.enabled, r.visible, r.rect, r.locator, r.sensitive, r.state) for r in records]
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


class DesktopAdapter:
    def __init__(self, worker, stop):
        self.worker = worker
        self.stop = stop

    def _uia_elements(self, window, depth, limit):
        from pywinauto import Desktop
        root = Desktop(backend='uia').window(handle=window.handle).wrapper_object()
        queue = [(root, 0)]
        result = []
        while queue and len(result) < limit:
            self.stop.check()
            control, level = queue.pop(0)
            info = control.element_info
            if info.process_id != window.process_id:
                continue
            sensitive = bool(info.element.CurrentIsPassword)
            role = info.control_type
            name = '[protected]' if sensitive else info.name
            sensitive = sensitive or protected(name, role)
            rect = info.rectangle
            bounds = None
            if rect.right > rect.left and rect.bottom > rect.top:
                bounds = {'left': rect.left, 'top': rect.top, 'width': rect.right - rect.left, 'height': rect.bottom - rect.top}
            identity = tuple(info.runtime_id)
            state = None
            if role == 'Edit' and not sensitive:
                try:
                    value = control.iface_value.CurrentValue
                    state = hashlib.sha256(value.encode()).hexdigest()
                except (AttributeError, TypeError):
                    state = None
            result.append((ElementRecord(role=role, name='[protected]' if sensitive else name[:200],
                enabled=info.enabled, visible=info.visible, rect=bounds,
                locator=('uia', identity), sensitive=sensitive, state=state), control))
            if level < depth and not sensitive:
                queue.extend((child, level + 1) for child in control.children())
        return result

    def _legacy_elements(self, window, depth, limit):
        import win32con
        import win32gui
        import win32process
        classes = {'Button': 'Button', 'Edit': 'Edit', 'Static': 'Text', 'ComboBox': 'ComboBox', 'ListBox': 'List', 'ScrollBar': 'ScrollBar'}
        result = []

        def visit(handle, _):
            self.stop.check()
            if len(result) >= limit:
                return True
            parent, level = win32gui.GetParent(handle), 1
            while parent and parent != window.handle and level <= depth:
                parent = win32gui.GetParent(parent)
                level += 1
            if parent != window.handle or level > depth:
                return True
            _, pid = win32process.GetWindowThreadProcessId(handle)
            role = classes.get(win32gui.GetClassName(handle))
            if not role or pid != window.process_id:
                return True
            sensitive = role == 'Edit' and bool(win32gui.GetWindowLong(handle, win32con.GWL_STYLE) & 0x20)
            # Never read edit contents as a label, even for non-password fields.
            name = '[unlabelled edit]' if role == 'Edit' else win32gui.GetWindowText(handle)
            sensitive = sensitive or protected(name, role)
            result.append((ElementRecord(role, '[protected]' if sensitive else name[:200],
                bool(win32gui.IsWindowEnabled(handle)), bool(win32gui.IsWindowVisible(handle)),
                window_bounds(handle), ('win32', handle), sensitive), handle))
            return True

        win32gui.EnumChildWindows(window.handle, visit, None)
        return result

    def _elements(self, window, depth, limit):
        validate_window(window)
        try:
            result = self._uia_elements(window, depth, limit)
            if len(result) > 1:
                return result
        except ComputerError:
            raise
        except Exception:  # noqa: BLE001 - UIA provider failure permits read-only Win32 observation.
            result = []
        legacy = self._legacy_elements(window, depth, limit)
        if legacy:
            return legacy
        if result:
            return result
        raise ComputerError('UNSUPPORTED', 'No supported accessibility controls are available.')

    def _observe(self, window, depth, limit):
        records = [record for record, _ in self._elements(window, depth, limit)]
        return digest(records), records

    async def observe(self, window, depth, limit, timeout):
        return await self.worker.call(self._observe, window, depth, limit, timeout=timeout)

    def _perform(self, window, record, action, args, authorize):
        self.stop.check()
        elements = self._elements(window, 10, 500)
        pair = next(((entry, control) for entry, control in elements if entry.locator == record.locator), None)
        if pair is None:
            raise ComputerError('STALE_REF', 'The accessible element was replaced.')
        current, control = pair
        if current.sensitive or not current.enabled or not current.visible or current.role != record.role or current.name != record.name or current.state != record.state:
            raise ComputerError('STALE_REF', 'The accessible element changed.')
        self.stop.check()
        if authorize:
            authorize(current)
        if record.locator[0] != 'uia':
            raise ComputerError('UNSUPPORTED', 'Legacy controls support observation only; UIA identity is required for actions.')
        if action == 'focus':
            import pywintypes
            import win32gui
            if win32gui.GetForegroundWindow() == window.handle:
                return True
            try:
                win32gui.SetForegroundWindow(window.handle)
            except pywintypes.error:
                # Some providers report an empty native error even when the
                # asynchronous focus transition completes. Verify state only;
                # never synthesize keys or attach input threads to force focus.
                pass
            deadline = time.monotonic() + 0.25
            while time.monotonic() < deadline:
                self.stop.check()
                if authorize:
                    authorize(current)
                if win32gui.GetForegroundWindow() == window.handle:
                    return True
                time.sleep(0.01)
            raise ComputerError('TARGET_NOT_FOREGROUND', 'Windows rejected the focus request.')
        from pywinauto.uia_defines import NoPatternInterfaceError
        pattern = None
        pattern_name = {'click': 'iface_invoke', 'type': 'iface_value', 'scroll': 'iface_scroll'}.get(action)
        if pattern_name:
            try:
                pattern = getattr(control, pattern_name)
            except NoPatternInterfaceError:
                raise ComputerError('UNSUPPORTED', 'The control does not expose the required accessibility pattern.') from None
        try:
            if action == 'click':
                pattern.Invoke()
                return False
            if action == 'type':
                if current.role != 'Edit' or control.element_info.element.CurrentIsPassword:
                    raise ComputerError('PERMISSION_DENIED', 'Typing requires a non-secret edit control.')
                pattern.SetValue(args['text'])
                return pattern.CurrentValue == args['text']
            if action == 'scroll':
                from comtypes.gen import UIAutomationClient as constants
                movement = constants.ScrollAmount_SmallIncrement if args['direction'] in ('down', 'right') else constants.ScrollAmount_SmallDecrement
                none = constants.ScrollAmount_NoAmount
                for _ in range(args['amount']):
                    self.stop.check()
                    if authorize:
                        authorize(current)
                    pattern.Scroll(movement if args['direction'] in ('left', 'right') else none,
                                               movement if args['direction'] in ('up', 'down') else none)
                return False
            if action == 'press_keys':
                import win32api
                import win32con
                import win32gui
                from pywinauto.keyboard import send_keys
                if win32gui.GetForegroundWindow() != window.handle:
                    raise ComputerError('TARGET_NOT_FOREGROUND', 'Focus the allowed window first.')
                control.element_info.element.SetFocus()
                if not control.element_info.element.CurrentHasKeyboardFocus:
                    raise ComputerError('ELEMENT_NOT_INTERACTABLE', 'The selected control could not receive focus.')
                mapping = {'ARROWUP': '{UP}', 'ARROWDOWN': '{DOWN}', 'ARROWLEFT': '{LEFT}', 'ARROWRIGHT': '{RIGHT}',
                           'TAB': '{TAB}', 'SHIFT+TAB': '+{TAB}', 'HOME': '{HOME}', 'END': '{END}',
                           'PAGEUP': '{PGUP}', 'PAGEDOWN': '{PGDN}', 'ESCAPE': '{ESC}'}
                for key in args['keys']:
                    self.stop.check()
                    if authorize:
                        authorize(current)
                    if win32gui.GetForegroundWindow() != window.handle:
                        raise ComputerError('TARGET_NOT_FOREGROUND', 'Focus changed during key input.')
                    if not control.element_info.element.CurrentHasKeyboardFocus:
                        raise ComputerError('ELEMENT_NOT_INTERACTABLE', 'Key input moved focus outside the granted control.')
                    modifiers = (win32con.VK_CONTROL, win32con.VK_MENU, win32con.VK_SHIFT, win32con.VK_LWIN, win32con.VK_RWIN)
                    if any(win32api.GetAsyncKeyState(code) & 0x8000 for code in modifiers):
                        raise ComputerError('CANCELLED', 'Human modifier input interrupted navigation keys.')
                    send_keys(mapping[key], pause=0.02)
                return False
        except ComputerError:
            raise
        except Exception:  # noqa: BLE001 - execution may have occurred; never suggest a fallback or retry.
            raise ComputerError('BACKEND_UNAVAILABLE', 'The action outcome is uncertain; observe again before deciding what to do.') from None
        raise ComputerError('UNSUPPORTED', 'No semantic implementation exists for this action.')

    async def perform(self, window, record, action, args, timeout, authorize=None):
        return await self.worker.call(self._perform, window, record, action, args, authorize, timeout=timeout)

    async def capture(self, window, timeout):
        def capture():
            validate_window(window)
            self.stop.check()
            return capture_window(window.handle)
        return await self.worker.call(capture, timeout=timeout)

    async def physical(self, window, action, points, duration, timeout, authorize=None, records=None):
        def apply():
            validate_window(window)
            self.stop.check()
            if records:
                live = {entry.locator: entry for entry, _ in self._elements(window, 10, 500)}
                for record in records:
                    entry = live.get(record.locator)
                    if entry is None or entry.rect != record.rect or entry.sensitive or not entry.visible or not entry.enabled:
                        raise ComputerError('STALE_REF', 'The fallback element moved or was replaced.')
                    if authorize:
                        authorize(entry)
            apply_input(window.handle, action, points, self.stop, duration, authorize)
            return False
        return await self.worker.call(apply, timeout=timeout)
