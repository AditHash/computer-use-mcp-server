"""Safe server status without probing or controlling the desktop."""

import logging
import os
import sys
from typing import Literal, TypedDict

from mcp.server.mcpserver import Context

logger = logging.getLogger(__name__)


class PermissionStatus(TypedDict):
    screenshots: bool
    interaction: bool


class ServerStatus(TypedDict):
    status: Literal["ready"]
    desktop_supported: bool
    available_tools: list[str]
    permissions: PermissionStatus


async def computer_get_status(ctx: Context) -> ServerStatus:
    """Report server readiness, registered tools, and local permission flags.

    Ready means this server can respond, not that desktop capture has been
    tested. No desktop APIs are called. Interaction is not implemented.
    """
    logger.info("Reading server status")
    tools = await ctx.mcp_server.list_tools()
    result: ServerStatus = {
        "status": "ready",
        "desktop_supported": sys.platform == "win32",
        "available_tools": [tool.name for tool in tools],
        "permissions": {
            "screenshots": os.environ.get("COMPUTER_USE_ALLOW_SCREENSHOTS") == "1",
            "interaction": False,
        },
    }
    logger.info("Server status read successfully")
    return result
