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
    fresh: bool = False  # a new, empty per-user folder: offer to import from an older version


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


def _stage(legacy, staging, items, now, replaced=None, **details):
    """Copy items and a backup into staging, check every byte, then write the marker.

    `replaced` is a current settings folder whose contents are kept, checked,
    under legacy-backup/replaced-<stamp>/ before it is swapped out.
    """
    stamp = now.strftime('%Y%m%d-%H%M%S')
    backup_name = f'runtime-{stamp}'
    staging.mkdir()
    for name in items:
        source = legacy / name
        for target in (staging / name, staging / BACKUP_FOLDER / backup_name / name):
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy(source, target)
            _verify(source, target)
    if replaced is not None:
        for name in _user_files(replaced):
            target = staging / BACKUP_FOLDER / f'replaced-{stamp}' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy(replaced / name, target)
            _verify(replaced / name, target)
    (staging / MARKER).write_text(json.dumps(dict(
        source=str(legacy), migrated_at=now.isoformat(timespec='seconds'), copied=list(items),
        backup=f'{BACKUP_FOLDER}/{backup_name}', **details), indent=2), encoding='utf-8')
    return backup_name


def _user_files(folder):
    """Names in a settings folder other than the bookkeeping marker (empty if it does not exist)."""
    try:
        return sorted(path.name for path in Path(folder).iterdir()
                      if path.name != MARKER and not path.name.startswith('.write-test-'))
    except FileNotFoundError:
        return []


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
        location.fresh = True  # nothing here yet and nothing in the engine folder to move
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


# --- Importing from an older version --------------------------------------
#
# A fresh extract has nothing in its own `runtime` to move, but the player
# usually still has the previous version's folder next to it, on the Desktop
# or in Downloads. The GUI offers to copy settings and history from there.
# Everything below is plain functions; the dialog in the GUI only shows the
# result and passes the player's choice back.

INSTALL_MARKER = 'ShopRefreshGUI.ini'  # an older install is recognised by its GUI settings
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
SEARCH_LIMIT = 3000  # folders looked at per search root; keeps a start fast on cluttered folders


class ImportRefused(Exception):
    """An import that was not attempted; the message says why, for the player."""


@dataclass(frozen=True)
class OlderInstall:
    folder: Path      # the folder the player knows (the release folder)
    runtime: Path     # where its settings and history are
    items: tuple
    last_used: float  # newest modification time of its settings or history

    @property
    def name(self):
        return self.folder.name

    @property
    def location(self):
        return self.folder.parent


def _last_used(runtime, items):
    paths = [runtime / name for name in items] + [runtime / 'ShopRefreshHistory' / 'ADB_History.csv']
    times = []
    for path in paths:
        try:
            times.append(path.stat().st_mtime)
        except OSError:
            pass
    return max(times, default=0.0)


def describe_install(folder, *, require_gui_settings=True):
    """The older install in `folder` (a release folder or its runtime folder), or None."""
    folder = Path(folder)
    places = [(folder / 'runtime', folder)]
    if not require_gui_settings:  # a folder the player chose: accept the runtime folder itself too
        places.append((folder, folder.parent if folder.name.lower() == 'runtime' else folder))
    for runtime, release in places:
        try:
            items = tuple(legacy_items(runtime))
        except OSError:
            continue
        if INSTALL_MARKER in items or (items and not require_gui_settings):
            return OlderInstall(release, runtime, items, _last_used(runtime, items))
    return None


