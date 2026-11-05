"""Read-only Windows desktop tools, independent of MCP."""

import ctypes
import logging
import sys
from ctypes import wintypes

logger = logging.getLogger(__name__)


def get_screen_size() -> dict[str, int]:
    """Return the primary screen width and height in Windows desktop coordinates.

    Coordinates may be scaled by Windows DPI settings. This reads the display
    size without taking a screenshot or moving the mouse.
    """
    logger.info("Reading primary screen dimensions")
    if sys.platform != "win32":
        logger.error("Screen size unavailable: Windows is required")
        raise RuntimeError("get_screen_size currently supports Windows only.")

    # Windows defines metric 0 as primary screen width and 1 as height.
    user32 = ctypes.windll.user32
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    if width <= 0 or height <= 0:
        logger.error("Windows could not report the primary screen size")
        raise RuntimeError("Windows could not report the primary screen size.")

    logger.info("Primary screen dimensions read successfully")
    return {"width": width, "height": height}


def get_mouse_position() -> dict[str, int]:
    """Return the mouse cursor's x and y desktop coordinates."""
    logger.info("Reading mouse cursor position")
    if sys.platform != "win32":
        logger.error("Mouse position unavailable: Windows is required")
        raise RuntimeError("get_mouse_position currently supports Windows only.")

    point = wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        logger.error("Windows could not read the cursor position")
        raise RuntimeError("Windows could not read the cursor position.")

    logger.info("Mouse cursor position read successfully")
    return {"x": point.x, "y": point.y}
