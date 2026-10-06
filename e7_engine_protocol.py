"""Validated run settings and the compatibility adapter for older console engines."""
import math
import re
from dataclasses import dataclass
from e7_timing import validate_timing

STOP_KEY_CHARACTERS = "0123456789abcdefghijklmnopqrstuvwxyz/.,';[]`"

@dataclass(frozen=True)
class RunSettings:
    device: str
    budget: int
    tap_sleep: float
    stop_key: str
    random_offset: bool
    debug: bool
    tap_jitter: float = 0.03
    trace_input: bool = False


def validate_settings(device, budget, delay, stop_key, random_offset, debug, tap_jitter=0.03, trace_input=False):
    if not re.fullmatch(r'[0-9]+', str(budget).strip()):
        raise ValueError("The skystone budget must be a whole number of at least 3.")
    try:
        amount, sleep, jitter = int(budget), float(delay), float(tap_jitter)
    except (ValueError, TypeError):
        raise ValueError("Enter numbers for the skystone budget and tap delay.") from None
    if amount < 3:
        raise ValueError("The skystone budget must be a whole number of at least 3.")
    sleep, jitter = validate_timing(sleep, jitter)
    device = device.strip() or "localhost:5555"
    key = stop_key.strip().lower() or "esc"
    if any(c in device for c in "\r\n"):
        raise ValueError("The device must be a single ADB address.")
    if key != "esc" and (len(key) != 1 or key not in STOP_KEY_CHARACTERS):
        raise ValueError("Use Esc or a single letter, number, or / . , ' ; [ ] ` as the stop key.")
    if type(trace_input) is not bool:
        raise ValueError('Input tracing must be on or off.')
    return RunSettings(device, amount, sleep, key, bool(random_offset), bool(debug), jitter, trace_input)


class EngineProtocol:
    """Answer observed prompts: the engine skips device selection with one device.

    Never send a timed, positional answer list. A skipped prompt otherwise shifts
    every subsequent setting and can start a run with the wrong budget.
    """
    def __init__(self, settings):
        self.settings = settings
        self.pending = ""
        self.started = False

    def feed(self, text):
        self.pending = (self.pending + text)[-12000:]
        s = self.settings
        prompts = (
            ("when you finish reading, press enter to continue!", ""),
            ("Device: ", s.device),
            ("leave blank for yes, or type (yes/no): ", "no"),
            ("Launch in debug mode? leave bank for no (yes/no): ", "yes" if s.debug else "no"),
            ("Key: ", s.stop_key),
            ("Enable randomize click (yes/no): ", "yes" if s.random_offset else "no"),
            ("Tap sleep(in seconds) Recommend - leave blank for 0.3 sec : ", str(s.tap_sleep)),
            ("Amount of skystone that you want to spend: ", str(s.budget)),
            ("Press enter to start!", ""),
            ("press enter to exit...", ""),
            ("Press enter to exit ...", ""),
        )
        answers = []
        while True:
            matches = [(self.pending.find(prompt), prompt, answer) for prompt, answer in prompts if prompt in self.pending]
            if not matches:
                break
            at, prompt, answer = min(matches)
            self.pending = self.pending[at + len(prompt):]
            if prompt == "Press enter to start!":
                self.started = True
            answers.append(answer)
        return answers
