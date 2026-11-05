"""Operator-owned application allowlist; never granted through tool arguments."""

import json
import ntpath
import os
from pathlib import PureWindowsPath

import psutil
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


def configure_allowed_applications(apps: list[str]) -> None:
    """Resolve trusted CLI app selections into the existing exact-path policy.

    This startup helper is not an MCP tool. Multiple running executable paths
    for one app name are ambiguous and never silently selected.
    """
    resolved = set(allowed_applications())
    if len(apps) > 32:
        raise ToolError("INVALID_ARGUMENT: At most 32 app selections are allowed.")
    for app in apps:
        if PureWindowsPath(app).is_absolute():
            resolved.update(_validated_paths([app]))
            continue
        if not app or ntpath.basename(app) != app or any(char in app for char in '*?\x00:/\\'):
            raise ToolError("INVALID_ARGUMENT: Use a running app name or an absolute executable path.")
        name = app.casefold() if app.casefold().endswith('.exe') else app.casefold() + '.exe'
        try:
            matches = {
                normalize_executable(process.info['exe'])
                for process in psutil.process_iter(['name', 'exe'])
                if (process.info.get('name') or '').casefold() == name and process.info.get('exe')
            }
        except (psutil.Error, OSError):
            raise ToolError("BACKEND_UNAVAILABLE: Running applications could not be resolved.") from None
        if not matches:
            raise ToolError("INVALID_ARGUMENT: That app is not running. Open it first, then restart the server.")
        if len(matches) > 1:
            raise ToolError("INVALID_ARGUMENT: App name is ambiguous; specify its full executable path.")
        resolved.update(matches)
    validated = _validated_paths(sorted(resolved))
    # Change policy only after all selections resolve and validate successfully.
    os.environ['COMPUTER_USE_ALLOWED_APPS'] = json.dumps(sorted(validated))
