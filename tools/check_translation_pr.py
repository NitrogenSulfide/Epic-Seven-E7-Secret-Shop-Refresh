#!/usr/bin/env python3
"""Check outside pull requests for the translation work (and touched files in general).

Reads everything from git revisions, never from the working tree, and never runs
the PR's code (it parses and compiles it, which executes nothing). Fetch a PR first:

    git fetch origin pull/12/head:pr-12

Then:

    python tools/check_translation_pr.py files BASE HEAD
        Lists every file the range touches and flags ones a normal PR has no
        reason to change (build scripts, binaries, assets, CI, licence...).

    python tools/check_translation_pr.py extraction BASE HEAD
        For the "move English text out of the code" commit. Replaces every
        t('key', name=value) call with the English text from locales/en.json,
        rebuilt as the string or f-string it stands for, then compares the code
        with BASE. Anything left over is not a pure text move and fails the run.
        Also fails on files outside the GUI, unexpected file types, renames,
        deletions, unknown keys, encoding tricks, and English text the app
        matches on by wording.

    python tools/check_translation_pr.py locale HEAD [locales/pt_BR.json]
        Checks a translation file against locales/en.json at the same revision.

Exit code 1 if anything is a PROBLEM, else 0. READ items are not failures; they
are the parts a person still has to look at (new helper code, tests, docs).

This is a filter, not a proof: it cannot see that translated text is compared
through a variable, for example. Still read the diff; this tells you where.
"""
import argparse
import ast
import difflib
import fnmatch
import io
import json
import re
import string
import subprocess
import sys
import tokenize

# Modules only the GUI imports (checked against origin/main 0.2.7, plus the
# older-version import dialog from 90d4538). The engine never loads these, so
# moving their text into t() cannot change engine output.
GUI_FILES = {
    'e7_shop_refresh_gui.py', 'e7_about.py', 'e7_appearance.py', 'e7_connection.py',
    'e7_setup.py', 'e7_tracker.py', 'e7_report.py', 'e7_session_estimate.py',
    'e7_elevation.py', 'e7_links.py', 'e7_process.py', 'e7_window_preview.py',
    'e7_import_dialog.py',
}
NEW_CODE_FILES = {'e7_i18n.py'}
LOCALE_DIR = 'locales/'
ENGLISH = 'locales/en.json'
TRANSLATE_FUNC = 't'
I18N_MODULE = 'e7_i18n'
CONVERSIONS = {None, 's', 'r', 'a'}

# Paths a Gold-cap or translation PR has no reason to touch (matched lower-case).
SENSITIVE = [
    '.github/*', '*.ps1', '*.sh', '*.cmd', '*.bat', '*.cs', '*.exe', '*.dll', '*.ico',
    '*.png', '*.gif', '*.jpg', '*.wav', '*.spec', '*.pth', '*.pyw', '*.vbs', '*.toml',
    '*.cfg', '*.ini', 'adb-assets/*', 'assets/*', 'e7_gui_assets/*', 'release/*',
    '*requirements*.txt', '*.gitignore', '*.gitattributes', '.gitmodules', 'version',
    'license', 'upstream.md', 'build_*', 'tools/*', '.review-*', 'makefile',
]

# English text the GUI recognises by its wording. If one of these ends up in
# en.json, translating it breaks colouring, state checks or engine parsing.
MATCHED_TEXT = [
    'E7GUI_', 'Progress:', 'Shop refresh terminated!', '---Result---', 'Navigation: ',
    'Waiting for visible game controls.', 'Covenant purchases:', 'Mystic purchases:',
    'Friendship purchases:', 'Not saved yet', 'to stop debug',
    'check image - find it in taskbar',
]
# The Activity log picks a colour by searching for these words (e7_shop_refresh_gui._event).
COLOUR_WORDS = re.compile(r'failed|error|exception|traceback|not recognized|could not|'
                          r'cannot|stop|pause|waiting|cancel|needs help', re.I)
# The release script copies an explicit file list into the package, so the
# translation PR has to add e7_i18n.py and the locale files to it. That one kind
# of change is allowed: new entries inside the $mapping block, nothing removed.
PACKAGING_SCRIPT = 'build_release.ps1'
PACKAGING_ENTRY = re.compile(r"^ {4}'(e7_i18n\.py|locales/[A-Za-z_]+\.json)' = '(?P<member>[^']*)'$")
MAPPING_START = '$mapping = [ordered]@{'
PLAIN_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


