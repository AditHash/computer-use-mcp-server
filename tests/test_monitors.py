"""Monitor geometry checks without capturing any screen content."""

import unittest
from unittest.mock import patch

from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from server import mcp
from src.tools import monitors


class MonitorTests(unittest.TestCase):
    def test_negative_coordinates_primary_detection_and_no_capture(self):
        left = {"left": -1280, "top": 0, "width": 1280, "height": 1024}
        primary = {"left": 0, "top": 0, "width": 1920, "height": 1080}
        with patch.object(monitors.sys, "platform", "win32"), patch.object(monitors, "MSS") as factory:
            display = factory.return_value.__enter__.return_value
            display.monitors = [{"left": -1280, "top": 0, "width": 3200, "height": 1080}, left, primary]
            display.primary_monitor = primary
            result = monitors.list_monitors()
            self.assertEqual(result, [
                {"index": 1, **left, "is_primary": False},
                {"index": 2, **primary, "is_primary": True},
            ])
            display.grab.assert_not_called()
            factory.return_value.__exit__.assert_called_once()

    def test_backend_errors_hide_internal_details(self):
        with patch.object(monitors.sys, "platform", "win32"), patch.object(monitors, "MSS") as factory:
            factory.side_effect = monitors.ScreenShotError("private backend details")
            with self.assertRaisesRegex(ToolError, "BACKEND_UNAVAILABLE") as error:
                monitors.list_monitors()
            self.assertNotIn("private backend details", str(error.exception))

    def test_non_windows_does_not_open_backend(self):
        with patch.object(monitors.sys, "platform", "linux"), patch.object(monitors, "MSS") as factory:
            with self.assertRaisesRegex(ToolError, "UNSUPPORTED"):
                monitors.list_monitors()
            factory.assert_not_called()


class MonitorMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_geometry_works_with_screenshots_disabled(self):
        import os

        with patch.dict(os.environ, {"COMPUTER_USE_ALLOW_SCREENSHOTS": "0"}), patch.object(monitors.sys, "platform", "win32"), patch.object(monitors, "MSS") as factory:
            display = factory.return_value.__enter__.return_value
            primary = {"left": 0, "top": 0, "width": 1920, "height": 1080}
            display.monitors = [primary, primary]
            display.primary_monitor = primary
            async with Client(mcp) as client:
                result = await client.call_tool("list_monitors", {})
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["result"], [
                {"index": 1, **primary, "is_primary": True}
            ])
            display.grab.assert_not_called()


if __name__ == "__main__":
    unittest.main()
