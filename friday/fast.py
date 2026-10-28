"""Instant path: status questions and everyday device commands, handled with no model call.

Deliberately narrow: short, unambiguous phrasings only. Anything else goes to the model.
"""
import datetime
import re

from . import config
from .tools import mac, productivity, system
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
_NOT_APPS = re.compile(r"\b(file|folder|email|mail|document|link|url|tab|website|page|the|my|a|an|it|this|that)\b|[./]", re.I)

# (pattern, handler(match) -> (spoken, tool_name)); each handler calls the same registered tool the model would use
COMMANDS = [
    (r"(?:set )?(?:the )?volume (?:to )?(\d{1,3})(?: ?%| percent)?", lambda m: (mac.set_volume(int(m[1])), "set_volume")),
    (r"mute", lambda m: (mac.mute(True), "mute")),
    (r"unmute", lambda m: (mac.mute(False), "mute")),
    (r"(play|pause|resume)(?: the)?(?: music| song)?", lambda m: (mac.media({"resume": "play"}.get(m[1], m[1])), "media")),
    (r"(?:next|skip)(?: song| track)?", lambda m: (mac.media("next"), "media")),
    (r"previous(?: song| track)?", lambda m: (mac.media("previous"), "media")),
    (r"lock(?: the| my)? (?:screen|mac|computer|laptop)", lambda m: (mac.lock_screen(), "lock_screen")),
    (r"(?:turn )?dark mode (on|off)|turn (on|off) dark mode", lambda m: (mac.dark_mode((m[1] or m[2]) == "on"), "dark_mode")),
    (r"(?:set )?(?:a )?timer (?:for )?(\d{1,3}) ?(?:min|mins|minutes?)",
     lambda m: (productivity.set_reminder(f"Timer: {m[1]} minutes", (datetime.datetime.now(config.TZ) + datetime.timedelta(minutes=int(m[1]))).isoformat(timespec="seconds")), "set_reminder")),
    (r"open ([a-z0-9 ]{2,30})", lambda m: None if _NOT_APPS.search(m[1]) else (system.open_application(m[1].title()), "open_application")),
]
_COMPILED = [(re.compile(rf"^{p}$", re.I), h) for p, h in COMMANDS]
_LEAD = re.compile(r"^(?:(?:hey|ok|okay)\s+)?(?:friday|jarvis|edith)?[,\s]*(?:please\s+|can you\s+|could you\s+)?", re.I)


def answer(text, persona, tainted=False, now=None):
    """-> (spoken, tool) when handled instantly, else None (the model takes it)."""
    t = _LEAD.sub("", text.strip()).rstrip(" .!?").strip()
    if not tainted:   # after untrusted content, acting needs a confirm card: leave it to the agent
        for rx, handler in _COMPILED:
            m = rx.match(t)
            if m and (out := handler(m)):
                return out
    return _status(text, persona, now)


def _status(text, persona, now):
    if len(text) > 70 or _ACTION.search(text):
        return None
    hits = [k for k, rx in _INTENTS if rx.search(text)]
    if len(hits) != 1:
        return None
    k, a = hits[0], ADDRESS.get(persona, "")
    if k == "time":
        return f"It's {(now or datetime.datetime.now(config.TZ)):%H:%M}{a}.", "get_system_time"
    s = read_system()
    batt = "no battery" if s["battery"] is None else f"{s['battery']} percent{', charging' if s['plugged'] else ''}"
    return {
        "battery": f"Battery's at {batt}{a}." if s["battery"] is not None else f"This Mac has no battery{a}.",
        "disk": f"Disk is {s['disk']:.0f} percent full{a}.",
        "ram": f"Memory's at {s['ram']:.0f} percent{a}.",
        "cpu": f"CPU is at {s['cpu']:.0f} percent{a}.",
        "status": f"CPU {s['cpu']:.0f}, memory {s['ram']:.0f}, disk {s['disk']:.0f} percent, battery {batt}{a}.",
    }[k], "get_system_stats"
