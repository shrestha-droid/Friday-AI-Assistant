from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_secrets_are_gitignored():
    lines = (ROOT / ".gitignore").read_text().splitlines()
    for pattern in [".env", "certs/", "*.wav", "*.log"]:
        assert pattern in lines, f"{pattern} missing from .gitignore"
