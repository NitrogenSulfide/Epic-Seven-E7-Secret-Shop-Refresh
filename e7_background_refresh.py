"""Background (Steam on Linux) implementation of the shared shop refresh loop."""
import argparse
import json
import math
import sys
import threading
import time

from e7_background import BackgroundGame
from e7_mouse_refresh import E7MouseShopRefresh
from e7_native_mouse import MouseStopped
from e7_session_control import listen_for_stop
from e7_timing import validate_timing


# Clicks a dry run may send: navigation only, never anything that spends.
DRY_RUN_ACTIONS = frozenset({'open shop', 'reveal home controls'})


class DryRunSkip(Exception):
    """A spending click was reached in a dry run; it was not sent."""


class E7BackgroundShopRefresh(E7MouseShopRefresh):
    def __init__(self, *, transport=None, dry_run=False, **settings):
        self.dry_run = dry_run
        self._dry_permit = False
        # The activity check is read at call time, after the engine has set
        # loop_active and _stop_requested.
        transport = transport or BackgroundGame(lambda: self.loop_active and not self._stop_requested.is_set())
        super().__init__(None, transport=transport, **settings)
        self._session_metadata['Control mode'] = 'Background (dry run)' if dry_run else 'Background'

    def _tap_observed(self, x, y, *, anchor=None, action='navigation'):
        if not self.dry_run:
            return super()._tap_observed(x, y, anchor=anchor, action=action)
        if action not in DRY_RUN_ACTIONS:
            print(f'Dry run: would click "{action}" at ({round(x)}, {round(y)}); not sent.', flush=True)
            raise DryRunSkip(action)
        self._dry_permit = True
        try:
            return super()._tap_observed(x, y, anchor=anchor, action=action)
        finally:
            self._dry_permit = False

    def record_session(self, outcome, reason='', duration=None):
        if self.dry_run:  # a dry run spends nothing; keep it out of session history
            self._session_recorded = True
            return
        return super().record_session(outcome, reason, duration)

    def tap(self, x, y):
        # Second lock: in a dry run only a permitted navigation click reaches the game.
        if self.dry_run and not self._dry_permit:
            raise MouseStopped('Dry run: an unexpected click was blocked. Nothing was spent.')
        return super().tap(x, y)

    def clickBuy(self, pos):
        try:
            return super().clickBuy(pos)
        except DryRunSkip:
            print(f'Dry run: {self._item_name or "item"} recognized and its Buy button found; skipped.', flush=True)
            return False

    def clickRefresh(self):
        try:
            return super().clickRefresh()
        except DryRunSkip:
            raise MouseStopped('Dry run complete: home, shop, both pages and the Refresh button were recognized. '
                               'Stopped before Refresh; nothing was spent.')

    def close_transport(self):
        close = getattr(self.mouse, 'close', None)
        if close is not None:
            close()


def run_background_session(arguments):
    parser = argparse.ArgumentParser(description='Background refresh session for Epic Seven on Steam (Linux).')
    parser.add_argument('--background-session', action='store_true', required=True)
    parser.add_argument('--budget', type=int, required=True)
    parser.add_argument('--delay', type=float, required=True)
    parser.add_argument('--stop-key', default='esc')
    parser.add_argument('--random-offset', choices=('yes', 'no'), required=True)
    parser.add_argument('--tap-jitter', type=float, default=None)
    parser.add_argument('--trace-input', action='store_true')
    parser.add_argument('--buy-friendship', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='navigate and recognize only; never Buy or Refresh')
    args = parser.parse_args(arguments)
    if not math.isfinite(args.budget) or args.budget < 3:
        parser.error('Invalid budget')
    try:
        validate_timing(args.delay, args.tap_jitter)
    except (TypeError, ValueError) as error:
        parser.error(str(error))
    app = None
    try:
        app = E7BackgroundShopRefresh(budget=args.budget, tap_sleep=args.delay, stop_refresh_key=args.stop_key,
                                      random_offset=args.random_offset == 'yes', debug=False,
                                      tap_jitter=args.tap_jitter, trace_input=args.trace_input,
                                      buy_friendship=args.buy_friendship, dry_run=args.dry_run)
        if sys.stdin is not None:
            threading.Thread(target=listen_for_stop, args=(sys.stdin, app), daemon=True).start()
        print('E7GUI_STARTED', flush=True)
        app.start()
        return 0
    except MouseStopped as error:
        print('E7GUI_MOUSE_STOPPED '+json.dumps({'reason': str(error)}), flush=True)
        if app is not None:
            app.reportLiveStats()
            app.record_session('failed', str(error))
            app.printResult()
        return 0
    except (ValueError, RuntimeError, OSError) as error:
        print('E7GUI_MOUSE_STOPPED '+json.dumps({'reason': f'Background session stopped. {error}'}), flush=True)
        return 3
    finally:
        if app is not None:
            app.close_transport()
