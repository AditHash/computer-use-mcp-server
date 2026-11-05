"""Basic computer facts and live resource usage, without personal identifiers."""

import logging
import os
import platform
import sys
from typing import TypedDict

import psutil
from mcp.server.mcpserver.exceptions import ToolError

logger = logging.getLogger(__name__)


class ComputerInfo(TypedDict):
    os_name: str
    os_release: str
    os_version: str
    architecture: str
    cpu_model: str | None
    cpu_logical_cores: int | None
    cpu_physical_cores: int | None


class MemoryUsage(TypedDict):
    total_bytes: int
    available_bytes: int
    used_bytes: int
    percent: float


class DiskUsage(TypedDict):
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float


class ComputerResources(TypedDict):
    cpu_percent: float
    memory: MemoryUsage
    system_disk: DiskUsage


def get_computer_info() -> ComputerInfo:
    """Return OS, architecture, and CPU facts. Unknown CPU details are null.

    Does not return usernames, hostnames, network addresses, or serial numbers.
    """
    logger.info("Reading computer information")
    try:
        result: ComputerInfo = {
            "os_name": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "cpu_model": platform.processor().strip() or None,
            "cpu_logical_cores": psutil.cpu_count(logical=True),
            "cpu_physical_cores": psutil.cpu_count(logical=False),
        }
    except (OSError, psutil.Error, NotImplementedError):
        logger.error("Computer information could not be read")
        raise ToolError("BACKEND_UNAVAILABLE: Computer information could not be read.") from None

    logger.info("Computer information read successfully")
    return result


def get_computer_resources() -> ComputerResources:
    """Read total CPU usage, RAM, and the system disk's space usage.

    CPU is sampled for 0.1 seconds. Memory and disk sizes are bytes; percentages
    are 0-100. Reports only the system disk, not all drives or any file contents.
    """
    logger.info("Reading computer resource usage")
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        # On Windows, SystemDrive usually holds C:. Do not expose that path.
        system_root = os.environ.get("SystemDrive", "C:") + "\\" if sys.platform == "win32" else "/"
        disk = psutil.disk_usage(system_root)
        result: ComputerResources = {
            "cpu_percent": cpu_percent,
            "memory": {
                "total_bytes": memory.total,
                "available_bytes": memory.available,
                "used_bytes": memory.used,
                "percent": memory.percent,
            },
            "system_disk": {
                "total_bytes": disk.total,
                "used_bytes": disk.used,
                "free_bytes": disk.free,
                "percent": disk.percent,
            },
        }
    except (OSError, psutil.Error, NotImplementedError):
        logger.error("Computer resource usage could not be read")
        raise ToolError("BACKEND_UNAVAILABLE: Computer resource usage could not be read.") from None

    logger.info("Computer resource usage read successfully")
    return result
