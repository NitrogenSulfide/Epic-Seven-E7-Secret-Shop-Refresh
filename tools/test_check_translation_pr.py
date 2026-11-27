"""Scenario tests for tools/check_translation_pr.py on the real 0.2.7 GUI file.

Usage: python tools/test_check_translation_pr.py [REPO] [--show]   (needs origin/main fetched)
"""
import json, os, shutil, stat, subprocess, sys, tempfile

SRC = os.path.abspath(next((a for a in sys.argv[1:] if not a.startswith('--')), '.'))
TOOL = os.path.join(SRC, 'tools', 'check_translation_pr.py')
work = tempfile.mkdtemp()
results = []


def _force(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def git(*a, cwd=None):
    return subprocess.run(['git', *a], cwd=cwd or work, check=True, capture_output=True,
                          text=True, encoding='utf-8').stdout


def write(path, data):
    full = os.path.join(work, path)
    os.makedirs(os.path.dirname(full) or work, exist_ok=True)
    if isinstance(data, bytes):
        with open(full, 'wb') as f:
            f.write(data)
    else:
        with open(full, 'w', encoding='utf-8', newline='\n') as f:
            f.write(data)


def commit(msg):
    git('add', '-A'); git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', msg)
    return git('rev-parse', 'HEAD').strip()


def run(*args):
    done = subprocess.run([sys.executable, TOOL, '--repo', work, *args], capture_output=True, text=True, encoding='utf-8')
    return done.returncode, done.stdout + done.stderr


EN = {
    'budget.label': 'Skystone budget',
    'log.ready': 'Ready. Session updates will appear here.',
    'est.gold': 'Gold needed ≈ {gold:,}',
    'log.stop_detected': 'Stop key detected: {key} via {how}.',
}
en_json = json.dumps(EN, ensure_ascii=False, indent=1)
i18n = 'def t(key, **values):\n    return key\n'


def body():
    git('init', '-q')
    gui = git('show', 'origin/main:e7_shop_refresh_gui.py', cwd=SRC)
    engine = git('show', 'origin/main:E7ADBShopRefresh.py', cwd=SRC)
    write('e7_shop_refresh_gui.py', gui); write('E7ADBShopRefresh.py', engine)
    build = git('show', 'origin/main:build_release.ps1', cwd=SRC)
    dialog = git('show', 'origin/main:e7_import_dialog.py', cwd=SRC)
    write('e7_about.py', 'TEXT = "hello"\n'); write('build_release.ps1', build)
    write('e7_import_dialog.py', dialog)
    base = commit('base')

    good = (gui
            .replace("text='Skystone budget'", "text=t('budget.label')")
            .replace('self._event("Ready. Session updates will appear here.")', "self._event(t('log.ready'))")
            .replace('lines = [f"Gold needed ≈ {int(gold):,}"]', "lines = [t('est.gold', gold=int(gold))]")
            .replace("""self._event(f"Stop key detected: {hotkey['key']} via {self._stop_key_detection}.")""",
                     "self._event(t('log.stop_detected', key=hotkey['key'], how=self._stop_key_detection))"))
    good = good.replace('import argparse\n', 'import argparse\nfrom e7_i18n import t\n', 1)
    for key in EN:
        assert f"t('{key}'" in good, f'test setup did not apply {key}'

    def scenario(name, expect_code, files, must=(), mode='extraction', delete=()):
        git('checkout', '-q', '-B', name, base)
        for path, data in files.items():
            write(path, data)
        for path in delete:
            git('rm', '-q', path)
        head = commit(name)
        code, out = run(mode, base, head) if mode != 'locale' else run('locale', head)
        ok = code == expect_code and all(m in out for m in must) and 'Traceback' not in out
        results.append((name, ok))
        print(f"{'PASS' if ok else 'FAIL'} {name} (exit {code})")
        if not ok or '--show' in sys.argv:
            print(out)

    std = {'locales/en.json': en_json, 'e7_i18n.py': i18n}
    scenario('clean', 0, {'e7_shop_refresh_gui.py': good, **std},
             ['4 text moves, nothing else changed', 'e7_i18n.py: new or changed helper'])
    scenario('sneaky-number', 1, {'e7_shop_refresh_gui.py': good.replace('18,000 gold per buy', '18,001 gold per buy'), **std},
             ['not a pure text move', '18,001'])
    scenario('sneaky-code', 1, {'e7_shop_refresh_gui.py': good + '\nimport os; os.system("calc")\n', **std}, ['os.system'])
    scenario('wrong-text', 1, {'e7_shop_refresh_gui.py': good, 'locales/en.json': json.dumps({**EN, 'log.ready': 'Ready!'})},
             ['not a pure text move', "Ready!"])
    scenario('engine-touched', 1, {'e7_shop_refresh_gui.py': good, **std,
                                   'E7ADBShopRefresh.py': engine + '\n# hi\n'}, ['not a GUI-only file'])
    scenario('matched-text', 1, {'e7_shop_refresh_gui.py': good,
                                 'locales/en.json': json.dumps({**EN, 'x': 'Not saved yet'})}, ['matches by'])
    scenario('compare', 1, {'e7_shop_refresh_gui.py': good.replace(
        "if self.setting_notice.get().startswith('Not saved yet'):",
        "if self.setting_notice.get().startswith(t('budget.label')):"), **std}, ['used in .startswith()'])
    scenario('unknown-key', 1, {'e7_shop_refresh_gui.py': good.replace("t('log.ready')", "t('log.nope')"), **std},
             ["'log.nope' is not in"])
    scenario('wrong-names', 1, {'e7_shop_refresh_gui.py': good.replace('gold=int(gold)', 'g=int(gold)'), **std}, ['passes'])
    scenario('bad-placeholder', 1, {'e7_shop_refresh_gui.py': good,
                                    'locales/en.json': json.dumps({**EN, 'y': 'x {a.__class__}'})}, ['not a plain name'])
    scenario('binary', 1, {'e7_shop_refresh_gui.py': good, **std, 'adb-assets/x.dll': b'MZ\0\0bin'},
             ['binary file'], mode='files')
    scenario('build-script', 1, {'build_release.ps1': 'Write-Host bye\n'}, ['build_release.ps1'], mode='files')
    scenario('duplicate-key', 1, {'e7_shop_refresh_gui.py': good, 'locales/en.json':
                                  '{"budget.label": "Skystone budget", "budget.label": "x"}'}, ['appears twice'])

    # Issue #7: the import dialog is GUI-only; the release script may gain package entries.
    dialog_en = json.dumps({**EN, 'import.button': 'Import'})
    dialog_good = dialog.replace("text='Import'", "text=t('import.button')").replace(
        'import tkinter as tk\n', 'import tkinter as tk\nfrom e7_i18n import t\n', 1)
    assert "t('import.button')" in dialog_good and 'from e7_i18n import t' in dialog_good
    scenario('import-dialog', 0, {'e7_import_dialog.py': dialog_good, 'locales/en.json': dialog_en,
                                  'e7_i18n.py': i18n}, ['e7_import_dialog.py: 1 text moves, nothing else'])
    entry = "    'e7_import_dialog.py' = 'e7_import_dialog.py'\n"
    assert entry in build

    def packaged(*lines):
        return build.replace(entry, entry + ''.join(f'    {line}\n' for line in lines))
    ok_build = packaged("'e7_i18n.py' = 'e7_i18n.py'", "'locales/en.json' = 'locales/en.json'")
    refused = ['build_release.ps1: changed. Build']
    scenario('packaging-ok', 0, {'build_release.ps1': ok_build, 'e7_shop_refresh_gui.py': good, **std},
             ['only adding e7_i18n.py'])
    scenario('packaging-ok-files', 0, {'build_release.ps1': ok_build}, ['Read the hunk'], mode='files')
    scenario('packaging-crlf', 0, {'build_release.ps1': ok_build.replace('\n', '\r\n').encode()},
             ['only adding e7_i18n.py'], mode='files')
    scenario('packaging-rename', 1, {'build_release.ps1': packaged("'e7_i18n.py' = 'E7 Secret Shop Refresh.exe'")},
             refused, mode='files')
    scenario('packaging-other-file', 1, {'build_release.ps1': packaged("'evil.py' = 'evil.py'")}, refused, mode='files')
    scenario('packaging-extra-command', 1, {'build_release.ps1': ok_build.replace(
        '$files = [ordered]@{}', '$files = [ordered]@{}\nRemove-Item C:\\x')}, refused, mode='files')
    scenario('packaging-outside-map', 1, {'build_release.ps1': build.replace(
        '$files = [ordered]@{}', "    'e7_i18n.py' = 'e7_i18n.py'\n$files = [ordered]@{}")}, refused, mode='files')
    scenario('packaging-removed-line', 1, {'build_release.ps1': ok_build.replace("    'VERSION' = 'VERSION'\n", ''),
                                           'e7_shop_refresh_gui.py': good, **std}, refused)
    # Codex review 2026-11-26.
    scenario('packaging-u2028', 1, {'build_release.ps1': ok_build.replace(
        'Set-StrictMode -Version Latest\n', 'Set-StrictMode -Version Latest ', 1)}, refused, mode='files')
    scenario('packaging-lone-cr', 1, {'build_release.ps1': ok_build.replace(
        'Set-StrictMode -Version Latest\n', 'Set-StrictMode -Version Latest\r', 1)}, refused, mode='files')
    scenario('packaging-duplicate', 1, {'build_release.ps1': packaged("'e7_i18n.py' = 'e7_i18n.py'",
                                                                      "'e7_i18n.py' = 'e7_i18n.py'")}, refused, mode='files')
    scenario('packaging-case-duplicate', 1, {'build_release.ps1': packaged(
        "'locales/en.json' = 'locales/en.json'", "'locales/EN.json' = 'locales/EN.json'")}, refused, mode='files')
    fresh_dialog = dialog_good.replace("self.choice = ('fresh', None)", "self.choice = (t('choice.fresh'), None)")
    assert fresh_dialog != dialog_good
    scenario('protocol-marker', 1, {'e7_import_dialog.py': fresh_dialog, 'e7_i18n.py': i18n, 'locales/en.json':
                                    json.dumps({**EN, 'import.button': 'Import', 'choice.fresh': 'fresh'})},
             ["'choice.fresh' is 'fresh', a marker"])

    # Bypasses Neon found (2026-11-25 review).
    cookie = ('# -*- coding: utf-7 -*-\n' + good).encode('utf-8')
    scenario('coding-cookie', 1, {'e7_shop_refresh_gui.py': cookie, **std}, ['encoding line changed'])
    scenario('unknown-file', 1, {'e7_shop_refresh_gui.py': good, **std, 'pyproject.toml': '[x]\n',
                                 'sitecustomize.pth': 'import os\n'}, ['pyproject.toml', 'sitecustomize.pth'])
    scenario('upper-case-ext', 1, {'BUILD.PS1': 'x\n'}, ['BUILD.PS1'], mode='files')
    scenario('non-ascii-path', 1, {'tools/çheck.py': 'x = 1\n'}, ['çheck.py'], mode='files')
    scenario('deleted-file', 1, {'e7_shop_refresh_gui.py': good, **std}, ['deleted'], delete=['build_release.ps1'])
    scenario('rename-swap', 1, {'e7_about.py': engine, **std}, ['not a pure text move'], delete=['E7ADBShopRefresh.py'])
    scenario('shadow-t', 1, {'e7_shop_refresh_gui.py': good + '\ndef t(key, **v):\n    return __import__("os").getcwd()\n', **std},
             ["also bound"])
    scenario('aliased-import', 1, {'e7_shop_refresh_gui.py': good.replace('from e7_i18n import t\n',
                                                                          'from evil import x as t\n'), **std},
             ['module-level'])
    scenario('reordered-args', 1, {'e7_shop_refresh_gui.py': good.replace(
        "key=hotkey['key'], how=self._stop_key_detection", "how=self._stop_key_detection, key=hotkey['key']"), **std},
             ['different order'])
    scenario('docstring-t', 1, {'e7_shop_refresh_gui.py': good + '\ndef helper():\n    t("budget.label")\n    return 1\n', **std},
             ['docstring'])
    scenario('default-arg-t', 1, {'e7_shop_refresh_gui.py': good + '\ndef helper(x=t("budget.label")):\n    return x\n', **std},
             ['import time'])

    pt = {'budget.label': 'Orçamento de Skystone', 'log.ready': 'Pronto. As atualizações da sessão aparecem aqui.',
          'est.gold': 'Ouro necessário ≈ {gold:,}', 'log.stop_detected': 'Tecla de parada detectada: {key} via {how}.'}
    scenario('locale-good', 0, {'locales/en.json': en_json, 'locales/pt_BR.json': json.dumps(pt, ensure_ascii=False)},
             ['4 of 4 keys translated'], mode='locale')
    scenario('locale-bad', 1, {'locales/en.json': en_json, 'locales/pt_BR.json': json.dumps(
        {**pt, 'est.gold': 'Ouro {ouro:,}', 'extra': 'x', 'log.ready': '{0.__class__}'}, ensure_ascii=False)},
             ['differ from English', "'extra' is not an English key", 'not a plain name'], mode='locale')
    scenario('locale-conversion', 1, {'locales/en.json': en_json, 'locales/pt_BR.json': json.dumps(
        {**pt, 'log.ready': 'x {y!z}'})}, ['invalid conversion'], mode='locale')


try:
    body()
finally:
    shutil.rmtree(work, onerror=_force)
print(f"\n{sum(ok for _, ok in results)}/{len(results)} scenarios passed")
sys.exit(0 if results and all(ok for _, ok in results) else 1)
