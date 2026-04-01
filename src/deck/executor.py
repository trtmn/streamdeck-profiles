"""Execute Stream Deck button actions natively.

Reads the action config from a button and runs the equivalent
macOS command without needing the Stream Deck app.
"""

from __future__ import annotations

import subprocess
import time
from typing import Any


class UnsupportedActionError(Exception):
    """Raised when an action type can't be executed natively."""

    def __init__(self, action_uuid: str, name: str) -> None:
        self.action_uuid = action_uuid
        self.name = name
        super().__init__(f"Unsupported action: {name} ({action_uuid})")


def execute(action_raw: dict[str, Any]) -> str:
    """Execute a button action dict. Returns a description of what was done."""
    uuid = action_raw.get("UUID", "")
    name = action_raw.get("Name", "")
    settings = action_raw.get("Settings") or {}

    # Check for Multi Action — execute sub-actions in sequence
    if uuid in ("com.elgato.streamdeck.multiactions",
                "com.elgato.streamdeck.multiactions.routine"):
        return _exec_multi_action(action_raw)

    handler = _HANDLERS.get(uuid)
    if handler is None:
        raise UnsupportedActionError(uuid, name)
    return handler(settings, action_raw)


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def _exec_soundboard(settings: dict, raw: dict) -> str:
    path = settings.get("path", "")
    volume = settings.get("volume", 100)
    if not path:
        return "No audio path configured"
    # afplay volume is 0.0 to 1.0 (or higher for boost)
    vol = volume / 100.0
    subprocess.Popen(
        ["afplay", "-v", str(vol), path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"Playing: {path}"


def _exec_open(settings: dict, raw: dict) -> str:
    path = settings.get("path", "")
    if not path:
        return "No path configured"
    subprocess.Popen(
        path,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"Opened: {path}"


def _exec_open_app(settings: dict, raw: dict) -> str:
    path = settings.get("path", "")
    if not path:
        return "No app path configured"
    subprocess.run(
        ["open", "-a", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"Launched: {path}"


def _exec_website(settings: dict, raw: dict) -> str:
    url = settings.get("url", settings.get("URL", ""))
    if not url:
        return "No URL configured"
    subprocess.run(
        ["open", url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"Opened: {url}"


def _exec_hotkey(settings: dict, raw: dict) -> str:
    hotkeys = settings.get("Hotkeys", [])
    if not hotkeys:
        return "No hotkey configured"

    hk = hotkeys[0]
    key_code = hk.get("NativeCode", -1)
    if key_code < 0:
        return "No valid key code"

    modifiers = []
    if hk.get("KeyCmd"):
        modifiers.append("command down")
    if hk.get("KeyShift"):
        modifiers.append("shift down")
    if hk.get("KeyOption"):
        modifiers.append("option down")
    if hk.get("KeyCtrl"):
        modifiers.append("control down")

    mod_str = ", ".join(modifiers) if modifiers else ""
    using = f" using {{{mod_str}}}" if mod_str else ""

    script = f'tell application "System Events" to key code {key_code}{using}'
    subprocess.run(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    title = ""
    states = raw.get("States", [])
    if states:
        title = states[0].get("Title", "")
    return f"Hotkey: {title or f'keycode {key_code}'}"


def _exec_text(settings: dict, raw: dict) -> str:
    text = settings.get("pastedText", "")
    if not text:
        return "No text configured"
    send_enter = settings.get("isSendingEnter", False)

    # Use pbcopy + Cmd+V for reliability with special characters
    proc = subprocess.run(
        ["pbcopy"],
        input=text.encode("utf-8"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to keystroke "v" using command down'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if send_enter:
        time.sleep(0.1)
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to keystroke return'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}"


def _exec_shortcut(settings: dict, raw: dict) -> str:
    name = settings.get("shortcutName", "")
    if not name:
        return "No shortcut configured"
    subprocess.Popen(
        ["shortcuts", "run", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"Shortcut: {name}"


def _exec_sleep(settings: dict, raw: dict) -> str:
    subprocess.run(
        ["pmset", "sleepnow"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return "Sleep"


def _exec_keyboard_maestro(settings: dict, raw: dict) -> str:
    macro_uuid = settings.get("macroUID", "")
    if not macro_uuid:
        return "No Keyboard Maestro macro configured"
    script = (
        f'tell application "Keyboard Maestro Engine" '
        f'to do script "{macro_uuid}"'
    )
    subprocess.run(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    title = ""
    states = raw.get("States", [])
    if states:
        title = states[0].get("Title", "")
    return f"KM Macro: {title or macro_uuid}"


def _exec_roku(settings: dict, raw: dict) -> str:
    """Handle Roku Remote plugin actions via ECP HTTP calls."""
    uuid = raw.get("UUID", "")
    ip = settings.get("rokuIP", settings.get("selectedRokuIP", ""))

    # Map plugin action UUIDs to ECP endpoints
    ecp_map = {
        "com.funky.rokuremotejs.home": "/keypress/Home",
        "com.funky.rokuremotejs.back": "/keypress/Back",
        "com.funky.rokuremotejs.up": "/keypress/Up",
        "com.funky.rokuremotejs.down": "/keypress/Down",
        "com.funky.rokuremotejs.left": "/keypress/Left",
        "com.funky.rokuremotejs.right": "/keypress/Right",
        "com.funky.rokuremotejs.ok": "/keypress/Select",
        "com.funky.rokuremotejs.select": "/keypress/Select",
        "com.funky.rokuremotejs.option": "/keypress/Info",
        "com.funky.rokuremotejs.volumeup": "/keypress/VolumeUp",
        "com.funky.rokuremotejs.volumedown": "/keypress/VolumeDown",
        "com.funky.rokuremotejs.volumemute": "/keypress/VolumeMute",
        "com.funky.rokuremotejs.power-on": "/keypress/PowerOn",
        "com.funky.rokuremotejs.poweroff": "/keypress/PowerOff",
    }

    endpoint = ecp_map.get(uuid)

    # App/input launch
    if uuid in ("com.funky.rokuremotejs.app",
                "com.funky.rokuremotejs.app-selection"):
        app_id = settings.get("appSelect", settings.get("selected_app_ID", ""))
        if app_id and ip:
            subprocess.run(
                ["curl", "-s", "-X", "POST", f"http://{ip}:8060/launch/{app_id}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"Roku: launch {app_id} on {ip}"
        return "Roku: no app or IP configured"

    if endpoint and ip:
        subprocess.run(
            ["curl", "-s", "-X", "POST", f"http://{ip}:8060{endpoint}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Roku: {endpoint} on {ip}"

    if not ip:
        return "Roku: no IP configured in button settings"
    return f"Roku: unknown action {uuid}"


def _exec_multi_action(raw: dict) -> str:
    """Execute sub-actions in a Multi Action sequentially."""
    action_groups = raw.get("Actions", [])
    if not action_groups:
        return "Multi Action: empty"

    results = []
    for group in action_groups:
        # Groups can be ActionGroup dicts with "Actions" key, or bare action dicts
        if "Actions" in group and isinstance(group["Actions"], list):
            for sub in group["Actions"]:
                try:
                    results.append(execute(sub))
                except UnsupportedActionError as e:
                    results.append(f"Skipped: {e.name}")
        elif "UUID" in group:
            # Bare action dict
            try:
                results.append(execute(group))
            except UnsupportedActionError as e:
                results.append(f"Skipped: {e.name}")

    return f"Multi Action: {'; '.join(results)}"


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS = {
    # Soundboard
    "com.elgato.streamdeck.soundboard.playaudio": _exec_soundboard,
    # System
    "com.elgato.streamdeck.system.open": _exec_open,
    "com.elgato.streamdeck.system.openapp": _exec_open_app,
    "com.elgato.streamdeck.system.website": _exec_website,
    "com.elgato.streamdeck.system.hotkey": _exec_hotkey,
    "com.elgato.streamdeck.system.hotkeyswitch": _exec_hotkey,
    "com.elgato.streamdeck.system.text": _exec_text,
    "com.elgato.streamdeck.system.sleep": _exec_sleep,
    # Shortcuts
    "shortcut.run": _exec_shortcut,
    # Keyboard Maestro
    "com.stairways.keyboardmaestro": _exec_keyboard_maestro,
    "com.stairways.keyboardmaestro.action": _exec_keyboard_maestro,
    # Roku Remote
    "com.funky.rokuremotejs.home": _exec_roku,
    "com.funky.rokuremotejs.back": _exec_roku,
    "com.funky.rokuremotejs.up": _exec_roku,
    "com.funky.rokuremotejs.down": _exec_roku,
    "com.funky.rokuremotejs.left": _exec_roku,
    "com.funky.rokuremotejs.right": _exec_roku,
    "com.funky.rokuremotejs.ok": _exec_roku,
    "com.funky.rokuremotejs.select": _exec_roku,
    "com.funky.rokuremotejs.option": _exec_roku,
    "com.funky.rokuremotejs.volumeup": _exec_roku,
    "com.funky.rokuremotejs.volumedown": _exec_roku,
    "com.funky.rokuremotejs.volumemute": _exec_roku,
    "com.funky.rokuremotejs.power-on": _exec_roku,
    "com.funky.rokuremotejs.poweroff": _exec_roku,
    "com.funky.rokuremotejs.app": _exec_roku,
    "com.funky.rokuremotejs.app-selection": _exec_roku,
}
