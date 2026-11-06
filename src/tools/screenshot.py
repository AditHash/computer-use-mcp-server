"""Opt-in primary-display screenshots returned as MCP images."""

import logging
import os
import sys

from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError
from mss import MSS, ScreenShotError
from mss.tools import to_png

from src.backends.desktop_session import require_interactive_session

logger = logging.getLogger(__name__)

MAX_PIXELS = 16_000_000
MAX_PNG_BYTES = 10 * 1024 * 1024


def take_screenshot() -> Image:
    """Capture the primary Windows display as a PNG image.

    Requires the local operator to set COMPUTER_USE_ALLOW_SCREENSHOTS=1 in
    the server environment. Returns physical pixels, without saving a file.
    """
    if os.environ.get("COMPUTER_USE_ALLOW_SCREENSHOTS") != "1":
        logger.warning("Screenshot denied: local permission is disabled")
        raise ToolError("PERMISSION_DENIED: Screenshots are disabled by the local operator.")
    if sys.platform != "win32":
        raise ToolError("UNSUPPORTED: Screenshots currently support Windows only.")
    from src.core.runtime import get_runtime
    get_runtime().stop.check()
    require_interactive_session()

    logger.info("Capturing the primary display")
    try:
        # Create and close the capture object on the same MCP worker thread.
        with MSS() as capture:
            monitor = capture.primary_monitor
            width, height = monitor["width"], monitor["height"]
            if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                raise ToolError("OUT_OF_BOUNDS: Display exceeds the 16 megapixel limit.")
            frame = capture.grab(monitor)
            png = to_png(frame.rgb, frame.size)
    except (ScreenShotError, OSError):
        logger.error("Windows screenshot capture failed")
        raise ToolError("BACKEND_UNAVAILABLE: Windows could not capture the display.") from None

    if png is None or len(png) > MAX_PNG_BYTES:
        raise ToolError("OUT_OF_BOUNDS: Screenshot exceeds the 10 MiB PNG limit.")

    logger.info("Screenshot captured successfully")
    return Image(data=png, format="png")