class Report:
    def __init__(self):
        self.problems, self.reads, self.notes = [], [], []

    def problem(self, text): self.problems.append(text)
    def read(self, text): self.reads.append(text)
    def note(self, text): self.notes.append(text)

    def print(self):
        for title, items in (('PROBLEM', self.problems), ('READ', self.reads), ('OK', self.notes)):
            for item in items:
                print(f'{title}: {item}')
        print(f'\n{len(self.problems)} problem(s), {len(self.reads)} item(s) to read by hand.')
        return 1 if self.problems else 0


def git(repo, *args):
    done = subprocess.run(['git', '-c', 'core.quotepath=false', '-C', repo, *args], capture_output=True)
    if done.returncode:
        raise SystemExit(f'git {" ".join(args)} failed: {done.stderr.decode(errors="replace").strip()}')
    return done.stdout


def show_bytes(repo, rev, path):
    done = subprocess.run(['git', '-C', repo, 'show', f'{rev}:{path}'], capture_output=True)
    return done.stdout if done.returncode == 0 else None


def show_text(repo, rev, path, report):
    data = show_bytes(repo, rev, path)
    if data is None:
        return None
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        report.problem(f'{rev}:{path} is not UTF-8 ({error}).')
        return None


def changed_files(repo, base, head):
    """[(status, path, is_binary)] for base..head. Renames show as delete + add."""
    binary = set()
    fields = git(repo, 'diff', '-z', '--no-renames', '--numstat', base, head).split(b'\0')
    for entry in fields:
        if entry:
            added, _removed, path = entry.decode('utf-8', 'replace').split('\t', 2)
            if added == '-':
                binary.add(path)
    fields = git(repo, 'diff', '-z', '--no-renames', '--name-status', base, head).split(b'\0')
    out = []
    for status, path in zip(fields[0::2], fields[1::2]):
        if status:
            path = path.decode('utf-8', 'replace')
            out.append((status.decode()[0], path, path in binary))
    return out


def sensitive(path):
    lower = path.lower()
    return any(fnmatch.fnmatchcase(lower, pattern) for pattern in SENSITIVE)


def packaging_entries_only(repo, base, head):
    """True if base..head only adds e7_i18n.py / locales/*.json entries to the
    release script's $mapping block, each copied under its own name."""
    old, new = show_bytes(repo, base, PACKAGING_SCRIPT), show_bytes(repo, head, PACKAGING_SCRIPT)
    if old is None or new is None:
        return False
    try:
        old_lines = old.decode('utf-8').splitlines()
        new_lines = new.decode('utf-8').splitlines()
    except UnicodeDecodeError:
        return False
    if MAPPING_START not in old_lines or new_lines.count(MAPPING_START) != 1:
        return False
    start = new_lines.index(MAPPING_START)
    end = next((i for i in range(start + 1, len(new_lines)) if new_lines[i] == '}'), None)
    if end is None:
        return False
    added = 0
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
        if tag != 'insert':
            return False
        for j in range(j1, j2):
            match = PACKAGING_ENTRY.match(new_lines[j])
            if not (start < j < end and match and match.group('member') == match.group(1)):
                return False
            added += 1
    return added > 0


def check_files(repo, base, head, report):
    files = changed_files(repo, base, head)
    if not files:
        report.problem(f'{base}..{head} changes no files; check the revisions.')
    for status, path, binary in files:
        label = {'A': 'added', 'D': 'deleted', 'M': 'changed'}.get(status, f'status {status}')
        if binary:
            report.problem(f'{path}: binary file {label}. Ask why before going further.')
        elif path == PACKAGING_SCRIPT and status == 'M' and packaging_entries_only(repo, base, head):
            report.read(f'{path}: {label}, only adding e7_i18n.py / locales/*.json to the package '
                        'file list. Read the hunk.')
        elif sensitive(path):
            report.problem(f'{path}: {label}. Build, asset, CI, config or licence file; '
                           'a normal PR should not touch it.')
        elif any(ord(c) > 127 or c in '"\\' for c in path):
            report.problem(f'{path}: {label}. Unusual characters in the file name.')
        else:
            report.note(f'{path}: {label}')
    return files


