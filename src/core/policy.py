"""Operator-owned application allowlist; never granted through tool arguments."""

import json
import ntpath
import os
from pathlib import PureWindowsPath

from mcp.server.mcpserver.exceptions import ToolError


def normalize_executable(path: str) -> str:
    """Compare Windows executable paths without case or separator differences."""
    return ntpath.normcase(ntpath.normpath(path))


def allowed_applications() -> frozenset[str]:
    """Read a JSON array of up to 32 absolute executable paths from local policy."""
    raw = os.environ.get("COMPUTER_USE_ALLOWED_APPS", "").strip()
    if not raw:
        return frozenset()
    try:
        return _validated_paths(json.loads(raw))
    except (ValueError, TypeError):
        raise ToolError(
            "INVALID_ARGUMENT: COMPUTER_USE_ALLOWED_APPS must be a JSON array "
            "of up to 32 absolute Windows executable paths; wildcards are not allowed."
        ) from None


def _validated_paths(paths: object) -> frozenset[str]:
    try:
        if not isinstance(paths, list) or len(paths) > 32:
            raise ValueError
        for path in paths:
            if not isinstance(path, str) or len(path) > 1024:
                raise ValueError
            parsed = PureWindowsPath(path)
            if not parsed.is_absolute() or parsed.suffix.lower() != ".exe" or any(char in path for char in '*?\x00'):
                raise ValueError
        return frozenset(normalize_executable(path) for path in paths)
    except (ValueError, TypeError):
        raise ToolError(
            "INVALID_ARGUMENT: COMPUTER_USE_ALLOWED_APPS must be a JSON array "
            "of up to 32 absolute Windows executable paths; wildcards are not allowed."
        ) from None
