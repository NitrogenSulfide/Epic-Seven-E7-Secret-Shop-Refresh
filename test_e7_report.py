"""The paste-ready problem report: size limit and privacy."""
import tempfile
import unittest

from e7_report import anonymize, build_report


class ReportTest(unittest.TestCase):
    def test_user_name_and_home_are_hidden(self):
        text = anonymize(r'C:\Users\Natto\E7\engine.exe and natto again', home=r'C:\Users\Natto', user='Natto')
        self.assertEqual(text, r'~\E7\engine.exe and <user> again')

    def test_long_logs_are_trimmed_to_fit_a_reddit_comment(self):
        log = ''.join(f'Navigation: a long line number {i} '+'x'*200+'\n' for i in range(60))
        with tempfile.TemporaryDirectory() as folder:
            report = build_report(version='0.2.4', mode='Background', target='', state='Failed', reason='',
                                  log=log, app_dir=folder, since=0, system='Test', home='/nohome', user='')
        self.assertLessEqual(len(report), 8000)
        self.assertIn('Navigation: a long line number 59', report)
        self.assertNotIn('number 0 ', report)

    def test_report_without_a_log(self):
        report = build_report(version='0.2.4', mode='ADB', target='', state='Failed', reason='Engine exited',
                              log='', app_dir='/nonexistent', since=0, system='Test', home='/nohome', user='')
        self.assertIn('No log lines yet.', report)
        self.assertIn('- Result: Failed · Engine exited', report)


if __name__ == '__main__':
    unittest.main()
