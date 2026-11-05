"""Read-only discovery of locally approved desktop targets."""

import logging
from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError

from src.backends.windows import (
    BackendUnavailableError, UnsupportedPlatformError,
    discover_windows,
)
from src.core.policy import allowed_applications
from src.core.targets import TargetInfo, TargetRegistry

logger = logging.getLogger(__name__)
registry = TargetRegistry()


def computer_list_targets(kind: Literal["desktop", "browser"] | None = None) -> list[TargetInfo]:
    """List allowed Windows application windows as opaque target IDs and names.

    The local operator configures COMPUTER_USE_ALLOWED_APPS as a JSON array
    of full executable paths. No allowed apps means no targets. Browser target
    discovery is not implemented. This tool does not focus or control windows.
    """
    if kind == "browser":
        raise ToolError("UNSUPPORTED: Managed browser targets are not implemented yet.")
    logger.info("Discovering allowed desktop targets")
    try:
        allowed = allowed_applications()
        if not allowed:
            logger.info("No applications allowed for target discovery")
            return registry.refresh([], frozenset())
        windows = discover_windows(allowed)
        # Recheck local permission before exposing any window names.
        result = registry.refresh(windows, allowed_applications())
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
    return result
