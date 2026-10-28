"""Instant answers for simple status questions: no model call, a few milliseconds.

Deliberately narrow: one short question, one intent, no action words. Anything else goes to the model.
"""
import datetime
import re

from . import config
from .tools.system import read_system

_ACTION = re.compile(r"\b(remind|set|turn|open|close|write|send|delete|kill|start|stop|schedule|when|if|why|should|"
                     r"remember|forget|free|clean|clear|fix|explain)\b", re.I)
_INTENTS = [
    ("time", re.compile(r"\b(what(?:'s| is) the time|what time is it)\b", re.I)),
    ("battery", re.compile(r"\bbattery\b", re.I)),
    ("disk", re.compile(r"\b(disk|storage)\b", re.I)),
    ("ram", re.compile(r"\b(ram|memory usage|using .{0,12}memory)\b", re.I)),
    ("cpu", re.compile(r"\b(cpu|processor)\b", re.I)),
    ("status", re.compile(r"\bhow(?:'s| is) (?:my )?(mac|laptop|system|computer|machine)\b", re.I)),
]
ADDRESS = {"friday": ", boss", "jarvis": ", Shrestha", "edith": ""}


def answer(text, persona, now=None):
    """-> spoken answer, or None when the model should handle it."""
    if len(text) > 70 or _ACTION.search(text):
        return None
    hits = [k for k, rx in _INTENTS if rx.search(text)]
    if len(hits) != 1:
        return None
    k, a = hits[0], ADDRESS.get(persona, "")
    if k == "time":
        return f"It's {(now or datetime.datetime.now(config.TZ)):%H:%M}{a}."
    s = read_system()
    batt = ("no battery" if s["battery"] is None
            else f"{s['battery']} percent{', charging' if s['plugged'] else ''}")
    return {
        "battery": f"Battery's at {batt}{a}." if s["battery"] is not None else f"This Mac has no battery{a}.",
        "disk": f"Disk is {s['disk']:.0f} percent full{a}.",
        "ram": f"Memory's at {s['ram']:.0f} percent{a}.",
        "cpu": f"CPU is at {s['cpu']:.0f} percent{a}.",
        "status": f"CPU {s['cpu']:.0f}, memory {s['ram']:.0f}, disk {s['disk']:.0f} percent, battery {batt}{a}.",
    }[k]
