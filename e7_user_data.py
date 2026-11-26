"""Per-user settings and history, kept outside the install folder.

Releases before 0.2.8 kept ADBconfig.ini, ShopRefreshGUI.ini and
ShopRefreshHistory/ in the engine folder (`runtime` in the player ZIP), so every
update meant copying that folder by hand. They now live in a per-user folder:

* Windows: %LOCALAPPDATA%\\E7 Secret Shop Refresh
* Linux:   $XDG_DATA_HOME/e7-shop-refresh (default ~/.local/share/e7-shop-refresh)
* E7_DATA_DIR overrides both.

On first start the files are copied once from the old engine folder. The old
folder is never changed or deleted; a second, timestamped copy also goes to
<data>/legacy-backup/. A copy that fails leaves the GUI on the old folder for
that run, exactly as before, and the next start retries. Every step is safe to
repeat: nothing in the per-user folder is ever overwritten by the migration.

Diagnostics (session logs, mouse-failures, previews, setup captures) and
prepared navigation references stay beside the engine for now.
"""
from dataclasses import dataclass, field
import datetime
import filecmp
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import uuid

APP_FOLDER_WINDOWS = 'E7 Secret Shop Refresh'
APP_FOLDER_POSIX = 'e7-shop-refresh'
ENVIRONMENT_VARIABLE = 'E7_DATA_DIR'
# The user data that used to sit in the engine folder.
MIGRATED_ITEMS = ('ADBconfig.ini', 'ShopRefreshGUI.ini', 'ShopRefreshHistory')
MARKER = 'migrated-from-runtime.json'
BACKUP_FOLDER = 'legacy-backup'


class MigrationError(OSError):
    pass


@dataclass
class DataLocation:
    """Where settings and history live for this run, and what happened to get there."""
    directory: Path
    events: list = field(default_factory=list)
    migrated: bool = False
    fallback: bool = False


def default_data_directory(environ=None, os_name=None, home=None):
    environ = os.environ if environ is None else environ
    os_name = os.name if os_name is None else os_name
    selected = (environ.get(ENVIRONMENT_VARIABLE) or '').strip()
    if selected:
        return Path(os.path.expandvars(selected)).expanduser()
    home = Path.home() if home is None else Path(home)
    if os_name == 'nt':
        base = (environ.get('LOCALAPPDATA') or '').strip()
        return (Path(base) if base else home / 'AppData' / 'Local') / APP_FOLDER_WINDOWS
    base = (environ.get('XDG_DATA_HOME') or '').strip()
    # XDG says a relative XDG_DATA_HOME is invalid and must be ignored.
    base = Path(base) if base and PurePosixPath(base).is_absolute() else home / '.local' / 'share'
    return base / APP_FOLDER_POSIX


def legacy_items(folder):
    folder = Path(folder)
    return [name for name in MIGRATED_ITEMS if (folder / name).exists()]


def _same_folder(first, second):
    try:
        return Path(first).resolve() == Path(second).resolve()
    except OSError:
        return False


def _copy(source, target):
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)


def _verify(source, target):
    """Byte-compare a copied file or tree; raise if anything differs or is missing."""
    if source.is_dir():
        if not target.is_dir():
            raise MigrationError(f'{target} was not created')
        for path in source.rglob('*'):
            if path.is_file():
                _verify(path, target / path.relative_to(source))
        return
    if not target.is_file() or not filecmp.cmp(source, target, shallow=False):
        raise MigrationError(f'{target} does not match {source}')


def _writable(folder):
    probe = folder / f'.write-test-{uuid.uuid4().hex}'
    try:
        probe.write_bytes(b'')
        probe.unlink()
        return True
    except OSError:
        return False


def _migrate(legacy, data, items, now):
    """Copy items into data without overwriting; returns (copied, kept)."""
    stamp = now.strftime('%Y%m%d-%H%M%S')
    staging = data / f'.migrating-{uuid.uuid4().hex}'
    backup = data / BACKUP_FOLDER / f'runtime-{stamp}-{uuid.uuid4().hex[:6]}'
    copied, kept = [], []
    try:
        staging.mkdir()
        backup.mkdir(parents=True)
        for name in items:
            source = legacy / name
            # The backup is a full second copy, made and checked before anything is placed.
            _copy(source, backup / name)
            _verify(source, backup / name)
            if (data / name).exists():
                kept.append(name)
                continue
            _copy(source, staging / name)
            _verify(source, staging / name)
        for name in items:
            if name in kept:
                continue
            target = data / name
            if target.exists():  # another GUI instance finished first
                kept.append(name)
                continue
            os.rename(staging / name, target)  # never replaces an existing file
            copied.append(name)
        (data / MARKER).write_text(json.dumps(dict(
            source=str(legacy), migrated_at=now.isoformat(timespec='seconds'),
            copied=copied, kept_existing=kept, backup=str(backup)), indent=2), encoding='utf-8')
    except OSError as error:
        raise MigrationError(f'Copy from {legacy} failed: {error}') from error
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return copied, kept, backup


def prepare_data_directory(legacy_folder, data_folder=None, *, environ=None, now=None):
    """Choose this run's settings/history folder, migrating once from the old engine folder.

    Never raises for file-system problems: on any failure the old engine folder
    is used, as in earlier releases, and the reason is in `events`.
    """
    legacy = Path(legacy_folder)
    data = Path(data_folder) if data_folder is not None else default_data_directory(environ)
    now = now or datetime.datetime.now()
    location = DataLocation(data)
    if _same_folder(legacy, data):
        return location
    items = legacy_items(legacy)

    def fall_back(reason):
        location.directory, location.fallback = legacy, True
        location.events.append(f'{reason} Settings and history stay in {legacy} for this run; nothing was deleted.')
        return location

    try:
        data.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return fall_back(f'Could not create the settings folder {data}: {error}.')
    marker = data / MARKER
    if marker.exists():
        return location  # migrated on an earlier start; the old folder is left alone
    if not _writable(data):
        if legacy_items(data):
            location.events.append(f'Warning: the settings folder {data} is read-only; changes cannot be saved.')
            return location
        return fall_back(f'The settings folder {data} is read-only.')
    if not items:
        return location  # fresh install
    try:
        copied, kept, backup = _migrate(legacy, data, items, now)
    except MigrationError as error:
        return fall_back(f'Settings migration failed: {error}.')
    location.migrated = True
    if copied:
        location.events.append(f'Settings and history moved to {data} ({", ".join(copied)}).')
    if kept:
        location.events.append(f'Kept the existing {", ".join(kept)} already in {data}; the old copy was not used.')
    location.events.append(f'The old copies stay in {legacy}; a backup is in {backup}.')
    return location
