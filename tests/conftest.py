import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.genai import types  # noqa: E402

from friday import config, db  # noqa: E402
from friday.llm import LLMResult  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Every test gets its own empty SQLite file. No test touches data/friday.db."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    db._ready.discard(str(tmp_path / "test.db"))


class FakeLLM:
    """Plays back scripted replies. Each item is a str (final text), a list of (name, args) calls,
    or an Exception to raise. No network."""

    def __init__(self, script):
        self.script = list(script)
        self.models_used = []
        self.seen_contents = []

    async def generate(self, model, contents, system, tools=None):
        self.models_used.append(model)
        self.seen_contents.append(len(contents))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return LLMResult(content=types.Content(role="model", parts=[types.Part(text=item)]), text=item, calls=[])
        parts = [types.Part(function_call=types.FunctionCall(id=f"c{i}", name=n, args=a)) for i, (n, a) in enumerate(item)]
        return LLMResult(content=types.Content(role="model", parts=parts), text="",
                         calls=[(n, a, f"c{i}") for i, (n, a) in enumerate(item)])


async def no_sleep(_):
    return None


def run(coro):
    return asyncio.run(coro)
