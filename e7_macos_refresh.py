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
import time
from pathlib import Path

from e7_background_refresh import E7BackgroundShopRefresh
from e7_macos import MacMouse
from e7_native_mouse import MouseStopped
from e7_session_control import listen_for_stop
from e7_timing import validate_timing

# Private, git-ignored evidence: every shop frame the engine checked for an
# item, with each item's outcome. An item skipped without a log line (an
# unread name, a dimmed row) can then be reproduced offline.
SCAN_FRAMES = Path(__file__).resolve().parent/'.local-state'/'mac-scan-frames'
SCAN_SESSIONS_KEPT = 5


class E7MacShopRefresh(E7BackgroundShopRefresh):
    def __init__(self, *, transport=None, dry_run=False, **settings):
        # The activity check is read at call time, after the engine has set
        # loop_active and _stop_requested.
        transport = transport or MacMouse(lambda: self.loop_active and not self._stop_requested.is_set())
        super().__init__(transport=transport, dry_run=dry_run, **settings)
        self._session_metadata['Control mode'] = 'Mac (dry run)' if dry_run else 'Mac'
        self._scan_root, self._scan_dir, self._scan_rgb, self._scan_file, self._scan_count = SCAN_FRAMES, None, None, None, 0

    def findItemPosition(self, frame, template):
        name = next((key for key, item in self.storage.inventory.items() if item.image is template), None)
        outcome = 'error'
        try:
            point = super().findItemPosition(frame, template)
            outcome = 'none' if point is None else 'buy'
            return point
        except Exception as error:
            outcome = f'stop: {error}'
            raise
        finally:
            self._record_scan(name, outcome)

    def _record_scan(self, name, outcome):
        """Save each checked frame once, and one outcome line per item check.
        Never raises: evidence must not change what the session does."""
        rgb = getattr(self, '_rgb', None)
        if rgb is None or self._scan_root is None:
            return
        try:
            from PIL import Image
            if self._scan_dir is None:
                self._scan_dir = self._scan_root/time.strftime('%Y%m%d-%H%M%S')
                self._scan_dir.mkdir(parents=True, exist_ok=True)
                sessions = sorted(path for path in self._scan_root.iterdir() if path.is_dir())
                for old in sessions[:-SCAN_SESSIONS_KEPT]:
                    shutil.rmtree(old, ignore_errors=True)
            if rgb is not self._scan_rgb:
                self._scan_rgb, self._scan_count = rgb, self._scan_count+1
                self._scan_file = (f'{self._scan_count:03d}_r{getattr(self, "refresh_count", 0)}'
                                   f'_p{getattr(self, "_scan_page", 0)}.jpg')
                Image.fromarray(rgb).save(self._scan_dir/self._scan_file, quality=92)
            with (self._scan_dir/'scans.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(dict(file=self._scan_file, item=name, outcome=outcome))+'\n')
        except (OSError, ValueError, TypeError):
            pass


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
