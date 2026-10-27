"""The server must start with only server/requirements.txt installed (flask,
gunicorn, numpy): none of the desktop, plotting or training packages.

Run:  python3 server/tests/test_dependencies.py
"""
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NOT_ON_SERVER = ['matplotlib', 'PIL', 'tkinter', 'torch', 'gymnasium', 'stable_baselines3']

_CHECK = '''
import sys

class _Block:
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in {blocked!r}:
            raise ImportError('not installed on the server: ' + name)

sys.meta_path.insert(0, _Block())
sys.path.insert(0, {repo!r})
import server.app
from server import ai
print(','.join(ai.STRATEGY_NAMES))
'''


def test_server_starts_with_only_its_requirements():
    env = dict(os.environ, CAMPAIGN_DB=os.path.join(tempfile.mkdtemp(), 'deps.db'))
    code = _CHECK.format(blocked=set(NOT_ON_SERVER), repo=REPO)
    proc = subprocess.run([sys.executable, '-c', code], cwd=tempfile.gettempdir(),
                          env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert 'Default' in proc.stdout.split(',')


if __name__ == '__main__':
    test_server_starts_with_only_its_requirements()
    print('OK: the server imports without', ', '.join(NOT_ON_SERVER))
