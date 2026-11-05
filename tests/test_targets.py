"""Discovery permissions, opaque IDs, expiry, and process replacement."""

import json
import os
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from src.core.policy import allowed_applications, normalize_executable
from src.core.targets import TargetRegistry, WindowRecord

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












if __name__ == '__main__':
    unittest.main()
