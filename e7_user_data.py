"""Per-user settings and history, kept outside the install folder.

Releases before 0.2.8 kept ADBconfig.ini, ShopRefreshGUI.ini and
ShopRefreshHistory/ in the engine folder (`runtime` in the player ZIP), so every
update meant copying that folder by hand. They now live in a per-user folder:

* Windows: %LOCALAPPDATA%\\E7 Secret Shop Refresh
* Linux:   $XDG_DATA_HOME/e7-shop-refresh (default ~/.local/share/e7-shop-refresh)
* E7_DATA_DIR overrides both.

On first start the files are copied once from the old engine folder. The old
folder is never changed or deleted; a second copy also goes to
<data>/legacy-backup/. The move is all or nothing: everything is copied and
checked in a staging folder beside the new one, which then becomes the new
folder in one rename. Until that rename the new folder does not exist, so a
failure (or a crash) leaves the GUI on the old folder for that run, exactly as
before, and the next start retries. A per-user folder that already holds files
is never overwritten or merged into.

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
import stat
import sys
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
    selected = os.path.expandvars((environ.get(ENVIRONMENT_VARIABLE) or '').strip()).strip()
    if selected:
        # Absolute, so the engine (started in the engine folder) uses the same place.
        return Path(selected).expanduser().absolute()

    def user_home():
        return Path.home() if home is None else Path(home)
    if os_name == 'nt':
        base = (environ.get('LOCALAPPDATA') or '').strip()
        return (Path(base) if base else user_home() / 'AppData' / 'Local') / APP_FOLDER_WINDOWS
    base = (environ.get('XDG_DATA_HOME') or '').strip()
    # XDG says a relative XDG_DATA_HOME is invalid and must be ignored.
    base = Path(base) if base and PurePosixPath(base).is_absolute() else user_home() / '.local' / 'share'
    return base / APP_FOLDER_POSIX


def _remove_tree(folder):
    """Remove a staging folder, including copies that kept a read-only attribute."""
    def make_writable(function, path, _error):
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            function(path)
        except OSError:
            pass
    if folder.exists():
        if sys.version_info >= (3, 12):
            shutil.rmtree(folder, onexc=make_writable)
        else:
            shutil.rmtree(folder, onerror=make_writable)


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


def _stage(legacy, staging, items, now):
    """Copy items and a backup into staging, check every byte, then write the marker."""
    stamp = now.strftime('%Y%m%d-%H%M%S')
    backup_name = f'runtime-{stamp}'
    staging.mkdir()
    for name in items:
        source = legacy / name
        for target in (staging / name, staging / BACKUP_FOLDER / backup_name / name):
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy(source, target)
            _verify(source, target)
    (staging / MARKER).write_text(json.dumps(dict(
        source=str(legacy), migrated_at=now.isoformat(timespec='seconds'), copied=list(items),
        backup=f'{BACKUP_FOLDER}/{backup_name}'), indent=2), encoding='utf-8')
    return backup_name


def _is_empty_folder(folder):
    try:
        return folder.is_dir() and not any(folder.iterdir())
    except OSError:
        return False


def prepare_data_directory(legacy_folder, data_folder=None, *, environ=None, now=None):
    """Choose this run's settings/history folder, migrating once from the old engine folder.

    Never raises for file-system problems: on any failure the old engine folder
    is used, as in earlier releases, and the reason is in `events`.
    """
    legacy = Path(legacy_folder)
    try:
        data = Path(data_folder) if data_folder is not None else default_data_directory(environ)
    except (RuntimeError, OSError) as error:  # no home folder at all
        return DataLocation(legacy, [f'No per-user settings folder is available ({error}); '
                                     f'settings and history stay in {legacy}.'], fallback=True)
    data = data.absolute()
    now = now or datetime.datetime.now()
    location = DataLocation(data)
    if _same_folder(legacy, data):
        return location

    def fall_back(reason):
        location.directory, location.fallback = legacy, True
        location.events.append(f'{reason} Settings and history stay in {legacy} for this run; nothing was deleted.')
        return location

    def use_existing():
        if not _writable(data):
            location.events.append(f'Warning: the settings folder {data} is read-only; changes cannot be saved.')
        return location

    items = legacy_items(legacy)
    if (data / MARKER).exists():
        return use_existing()  # migrated on an earlier start; the old folder is left alone
    if data.exists() and not _is_empty_folder(data):
        if not data.is_dir():
            return fall_back(f'The settings folder {data} is not a folder.')
        if items:
            # Never merge into or overwrite a folder that is already in use.
            location.events.append(f'Settings folder {data} is already in use, so the old settings in {legacy} '
                                   'were not imported; they are left unchanged there.')
            try:  # say it once, not on every start
                (data / MARKER).write_text(json.dumps(dict(
                    source=str(legacy), migrated_at=now.isoformat(timespec='seconds'), copied=[],
                    skipped='settings folder already in use'), indent=2), encoding='utf-8')
            except OSError:
                pass
        return use_existing()
    if not items:  # fresh install
        try:
            data.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            return fall_back(f'Could not create the settings folder {data}: {error}.')
        if not _writable(data):
            return fall_back(f'The settings folder {data} is read-only.')
        return location
    staging = data.parent / f'.{data.name}.migrating-{uuid.uuid4().hex}'
    try:
        data.parent.mkdir(parents=True, exist_ok=True)
        backup_name = _stage(legacy, staging, items, now)
        if _is_empty_folder(data):
            data.rmdir()  # an empty folder left by an earlier fresh start
        os.rename(staging, data)  # one step; fails if another start created the folder first
    except OSError as error:
        _remove_tree(staging)
        if (data / MARKER).exists():
            return use_existing()  # another GUI instance finished the same move first
        return fall_back(f'Settings migration to {data} failed: {error}.')
    location.migrated = True
    location.events.append(f'Settings and history moved to {data} ({", ".join(items)}).')
    location.events.append(f'The old copies stay in {legacy}; a backup is in {data / BACKUP_FOLDER / backup_name}.')
    return location
