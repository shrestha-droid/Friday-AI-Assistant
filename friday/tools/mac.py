"""Control of this Mac: sound, media, apps, screen, appearance, clipboard, Wi-Fi, power, and Apple Shortcuts."""
import subprocess
import urllib.parse

from .. import permissions
from ..registry import CONFIRM, tool


def osa(script):
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        # almost always macOS waiting on its one-time "allow to control ..." prompt
        raise RuntimeError("macOS is asking for permission to control that app. Click Allow on the prompt, then ask again.")
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:200] or "AppleScript failed")
    return r.stdout.strip()


def _running(app):
    return subprocess.run(["pgrep", "-xq", app]).returncode == 0


@tool(effects=True)
def set_volume(percent: int):
    """Sets the Mac's output volume, 0 to 100."""
    p = max(0, min(100, int(percent)))
    osa(f"set volume output volume {p} without output muted")
    return f"Volume {p}%."


@tool(effects=True)
def mute(on: bool = True):
    """Mutes (on=True) or unmutes (on=False) the Mac."""
    osa(f"set volume {'with' if on else 'without'} output muted")
    return "Muted." if on else "Unmuted."


@tool(effects=True)
def media(action: str):
    """Controls music in Spotify (if running) or Apple Music. action: play, pause, playpause, next, previous."""
    verb = {"play": "play", "pause": "pause", "playpause": "playpause", "next": "next track", "previous": "previous track"}.get(action)
    if not verb:
        return "action must be play, pause, playpause, next or previous."
    app = "Spotify" if _running("Spotify") else "Music"
    osa(f'tell application "{app}" to {verb}')
    return f"{app}: {action}."


@tool(tier=CONFIRM, effects=True, describe=lambda a: f"Quit {a.get('app_name')} (unsaved work could be lost)")
def quit_application(app_name: str):
    """Quits a running app by name."""
    osa(f'tell application "{app_name.replace(chr(34), "")}" to quit')
    return f"Quit {app_name}."


@tool()
def list_running_apps():
    """Lists the apps currently open (not background processes)."""
    return osa('tell application "System Events" to get name of every application process whose background only is false')


@tool(effects=True)
def lock_screen():
    """Locks the Mac by putting the display to sleep (a password is needed to wake it, if that is set in macOS)."""
    subprocess.run(["pmset", "displaysleepnow"], check=True, timeout=5)
    return "Locked."


@tool(effects=True)
def dark_mode(on: bool = True):
    """Turns macOS dark mode on or off."""
    osa(f'tell application "System Events" to tell appearance preferences to set dark mode to {"true" if on else "false"}')
    return f"Dark mode {'on' if on else 'off'}."


@tool(effects=True)
def open_url(url: str):
    """Opens a web address (http or https only) in the default browser."""
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        return "Only http and https links can be opened."
    subprocess.run(["open", url], check=True, timeout=10)
    return f"Opened {url}."


@tool(gate=lambda a: permissions.check_path(a.get("path", "")), effects=True)
def reveal_in_finder(path: str):
    """Shows a file or folder in Finder."""
    subprocess.run(["open", "-R", path], check=True, timeout=10)
    return "Shown in Finder."


@tool(untrusted=True)
def get_clipboard():
    """Returns the text currently on the clipboard."""
    return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5).stdout[:4000] or "The clipboard is empty."


@tool(effects=True)
def set_clipboard(text: str):
    """Puts text on the clipboard."""
    subprocess.run(["pbcopy"], input=text, text=True, timeout=5, check=True)
    return "Copied."


@tool(tier=CONFIRM, effects=True, describe=lambda a: f"Turn Wi-Fi {'on' if a.get('on', True) else 'off'}")
def wifi(on: bool):
    """Turns Wi-Fi on or off. Off also cuts the cloud brain until it is back on."""
    subprocess.run(["networksetup", "-setairportpower", "en0", "on" if on else "off"], check=True, timeout=10)
    return f"Wi-Fi {'on' if on else 'off'}."


@tool(tier=CONFIRM, effects=True, describe=lambda a: f"{str(a.get('action', '')).capitalize()} the Mac")
def power(action: str):
    """Puts the Mac to sleep, or restarts or shuts it down. action: sleep, restart, shutdown."""
    verb = {"sleep": "sleep", "restart": "restart", "shutdown": "shut down"}.get(action)
    if not verb:
        return "action must be sleep, restart or shutdown."
    osa(f'tell application "System Events" to {verb}')
    return f"{action.capitalize()}."


@tool()
def list_shortcuts():
    """Lists the owner's Apple Shortcuts by name."""
    out = subprocess.run(["shortcuts", "list"], capture_output=True, text=True, timeout=15).stdout.strip()
    return out or "No shortcuts found (or macOS has not allowed access yet)."


@tool(effects=True, untrusted=True)
def run_shortcut(name: str, input_text: str = ""):
    """Runs one of the owner's Apple Shortcuts by exact name, optionally with text input. This reaches almost anything on the Mac."""
    cmd = ["shortcuts", "run", name] + (["--input-path", "-"] if input_text else [])
    r = subprocess.run(cmd, input=input_text or None, capture_output=True, text=True, timeout=60)
    if r.returncode:
        return f"Shortcut failed: {r.stderr.strip()[:200]}"
    return r.stdout.strip()[:2000] or f"Ran {name}."
