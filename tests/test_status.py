"""Read-only server status and permission reporting through MCP."""

import os
import unittest
from unittest.mock import patch

from mcp import Client

from server import mcp


class StatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_status_matches_discovered_tools_and_has_no_arguments(self):
        with patch.dict(os.environ, {}, clear=True):
            async with Client(mcp) as client:
                tools = await client.list_tools()
                status = next(tool for tool in tools.tools if tool.name == "computer_get_status")
                self.assertEqual(status.input_schema.get("properties", {}), {})
                result = await client.call_tool("computer_get_status", {})
            self.assertFalse(result.is_error)
            data = result.structured_content
            self.assertEqual(data["status"], "ready")
            self.assertEqual(data["available_tools"], [tool.name for tool in tools.tools])
            self.assertEqual(data["permissions"], {"screenshots": False, "interaction": False,
                "target_screenshots": False, "inspection": True, "navigation": False, "focus": False, "fallback": False})
            self.assertFalse(data['automation_stopped'])
            self.assertEqual(set(data), {"status", "automation_stopped", "desktop_supported", "available_tools", "permissions"})

    async def test_status_tracks_screenshot_permission_without_capturing(self):
        with patch('src.tools.screenshot.MSS') as capture:
            async with Client(mcp) as client:
                for setting, expected in (("1", True), ("0", False), ("true", False)):
                    with self.subTest(setting=setting), patch.dict(os.environ, {"COMPUTER_USE_ALLOW_SCREENSHOTS": setting}):
                        result = await client.call_tool("computer_get_status", {})
                        self.assertFalse(result.is_error)
                        self.assertEqual(result.structured_content["permissions"]["screenshots"], expected)
                        self.assertFalse(result.structured_content["permissions"]["interaction"])
            capture.assert_not_called()

    async def test_status_remains_available_without_a_windows_desktop(self):
        with patch('sys.platform', 'linux'):
            async with Client(mcp) as client:
                result = await client.call_tool("computer_get_status", {})
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["status"], "ready")
            self.assertFalse(result.structured_content["desktop_supported"])


if __name__ == "__main__":
    unittest.main()
