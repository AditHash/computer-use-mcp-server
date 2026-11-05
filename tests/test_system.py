"""System facts and resource metrics, without user or process information."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from server import mcp
from src.tools import system


class SystemTests(unittest.TestCase):
    def test_info_is_limited_to_system_and_cpu_facts(self):
        with patch.multiple(system.platform, system=lambda: 'Windows', release=lambda: '11', version=lambda: '10.0.test', machine=lambda: 'AMD64', processor=lambda: 'Test CPU'), patch.object(system.psutil, 'cpu_count', side_effect=lambda logical: 8 if logical else 4):
            result = system.get_computer_info()
        self.assertEqual(result, {
            'os_name': 'Windows', 'os_release': '11', 'os_version': '10.0.test',
            'architecture': 'AMD64', 'cpu_model': 'Test CPU',
            'cpu_logical_cores': 8, 'cpu_physical_cores': 4,
        })

    def test_unknown_cpu_details_are_null_not_invented(self):
        with patch.object(system.platform, 'processor', return_value=''), patch.object(system.psutil, 'cpu_count', return_value=None):
            result = system.get_computer_info()
        self.assertIsNone(result['cpu_model'])
        self.assertIsNone(result['cpu_physical_cores'])
        self.assertIsNone(result['cpu_logical_cores'])

    def test_resource_units_sampling_and_windows_system_drive(self):
        memory = SimpleNamespace(total=1000, available=600, used=400, percent=40.0)
        disk = SimpleNamespace(total=2000, used=500, free=1500, percent=25.0)
        with patch.object(system.sys, 'platform', 'win32'), patch.dict(os.environ, {'SystemDrive': 'D:'}), patch.object(system.psutil, 'cpu_percent', return_value=12.5) as cpu, patch.object(system.psutil, 'virtual_memory', return_value=memory), patch.object(system.psutil, 'disk_usage', return_value=disk) as usage:
            result = system.get_computer_resources()
        cpu.assert_called_once_with(interval=0.1)
        usage.assert_called_once_with('D:\\')
        self.assertEqual(result, {
            'cpu_percent': 12.5,
            'memory': {'total_bytes': 1000, 'available_bytes': 600, 'used_bytes': 400, 'percent': 40.0},
            'system_disk': {'total_bytes': 2000, 'used_bytes': 500, 'free_bytes': 1500, 'percent': 25.0},
        })

    def test_other_platforms_use_root_disk(self):
        with patch.object(system.sys, 'platform', 'linux'), patch.object(system.psutil, 'cpu_percent', return_value=0), patch.object(system.psutil, 'virtual_memory'), patch.object(system.psutil, 'disk_usage') as usage:
            system.get_computer_resources()
        usage.assert_called_once_with('/')

    def test_errors_do_not_disclose_backend_details(self):
        for function, failing_call in (
            (system.get_computer_info, 'cpu_count'),
            (system.get_computer_resources, 'cpu_percent'),
        ):
            with self.subTest(function=function.__name__), patch.object(system.psutil, failing_call, side_effect=OSError('private backend details')):
                with self.assertRaisesRegex(ToolError, 'BACKEND_UNAVAILABLE') as error:
                    function()
                self.assertNotIn('private backend details', str(error.exception))


class SystemMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_metrics_need_no_screenshot_permission_or_client_arguments(self):
        with patch.dict(os.environ, {'COMPUTER_USE_ALLOW_SCREENSHOTS': '0'}):
            async with Client(mcp) as client:
                tools = await client.list_tools()
                for name in ('get_computer_info', 'get_computer_resources'):
                    tool = next(tool for tool in tools.tools if tool.name == name)
                    self.assertEqual(tool.input_schema.get('properties', {}), {})
                info = await client.call_tool('get_computer_info', {})
                resources = await client.call_tool('get_computer_resources', {})
        self.assertFalse(info.is_error)
        self.assertFalse(resources.is_error)
        self.assertIsInstance(info.structured_content['os_name'], str)
        self.assertGreater(resources.structured_content['memory']['total_bytes'], 0)
        self.assertGreater(resources.structured_content['system_disk']['total_bytes'], 0)


if __name__ == '__main__':
    unittest.main()
