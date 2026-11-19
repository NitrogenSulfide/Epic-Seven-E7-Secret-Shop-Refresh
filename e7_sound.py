"""winsound-compatible session sounds for Linux (PipeWire/PulseAudio or ALSA)
and macOS (the built-in afplay)."""
import shutil
import subprocess

SND_FILENAME, SND_ALIAS, SND_ASYNC, SND_NODEFAULT = 0x20000, 0x10000, 0x1, 0x2


def PlaySound(sound, flags):
    """Play a WAV file in the background. System aliases have no Linux
    equivalent and are ignored; the caller's own WAV files cover both events."""
    if not flags & SND_FILENAME:
        return
    for player in ('paplay', 'pw-play', 'aplay', 'afplay'):
        path = shutil.which(player)
        if path:
            subprocess.Popen([path, *(['-q'] if player == 'aplay' else []), str(sound)],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    raise OSError('No sound player (paplay, pw-play, aplay or afplay) was found.')
