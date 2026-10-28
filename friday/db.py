"""One SQLite file for everything. A new connection per call (cheap, thread-safe)."""
import json
import sqlite3
import time

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts(
  id INTEGER PRIMARY KEY, category TEXT NOT NULL DEFAULT 'general', content TEXT NOT NULL,
  source TEXT, created_at REAL, updated_at REAL, last_used_at REAL,
  pinned INTEGER NOT NULL DEFAULT 0, history TEXT NOT NULL DEFAULT '');
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(content, category, content='facts', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
  INSERT INTO facts_fts(rowid, content, category) VALUES (new.id, new.content, new.category); END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
  INSERT INTO facts_fts(facts_fts, rowid, content, category) VALUES('delete', old.id, old.content, old.category); END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
  INSERT INTO facts_fts(facts_fts, rowid, content, category) VALUES('delete', old.id, old.content, old.category);
  INSERT INTO facts_fts(rowid, content, category) VALUES (new.id, new.content, new.category); END;

CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, content TEXT NOT NULL, created_at REAL);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(content, content='notes', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
  INSERT INTO notes_fts(rowid, content) VALUES (new.id, new.content); END;

CREATE TABLE IF NOT EXISTS episodes(id INTEGER PRIMARY KEY, session_id TEXT, summary TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, ts REAL, session_id TEXT, tool TEXT, args TEXT,
  tier TEXT, decision TEXT, approver TEXT, result_chars INTEGER);
CREATE TABLE IF NOT EXISTS reminders(
  id INTEGER PRIMARY KEY, text TEXT NOT NULL, due_at REAL NOT NULL,
  repeat_rule TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, due_at REAL, status TEXT NOT NULL DEFAULT 'open',
  created_at REAL, done_at REAL);
CREATE TABLE IF NOT EXISTS proactive_log(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, message TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""

_ready = set()


def db():
    path = str(config.DB_PATH)
    if path != ":memory:":
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    if path not in _ready:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
        _ready.add(path)
    return con


def meta_get(key, default=None):
    with db() as c:
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def meta_set(key, value):
    with db() as c:
        c.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, str(value)))


def audit(session_id, tool, args, tier, decision, approver="", result_chars=0):
    with db() as c:
        c.execute(
            "INSERT INTO audit(ts,session_id,tool,args,tier,decision,approver,result_chars) VALUES(?,?,?,?,?,?,?,?)",
            (time.time(), session_id, tool, json.dumps(args, default=str)[:500], tier, decision, approver, result_chars))


def log_proactive(kind, message, outcome="sent"):
    with db() as c:
        c.execute("INSERT INTO proactive_log(ts,kind,message,outcome) VALUES(?,?,?,?)",
                  (time.time(), kind, message, outcome))
