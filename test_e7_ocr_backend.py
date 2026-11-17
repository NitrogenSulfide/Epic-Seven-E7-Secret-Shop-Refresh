import os
import subprocess
import unittest
from unittest import mock

import numpy as np

import e7_mouse_confirmation as ocr

TSV = ('level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
       '1\t1\t0\t0\t0\t0\t0\t0\t400\t100\t-1\t\n'
       '5\t1\t1\t1\t1\t1\t20\t10\t60\t20\t95\tFriendship\n'
       '5\t1\t1\t1\t1\t2\t100\t10\t40\t20\t94\tPoints\n'
       '5\t1\t2\t1\t1\t1\t200\t60\t30\t20\t90\t1/1\n'
       '5\t1\t2\t1\t1\t2\t240\t60\t30\t20\t90\tBuy\n'
       '5\t1\t2\t1\t1\t3\t280\t60\t30\t20\t10\t \n')


class TesseractBackendTest(unittest.TestCase):
    def setUp(self):
        self.rgb = np.full((1080, 1920, 3), 80, dtype=np.uint8)

    def run_ocr(self, region, **kw):
        done = subprocess.CompletedProcess([], 0, stdout=TSV, stderr='')
        with mock.patch.object(ocr, 'ocr_backend', return_value='tesseract'), \
                mock.patch('shutil.which', return_value='/usr/bin/tesseract'), \
                mock.patch.object(ocr.subprocess, 'run', return_value=done) as run:
            return ocr.read_ui_text(self.rgb, region, **kw), run

    def test_words_map_back_to_frame_coordinates(self):
        result, run = self.run_ocr((960, 110, 1880, 1080))
        self.assertEqual(result['text'], 'friendship points\n1/1 buy')
        # Tesseract saw a 2x image: (20,10)-(80,30) is (10,5)-(40,15) in the crop.
        self.assertEqual(result['words'][0], dict(text='friendship', box=[970.0, 115.0, 1000.0, 125.0]))
        self.assertEqual([w['text'] for w in result['words']], ['friendship', 'points', '1/1', 'buy'])
        self.assertIn('--psm', run.call_args.args[0])

    def test_caller_scale_is_also_undone(self):
        result, _ = self.run_ocr((1000, 400, 1200, 500), scale=2, contrast=True)
        self.assertEqual(result['words'][0]['box'], [1005.0, 402.5, 1020.0, 407.5])

    def test_missing_tesseract_refuses(self):
        with mock.patch.object(ocr, 'ocr_backend', return_value='tesseract'), mock.patch('shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'Tesseract OCR is not installed'):
                ocr.read_ui_text(self.rgb, (0, 0, 100, 100))

    def test_failure_and_timeout_refuse(self):
        failed = subprocess.CompletedProcess([], 1, stdout='', stderr='boom')
        with mock.patch.object(ocr, 'ocr_backend', return_value='tesseract'), \
                mock.patch('shutil.which', return_value='/usr/bin/tesseract'):
            with mock.patch.object(ocr.subprocess, 'run', return_value=failed):
                with self.assertRaisesRegex(ValueError, 'No confirmation click'):
                    ocr.read_ui_text(self.rgb, (0, 0, 100, 100))
            with mock.patch.object(ocr.subprocess, 'run', side_effect=subprocess.TimeoutExpired('t', 20)):
                with self.assertRaisesRegex(ValueError, 'timed out'):
                    ocr.read_ui_text(self.rgb, (0, 0, 100, 100))

    def test_backend_choice(self):
        with mock.patch.object(ocr.os, 'name', 'nt'), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('E7_OCR', None)
            self.assertEqual(ocr.ocr_backend(), 'windows')
            os.environ['E7_OCR'] = 'tesseract'
            self.assertEqual(ocr.ocr_backend(), 'tesseract')
        with mock.patch.object(ocr.os, 'name', 'posix'):
            self.assertEqual(ocr.ocr_backend(), 'tesseract')


class WindowsOcrFailureTest(unittest.TestCase):
    """GitHub #2/#3: a Windows without English OCR stopped with a generic
    message, and PowerShell's cp850 error text crashed the UTF-8 reader."""

    REASON = 'English Windows OCR is not installed (OCR languages: pt-BR)'

    def setUp(self):
        self.rgb = np.full((200, 200, 3), 80, dtype=np.uint8)
        ocr.close_ocr_server()
        self.addCleanup(ocr.close_ocr_server)
        self.addCleanup(setattr, ocr, '_ocr_server', None)
        patches = [mock.patch.object(ocr, 'ocr_backend', return_value='windows'),
                   mock.patch.object(ocr, '_powershell_command', return_value=['powershell'])]
        for patch in patches:
            patch.start(); self.addCleanup(patch.stop)

    def read_with(self, *, server_error, stderr):
        server = mock.Mock(); server.read.side_effect = server_error
        failed = subprocess.CompletedProcess([], 1, stdout='', stderr=stderr)
        with mock.patch.object(ocr, '_OcrServer', return_value=server), \
                mock.patch.object(ocr.subprocess, 'run', return_value=failed) as run:
            with self.assertRaises(ValueError) as caught:
                ocr.read_ui_text(self.rgb, (0, 0, 100, 100))
        self.assertEqual(run.call_args.kwargs['errors'], 'replace')
        return str(caught.exception)

    def test_helper_reason_reaches_the_user(self):
        stderr = self.REASON + '. Add English in Settings\r\nAt line:58 char:5\r\n+ throw ...\r\n'
        message = self.read_with(server_error=ValueError(self.REASON), stderr=stderr)
        self.assertIn(self.REASON, message)
        self.assertNotIn('At line', message)
        self.assertTrue(message.endswith('No confirmation click sent.'))

    def test_clixml_error_is_decoded(self):
        stderr = ('#< CLIXML\r\n<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">'
                  '<S S="Error">English Windows OCR is not installed &amp; more_x000D__x000A_</S>'
                  '<S S="Error">At line:58 char:5_x000D__x000A_</S></Objs>')
        message = self.read_with(server_error=OSError('The OCR process stopped answering.'), stderr=stderr)
        self.assertIn('English Windows OCR is not installed & more', message)
        self.assertNotIn('CLIXML', message)

    def test_server_reason_kept_when_one_shot_is_silent(self):
        message = self.read_with(server_error=ValueError(self.REASON), stderr='')
        self.assertIn(self.REASON, message)

    def test_cp850_output_does_not_crash_the_reader(self):
        # Real pipes: the bytes a Portuguese PowerShell writes ('ó' is 0xa2 in cp850).
        import sys
        script = "import sys; sys.stderr.buffer.write(b'Exce\\xa2o: falhou\\n'); sys.exit(1)"
        real_run = subprocess.run
        def run(command, **options):
            options.pop('creationflags', None)
            return real_run([sys.executable, '-c', script], **{k: v for k, v in options.items() if k != 'env'})
        server = mock.Mock(); server.read.side_effect = OSError('The OCR process stopped answering.')
        with mock.patch.object(ocr, '_OcrServer', return_value=server), \
                mock.patch.object(ocr.subprocess, 'run', side_effect=run):
            with self.assertRaisesRegex(ValueError, r'Exce�o: falhou\. No confirmation click sent\.'):
                ocr.read_ui_text(self.rgb, (0, 0, 100, 100))


if __name__ == '__main__':
    unittest.main()
