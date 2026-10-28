"""Reminders, tasks, notes, focus mode and the briefing. All owner-authored data, so all trusted."""
import datetime
import time

from .. import config, db
from ..registry import tool

REPEATS = {"", "daily", "weekly"}


def parse_when(when_iso):
    """ISO text -> epoch seconds. A time with no zone is read as the owner's local time."""
    dt = datetime.datetime.fromisoformat(when_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=config.TZ)
    return dt.timestamp()


def fmt(ts):
    return datetime.datetime.fromtimestamp(ts, config.TZ).strftime("%a %d %b %H:%M")


@tool(effects=True)
def set_reminder(text: str, when_iso: str, repeat: str = ""):
    """Sets a reminder. when_iso is an ISO 8601 local time like 2026-10-29T09:00 (work it out from the current time). repeat is '', 'daily' or 'weekly'."""
    if repeat not in REPEATS:
        return "repeat must be '', 'daily' or 'weekly'."
    try:
        due = parse_when(when_iso)
    except ValueError:
        return "I could not read that time. Use ISO format like 2026-10-29T09:00."
    if due < time.time() - 60:
        return "That time is already in the past."
    with db.db() as c:
        rid = c.execute("INSERT INTO reminders(text,due_at,repeat_rule) VALUES(?,?,?)", (text, due, repeat)).lastrowid
    return f"Reminder #{rid} set for {fmt(due)}."


@tool()
def list_reminders():
    """Lists pending reminders."""
    with db.db() as c:
        rows = c.execute("SELECT id,text,due_at,repeat_rule FROM reminders WHERE status='pending' ORDER BY due_at").fetchall()
    return "\n".join(f"#{r['id']} {fmt(r['due_at'])} {r['text']}{' (' + r['repeat_rule'] + ')' if r['repeat_rule'] else ''}"
                     for r in rows) or "No pending reminders."


@tool(effects=True)
def cancel_reminder(reminder_id: int):
    """Cancels a reminder by number."""
    with db.db() as c:
        n = c.execute("UPDATE reminders SET status='cancelled' WHERE id=? AND status='pending'", (reminder_id,)).rowcount
    return "Cancelled." if n else "No such pending reminder."


@tool(effects=True)
def add_task(title: str, due_iso: str = ""):
    """Adds a to-do. due_iso is optional, ISO 8601 local time."""
    try:
        due = parse_when(due_iso) if due_iso else None
    except ValueError:
        return "I could not read that due time."
    with db.db() as c:
        tid = c.execute("INSERT INTO tasks(title,due_at,created_at) VALUES(?,?,?)", (title, due, time.time())).lastrowid
    return f"Task #{tid} added."


@tool()
def list_tasks():
    """Lists open tasks, soonest deadline first."""
    with db.db() as c:
        rows = c.execute("SELECT id,title,due_at FROM tasks WHERE status='open' ORDER BY due_at IS NULL, due_at").fetchall()
    return "\n".join(f"#{r['id']} {r['title']}{' (due ' + fmt(r['due_at']) + ')' if r['due_at'] else ''}"
                     for r in rows) or "No open tasks."


@tool(effects=True)
def complete_task(task_id: int):
    """Marks a task as done."""
    with db.db() as c:
        n = c.execute("UPDATE tasks SET status='done', done_at=? WHERE id=? AND status='open'", (time.time(), task_id)).rowcount
    return "Done." if n else "No such open task."


@tool(effects=True)
def take_note(text: str):
    """Saves a quick note."""
    with db.db() as c:
        nid = c.execute("INSERT INTO notes(content,created_at) VALUES(?,?)", (text, time.time())).lastrowid
    return f"Note #{nid} saved."


@tool()
def search_notes(query: str):
    """Searches saved notes."""
    from ..memory import _tokens
    toks = sorted(_tokens(query))
    if not toks:
        return "Give me a word to search for."
    with db.db() as c:
        rows = c.execute("SELECT n.id,n.content FROM notes_fts JOIN notes n ON n.id=notes_fts.rowid WHERE notes_fts MATCH ? ORDER BY rank LIMIT 5",
                         (" OR ".join(f'"{t}"' for t in toks),)).fetchall()
    return "\n".join(f"#{r['id']} {r['content']}" for r in rows) or "No matching notes."


@tool(effects=True)
def focus_mode(minutes: int):
    """Silences non-urgent proactive alerts for this many minutes (0 turns focus mode off)."""
    db.meta_set("focus_until", time.time() + max(0, minutes) * 60)
    return f"Focus mode on for {minutes} minutes." if minutes > 0 else "Focus mode off."


def briefing_facts(now=None):
    """Read-only facts for a briefing: date, tasks, reminders, system."""
    from .system import read_system
    now = now or time.time()
    day = datetime.datetime.fromtimestamp(now, config.TZ).strftime("%A %d %B")
    end_of_day = datetime.datetime.fromtimestamp(now, config.TZ).replace(hour=23, minute=59, second=59).timestamp()
    with db.db() as c:
        tasks = c.execute("SELECT title,due_at FROM tasks WHERE status='open' ORDER BY due_at IS NULL, due_at LIMIT 8").fetchall()
        rem = c.execute("SELECT text,due_at FROM reminders WHERE status='pending' AND due_at<=? ORDER BY due_at", (end_of_day,)).fetchall()
    s = read_system()
    lines = [f"Today is {day}."]
    lines.append("Open tasks: " + ("; ".join(t["title"] + (f" (due {fmt(t['due_at'])})" if t["due_at"] else "") for t in tasks) or "none") + ".")
    lines.append("Reminders today: " + ("; ".join(f"{r['text']} at {fmt(r['due_at'])}" for r in rem) or "none") + ".")
    lines.append(f"System: CPU {s['cpu']}%, RAM {s['ram']}%, disk {s['disk']}%"
                 + (f", battery {s['battery']}%." if s["battery"] is not None else "."))
    return "\n".join(lines)


@tool()
def brief_me():
    """Returns the facts for a briefing: date, open tasks, today's reminders and system health. Summarise them aloud in at most 4 sentences."""
    return briefing_facts()
