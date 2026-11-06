"""Screenshot permission and output checks; no real desktop is captured."""

import base64
import os
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from server import mcp
from src.tools import screenshot


class ScreenshotTests(unittest.TestCase):
    def setUp(self):
        session = patch.object(screenshot, 'require_interactive_session')
        session.start()
        self.addCleanup(session.stop)
        self.environment = patch.dict(os.environ, {"COMPUTER_USE_ALLOW_SCREENSHOTS": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.platform = patch.object(screenshot.sys, "platform", "win32")
        self.platform.start()
        self.addCleanup(self.platform.stop)
        self.factory = patch.object(screenshot, "MSS")
        self.capture_factory = self.factory.start()
        self.addCleanup(self.factory.stop)
        self.capture = self.capture_factory.return_value.__enter__.return_value
        self.capture.primary_monitor = {"left": 0, "top": 0, "width": 2, "height": 1}
        self.capture.grab.return_value = SimpleNamespace(
            rgb=b"\xff\x00\x00\x00\xff\x00", size=(2, 1)
        )

    def test_permission_is_denied_before_opening_capture(self):
        for setting in ("", "0", "true"):
            with self.subTest(setting=setting), patch.dict(
                os.environ, {"COMPUTER_USE_ALLOW_SCREENSHOTS": setting}
            ), self.assertRaisesRegex(ToolError, "PERMISSION_DENIED"):
                screenshot.take_screenshot()
        self.capture_factory.assert_not_called()

    def test_returns_png_image_without_logging_pixels(self):
        with self.assertLogs(screenshot.logger, level="INFO") as logs:
            image = screenshot.take_screenshot()
        self.assertEqual(image.data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", image.data[16:24]), (2, 1))
        self.assertNotIn(repr(image.data), " ".join(logs.output))
        self.capture.grab.assert_called_once_with(self.capture.primary_monitor)
        self.capture_factory.return_value.__exit__.assert_called_once()

    def test_rejects_oversized_monitor_before_capture(self):
        self.capture.primary_monitor = {"width": 100_000, "height": 100_000}
        with self.assertRaisesRegex(ToolError, "OUT_OF_BOUNDS"):
            screenshot.take_screenshot()
        self.capture.grab.assert_not_called()

    def test_rejects_oversized_encoded_result(self):
        with patch.object(screenshot, "MAX_PNG_BYTES", 1), self.assertRaisesRegex(ToolError, "OUT_OF_BOUNDS"):
            screenshot.take_screenshot()

    def test_capture_failure_hides_backend_details(self):
        self.capture.grab.side_effect = screenshot.ScreenShotError("private backend details")
        with self.assertRaisesRegex(ToolError, "BACKEND_UNAVAILABLE") as error:
            screenshot.take_screenshot()
        self.assertNotIn("private backend details", str(error.exception))

    def test_non_windows_is_explicitly_unsupported(self):
        with patch.object(screenshot.sys, "platform", "linux"), self.assertRaisesRegex(ToolError, "UNSUPPORTED"):
            screenshot.take_screenshot()
        self.capture_factory.assert_not_called()


class ScreenshotMCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        session = patch.object(screenshot, 'require_interactive_session')
        session.start()
        self.addCleanup(session.stop)
    async def test_permission_denial_is_an_mcp_error_without_capture(self):
        with patch.dict(os.environ, {"COMPUTER_USE_ALLOW_SCREENSHOTS": "0"}), patch.object(screenshot, "MSS") as capture:
            async with Client(mcp) as client:
                result = await client.call_tool("take_screenshot", {})
            self.assertTrue(result.is_error)
            self.assertIn("PERMISSION_DENIED", result.content[0].text)
            capture.assert_not_called()

    async def test_image_is_delivered_as_png_content(self):
        with patch.dict(os.environ, {"COMPUTER_USE_ALLOW_SCREENSHOTS": "1"}), patch.object(screenshot.sys, "platform", "win32"), patch.object(screenshot, "MSS") as factory:
            capture = factory.return_value.__enter__.return_value
            capture.primary_monitor = {"width": 2, "height": 1}
            capture.grab.return_value = SimpleNamespace(rgb=b"\xff\x00\x00\x00\xff\x00", size=(2, 1))
            async with Client(mcp) as client:
                result = await client.call_tool("take_screenshot", {})
            self.assertFalse(result.is_error)
            image = result.content[0]
            self.assertEqual(image.type, "image")
            self.assertEqual(image.mime_type, "image/png")
            self.assertEqual(base64.b64decode(image.data)[:8], b"\x89PNG\r\n\x1a\n")
            self.assertIsNone(result.structured_content)


if __name__ == "__main__":
    unittest.main()
