import os
from pathlib import Path

from .. import config, permissions
from ..registry import tool

MAX_READ = 20_000


def _read_gate(args):
    return permissions.check_path(args.get("filepath") or args.get("directory", "."))


def _write_gate(args):
    return permissions.check_path(args.get("filepath", ""), write=True)


def _outside_project(args):
    p = Path(args.get("filepath", "")).expanduser().resolve()
    return config.ROOT != p and config.ROOT not in p.parents


@tool(gate=lambda a: permissions.check_path(a.get("directory", ".")))
def list_workspace_files(directory: str):
    """Lists the files in a folder. Pass '.' for the Friday project folder."""
    d = Path(directory).expanduser()
    if not d.is_dir():
        return f"'{directory}' is not a folder."
    names = sorted(n for n in os.listdir(d) if not permissions._is_secret(d / n))
    return f"Files in '{directory}': {', '.join(names)}"


@tool(gate=_read_gate, untrusted=_outside_project)
def read_file_content(filepath: str):
    """Reads the text inside a file (first 20,000 characters)."""
    p = Path(filepath).expanduser()
    if not p.is_file():
        return f"'{filepath}' is not a file."
    return p.read_text(encoding="utf-8", errors="ignore")[:MAX_READ]


@tool(gate=_write_gate, effects=True,
      describe=lambda a: f"Write {len(a.get('content', ''))} characters to {a.get('filepath')}")
def write_file_content(filepath: str, content: str):
    """Writes or overwrites a file with the given text."""
    p = Path(filepath).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {filepath}."
