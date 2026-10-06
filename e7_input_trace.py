"""Optional input telemetry. Never sample randomness, wait, capture or send input."""
import json
import time
from pathlib import Path

TRACE_PREFIX = 'E7GUI_TRACE '
TRACE_LIMIT = 512 * 1024
LOG_LIMIT = 2 * 1024 * 1024


class InputTrace:
    def __init__(self, enabled=False, *, clock=None, sink=None):
        self.enabled = enabled
        self.clock = clock or time.monotonic
        self.sink = sink or (lambda text: print(text, flush=True))
        self.bytes = 0
        self.boundary = None
        self.interval = 'initial scan'
        self.number = 0
        self.counts = 0
        self.retries = 0
        self.paused = 0
        self.pause_started = None

    def emit(self, kind, **values):
        if not self.enabled:
            return
        try:
            text = TRACE_PREFIX + json.dumps(dict(kind=kind, **values), separators=(',', ':'), allow_nan=False)
            size = len(text.encode('utf-8')) + 1
            if self.bytes + size > TRACE_LIMIT:
                self.sink(TRACE_PREFIX + '{"kind":"limit"}')
                self.enabled = False
                return
            self.sink(text)
            self.bytes += size
        except (OSError, ValueError, TypeError):
            # Observability must not turn an accepted action into a retry.
            self.enabled = False

    def begin(self, purchases):
        if self.enabled:
            self.boundary = self.clock()
            self.counts = purchases
            self.retries = self.paused = 0
            self.pause_started = None

    def retry(self):
        if self.enabled:
            self.retries += 1

    def pause(self):
        if self.enabled and self.pause_started is None:
            self.pause_started = self.clock()

    def resume(self):
        if self.enabled and self.pause_started is not None:
            self.paused += max(0, self.clock() - self.pause_started)
            self.pause_started = None

    def complete(self, purchases):
        if not self.enabled or self.boundary is None:
            return
        now = self.clock()
        self._interval(now, purchases, 'complete')
        self.boundary = now
        self.interval = 'refresh cycle'
        self.number += 1
        self.counts = purchases
        self.retries = self.paused = 0

    def finish(self, purchases, outcome):
        if self.enabled and self.boundary is not None:
            now = self.clock()
            if self.pause_started is not None:
                self.paused += max(0, now - self.pause_started)
                self.pause_started = None
            self._interval(now, purchases, outcome)
            self.boundary = None

    def _interval(self, now, purchases, outcome):
        self.emit('cycle', interval=self.interval, number=self.number,
                  elapsed_ms=round(max(0, now - self.boundary) * 1000, 3),
                  purchases=max(0, purchases - self.counts), retries=self.retries,
                  paused_ms=round(self.paused * 1000, 3), outcome=outcome)


class BoundedSessionLog:
    """Cap each saved log without deleting earlier sessions or their history."""
    def __init__(self, path, *, limit=LOG_LIMIT):
        self.path = Path(path)
        self.limit = limit
        self.bytes = 0
        self.full = False
        self.path.write_text('Session diagnostics (local only)\n', encoding='utf-8')
        self.bytes = self.path.stat().st_size

    def append(self, text):
        if self.full:
            return
        payload = text.encode('utf-8')
        marker = b'\nSaved log size limit reached; session continues.\n'
        with self.path.open('ab') as stream:
            if self.bytes + len(payload) + len(marker) > self.limit:
                stream.write(marker)
                self.bytes += len(marker)
                self.full = True
            else:
                stream.write(payload)
                self.bytes += len(payload)


def format_trace_line(line):
    if not line.startswith(TRACE_PREFIX):
        return line
    try:
        data = json.loads(line[len(TRACE_PREFIX):])
        if data['kind'] == 'click':
            return (f"[Input] {data['action']}: anchor={data['anchor']}, offset={data['offset']}, "
                    f"final={data['final']} (1920×1080); {data['mapped_space']}={data['mapped']}; {data['outcome']}")
        if data['kind'] == 'delay':
            base = f"baseline={data['baseline_ms']:.1f}ms, " if data['baseline_ms'] is not None else ''
            return (f"[Timing] {data['action']}: {base}requested={data['requested_ms']:.1f}ms, "
                    f"measured={data['elapsed_ms']:.1f}ms" + ('; interrupted' if data['interrupted'] else ''))
        if data['kind'] == 'cycle':
            name = 'Initial scan' if data['interval'] == 'initial scan' else f"Cycle {data['number']}"
            return (f"[Timing] {name}: {data['elapsed_ms']/1000:.3f}s, purchases={data['purchases']}, "
                    f"retries={data['retries']}, paused={data['paused_ms']/1000:.3f}s; {data['outcome']}")
        if data['kind'] == 'limit':
            return '[Input] Detailed trace size limit reached; session continues without detailed events.'
    except (ValueError, KeyError, TypeError):
        pass
    return line
