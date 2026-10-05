"""The same tap timing contract for the GUI, ADB and Windows Mouse."""
import math

MAX_TAP_DELAY = 2.0
MAX_TAP_JITTER = 0.10


def validate_timing(delay, jitter=None):
    delay = float(delay)
    if not math.isfinite(delay) or not 0 < delay <= MAX_TAP_DELAY:
        raise ValueError('Tap delay must be greater than 0 and at most 2.00 seconds.')
    if jitter is not None:
        jitter = float(jitter)
        if not math.isfinite(jitter) or not 0 <= jitter <= MAX_TAP_JITTER:
            raise ValueError('Timing variation must be between 0 and 0.10 seconds.')
    return delay, jitter


def sample_tap_delay(delay, jitter, randomized, calibration, uniform):
    # Clamp the final sample as well as validating the configured baseline.
    variation = min(delay * .10, .05) if jitter is None else min(jitter, delay * .5)
    sampled = delay + uniform(-variation, variation) if randomized and not calibration else delay
    return min(MAX_TAP_DELAY, sampled)
