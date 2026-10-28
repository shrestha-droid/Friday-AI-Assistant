"""@tool decorator: one place that knows every tool, its safety tier and whether its output is untrusted."""
from dataclasses import dataclass
from typing import Callable

SAFE, CONFIRM, BLOCKED = "safe", "confirm", "blocked"


@dataclass
class Tool:
    fn: Callable
    name: str
    tier: str = SAFE
    effects: bool = False          # changes something outside this process
    untrusted: object = False      # bool, or callable(args) -> bool: output may carry attacker text
    gate: Callable | None = None   # callable(args) -> (tier, reason): decides per call
    describe: Callable | None = None  # callable(args) -> str for the confirm card

    def resolve(self, args):
        return self.gate(args) if self.gate else (self.tier, "")

    def is_untrusted(self, args):
        return self.untrusted(args) if callable(self.untrusted) else bool(self.untrusted)

    def summary(self, args):
        if self.describe:
            return self.describe(args)
        shown = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in args.items())
        return f"{self.name}({shown})"


_TOOLS: dict[str, Tool] = {}


def tool(tier=SAFE, **kw):
    def deco(fn):
        _TOOLS[fn.__name__] = Tool(fn=fn, name=fn.__name__, tier=tier, **kw)
        return fn
    return deco


def get(name):
    return _TOOLS.get(name)


def all_tools():
    return list(_TOOLS.values())


def declarations():
    """The plain functions; the Gemini SDK reads names, docstrings and type hints from them."""
    return [t.fn for t in _TOOLS.values()]
