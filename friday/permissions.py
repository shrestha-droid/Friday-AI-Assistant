"""What Friday may do. Allowlists for reads, confirmation for writes, hard blocks for secrets."""
import re
import shlex
from pathlib import Path

from . import config
from .registry import BLOCKED, CONFIRM, SAFE

# Anything that touches these is refused outright, for reads too.
_SECRET_NAMES = re.compile(r"(^\.env($|\.)|\.pem$|\.key$|^id_(rsa|ed25519|ecdsa)|session_token$|\.p12$|\.keychain)", re.I)
_SECRET_DIRS = (".ssh", ".aws", ".gnupg", "Library/Keychains", "Library/Application Support/Google",
                "Library/Application Support/BraveSoftware", "Library/Application Support/Firefox",
                "Library/Cookies")

_SHELL_DENY = [
    r"\bsudo\b", r"\brm\s+(-\w*\s+)*-\w*[rR]", r"\brm\s+--recursive", r"\bmkfs", r"\bdd\s+if=",
    r"\bchmod\s+-R", r"\bchown\s+-R", r"(curl|wget)[^|]*\|\s*(sh|bash|zsh)", r">\s*/etc/", r":\(\)\s*\{",
    r"\b(shutdown|reboot|halt)\b", r"\bdiskutil\s+(erase|partition)", r"\blaunchctl\s+(unload|remove)",
    r"\.env\b", r"\.pem\b", r"id_rsa", r"\.ssh\b", r"Keychains", r"session_token",
]
_SHELL_META = re.compile(r"[|;&<>`$()\n]")
_READ_ONLY = {"ls", "pwd", "date", "whoami", "df", "uptime", "hostname", "uname", "echo"}
_GIT_READ_ONLY = {"status", "log", "diff", "branch"}


def classify_shell(command):
    """-> (tier, reason). Deny first, then allowlist, everything else asks."""
    for pat in _SHELL_DENY:
        if re.search(pat, command):
            return BLOCKED, f"command matches a forbidden pattern ({pat})"
    if _SHELL_META.search(command):
        return CONFIRM, "contains shell operators"
    try:
        argv = shlex.split(command)
    except ValueError:
        return CONFIRM, "could not be parsed"
    if not argv:
        return BLOCKED, "empty command"
    if argv[0] in _READ_ONLY:
        return SAFE, ""
    if argv[0] == "git" and len(argv) > 1 and argv[1] in _GIT_READ_ONLY:
        return SAFE, ""
    return CONFIRM, "not on the read-only list"


def _is_secret(p: Path):
    s = str(p)
    return bool(_SECRET_NAMES.search(p.name)) or any(f"/{d}" in s for d in _SECRET_DIRS)


def check_path(path, write=False):
    """-> (tier, reason). Symlinks are resolved first so a link cannot sneak past the roots."""
    try:
        p = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return BLOCKED, "invalid path"
    if _is_secret(p):
        return BLOCKED, "that file holds secrets"
    if not any(p == r or r in p.parents for r in config.ALLOWED_ROOTS):
        return BLOCKED, "outside the folders I am allowed to use"
    return (CONFIRM, "") if write else (SAFE, "")


def effective_tier(tier, effects, tainted):
    """Once untrusted content is in the conversation, anything that acts needs a human yes."""
    if tier == SAFE and effects and tainted:
        return CONFIRM
    return tier


def wrap_untrusted(source, text):
    return f'<untrusted_content source="{source}">\n{text}\n</untrusted_content>'