def _is_link(entry):
    """Symlinks, junctions and other reparse points are never followed."""
    try:
        if entry.is_symlink():
            return True
        isjunction = getattr(os.path, 'isjunction', None)
        if isjunction is not None and isjunction(entry.path):
            return True
        return bool(getattr(entry.stat(follow_symlinks=False), 'st_file_attributes', 0) & FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return True


def _resolved(path):
    try:
        return Path(path).resolve()
    except OSError:
        return Path(path).absolute()


def find_older_installs(roots, exclude=()):
    """Older installs under `roots`, most recently used first.

    `roots` is a list of (folder, depth): depth 1 looks at the folder's
    children, depth 2 at their children too. Links are not followed and
    unreadable folders are skipped quietly. `exclude` lists runtime folders
    that are not older installs (this app's own, the settings folder).
    """
    excluded = {_resolved(path) for path in exclude}
    found = {}
    for root, depth in roots:
        level, looked_at = [Path(root)], 0
        for _ in range(depth):
            deeper = []
            for folder in level:
                try:
                    with os.scandir(folder) as entries:
                        children = [entry for entry in entries if entry.is_dir(follow_symlinks=False)]
                except OSError:
                    continue
                for entry in children:
                    looked_at += 1
                    if looked_at > SEARCH_LIMIT:
                        break
                    if _is_link(entry):
                        continue
                    install = describe_install(entry.path)
                    if install is None:
                        deeper.append(Path(entry.path))
                        continue
                    key = _resolved(install.runtime)
                    if key not in excluded:
                        found.setdefault(key, install)
            level = deeper
    return sorted(found.values(), key=lambda install: install.last_used, reverse=True)


def _known_folder(name):
    """Desktop or Downloads as Windows reports it (they can be moved, e.g. to OneDrive)."""
    import ctypes
    from ctypes import wintypes
    ids = {'Desktop': '{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}', 'Downloads': '{374DE290-123F-4565-9164-39C4925E467B}'}

    class GUID(ctypes.Structure):
        _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD),
                    ('Data4', ctypes.c_ubyte * 8)]
    guid = GUID()
    ctypes.oledll.ole32.CLSIDFromString(ids[name], ctypes.byref(guid))
    path = ctypes.c_wchar_p()
    ctypes.oledll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path))
    try:
        return Path(path.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(path)


def default_search_roots(app_folder, *, os_name=None, home=None, known_folder=None):
    """Where an older version usually is: beside this one, on the Desktop, in Downloads."""
    os_name = os.name if os_name is None else os_name
    roots = [(Path(app_folder).parent, 1)]
    for name in ('Desktop', 'Downloads'):
        folder = None
        if os_name == 'nt':
            try:
                folder = (known_folder or _known_folder)(name)
            except (OSError, AttributeError, ValueError):
                folder = None
        if folder is None:
            try:
                folder = (Path.home() if home is None else Path(home)) / name
            except (RuntimeError, OSError):
                continue
        roots.append((Path(folder), 2))
    unique, seen = [], set()
    for folder, depth in roots:
        key = _resolved(folder)
        if key not in seen:
            seen.add(key)
            unique.append((folder, depth))
    return unique


def needs_import_choice(location):
    """Ask about older settings only for a new, empty per-user folder with no choice recorded yet."""
    folder = Path(location.directory)
    try:
        return (location.fresh and not location.fallback and not (folder / MARKER).exists()
                and not _user_files(folder))
    except OSError:
        return False


def record_fresh_start(data_folder, now=None):
    """Remember "Start fresh" so the question is not asked on every start."""
    now = now or datetime.datetime.now()
    (Path(data_folder) / MARKER).write_text(json.dumps(dict(
        source=None, migrated_at=now.isoformat(timespec='seconds'), copied=[],
        skipped='started fresh; no older settings imported'), indent=2), encoding='utf-8')


def has_user_data(data_folder):
    """True when the settings folder already holds settings or history (not just bookkeeping)."""
    return bool(_user_files(data_folder))


def import_older_install(source_runtime, data_folder, *, replace=False, now=None):
    """Copy settings and history from an older install into the per-user folder.

    The same all-or-nothing copy as the first-start move: everything is copied
    and byte-checked in a staging folder, which then becomes the settings
    folder by rename. The older install is only read. A settings folder that
    already holds settings is refused unless `replace` is set; its contents
    are then kept, checked, under legacy-backup/replaced-<stamp>/.
    Returns Activity-log lines; raises ImportRefused or OSError.
    """
    source, data = Path(source_runtime), Path(data_folder).absolute()
    now = now or datetime.datetime.now()
    items = legacy_items(source)
    if not items:
        raise ImportRefused(f'No settings or history were found in {source}.')
    if _same_folder(source, data):
        raise ImportRefused(f'{source} is already the settings folder.')
    current = _user_files(data)
    if current and not replace:
        raise ImportRefused(f'The settings folder {data} already holds settings; nothing was imported.')
    staging = data.parent / f'.{data.name}.migrating-{uuid.uuid4().hex}'
    aside = data.parent / f'.{data.name}.replaced-{uuid.uuid4().hex}'
    try:
        data.parent.mkdir(parents=True, exist_ok=True)
        backup_name = _stage(source, staging, items, now, replaced=data if current else None, imported=True)
        if data.exists():
            os.rename(data, aside)  # holds only what the backup above already has
            if _user_files(aside) != current:  # something was saved meanwhile: keep it, import nothing
                os.rename(aside, data)
                raise ImportRefused(f'The settings folder {data} changed during the import; nothing was imported.')
            try:
                os.rename(staging, data)
            except OSError:
                os.rename(aside, data)
                raise
            _remove_tree(aside)
        else:
            os.rename(staging, data)
    except BaseException:
        _remove_tree(staging)
        raise
    stamp = now.strftime('%Y%m%d-%H%M%S')
    events = [f'Imported settings and history from {source} into {data} ({", ".join(items)}).',
              f'{source} was not changed; a backup of what was imported is in {data / BACKUP_FOLDER / backup_name}.']
    if current:
        events.append(f'The settings that were replaced are in {data / BACKUP_FOLDER / ("replaced-" + stamp)}.')
    return events
