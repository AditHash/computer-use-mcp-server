"""Read-only discovery of locally approved desktop targets."""

import logging
from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError

from src.backends.windows import (
    BackendUnavailableError,
    UnsupportedPlatformError,
    discover_windows,
    foreground_window_handle,
)
from src.core.policy import allowed_applications
from src.core.targets import TargetInfo, TargetRegistry

logger = logging.getLogger(__name__)
registry = TargetRegistry()


def effective_applications():
    from src.core.runtime import get_runtime
    policy = get_runtime().source.load()
    if not policy.permissions.inspect:
        return frozenset()
    return allowed_applications() | frozenset(policy.desktop.allowed_apps)


def computer_list_targets(kind: Literal["desktop", "browser"] | None = None) -> list[TargetInfo]:
    """List allowed Windows application windows as opaque target IDs and names.

    The local operator configures COMPUTER_USE_ALLOWED_APPS as a JSON array
    of full executable paths, or uses a trusted local policy. Managed browser
    pages are listed after approved browser_open calls. This tool does not focus
    or control windows.
    """
    from src.core.runtime import get_runtime
    browser = get_runtime().browser_targets()
    if kind == 'browser':
        return browser
    logger.info("Discovering allowed desktop targets")
    try:
        allowed = effective_applications()
        if not allowed:
            logger.info("No applications allowed for target discovery")
            return registry.refresh([], frozenset()) + (browser if kind is None else [])
        windows = discover_windows(allowed)
        # Recheck local permission before exposing any window names.
        result = registry.refresh(windows, effective_applications())
    except UnsupportedPlatformError:
        registry.refresh([], frozenset())
        raise ToolError("UNSUPPORTED: Desktop discovery currently supports Windows only.") from None
    except BackendUnavailableError:
        registry.refresh([], frozenset())
        logger.error("Windows target discovery failed")
        raise ToolError("BACKEND_UNAVAILABLE: Windows could not list application targets.") from None
    except ToolError:
        registry.refresh([], frozenset())
        raise

    logger.info("Discovered %d allowed desktop targets", len(result))
    return result + (browser if kind is None else [])


def get_active_window() -> TargetInfo | None:
    """Return the active allowed target, or null when it cannot be disclosed.

    Reads metadata only. A window outside the local application allowlist is
    never identified. Focus changes during the query return null.
    """
    logger.info("Reading the active allowed window")
    allowed = effective_applications()
    if not allowed:
        logger.info("No active window disclosed: no applications allowed")
        return None
    try:
        before = foreground_window_handle()
        if not before:
            return None
        listed = computer_list_targets(kind="desktop")
        if before != foreground_window_handle() or effective_applications() != allowed:
            logger.info("Active window changed during discovery")
            return None
        target_id = registry.target_id_for_handle(before)
        result = next((target for target in listed if target['target_id'] == target_id), None)
    except UnsupportedPlatformError:
        raise ToolError("UNSUPPORTED: Active-window discovery currently supports Windows only.") from None
    except BackendUnavailableError:
        logger.error("Active-window discovery failed")
        raise ToolError("BACKEND_UNAVAILABLE: Windows could not identify the active window.") from None
    logger.info("Active-window query completed")
    return result
