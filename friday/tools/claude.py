"""Hand a task to Claude Code (the `claude` CLI), the way the owner would, and report back when it is done.

The job runs in the background (it can take minutes); Friday announces the result when it finishes.
"""
import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .. import config, permissions
from ..registry import tool

log = logging.getLogger("friday.claude")
LOOP = None                  # the server's event loop, set at startup (events must be published from it)
JOBS: dict[int, dict] = {}   # ponytail: in memory, lost on restart; persist if jobs ever outlive a session


def _folder(name):
    p = Path(name).expanduser()
    return p if p.is_absolute() else config.ALLOWED_ROOTS[0] / p


def _announce(job):
    from ..events import bus
    first = job["result"].strip().split("\n")[0][:220]
    msg = f"Claude finished: {first}" if job["status"] == "done" else f"Claude job failed: {first}"
    if LOOP:
        LOOP.call_soon_threadsafe(bus.publish, "claude", message=msg, job=job["id"])


def _run(job):
    try:
        r = subprocess.run([shutil.which("claude") or "claude", "-p", job["task"], "--permission-mode", "acceptEdits"],
                           cwd=job["folder"], capture_output=True, text=True, timeout=config.CLAUDE_TIMEOUT_S)
        job["status"] = "done" if r.returncode == 0 else "failed"
        job["result"] = (r.stdout or r.stderr or "No output.").strip()[:8000]
    except subprocess.TimeoutExpired:
        job["status"], job["result"] = "failed", f"Timed out after {config.CLAUDE_TIMEOUT_S // 60} minutes."
    job["ended"] = time.time()
    log.info("claude job #%d %s", job["id"], job["status"])
    _announce(job)


@tool(gate=lambda a: permissions.check_path(_folder(a.get("folder", "")), write=True),   # always a confirm card
      effects=True, describe=lambda a: f"Ask Claude Code, in {_folder(a.get('folder', ''))}: {a.get('task')}")
def ask_claude(task: str, folder: str = ""):
    """Gives a task to Claude Code (coding, fixing, writing, research in a project folder). It runs in the background and
    edits files there; Friday announces the result when it finishes. folder is a project folder name or path."""
    if not shutil.which("claude"):
        return "The claude command is not installed."
    d = _folder(folder)
    if not d.is_dir():
        return f"No folder {d}."
    job = {"id": len(JOBS) + 1, "task": task, "folder": str(d), "status": "running", "result": "", "started": time.time()}
    JOBS[job["id"]] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return f"Claude job #{job['id']} started in {d.name}. I'll tell you when it's done."


@tool()
def check_claude(job_id: int = 0):
    """Status and result of a Claude job (0 = the latest)."""
    if not JOBS:
        return "No Claude jobs yet."
    job = JOBS.get(job_id) or JOBS[max(JOBS)]
    took = int((job.get("ended") or time.time()) - job["started"])
    return f"Job #{job['id']} ({job['status']}, {took}s) in {Path(job['folder']).name}: {job['result'] or 'still working.'}"
