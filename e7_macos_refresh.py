"""Mac (iPad app on Apple silicon) session: the shared refresh loop over MacMouse.

Reuses E7BackgroundShopRefresh for its dry run (navigation only; Refresh and
Buy are recognized but never sent). Input takes over the real pointer, so
the game must stay the active window: see e7_macos.MacMouse.
"""
import argparse
import json
import math
import shutil
import sys
import threading

from e7_background_refresh import E7BackgroundShopRefresh
from e7_macos import MacMouse
from e7_native_mouse import MouseStopped
from e7_session_control import listen_for_stop
from e7_timing import validate_timing


class E7MacShopRefresh(E7BackgroundShopRefresh):
    def __init__(self, *, transport=None, dry_run=False, **settings):
        # The activity check is read at call time, after the engine has set
        # loop_active and _stop_requested.
        transport = transport or MacMouse(lambda: self.loop_active and not self._stop_requested.is_set())
        super().__init__(transport=transport, dry_run=dry_run, **settings)
        self._session_metadata['Control mode'] = 'Mac (dry run)' if dry_run else 'Mac'


def require_ocr():
    if shutil.which('tesseract') is None:
        raise ValueError('Tesseract OCR is not installed, and purchase confirmations cannot be checked without it. '
                         'Install it with: brew install tesseract. No input sent.')


def run_macos_session(arguments):
    parser = argparse.ArgumentParser(description='Mac refresh session for the Epic Seven iPad app; uses the real pointer.')
    parser.add_argument('--macos-session', action='store_true', required=True)
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
        require_ocr()
        app = E7MacShopRefresh(budget=args.budget, tap_sleep=args.delay, stop_refresh_key=args.stop_key,
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
        print('E7GUI_MOUSE_STOPPED '+json.dumps({'reason': f'Mac session stopped. {error}'}), flush=True)
        return 3
    finally:
        if app is not None:
            app.close_transport()
