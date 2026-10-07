"""Approximate remaining time from confirmed refreshes; no engine/input changes."""
from collections import deque
import time


class SessionEstimate:
    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.reset()

    def reset(self, budget=0, *, enabled=False):
        self.enabled = enabled
        self.total = budget // 3
        self.refreshes = 0
        self.samples = deque(maxlen=8)
        self.last_at = None
        self.paused_at = None
        self.pause_total = 0.0

    def _active_time(self, observed_at=None):
        now = self.clock() if observed_at is None else observed_at
        return (self.paused_at if self.paused_at is not None else now) - self.pause_total

    def observe(self, refreshes, observed_at=None):
        if not self.enabled or refreshes <= self.refreshes:
            return
        now = self._active_time(observed_at)
        if self.last_at is not None and self.paused_at is None:
            count = refreshes - self.refreshes
            seconds = (now - self.last_at) / count
            # Batched/duplicate output must not turn into near-zero cycles.
            if seconds >= .25:
                self.samples.extend([seconds] * min(count, self.samples.maxlen))
        self.refreshes = refreshes
        self.last_at = now

    def pause(self, observed_at=None):
        if self.enabled and self.paused_at is None:
            self.paused_at = self.clock() if observed_at is None else observed_at

    def resume(self, observed_at=None):
        if self.paused_at is not None:
            now = self.clock() if observed_at is None else observed_at
            self.pause_total += max(0.0, now - self.paused_at)
            self.paused_at = None

    @property
    def finishing(self):
        return self.enabled and self.refreshes >= self.total

    def remaining(self, observed_at=None):
        if not self.enabled or self.finishing or len(self.samples) < 3:
            return None
        average = sum(self.samples) / len(self.samples)
        since_refresh = max(0.0, self._active_time(observed_at) - self.last_at)
        return max(1.0, (self.total - self.refreshes) * average - since_refresh)
