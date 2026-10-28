import shlex
import subprocess

from .. import config, permissions
from ..registry import tool


@tool(gate=lambda a: permissions.classify_shell(a.get("command", "")), effects=True, untrusted=True,
      describe=lambda a: f"Run: {a.get('command')}")
def execute_terminal_command(command: str):
    """Runs a terminal command in the project folder and returns its output. Read-only commands run at once; anything else asks the owner first."""
    # The policy already decided. Operators only get here after a human approved this exact line.
    if permissions._SHELL_META.search(command):
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15, cwd=config.ROOT)
    else:
        r = subprocess.run(shlex.split(command), capture_output=True, text=True, timeout=15, cwd=config.ROOT)
    return (r.stdout or r.stderr or "Command ran with no output.")[:4000]
