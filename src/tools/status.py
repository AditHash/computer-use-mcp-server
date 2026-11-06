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
    target_screenshots: bool
    inspection: bool
    navigation: bool
    focus: bool
    fallback: bool


class ServerStatus(TypedDict):
    status: Literal["ready", "stopped"]
    automation_stopped: bool
    desktop_supported: bool
    available_tools: list[str]
    permissions: PermissionStatus


async def computer_get_status(ctx: Context) -> ServerStatus:
    """Report server readiness, registered tools, and local permission flags.

    Ready means this server can respond, not that desktop capture has been
    tested. No desktop APIs are called. Local policy and stop state determine
    enabled permissions; callers cannot grant themselves additional access.
    """
    logger.info("Reading server status")
    tools = await ctx.mcp_server.list_tools()
    from src.core.runtime import get_runtime
    runtime = get_runtime()
    policy = runtime.source.load()
    active = not runtime.stop.event.is_set()
    result: ServerStatus = {
        "status": "ready" if active else "stopped",
        "automation_stopped": not active,
        "desktop_supported": sys.platform == "win32",
        "available_tools": [tool.name for tool in tools],
        "permissions": {
            "screenshots": os.environ.get("COMPUTER_USE_ALLOW_SCREENSHOTS") == "1" and active,
            "interaction": policy.permissions.interact and active,
            "target_screenshots": policy.permissions.screenshot and active,
            "inspection": policy.permissions.inspect and active,
            "navigation": policy.permissions.navigate and active,
            "focus": policy.permissions.focus and policy.permissions.interact and active,
            "fallback": policy.permissions.fallback and policy.permissions.interact and active,
        },
    }
    logger.info("Server status read successfully")
    return result
