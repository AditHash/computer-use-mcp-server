"""Discovery permissions, opaque IDs, expiry, and process replacement."""

import json
import os
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from server import mcp
from src.backends import windows as windows_backend
from src.core.policy import allowed_applications, configure_allowed_applications, normalize_executable
from src.core.targets import TargetRegistry, WindowRecord
from src.tools import targets

APP = r'C:\Windows\System32\notepad.exe'
ALLOWED = frozenset({normalize_executable(APP)})
WINDOW = WindowRecord(handle=123, process_id=42, process_started=100.0,
                      executable=normalize_executable(APP), window_class='Notepad', title='Test note')


class PolicyTests(unittest.TestCase):
    def test_default_is_empty_and_paths_are_case_insensitive(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(allowed_applications(), frozenset())
        with patch.dict(os.environ, {'COMPUTER_USE_ALLOWED_APPS': json.dumps([APP.upper()])}):
            self.assertEqual(allowed_applications(), ALLOWED)

    def test_invalid_policy_never_grants_access(self):
        for value in ('not-json', '"notepad.exe"', '["notepad.exe"]', '["*"]', '[42]'):
            with self.subTest(value=value), patch.dict(os.environ, {'COMPUTER_USE_ALLOWED_APPS': value}):
                with self.assertRaisesRegex(ToolError, 'INVALID_ARGUMENT'):
                    allowed_applications()

    def test_startup_resolves_a_running_app_to_an_exact_path(self):
        process = SimpleNamespace(info={'name': 'Notepad.exe', 'exe': APP})
        with patch.dict(os.environ, {}, clear=True), patch('src.core.policy.psutil.process_iter', return_value=[process]):
            configure_allowed_applications(['notepad'])
            self.assertEqual(allowed_applications(), ALLOWED)

    def test_ambiguous_running_app_names_do_not_change_policy(self):
        processes = [SimpleNamespace(info={'name': 'notepad.exe', 'exe': path})
                     for path in (APP, r'C:\Other\notepad.exe')]
        with patch.dict(os.environ, {}, clear=True), patch('src.core.policy.psutil.process_iter', return_value=processes):
            with self.assertRaisesRegex(ToolError, 'ambiguous'):
                configure_allowed_applications(['notepad'])
            self.assertEqual(allowed_applications(), frozenset())

    def test_missing_app_does_not_change_policy(self):
        with patch.dict(os.environ, {}, clear=True), patch('src.core.policy.psutil.process_iter', return_value=[]):
            with self.assertRaisesRegex(ToolError, 'running'):
                configure_allowed_applications(['notepad'])
            self.assertEqual(allowed_applications(), frozenset())

    def test_explicit_paths_still_pass_through_policy_validation(self):
        with patch.dict(os.environ, {}, clear=True):
            configure_allowed_applications([APP])
            self.assertEqual(allowed_applications(), ALLOWED)


class RegistryTests(unittest.TestCase):
    def test_ids_are_opaque_and_stable_but_titles_can_change(self):
        registry = TargetRegistry()
        first = registry.refresh([WINDOW], ALLOWED)[0]
        second = registry.refresh([replace(WINDOW, title='New title')], ALLOWED)[0]
        self.assertEqual(first['target_id'], second['target_id'])
        self.assertEqual(second['name'], 'New title')
        self.assertEqual(set(first), {'target_id', 'name', 'kind'})
        self.assertTrue(first['target_id'].startswith('t_'))

    def test_reused_handle_and_pid_get_a_new_id_for_a_new_process(self):
        registry = TargetRegistry()
        first = registry.refresh([WINDOW], ALLOWED)[0]['target_id']
        second = registry.refresh([replace(WINDOW, process_started=200.0)], ALLOWED)[0]['target_id']
        self.assertNotEqual(first, second)

    def test_closed_revoked_and_expired_entries_are_not_reused(self):
        now = [0.0]
        registry = TargetRegistry(clock=lambda: now[0])
        first = registry.refresh([WINDOW], ALLOWED)[0]['target_id']
        self.assertEqual(registry.refresh([], ALLOWED), [])
        second = registry.refresh([WINDOW], ALLOWED)[0]['target_id']
        self.assertNotEqual(first, second)
        self.assertEqual(registry.refresh([WINDOW], frozenset()), [])
        third = registry.refresh([WINDOW], ALLOWED)[0]['target_id']
        self.assertNotEqual(second, third)
        now[0] = 61.0
        fourth = registry.refresh([WINDOW], ALLOWED)[0]['target_id']
        self.assertNotEqual(third, fourth)

    def test_titles_and_target_count_are_bounded(self):
        windows = [replace(WINDOW, handle=index, title='x' * 1000) for index in range(105)]
        result = TargetRegistry().refresh(windows, ALLOWED)
        self.assertEqual(len(result), 100)
        self.assertTrue(all(len(target['name']) == 200 for target in result))

    def test_foreground_lookup_does_not_return_expired_ids(self):
        now = [0.0]
        registry = TargetRegistry(clock=lambda: now[0])
        target = registry.refresh([WINDOW], ALLOWED)[0]
        self.assertEqual(registry.target_id_for_handle(WINDOW.handle), target['target_id'])
        now[0] = 61.0
        self.assertIsNone(registry.target_id_for_handle(WINDOW.handle))


class DiscoveryTests(unittest.TestCase):
    def test_empty_policy_does_not_enumerate_windows(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(targets, 'discover_windows') as discover:
            self.assertEqual(targets.computer_list_targets(), [])
        discover.assert_not_called()

    def test_browser_backend_is_explicitly_unavailable(self):
        with self.assertRaisesRegex(ToolError, 'UNSUPPORTED'):
            targets.computer_list_targets(kind='browser')

    def test_policy_revocation_is_checked_before_returning_results(self):
        with patch.object(targets, 'allowed_applications', side_effect=[ALLOWED, frozenset()]), patch.object(targets, 'discover_windows', return_value=[WINDOW]):
            self.assertEqual(targets.computer_list_targets(), [])

    def test_active_window_without_permission_does_not_query_foreground(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(targets, 'foreground_window_handle') as foreground:
            self.assertIsNone(targets.get_active_window())
        foreground.assert_not_called()

    def test_active_window_reuses_the_discovery_target_id(self):
        with patch.dict(os.environ, {'COMPUTER_USE_ALLOWED_APPS': json.dumps([APP])}), patch.object(targets, 'discover_windows', return_value=[WINDOW]), patch.object(targets, 'foreground_window_handle', return_value=WINDOW.handle):
            listed = targets.computer_list_targets()[0]
            self.assertEqual(targets.get_active_window(), listed)

    def test_active_window_not_allowed_or_focus_changed_returns_none(self):
        for handles in ((999, 999), (WINDOW.handle, 999)):
            with self.subTest(handles=handles), patch.dict(os.environ, {'COMPUTER_USE_ALLOWED_APPS': json.dumps([APP])}), patch.object(targets, 'discover_windows', return_value=[WINDOW]), patch.object(targets, 'foreground_window_handle', side_effect=handles):
                self.assertIsNone(targets.get_active_window())


class TargetsMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_window_without_permission_is_a_successful_null_result(self):
        with patch.dict(os.environ, {}, clear=True):
            async with Client(mcp) as client:
                result = await client.call_tool('get_active_window', {})
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content, {'result': None})

    async def test_allowed_windows_are_returned_without_internal_identity(self):
        with patch.dict(os.environ, {'COMPUTER_USE_ALLOWED_APPS': json.dumps([APP])}), patch.object(targets, 'discover_windows', return_value=[WINDOW]):
            async with Client(mcp) as client:
                result = await client.call_tool('computer_list_targets', {'kind': 'desktop'})
        self.assertFalse(result.is_error)
        target = result.structured_content['result'][0]
        self.assertEqual(set(target), {'target_id', 'name', 'kind'})
        self.assertEqual(target['kind'], 'desktop')

    async def test_client_arguments_cannot_grant_application_permission(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(targets, 'discover_windows') as discover:
            async with Client(mcp) as client:
                result = await client.call_tool('computer_list_targets', {'allowed_apps': [APP]})
        self.assertTrue(result.is_error or result.structured_content['result'] == [])
        discover.assert_not_called()

    async def test_unknown_kind_is_rejected_before_discovery(self):
        with patch.object(targets, 'discover_windows') as discover:
            async with Client(mcp) as client:
                result = await client.call_tool('computer_list_targets', {'kind': 'shell'})
        self.assertTrue(result.is_error)
        discover.assert_not_called()


class WindowsBackendTests(unittest.TestCase):
    def test_unapproved_titles_are_not_read(self):
        from unittest.mock import Mock

        native_error = type('NativeError', (Exception,), {})
        gui = SimpleNamespace(
            EnumWindows=lambda callback, extra: [callback(handle, extra) for handle in (10, 20)],
            IsWindowVisible=lambda handle: True,
            GetWindowText=Mock(return_value='Allowed note'),
            GetClassName=lambda handle: 'Notepad',
        )
        process_api = SimpleNamespace(GetWindowThreadProcessId=lambda handle: (1, handle))

        def process(pid):
            return SimpleNamespace(
                create_time=lambda: 100.0,
                exe=lambda: APP if pid == 10 else r'C:\Other\app.exe',
                is_running=lambda: True,
            )

        modules = {'pywintypes': SimpleNamespace(error=native_error), 'win32gui': gui, 'win32process': process_api}
        with patch.dict('sys.modules', modules), patch.object(windows_backend.sys, 'platform', 'win32'), patch.object(windows_backend.psutil, 'Process', side_effect=process):
            result = windows_backend.discover_windows(ALLOWED)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].handle, 10)
        gui.GetWindowText.assert_called_once_with(10)

    def test_owner_change_during_enumeration_discards_the_window(self):
        from unittest.mock import Mock

        native_error = type('NativeError', (Exception,), {})
        gui = SimpleNamespace(
            EnumWindows=lambda callback, extra: callback(10, extra),
            IsWindowVisible=lambda handle: True,
            GetWindowText=lambda handle: 'Allowed note',
            GetClassName=lambda handle: 'Notepad',
        )
        process_api = SimpleNamespace(GetWindowThreadProcessId=Mock(side_effect=[(1, 42), (1, 99)]))
        process = SimpleNamespace(create_time=lambda: 100.0, exe=lambda: APP, is_running=lambda: True)
        modules = {'pywintypes': SimpleNamespace(error=native_error), 'win32gui': gui, 'win32process': process_api}
        with patch.dict('sys.modules', modules), patch.object(windows_backend.sys, 'platform', 'win32'), patch.object(windows_backend.psutil, 'Process', return_value=process):
            self.assertEqual(windows_backend.discover_windows(ALLOWED), [])


if __name__ == '__main__':
    unittest.main()
