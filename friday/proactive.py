"""The EDITH part: speaks up on its own. It only notifies or asks, it never acts by itself."""
import asyncio
import datetime
import json
import logging
import sqlite3
import subprocess
import time

import psutil

from . import config, db
from .events import bus
from .tools.productivity import briefing_facts
from .tools.system import read_system

log = logging.getLogger("friday.proactive")


def local(ts):
    return datetime.datetime.fromtimestamp(ts, config.TZ)


def in_quiet_hours(ts, spec=None):
    start, end = (spec or config.QUIET_HOURS).split("-")
    now = local(ts).strftime("%H:%M")
    return (start <= now < end) if start <= end else (now >= start or now < end)


def notify_mac(title, message):
    subprocess.run(["osascript", "-e", f"display notification {json.dumps(message)} with title {json.dumps(title)}"],
                   capture_output=True, timeout=5)


def top_process():
    procs = sorted(psutil.process_iter(["name", "memory_percent"]), key=lambda p: p.info["memory_percent"] or 0)
    return procs[-1].info["name"] if procs else "unknown"


class Watchers:
    """Battery, disk and RAM, with cooldown, hysteresis (no flapping) and quiet hours."""

    def __init__(self):
        self.last = {}
        self.armed = {"battery": True, "disk": True, "ram": True}
        self.ram_since = None

    def evaluate(self, r, now, quiet=False, focus=False, top=lambda: "unknown"):
        raw = []
        b = r.get("battery")
        if b is not None and not r.get("plugged") and b < config.BATTERY_LOW_PCT:
            if self.armed["battery"]:
                raw.append(("battery", f"Battery is at {b} percent and not charging.",
                            "high" if b < config.BATTERY_CRITICAL_PCT else "normal"))
        elif b is None or r.get("plugged") or b > config.BATTERY_LOW_PCT + 5:
            self.armed["battery"] = True

        if r["disk"] > config.DISK_HIGH_PCT:
            if self.armed["disk"]:
                raw.append(("disk", f"The disk is {r['disk']} percent full.", "normal"))
        elif r["disk"] < config.DISK_HIGH_PCT - 5:
            self.armed["disk"] = True

        if r["ram"] > config.RAM_HIGH_PCT:
            self.ram_since = self.ram_since or now
            if self.armed["ram"] and now - self.ram_since >= config.RAM_HIGH_FOR_S:
                raw.append(("ram", f"Memory has been above {config.RAM_HIGH_PCT} percent for a while. Biggest user: {top()}.", "normal"))
        else:
            self.ram_since = None
            if r["ram"] < config.RAM_HIGH_PCT - 10:
                self.armed["ram"] = True

        fired = []
        for kind, msg, prio in raw:
            last = self.last.get(kind)
            if last is not None and now - last < config.ALERT_COOLDOWN_S:
                continue
            if (quiet or focus) and prio != "high":
                continue
            self.last[kind] = now
            self.armed[kind] = False
            fired.append({"kind": kind, "message": msg, "priority": prio})
        return fired


class Proactive:
    def __init__(self, agent, now=time.time, read=read_system, notify=notify_mac):
        self.agent, self.now, self.read, self.notify = agent, now, read, notify
        self.watchers = Watchers()

    # --- checks (plain functions so tests can drive them with a fake clock) ---
    def check_reminders(self):
        now = self.now()
        fired = []
        with db.db() as c:
            for r in c.execute("SELECT * FROM reminders WHERE status='pending' AND due_at<=?", (now,)).fetchall():
                step = {"daily": 86400, "weekly": 7 * 86400}.get(r["repeat_rule"])
                if step:
                    nxt = r["due_at"] + step
                    while nxt <= now:
                        nxt += step
                    c.execute("UPDATE reminders SET due_at=? WHERE id=?", (nxt, r["id"]))
                else:
                    c.execute("UPDATE reminders SET status='done' WHERE id=?", (r["id"],))
                fired.append(r["text"])
        for text in fired:
            self._emit("reminder", f"Reminder: {text}", "high")
        return fired

    def check_watchers(self):
        now = self.now()
        focus = now < float(db.meta_get("focus_until", 0))
        alerts = self.watchers.evaluate(self.read(), now, in_quiet_hours(now), focus, top_process)
        for a in alerts:
            self._emit("alert", a["message"], a["priority"], sub=a["kind"])
        return alerts

    async def maybe_brief(self):
        now = self.now()
        hh, mm = map(int, config.BRIEFING_TIME.split(":"))
        start = local(now).replace(hour=hh, minute=mm, second=0, microsecond=0).timestamp()
        today = local(now).strftime("%Y-%m-%d")
        if not (start <= now < start + 3 * 3600) or db.meta_get("last_brief") == today:
            return None
        db.meta_set("last_brief", today)
        text = await self.agent.narrate(briefing_facts(now))
        self._emit("briefing", text, "normal")
        return text

    def maybe_backup(self):
        today = local(self.now()).strftime("%Y%m%d")
        if db.meta_get("last_backup") == today:
            return None
        config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        dest = config.BACKUP_DIR / f"friday-{today}.db"
        out = sqlite3.connect(dest)
        with db.db() as src:
            src.backup(out)
        out.close()
        for old in sorted(config.BACKUP_DIR.glob("friday-*.db"))[:-config.BACKUPS_KEPT]:
            old.unlink()
        db.meta_set("last_backup", today)
        return dest

    def _emit(self, kind, message, priority, sub=""):
        bus.publish(kind, message=message, priority=priority, sub=sub)
        db.log_proactive(sub or kind, message)
        log.info("proactive %s: %s", kind, message)
        try:
            self.notify("Friday", message)
        except Exception:
            log.warning("desktop notification failed")

    # --- the loop ---
    async def run(self):
        n = 0
        every = max(1, config.WATCH_EVERY_S // config.TICK_S)
        while True:
            try:
                # ponytail: runs on the event loop (asyncio.Queue is not thread-safe). Each check is a few ms.
                self.check_reminders()
                if n % every == 0:
                    self.check_watchers()
                    await self.maybe_brief()
                    self.maybe_backup()
            except Exception:
                log.exception("proactive tick failed")
            n += 1
            await asyncio.sleep(config.TICK_S)
