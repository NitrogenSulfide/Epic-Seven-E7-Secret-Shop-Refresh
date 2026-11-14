"""A short, paste-ready problem report (Reddit or GitHub) built from the
current session. Read-only: it sends nothing and changes no files.

The report holds what a helper needs without a second question: app version,
system, mode, game window setup, the stop reason, the newest failure record of
this session and the last log lines. Paths are shortened and the user name is
replaced, so a public paste does not reveal the Windows account name.
"""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import platform
import re

LOG_LINES = 60
# Reddit cuts comments at 10,000 characters; leave room for the player's words.
MAX_CHARS = 8000
FAILURE_FOLDER = 'mouse-failures'


def system_name():
    if os.name == 'nt':
        version = platform.version()  # e.g. 10.0.26100
        build = int(version.rsplit('.', 1)[-1]) if version.rsplit('.', 1)[-1].isdigit() else 0
        return f'Windows {"11" if build >= 22000 else "10"} ({version})'
    return f'{platform.system()} {platform.release()}'.strip()


def anonymize(text, *, home=None, user=None):
    home = str(Path.home()) if home is None else home
    if user is None:
        try:
            user = getpass.getuser()
        except Exception:
            user = ''
    if home and len(home) > 3:
        text = text.replace(home, '~').replace(home.replace('\\', '/'), '~')
    if user and len(user) >= 3:
        text = re.sub(re.escape(user), '<user>', text, flags=re.IGNORECASE)
    return text


def latest_failure(app_dir, since):
    """The newest failure record written at or after `since` (epoch seconds)."""
    root = Path(app_dir)/FAILURE_FOLDER
    try:
        folders = [p for p in root.iterdir() if p.is_dir() and p.stat().st_mtime >= since]
    except OSError:
        return None
    return max(folders, key=lambda p: p.stat().st_mtime) if folders else None


def game_window_line(log):
    found = None
    for line in log.splitlines():
        if line.startswith('Game window: '):
            found = line.removeprefix('Game window: ').strip()
    return found


def build_report(*, version, mode, target, state, reason, log, app_dir, since,
                 system=None, home=None, user=None, lines=LOG_LINES, max_chars=MAX_CHARS):
    """Markdown that reads well on Reddit (old and new) and GitHub. The log is
    indented four spaces, which both render as a code block."""
    head = [f'**E7 Secret Shop Refresh v{version} report**', '',
            f'- System: {system or system_name()}',
            f'- Mode: {mode}' + (f' · {target}' if target else '')]
    window = game_window_line(log)
    if window:
        head.append(f'- Game window: {window}')
    head.append(f'- Result: {state}' + (f' · {reason}' if reason else ''))
    failure = latest_failure(app_dir, since) if since is not None else None
    if failure is not None:
        record = ''
        try:
            record = json.dumps(json.loads((failure/'failure.json').read_text(encoding='utf-8')))
        except (OSError, ValueError):
            pass
        pictures = ', '.join(sorted(p.name for p in failure.glob('*.png')))
        head.append(f'- Failure record: {FAILURE_FOLDER}/{failure.name}' + (f' {record}' if record else ''))
        if pictures:
            head.append(f'- Pictures to attach from that folder: {pictures}')
    head.append('')
    tail = [line for line in log.splitlines() if line.strip()][-lines:]
    def render(tail):
        body = ([f'Last {len(tail)} log lines:', ''] + ['    '+line for line in tail]) if tail else ['No log lines yet.']
        return anonymize('\n'.join(head + body) + '\n', home=home, user=user)
    report = render(tail)
    while len(report) > max_chars and tail:
        tail = tail[max(1, len(tail)//10):]
        report = render(tail)
    return report
