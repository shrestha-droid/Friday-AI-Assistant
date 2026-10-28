"""Conversation history per browser tab. The model has no memory: we resend this every call."""
import asyncio
import time
import uuid
from dataclasses import dataclass, field

from . import config, memory


@dataclass
class Session:
    id: str
    contents: list = field(default_factory=list)
    tainted: bool = False          # untrusted content has been seen this conversation
    pending: object = None         # a confirm card waiting for a yes/no
    persona: str = "friday"
    last_used: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _is_user_text(content):
    return content.role == "user" and any(getattr(p, "text", None) for p in content.parts or [])


def trim(session, max_turns=None):
    """Keep the last N user turns. Cuts only at a user message so tool call/response pairs stay whole."""
    max_turns = max_turns or config.MAX_HISTORY_TURNS
    starts = [i for i, c in enumerate(session.contents) if _is_user_text(c)]
    if len(starts) <= max_turns:
        return
    cut = starts[-max_turns]
    dropped = [p.text for c in session.contents[:cut] if _is_user_text(c) for p in c.parts if p.text]
    # ponytail: no LLM summary yet, we keep the owner's own words. Summarise with the model if recall gets noisy.
    memory.add_episode(session.id, " | ".join(t[:80] for t in dropped)[:600])
    del session.contents[:cut]


class Sessions:
    def __init__(self):
        self._by_id: dict[str, Session] = {}

    def get(self, session_id=None):
        self.sweep()
        sid = session_id or uuid.uuid4().hex[:12]
        s = self._by_id.setdefault(sid, Session(id=sid))
        s.last_used = time.time()
        return s

    def sweep(self):
        cutoff = time.time() - config.SESSION_IDLE_S
        for sid in [k for k, s in self._by_id.items() if s.last_used < cutoff]:
            del self._by_id[sid]


sessions = Sessions()
