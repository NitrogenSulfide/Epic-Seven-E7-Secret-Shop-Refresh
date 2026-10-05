"""Offline session persistence, Stop commands and interoperable Excel structure."""
import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from e7_history import append_session, read_sessions, export_sessions, new_session_metadata
from e7_engine_protocol import validate_settings
from e7_links import bug_report_url, release_url
from e7_timing import validate_timing, sample_tap_delay
from e7_session_control import listen_for_stop
from E7ADBShopRefresh import E7ADBShopRefresh, run_gui_session


class SessionCleanupTests(unittest.TestCase):
    def test_all_entry_points_reject_invalid_delays_before_capture(self):
        for delay in (0, -.1, 2.01, 86400, float('nan'), float('inf')):
            with self.subTest(delay=delay), self.assertRaises(ValueError):
                validate_timing(delay, .1)
            with self.assertRaises(ValueError):
                validate_settings('fake', '12', str(delay), 'esc', True, False)
            with patch.object(E7ADBShopRefresh, 'checkScreenDimension') as capture, self.assertRaises(ValueError):
                E7ADBShopRefresh(tap_sleep=delay)
            capture.assert_not_called()
        self.assertEqual(sample_tap_delay(2., .1, True, False, lambda a,b:b), 2.)

    def test_legacy_migration_preserves_bytes_values_and_unknown_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.csv'
            original = b'Duration,Skystone spent,Gold spent,Covenant bookmark,Mystic medal,Custom\n10,3,184000,1,0,retain me\n'
            path.write_bytes(original)
            record = new_session_metadata('Mouse')
            record.update({'Duration': 2, 'Skystone spent': 3, 'Outcome': 'stopped', 'Reason': 'User stop'})
            append_session(path, record)
            rows = read_sessions(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['Custom'], 'retain me')
            self.assertEqual(rows[0]['Skystone spent'], '3')
            self.assertEqual(rows[1]['Mode'], 'Normal')
            self.assertEqual(rows[1]['Control mode'], 'Mouse')
            self.assertEqual(next((path.parent/'schema-backups').glob('*.csv')).read_bytes(), original)
            append_session(path, record)
            self.assertEqual(len(read_sessions(path)), 2)

    def test_explicit_mode_wins_over_legacy_friendship_heuristic(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.csv'
            path.write_text('Duration,Skystone spent,Gold spent,Covenant bookmark,Mystic medal\n10,3,0,0,0,0\n', encoding='utf-8')
            self.assertEqual(read_sessions(path)[0]['Mode'], 'Debug')
            record = dict(new_session_metadata('ADB'), Duration=1, Outcome='completed')
            append_session(path, record)
            self.assertEqual([row['Mode'] for row in read_sessions(path)], ['Debug', 'Normal'])

    def test_failed_atomic_replace_leaves_history_intact(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.csv'
            original = b'Duration,Skystone spent,Gold spent,Covenant bookmark,Mystic medal\n10,3,0,0,0\n'
            path.write_bytes(original)
            with patch.object(Path, 'replace', side_effect=OSError('test write failure')), self.assertRaises(OSError):
                append_session(path, new_session_metadata('ADB'))
            self.assertEqual(path.read_bytes(), original)

    def test_excel_exports_more_than_25_rows_as_numbers_and_safe_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sessions.xlsx'
            rows = [dict(new_session_metadata('ADB'), Duration=i, **{'Skystone spent': 3, 'Reason': '=1+1'}) for i in range(30)]
            export_sessions(path, rows)
            with ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                for name in archive.namelist():
                    ET.fromstring(archive.read(name))
                ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
                self.assertEqual(len(sheet.findall('s:sheetData/s:row', ns)), 32)
                self.assertEqual(sheet.find(".//s:c[@r='H2']/s:v", ns).text, '3.0')
                self.assertEqual(sheet.find(".//s:c[@r='H32']/s:v", ns).text, '90.0')
                self.assertIsNone(sheet.find(".//s:c[@r='F2']/s:f", ns))
                self.assertEqual(sheet.find(".//s:c[@r='F2']/s:is/s:t", ns).text, '=1+1')

    def test_stop_interrupts_wait_and_saves_one_record(self):
        app = E7ADBShopRefresh.__new__(E7ADBShopRefresh)
        app._stop_requested = threading.Event()
        app._stop_reason = ''
        app.loop_active, app.debug, app.refresh_count = True, False, 2
        app._session_metadata = new_session_metadata('ADB')
        app._session_clock = time.monotonic()
        app.storage = Mock()
        waiting = threading.Thread(target=app.wait, args=(2.,))
        waiting.start()
        listen_for_stop(io.StringIO('STOP\n'), app)
        waiting.join(timeout=.5)
        self.assertFalse(waiting.is_alive())
        self.assertFalse(app.loop_active)
        app.record_session('stopped', app._stop_reason)
        app.record_session('failed', 'must not duplicate')
        app.storage.writeToCSV.assert_called_once()
        record = app.storage.writeToCSV.call_args.kwargs
        self.assertEqual(record['skystone_spent'], 6)
        self.assertEqual(record['session']['Outcome'], 'stopped')
        self.assertEqual(record['session']['Control mode'], 'ADB')

    def test_failure_after_partial_progress_saves_results_in_finally(self):
        app = E7ADBShopRefresh.__new__(E7ADBShopRefresh)
        app._stop_requested = threading.Event()
        app.debug, app.refresh_count, app._stop_reason = False, 2, ''
        app.keyboard_thread, app.storage = Mock(), Mock()
        app.refreshShop = Mock(side_effect=RuntimeError('recognition failed'))
        with self.assertRaisesRegex(RuntimeError, 'recognition failed'):
            app.start()
        app.storage.writeToCSV.assert_called_once()
        self.assertEqual(app.storage.writeToCSV.call_args.kwargs['session']['Outcome'], 'failed')
        app.keyboard_thread.join.assert_called_once()

    def test_structured_adb_passes_settings_and_leaves_stdin_for_stop(self):
        settings = dict(device='fake', budget=12, tap_sleep=.3, stop_key='esc', random_offset=True, debug=False, tap_jitter=.1)
        fake = Mock()
        with patch('E7ADBShopRefresh.E7ADBShopRefresh', return_value=fake) as engine, \
                patch('E7ADBShopRefresh.threading.Thread') as listener, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(run_gui_session(['--gui-session', json.dumps(settings)]), 0)
        self.assertEqual(engine.call_args.kwargs['ip_port'], 'fake')
        self.assertEqual(engine.call_args.kwargs['budget'], 12)
        self.assertIn('E7GUI_STARTED', output.getvalue())
        listener.return_value.start.assert_called_once()
        fake.start.assert_called_once()

    def test_bug_link_prefills_version_and_mode_without_private_logs(self):
        from urllib.parse import parse_qs, urlparse
        query = parse_qs(urlparse(bug_report_url('0.1.3-rc1', 'Mouse')).query)
        self.assertIn('v0.1.3-rc1', query['body'][0])
        self.assertIn('Mouse', query['body'][0])
        self.assertNotIn('Engine:', query['body'][0])
        self.assertTrue(release_url('0.1.2').endswith('/tag/v0.1.2'))
        self.assertTrue(release_url('0.1.3-rc1').endswith('/releases'))


if __name__ == '__main__':
    unittest.main()
