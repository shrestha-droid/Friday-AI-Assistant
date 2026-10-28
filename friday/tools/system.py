import datetime
import os
import signal
import subprocess

import psutil

from .. import config
from ..registry import CONFIRM, tool


@tool()
def get_system_time():
    """Returns the current local date and time."""
    return datetime.datetime.now(config.TZ).strftime("%A, %d %B %Y, %H:%M")


def read_system():
    """Raw numbers, also used by the HUD and the watchers."""
    batt = psutil.sensors_battery()
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage("/").percent,
        "battery": round(batt.percent) if batt else None,
        "plugged": batt.power_plugged if batt else None,
    }


@tool()
def get_system_stats():
    """Returns CPU, RAM, disk and battery status of this Mac."""
    s = read_system()
    batt = "no battery" if s["battery"] is None else f"{s['battery']}%{' (charging)' if s['plugged'] else ''}"
    return f"CPU {s['cpu']}%, RAM {s['ram']}%, disk {s['disk']}%, battery {batt}"


@tool(effects=True)
def open_application(app_name: str):
    """Opens a macOS application by name, for example 'Safari' or 'Spotify'."""
    r = subprocess.run(["open", "-a", app_name], capture_output=True, text=True, timeout=10)
    return f"Opened {app_name}." if r.returncode == 0 else f"Could not open {app_name}."


@tool()
def enter_standby():
    """Puts the assistant to sleep until the wake word is heard again."""
    return "Going to sleep."


@tool(tier=CONFIRM, effects=True, describe=lambda a: "Shut down the Friday server")
def shutdown_system():
    """Stops the Friday background server completely (kill switch)."""
    os.kill(os.getpid(), signal.SIGTERM)
    return "Shutting down."
