"""Stream Deck app lifecycle management."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass

_APP_PATH = "/Applications/Elgato Stream Deck.app"
_PROCESS_NAME = "Stream Deck"


@dataclass
class DeviceInfo:
    """A connected Stream Deck device."""

    id: str
    name: str
    cols: int
    rows: int
    type: int

    @property
    def size(self) -> str:
        return f"{self.cols}x{self.rows}"

    @property
    def button_count(self) -> int:
        return self.cols * self.rows


def list_devices() -> list[DeviceInfo]:
    """Get connected devices by reading plugin process args.

    Plugins receive a -info JSON payload at launch that includes all
    connected devices with their grid sizes. We parse that from any
    running plugin process.
    """
    # Prefer a built-in Elgato plugin (always present) over third-party
    _BUILTIN_PLUGINS = (
        "com.elgato.volume-controller",
        "com.elgato.applemusic",
        "com.elgato.applemail",
        "com.elgato.weather",
        "com.elgato.window-mover",
        "com.elgato.youtube",
    )
    result = subprocess.run(
        ["pgrep", "-f", "pluginUUID"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []

    pids = result.stdout.strip().split("\n")
    # Collect args from all plugin processes, preferring built-in Elgato plugins
    candidates: list[tuple[bool, str]] = []  # (is_builtin, json_str)
    for pid in pids:
        args_result = subprocess.run(
            ["ps", "-p", pid, "-o", "args="],
            capture_output=True, text=True,
        )
        if args_result.returncode != 0:
            continue
        args = args_result.stdout.strip()
        idx = args.find("-info ")
        if idx < 0:
            continue
        json_str = args[idx + 6:]
        is_builtin = any(p in args for p in _BUILTIN_PLUGINS)
        candidates.append((is_builtin, json_str))

    # Try built-in plugins first, then fall back to any plugin
    candidates.sort(key=lambda x: not x[0])
    for _, json_str in candidates:
        try:
            info = json.loads(json_str)
            return [
                DeviceInfo(
                    id=d["id"],
                    name=d["name"],
                    cols=d["size"]["columns"],
                    rows=d["size"]["rows"],
                    type=d["type"],
                )
                for d in info.get("devices", [])
            ]
        except (json.JSONDecodeError, KeyError):
            continue
    return []


def is_running() -> bool:
    """Check if the Stream Deck app is running."""
    result = subprocess.run(
        ["pgrep", "-x", _PROCESS_NAME],
        capture_output=True,
    )
    return result.returncode == 0


def stop() -> bool:
    """Stop the Stream Deck app. Returns True if it was stopped."""
    if not is_running():
        return True
    subprocess.run(["killall", _PROCESS_NAME], capture_output=True)
    # Wait up to 5 seconds for it to stop
    for _ in range(10):
        if not is_running():
            return True
        time.sleep(0.5)
    return not is_running()


def start() -> bool:
    """Start the Stream Deck app. Returns True if launch was initiated."""
    result = subprocess.run(["open", _APP_PATH], capture_output=True)
    return result.returncode == 0


def restart() -> bool:
    """Restart the Stream Deck app. Returns True if successful."""
    stopped = stop()
    if not stopped:
        return False
    time.sleep(0.5)
    return start()
