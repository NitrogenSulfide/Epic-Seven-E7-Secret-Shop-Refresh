"""Session sound players for Linux and macOS. Nothing is played."""
import unittest
from unittest.mock import patch

import e7_sound


class PlayerTest(unittest.TestCase):
    def play(self, available):
        with patch.object(e7_sound.shutil, 'which', side_effect=lambda name: f'/bin/{name}' if name in available else None), \
                patch.object(e7_sound.subprocess, 'Popen') as popen:
            e7_sound.PlaySound('/x/start.wav', e7_sound.SND_FILENAME | e7_sound.SND_ASYNC)
        return popen.call_args.args[0]

    def test_linux_players_come_first(self):
        self.assertEqual(self.play({'paplay', 'afplay'}), ['/bin/paplay', '/x/start.wav'])
        self.assertEqual(self.play({'aplay'}), ['/bin/aplay', '-q', '/x/start.wav'])

    def test_macos_uses_afplay(self):
        self.assertEqual(self.play({'afplay'}), ['/bin/afplay', '/x/start.wav'])

    def test_no_player_raises_and_aliases_are_ignored(self):
        with patch.object(e7_sound.shutil, 'which', return_value=None), self.assertRaisesRegex(OSError, 'afplay'):
            e7_sound.PlaySound('/x/start.wav', e7_sound.SND_FILENAME)
        with patch.object(e7_sound.subprocess, 'Popen') as popen:
            e7_sound.PlaySound('SystemAsterisk', e7_sound.SND_ALIAS)
        popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