def load_locale(text, where, report):
    """Parse a locale file, rejecting duplicate keys and non-string values."""
    duplicates = []

    def pairs(items):
        seen = {}
        for key, value in items:
            if key in seen:
                duplicates.append(key)
            seen[key] = value
        return seen

    try:
        data = json.loads(text, object_pairs_hook=pairs)
    except (ValueError, RecursionError) as error:
        report.problem(f'{where}: not valid JSON ({type(error).__name__}: {error}).')
        return None
    if not isinstance(data, dict):
        report.problem(f'{where}: must be one JSON object of "key": "text".')
        return None
    for key in duplicates:
        report.problem(f'{where}: key {key!r} appears twice; the later one wins silently.')
    for key, value in data.items():
        if not isinstance(value, str):
            report.problem(f'{where}: {key!r} is not a string.')
    return {k: v for k, v in data.items() if isinstance(v, str)}


def check_placeholders(key, template, where, report):
    """[(name, conversion, spec)] for each placeholder, or None if broken."""
    try:
        parts = list(string.Formatter().parse(template))
    except ValueError as error:
        report.problem(f'{where}: {key!r} has broken braces ({error}). Use {{{{ and }}}} for literal braces.')
        return None
    found, ok = [], True
    for _literal, name, spec, conversion in parts:
        if name is None:
            continue
        if not PLAIN_NAME.match(name):
            report.problem(f'{where}: {key!r} placeholder {{{name}}} is not a plain name; '
                           'attribute or index access is not allowed.')
            ok = False
        if conversion not in CONVERSIONS:
            report.problem(f'{where}: {key!r} placeholder {{{name}!{conversion}}} has an invalid conversion.')
            ok = False
        if spec and '{' in spec:
            report.problem(f'{where}: {key!r} placeholder {{{name}}} has a nested placeholder in its format.')
            ok = False
        found.append((name, conversion, spec or ''))
    return found if ok else None


def coding_cookie(source_bytes):
    """The PEP 263 encoding line, if any. Its presence can change how Python reads the file."""
    try:
        encoding, _lines = tokenize.detect_encoding(io.BytesIO(source_bytes).readline)
    except SyntaxError as error:
        return f'invalid ({error})'
    first_two = b'\n'.join(source_bytes.splitlines()[:2])
    return encoding if re.search(rb'coding[:=]', first_two) else None


def plain_constants(tree):
    """f-strings with no placeholders become plain strings, on both sides."""
    class Flatten(ast.NodeTransformer):
        def visit_FormattedValue(self, node):
            node.value = self.visit(node.value)  # leave format_spec as a JoinedStr
            return node

        def visit_JoinedStr(self, node):
            self.generic_visit(node)
            if all(isinstance(v, ast.Constant) for v in node.values):
                return ast.copy_location(ast.Constant(''.join(v.value for v in node.values)), node)
            return node
    return Flatten().visit(tree)


