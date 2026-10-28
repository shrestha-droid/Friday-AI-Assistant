"""Health check for the whole install. Never prints a secret, only whether it exists.

    friday_env/bin/python scripts/doctor.py          # offline checks
    friday_env/bin/python scripts/doctor.py --live   # also calls Gemini once
"""
import asyncio
import os
import socket
import stat
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from friday import config, db  # noqa: E402

problems = 0


def report(ok, label, hint=""):
    global problems
    problems += not ok
    print(f"{'OK  ' if ok else 'FAIL'}  {label}" + (f"  -> {hint}" if hint and not ok else ""))


report(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}", "needs 3.11+")
report(bool(config.API_KEY), "Gemini API key present in .env", "add GEMINI_API_KEY to .env")
report(not config.DEFAULT_MODEL.startswith(("gemini-1", "gemini-2")), f"model {config.DEFAULT_MODEL} is Gemini 3+")
for pkg in ("fastapi", "uvicorn", "google.genai", "psutil", "dotenv"):
    try:
        __import__(pkg)
        report(True, f"import {pkg}")
    except ImportError:
        report(False, f"import {pkg}", "pip install -r requirements.txt")

try:
    with db.db() as c:
        report(c.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite database is healthy")
        c.execute("SELECT * FROM facts_fts LIMIT 1")
        report(True, "full-text search (FTS5) works")
except Exception as e:
    report(False, "SQLite database", str(e))

tok = config.TOKEN_PATH
report(not tok.exists() or stat.S_IMODE(tok.stat().st_mode) == 0o600, "session token file is owner-only", f"chmod 600 {tok}")
report(config.ROOT.joinpath("certs", "key.pem").exists() or not config.ENABLE_HTTPS, "HTTPS certificate exists (made on first run)")

with socket.socket() as s:
    in_use = s.connect_ex((config.HOST, config.PORT)) == 0
print(f"INFO  port {config.PORT} is {'in use (server already running?)' if in_use else 'free'}")
print(f"INFO  allowed folders: {', '.join(map(str, config.ALLOWED_ROOTS))}")
print(f"INFO  briefing {config.BRIEFING_TIME}, quiet hours {config.QUIET_HOURS}, timezone {config.TZ.key}")
print("INFO  macOS permissions to grant when asked: Microphone (browser), Screen Recording (for analyze_screen), Notifications.")

if "--live" in sys.argv:
    from friday.llm import GeminiLLM, user_text
    try:
        res = asyncio.run(GeminiLLM().generate(config.DEFAULT_MODEL, [user_text("Say ok.")], "Reply with one word.", None))
        report(bool(res.text), f"{config.DEFAULT_MODEL} answered")
    except Exception as e:
        report(False, f"{config.DEFAULT_MODEL} answered", str(e)[:120])

print("\nAll good." if not problems else f"\n{problems} problem(s).")
sys.exit(1 if problems else 0)
