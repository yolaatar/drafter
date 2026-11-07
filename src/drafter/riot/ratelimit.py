"""Client-side sliding-window limiter mirroring Riot's "count:seconds,count:seconds" limits."""

import asyncio
import time
from collections import deque

# Riot counts on its side, so leave some slack for clock skew and in-flight requests.
_SAFETY_MARGIN_S = 0.1


def parse_limits(spec: str) -> list[tuple[int, float]]:
    limits = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        count, seconds = part.split(":")
        limits.append((int(count), float(seconds)))
    return limits


class RateLimiter:
    def __init__(self, spec: str, clock=time.monotonic):
        self._clock = clock
        self._lock = asyncio.Lock()
        self._spec = ""
        self._windows: list[tuple[int, float, deque[float]]] = []
        self.update(spec)

    @property
    def spec(self) -> str:
        return self._spec

    def update(self, spec: str) -> None:
        """Swap limits (e.g. from response headers), keeping the request history."""
        if spec == self._spec:
            return
        history = max((w[2] for w in self._windows), key=len, default=deque())
        self._windows = [(count, seconds, deque(history)) for count, seconds in parse_limits(spec)]
        self._spec = spec

    def wait_time(self) -> float:
        now = self._clock()
        wait = 0.0
        for count, seconds, stamps in self._windows:
            while stamps and stamps[0] <= now - seconds:
                stamps.popleft()
            if len(stamps) >= count:
                wait = max(wait, stamps[0] + seconds - now + _SAFETY_MARGIN_S)
        return wait

    def record(self) -> None:
        now = self._clock()
        for _, _, stamps in self._windows:
            stamps.append(now)

    async def acquire(self) -> None:
        async with self._lock:
            while (wait := self.wait_time()) > 0:
                await asyncio.sleep(wait)
            self.record()
