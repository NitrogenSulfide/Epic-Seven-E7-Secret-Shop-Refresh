import io
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from PIL import Image
from e7_setup import capture_frame, missing_references, prepare_captured_references, REFERENCE_NAMES


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name)
        self.captures = self.runtime/'setup-captures/example'
        self.captures.mkdir(parents=True)
        self.engine = self.runtime/'engine.exe'
        self.engine.write_bytes(b'Fixture engine, never executable')
        self.engine.with_suffix('.sha256').write_text(hashlib.sha256(self.engine.read_bytes()).hexdigest())

    def test_capture_uses_only_read_only_screencap(self):
        data = io.BytesIO()
        Image.new('RGB', (1920,1080)).save(data, format='PNG')
        calls = []
        def run(command, **options):
            calls.append(command)
            self.assertEqual(options['timeout'], 25)
            return SimpleNamespace(returncode=0, stdout=data.getvalue())
        capture_frame('adb.exe', 'fixture-device', self.captures/'home.png', runner=run)
        self.assertEqual(calls, [['adb.exe','-s','fixture-device','exec-out','screencap','-p']])
        self.assertEqual((self.captures/'home.png').read_bytes(), data.getvalue())

    def test_wrong_resolution_is_rejected_without_writing(self):
        data = io.BytesIO(); Image.new('RGB',(1280,720)).save(data,format='PNG')
        with self.assertRaisesRegex(ValueError, '1920'):
            capture_frame('adb','fixture',self.captures/'home.png',runner=lambda *a,**k:SimpleNamespace(returncode=0,stdout=data.getvalue()))
        self.assertFalse((self.captures/'home.png').exists())

    def test_failed_capture_does_not_overwrite_previous_image(self):
        image = self.captures/'home.png'; image.write_bytes(b'old private capture')
        with self.assertRaisesRegex(RuntimeError,'Screenshot failed'):
            capture_frame('adb','fixture',image,runner=lambda *a,**k:SimpleNamespace(returncode=1))
        self.assertEqual(image.read_bytes(),b'old private capture')

    def test_missing_reference_names(self):
        self.assertEqual(missing_references(self.runtime), list(REFERENCE_NAMES))
        folder = self.runtime/'adb-assets/gui-navigation'; folder.mkdir(parents=True)
        for name in REFERENCE_NAMES: (folder/name).write_bytes(b'fixture')
        self.assertEqual(missing_references(self.runtime), [])

    def test_failed_validation_preserves_existing_calibration(self):
        folder = self.runtime/'adb-assets/gui-navigation'; folder.mkdir(parents=True)
        (folder/REFERENCE_NAMES[0]).write_bytes(b'old reference')
        def run(command, **options):
            self.assertEqual(command[1], '--prepare-navigation-references')
            return SimpleNamespace(returncode=1)
        with self.assertRaisesRegex(RuntimeError,'did not pass'):
            prepare_captured_references(self.engine,self.runtime,self.captures,runner=run)
        self.assertEqual((folder/REFERENCE_NAMES[0]).read_bytes(), b'old reference')

    def test_success_preserves_backup_and_uses_offline_engine_only(self):
        folder = self.runtime/'adb-assets/gui-navigation'; folder.mkdir(parents=True)
        (folder/REFERENCE_NAMES[0]).write_bytes(b'old reference')
        def run(command, **options):
            self.assertEqual(command[1], '--prepare-navigation-references')
            self.assertNotIn('adb', ' '.join(command))
            output = Path(command[-1]); output.mkdir()
            for name in REFERENCE_NAMES: (output/name).write_bytes(b'new fixture reference')
            return SimpleNamespace(returncode=0)
        prepare_captured_references(self.engine,self.runtime,self.captures,runner=run)
        self.assertEqual(missing_references(self.runtime), [])
        backups = list(folder.parent.glob('gui-navigation-backup-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0]/REFERENCE_NAMES[0]).read_bytes(), b'old reference')

    def test_mismatched_engine_is_never_executed_for_setup(self):
        self.engine.write_bytes(b'Replaced fixture engine')
        def forbidden(*args, **kwargs):
            self.fail('Mismatched engine must not be executed')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            prepare_captured_references(self.engine,self.runtime,self.captures,runner=forbidden)


if __name__ == '__main__':
    unittest.main(verbosity=2)
