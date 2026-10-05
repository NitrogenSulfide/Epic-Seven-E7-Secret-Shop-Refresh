"""Product links; reports prefill version information, never private engine logs."""
from urllib.parse import urlencode

REPOSITORY = 'https://github.com/NitrogenSulfide/Epic-Seven-E7-Secret-Shop-Refresh'
PROFILE = 'https://github.com/NitrogenSulfide'


def release_url(version):
    # An unpublished experimental build has no release tag to link to yet.
    return REPOSITORY + ('/releases' if '-rc' in version else f'/releases/tag/v{version}')


def bug_report_url(version, control_mode):
    body = (f'### App version\nv{version}\n\n### Control mode\n{control_mode}\n\n'
            '### What happened?\n\n\n### Steps to reproduce\n1. \n\n'
            '### Expected behavior\n\n\n### Game client and Windows version\n\n')
    return REPOSITORY + '/issues/new?' + urlencode({'labels': 'bug', 'body': body})
