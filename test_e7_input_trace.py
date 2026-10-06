"""Fake-input checks for optional telemetry; no desktop input, game or ADB."""
import contextlib
import io
import json
from pathlib import Path
import random
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from E7ADBShopRefresh import E7ADBShopRefresh, run_gui_session
from e7_mouse_refresh import E7MouseShopRefresh
from e7_native_mouse import WindowsMouse, MouseStopped
from e7_input_trace import InputTrace, BoundedSessionLog, TRACE_PREFIX, format_trace_line
from e7_engine_protocol import validate_settings
import test_e7_shared_flow as fixtures


class InputTraceTests(unittest.TestCase):
    def trace(self, enabled=True, clock=None):
        output = []
        return InputTrace(enabled, clock=clock, sink=output.append), output

    def records(self, output):
        return [json.loads(line[len(TRACE_PREFIX):]) for line in output]

    def test_disabled_trace_does_not_read_clock_or_write(self):
        clock, sink = Mock(), Mock()
        trace = InputTrace(clock=clock, sink=sink)
        trace.begin(0); trace.pause(); trace.resume(); trace.complete(1); trace.finish(1, 'interrupted')
        trace.emit('anything')
        clock.assert_not_called(); sink.assert_not_called()

    def test_tracing_preserves_seeded_actions_counters_and_random_state_in_both_modes(self):
        fixture = fixtures.SharedFlowTests()
        for mode in ('adb', 'mouse'):
            runs = []
            for enabled in (False, True):
                app, state = fixture.make_app(mode, width=800, items=True)
                state['screen'] = 'shop'
                app.input_trace, output = self.trace(enabled)
                random.seed(701)
                with patch('e7_shop_flow.time.sleep'), contextlib.redirect_stdout(io.StringIO()):
                    app.refreshShop()
                runs.append((state['events'], [v.count for v in app.storage.inventory.values()], random.getstate()))
                if enabled:
                    records = self.records(output)
                    self.assertTrue(any(r['kind'] == 'click' for r in records))
                    cycles = [r for r in records if r['kind'] == 'cycle']
                    self.assertEqual([r['interval'] for r in cycles], ['initial scan', 'refresh cycle', 'refresh cycle'])
                    self.assertEqual([r['outcome'] for r in cycles], ['complete', 'complete', 'final scan'])
            self.assertEqual(runs[0], runs[1], mode)

    def test_logs_bounded_offset_and_actual_screen_mapping(self):
        app = E7MouseShopRefresh.__new__(E7MouseShopRefresh)
        mouse = WindowsMouse.__new__(WindowsMouse)
        mouse.view = (-800, 100, 0, 550)
        mouse.guard = Mock(); mouse.sender = Mock()
        app.mouse = mouse
        app.generateOffset = Mock(return_value=(75, 25))
        app.input_trace, output = self.trace()
        app._click_button((10,20,50,60))
        event = self.records(output)[0]
        self.assertEqual(event['anchor'], [30,40])
        self.assertEqual(event['offset'], [10,10])
        self.assertEqual(event['final'], [40,50])
        self.assertEqual(event['mapped'], [-783,121])
        self.assertEqual(event['outcome'], 'input sent')
        mouse.sender.assert_called_once_with((-783,121), 'click', 0)
        app.generateOffset.assert_called_once()

    def test_blocked_input_is_not_reported_as_sent_or_retried(self):
        app = E7ADBShopRefresh.__new__(E7ADBShopRefresh)
        app.input_trace, output = self.trace()
        app.tap = Mock(side_effect=MouseStopped('fake blocked target'))
        with self.assertRaises(MouseStopped):
            app._tap_observed(100,100, action='refresh')
        app.tap.assert_called_once()
        self.assertEqual(self.records(output)[0]['outcome'], 'blocked or failed')

    def test_sample_is_drawn_once_and_wait_measures_elapsed_independently(self):
        app = E7ADBShopRefresh.__new__(E7ADBShopRefresh)
        app.tap_sleep, app.tap_jitter, app.random_offset, app.debug = 2., .1, True, False
        app.loop_active = True
        app.wait = Mock()
        app.input_trace, output = self.trace(clock=Mock(side_effect=[10.,12.003]))
        with patch('E7ADBShopRefresh.random.uniform', return_value=.1) as uniform:
            app._wait_tap_delay('refresh dialog')
        uniform.assert_called_once_with(-.1,.1)
        app.wait.assert_called_once_with(2.)
        event = self.records(output)[0]
        self.assertEqual(event['requested_ms'], 2000)
        self.assertAlmostEqual(event['elapsed_ms'], 2003)

    def test_interrupted_wait_is_labelled_and_does_not_sleep_full_delay(self):
        app = E7ADBShopRefresh.__new__(E7ADBShopRefresh)
        app.loop_active = False
        app._stop_requested = threading.Event(); app._stop_requested.set()
        app.input_trace, output = self.trace()
        app._wait_observed(2., 'refresh dialog', baseline=.3)
        event = self.records(output)[0]
        self.assertTrue(event['interrupted'])
        self.assertLess(event['elapsed_ms'], 500)

    def test_cycles_separate_initial_scan_final_interval_and_pauses(self):
        trace, output = self.trace(clock=Mock(side_effect=[0,1,3,6,10,11]))
        trace.begin(0); trace.pause(); trace.resume(); trace.retry()
        trace.complete(1); trace.complete(3); trace.finish(3, 'final scan'); trace.finish(3, 'interrupted')
        records = self.records(output)
        self.assertEqual([r['elapsed_ms'] for r in records], [6000,4000,1000])
        self.assertEqual([r['purchases'] for r in records], [1,2,0])
        self.assertEqual(records[0]['paused_ms'], 2000)
        self.assertEqual(records[0]['retries'], 1)
        self.assertEqual(records[1]['number'], 1)

    def test_trace_io_failure_does_not_change_input_success(self):
        app = E7ADBShopRefresh.__new__(E7ADBShopRefresh)
        app.input_trace = InputTrace(True, sink=Mock(side_effect=OSError('fake full disk')))
        app.tap = Mock(return_value=(40,50))
        self.assertEqual(app._tap_observed(40,50), (40,50))
        self.assertFalse(app.input_trace.enabled)
        app.tap.assert_called_once()

    def test_detail_and_saved_log_limits_preserve_a_marker(self):
        trace, output = self.trace()
        trace.bytes = 512*1024
        trace.emit('click'); trace.emit('click')
        self.assertEqual(self.records(output), [{'kind':'limit'}])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'session.log'
            log = BoundedSessionLog(path, limit=180)
            log.append('first event\n'); log.append('界'*100); log.append('must not grow\n')
            self.assertLessEqual(path.stat().st_size, 180)
            self.assertIn('first event', path.read_text(encoding='utf-8'))
            self.assertIn('size limit reached', path.read_text(encoding='utf-8'))

    def test_structured_settings_are_optional_and_validated_before_engine_start(self):
        self.assertFalse(validate_settings('fake',12,.3,'esc',True,False).trace_input)
        for value in (1, 'true', None):
            with self.assertRaises(ValueError):
                validate_settings('fake',12,.3,'esc',True,False,.03,value)
        data = dict(device='fake', budget=12, tap_sleep=.3, stop_key='esc', random_offset=True,
                    debug=False, tap_jitter=.03, trace_input=True)
        with patch('E7ADBShopRefresh.E7ADBShopRefresh') as engine, patch('E7ADBShopRefresh.threading.Thread'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_gui_session(['--gui-session',json.dumps(data)]), 0)
        self.assertTrue(engine.call_args.kwargs['trace_input'])

    def test_malformed_event_stays_readable_without_breaking_diagnostics(self):
        self.assertEqual(format_trace_line('ordinary output'), 'ordinary output')
        for line in (TRACE_PREFIX+'broken', TRACE_PREFIX+'{"kind":"click"}', TRACE_PREFIX+'[]'):
            self.assertEqual(format_trace_line(line), line)


if __name__ == '__main__':
    unittest.main()
