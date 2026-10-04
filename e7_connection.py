"""Bounded ADB connection checks. No screenshots, input, or server shutdowns."""
from dataclasses import dataclass
import subprocess

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


@dataclass(frozen=True)
class ConnectionCheck:
    devices: tuple[str, ...]
    warning: str
    diagnostics: str
    ready: bool = False


def check_connection(adb, runtime, target=None, *, runner=None):
    runner = runner or subprocess.run
    output = []

    def run(*args):
        result = runner([str(adb), *args], cwd=runtime, capture_output=True,
                        text=True, errors='replace', timeout=5, creationflags=NO_WINDOW)
        output.append(result.stdout + result.stderr)
        return result

    def devices(result):
        return tuple(dict.fromkeys(parts[0] for line in result.stdout.splitlines()
                                  if len(parts := line.split()) >= 2 and parts[1] == 'device'))

    try:
        result = run('devices')
        if result.returncode:
            return ConnectionCheck((), 'ADB check failed. Open your emulator with ADB enabled, then retry.', ''.join(output))
        connected = devices(result)
        # Only an explicit Start attempts the selected network endpoint. Scans
        # never connect, choose other devices, or kill an existing ADB server.
        if target and target not in connected and ':' in target and not target.startswith('-'):
            run('connect', target)
            result = run('devices')
            connected = devices(result) if result.returncode == 0 else ()
        ready = bool(target and target in connected)
        if target and not ready:
            warning = 'Selected emulator is not connected. Open it, enable/authorize ADB, then press Start again.'
        elif not connected:
            warning = 'No connected emulator detected. Open your emulator with ADB enabled, then press Start.'
        else:
            warning = ''
        return ConnectionCheck(connected, warning, ''.join(output), ready)
    except (OSError, subprocess.SubprocessError):
        return ConnectionCheck((), 'Could not reach ADB. Open your emulator, enable/authorize ADB, then retry.', ''.join(output))