def is_t_call(node):
    """t('key') or e7_i18n.t('key'); not some_object.t(), which could be anything."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == TRANSLATE_FUNC
    return (isinstance(func, ast.Attribute) and func.attr == TRANSLATE_FUNC
            and isinstance(func.value, ast.Name) and func.value.id == I18N_MODULE)


def binds_name(tree, name):
    """Lines where `name` is assigned, a parameter, an import alias, a loop/with/except target."""
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, (ast.Store, ast.Del)):
            lines.append(node.lineno)
        elif isinstance(node, ast.arg) and node.arg == name:
            lines.append(node.lineno)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            lines.append(node.lineno)
        elif isinstance(node, ast.ExceptHandler) and node.name == name:
            lines.append(node.lineno)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if (alias.asname or alias.name.split('.')[0]) == name:
                    lines.append(node.lineno)
        elif isinstance(node, (ast.Global, ast.Nonlocal)) and name in node.names:
            lines.append(node.lineno)
    return lines


def check_import(new_tree, path, report):
    """t() needs exactly `from e7_i18n import t` at module level, and nothing else may bind t."""
    calls = [n for n in ast.walk(new_tree) if is_t_call(n)]
    if not calls:
        return
    top = [n for n in new_tree.body if isinstance(n, ast.ImportFrom) and n.module == I18N_MODULE
           and n.level == 0 and [(a.name, a.asname) for a in n.names] == [(TRANSLATE_FUNC, None)]]
    uses_module = any(isinstance(n.func, ast.Attribute) for n in calls)
    top_module = [n for n in new_tree.body if isinstance(n, ast.Import)
                  and [(a.name, a.asname) for a in n.names] == [(I18N_MODULE, None)]]
    if any(isinstance(n.func, ast.Name) for n in calls) and len(top) != 1:
        report.problem(f'{path}: uses t() but does not have exactly one module-level '
                       f'`from {I18N_MODULE} import {TRANSLATE_FUNC}`.')
    if uses_module and len(top_module) != 1:
        report.problem(f'{path}: uses {I18N_MODULE}.t() without one module-level `import {I18N_MODULE}`.')
    allowed = {n.lineno for n in top}
    other = [line for line in binds_name(new_tree, TRANSLATE_FUNC) if line not in allowed]
    if other:
        report.problem(f'{path}: the name {TRANSLATE_FUNC!r} is also bound on line(s) {other}, so some '
                       f'{TRANSLATE_FUNC}() calls may not be the translation helper.')


class Untranslate(ast.NodeTransformer):
    """Replace t('key', a=x) with the English string or f-string it stands for."""

    def __init__(self, english, path, report):
        self.english, self.path, self.report = english, path, report
        self.used, self.count = set(), 0

    def visit_ImportFrom(self, node):
        if (node.module == I18N_MODULE and node.level == 0
                and [(a.name, a.asname) for a in node.names] == [(TRANSLATE_FUNC, None)]):
            return None
        return node

    def visit_Import(self, node):
        if [(a.name, a.asname) for a in node.names] == [(I18N_MODULE, None)]:
            return None
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        if not is_t_call(node):
            return node
        where = f'{self.path}:{node.lineno}'
        if not node.args or not (isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            self.report.problem(f'{where}: t() key is not a literal string, so it cannot be checked.')
            return node
        key = node.args[0].value
        if key not in self.english:
            self.report.problem(f'{where}: key {key!r} is not in {ENGLISH}.')
            return node
        if len(node.args) > 1:
            self.report.problem(f'{where}: t({key!r}) passes positional values; use names like count=n.')
            return node
        values, order = {}, []
        for kw in node.keywords:
            if kw.arg is None:
                self.report.problem(f'{where}: t({key!r}) uses **mapping; pass each value by name.')
                return node
            values[kw.arg] = kw.value
            order.append(kw.arg)
        template = self.english[key]
        try:
            parts = list(string.Formatter().parse(template))
        except ValueError:
            return node  # reported by the en.json check
        names = [name for _l, name, _s, _c in parts if name is not None]
        if set(names) != set(values):
            self.report.problem(f'{where}: t({key!r}) passes {sorted(values)} but the English text '
                                f'uses {sorted(set(names))}.')
            return node
        if len(names) != len(set(names)):
            self.report.problem(f'{where}: {key!r} uses a placeholder twice; the original evaluated '
                                'that expression twice, t() evaluates it once.')
            return node
        if order != names:
            self.report.problem(f'{where}: t({key!r}) passes {order} in a different order from the '
                                f'English text {names}, which changes evaluation order.')
            return node
        if any(conversion not in CONVERSIONS for _l, name, _s, conversion in parts if name):
            return node  # reported by the en.json check
        self.used.add(key)
        self.count += 1
        pieces = []
        for literal, name, spec, conversion in parts:
            if literal:
                pieces.append(ast.Constant(literal))
            if name is not None:
                pieces.append(ast.FormattedValue(
                    value=values[name],
                    conversion=ord(conversion) if conversion else -1,
                    format_spec=ast.JoinedStr([ast.Constant(spec)]) if spec else None))
        if not names:
            new = ast.Constant(''.join(p.value for p in pieces))
        else:
            new = ast.JoinedStr(pieces)
        return ast.copy_location(new, node)


def contains_t(node):
    return any(is_t_call(n) for n in ast.walk(node))


def flag_risky_uses(tree, path, report):
    """Translated text used to decide something, or evaluated once at import time."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and contains_t(node):
            report.problem(f'{path}:{node.lineno}: translated text in a comparison (==, in, ...). '
                           'In Portuguese this check fails; use a state flag instead.')
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in ('startswith', 'endswith', 'find', 'index', 'count', 'removeprefix',
                                     'removesuffix', 'replace', 'split')
              and (contains_t(node.func.value) or any(contains_t(a) for a in node.args))):
            report.problem(f'{path}:{node.lineno}: translated text used in .{node.func.attr}(). '
                           'In Portuguese this check fails; use a state flag instead.')
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and contains_t(body[0].value)):
                report.problem(f'{path}:{body[0].lineno}: t() used as a docstring; that removes the docstring.')
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            frozen = node.args.defaults + [d for d in node.args.kw_defaults if d] + node.decorator_list
            if node.returns:
                frozen.append(node.returns)
            frozen += [a.annotation for a in node.args.args + node.args.kwonlyargs if a.annotation]
            if any(contains_t(n) for n in frozen):
                report.problem(f'{path}:{node.lineno}: t() in a default value, decorator or annotation; '
                               'it would be fixed at import time.')
    module_level = [s for s in tree.body if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    class_level = [s for c in ast.walk(tree) if isinstance(c, ast.ClassDef) for s in c.body
                   if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    for stmt in module_level + class_level:
        if contains_t(stmt):
            report.read(f'{path}:{stmt.lineno}: t() runs at import time (module or class level). Fine only '
                        'if the language is chosen before this module is imported.')


def compare_module(path, old_bytes, new_bytes, english, report):
    if coding_cookie(old_bytes) != coding_cookie(new_bytes):
        report.problem(f'{path}: the encoding line changed ({coding_cookie(old_bytes)!r} -> '
                       f'{coding_cookie(new_bytes)!r}). That can hide code in comments; reject it.')
        return set()
    try:
        old_tree = ast.parse(old_bytes)
    except SyntaxError as error:
        report.problem(f'{path}: base version does not parse ({error}).')
        return set()
    try:
        new_tree = ast.parse(new_bytes)
        compile(new_bytes, path, 'exec')  # catches __future__ order etc.; runs nothing
    except SyntaxError as error:
        report.problem(f'{path}: new version does not compile ({error}).')
        return set()
    if TRANSLATE_FUNC in {n.id for n in ast.walk(old_tree) if isinstance(n, ast.Name)} | \
            {a.arg for a in ast.walk(old_tree) if isinstance(a, ast.arg)}:
        report.problem(f'{path}: the base code already uses the name {TRANSLATE_FUNC!r}; t() calls '
                       'there may hit that instead. Rename one before extracting.')
    check_import(new_tree, path, report)
    flag_risky_uses(new_tree, path, report)
    untranslate = Untranslate(english, path, report)
    new_tree = ast.fix_missing_locations(untranslate.visit(new_tree))
    old_text = ast.unparse(plain_constants(old_tree)).splitlines()
    new_text = ast.unparse(plain_constants(new_tree)).splitlines()
    diff = list(difflib.unified_diff(old_text, new_text, f'{path} (base)', f'{path} (text put back)',
                                     n=2, lineterm=''))
    if diff:
        changed = sum(1 for line in diff if line[:1] in '+-' and line[:3] not in ('+++', '---'))
        # A problem, not just a note: the commit promised text moves only. The
        # expected state-flag fixes land here too; read each and decide.
        report.problem(f'{path}: {untranslate.count} text moves check out, but {changed} line(s) are '
                       'not a pure text move. Read every one:\n    ' + '\n    '.join(diff))
    else:
        report.note(f'{path}: {untranslate.count} text moves, nothing else changed.')
    return untranslate.used


def check_extraction(repo, base, head, report):
    files = check_files(repo, base, head, report)
    en_text = show_text(repo, head, ENGLISH, report)
    if en_text is None:
        report.problem(f'{ENGLISH} does not exist at {head}.')
        return
    english = load_locale(en_text, ENGLISH, report) or {}
    for key, value in english.items():
        check_placeholders(key, value, ENGLISH, report)
        for prefix in MATCHED_TEXT:
            if prefix in value:
                report.problem(f'{ENGLISH}: {key!r} contains {prefix!r}, which the app matches by '
                               'wording. It must stay hard-coded English.')
    old_en_text = show_text(repo, base, ENGLISH, report)
    if old_en_text is not None:
        old_english = load_locale(old_en_text, f'{base}:{ENGLISH}', report) or {}
        changed = sorted(k for k in old_english if english.get(k) != old_english[k])
        if changed:
            report.problem(f'{ENGLISH}: existing English text changed or removed for {changed[:20]}. '
                           'Code using those keys is not re-checked; review those callers by hand.')
    used = set()
    for status, path, _binary in files:
        if path == ENGLISH or (path == PACKAGING_SCRIPT and status == 'M'):
            continue  # check_files already judged the release script
        if status == 'D':
            report.problem(f'{path}: deleted. An extraction commit should not delete files.')
        elif path.startswith(LOCALE_DIR):
            report.problem(f'{path}: other languages belong in the second commit.')
        elif path in NEW_CODE_FILES or (path.startswith('test_') and path.endswith('.py') and '/' not in path):
            report.read(f'{path}: new or changed helper/test code. Read it in full before running tests.')
        elif path in GUI_FILES:
            old_bytes, new_bytes = show_bytes(repo, base, path), show_bytes(repo, head, path)
            if old_bytes is None:
                report.problem(f'{path}: did not exist at {base}.')
            else:
                used |= compare_module(path, old_bytes, new_bytes, english, report)
        elif path.endswith('.py'):
            report.problem(f'{path}: not a GUI-only file (the engine may load it). '
                           'The extraction should not touch it.')
        elif (path.endswith('.md') or path == 'CREDITS.txt') and '/' not in path.replace('docs/', '', 1):
            report.read(f'{path}: documentation change. Skim it.')
        else:
            report.problem(f'{path}: not a file the extraction commit should touch.')
    unused = sorted(set(english) - used)
    if unused:
        report.read(f'{ENGLISH}: {len(unused)} key(s) never used by a t() call in the changed files '
                    f'(may be used elsewhere): {", ".join(unused[:20])}')
    coloured = sorted(k for k, v in english.items() if COLOUR_WORDS.search(v))
    if coloured:
        report.read(f'{ENGLISH}: {len(coloured)} text(s) contain words the Activity log colours by '
                    f'(error, stop, waiting...). If any reach the log, their colour is lost in '
                    f'Portuguese unless the colour is passed as a tag: {", ".join(coloured[:20])}')


def check_locale(repo, rev, path, report):
    en_text, target_text = show_text(repo, rev, ENGLISH, report), show_text(repo, rev, path, report)
    if en_text is None or target_text is None:
        report.problem(f'{ENGLISH if en_text is None else path} could not be read at {rev}.')
        return
    english = load_locale(en_text, ENGLISH, report) or {}
    target = load_locale(target_text, path, report) or {}
    for key in sorted(set(target) - set(english)):
        report.problem(f'{path}: {key!r} is not an English key; it would never be shown.')
    missing = sorted(set(english) - set(target))
    if missing:
        report.read(f'{path}: {len(missing)} key(s) untranslated (shown in English): {", ".join(missing[:20])}')
    growth = []
    for key in sorted(set(english) & set(target)):
        ours = check_placeholders(key, target[key], path, report)
        theirs = check_placeholders(key, english[key], ENGLISH, report)
        if ours is None or theirs is None:
            continue
        if sorted(ours) != sorted(theirs):
            report.problem(f'{path}: {key!r} placeholders {sorted(ours)} differ from English {sorted(theirs)}.')
        if english[key].strip() and len(target[key]) > 1.4 * len(english[key]) and len(target[key]) > 12:
            growth.append((len(target[key]) / len(english[key]), key))
    if growth:
        top = ', '.join(f'{k} ({r:.1f}x)' for r, k in sorted(growth, reverse=True)[:15])
        report.read(f'{path}: much longer than English; check these fit on screen: {top}')
    report.note(f'{path}: {len(target)} of {len(english)} keys translated.')


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', default='.', help='repository folder (default: current folder)')
    sub = parser.add_subparsers(dest='mode', required=True)
    for mode in ('files', 'extraction'):
        p = sub.add_parser(mode)
        p.add_argument('base')
        p.add_argument('head')
    p = sub.add_parser('locale')
    p.add_argument('rev')
    p.add_argument('path', nargs='?', default='locales/pt_BR.json')
    args = parser.parse_args()
    report = Report()
    if args.mode == 'files':
        check_files(args.repo, args.base, args.head, report)
    elif args.mode == 'extraction':
        check_extraction(args.repo, args.base, args.head, report)
    else:
        check_locale(args.repo, args.rev, args.path, report)
    sys.exit(report.print())


if __name__ == '__main__':
    main()
