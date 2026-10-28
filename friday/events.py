"""Tiny in-process pub/sub. /api/events streams whatever is published here to the UI."""
import asyncio
import time


class Bus:
    def __init__(self):
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self):
        q = asyncio.Queue(maxsize=100)
        self._subs.add(q)
        return q

    def unsubscribe(self, q):
        self._subs.discard(q)

    def publish(self, kind, **data):
        event = {"kind": kind, "ts": time.time(), **data}
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # a slow browser tab must never block the assistant
        return event


bus = Bus()
