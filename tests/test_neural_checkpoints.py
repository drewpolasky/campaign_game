"""Desktop AI menu: only offer neural checkpoints the current encoder can run.

A checkpoint trained before an issue-set change expects a different
observation size; listing it would silently play Default every turn.

Run:  python -m pytest tests/test_neural_checkpoints.py
"""
import json
import os
import sys
import zipfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

pytest.importorskip('numpy')
pytest.importorskip('tkinter')
pytest.importorskip('PIL.ImageTk')

import CampaignGame as cg  # noqa: E402
from rl.obs import OBS_DIM  # noqa: E402


def _fake_checkpoint(path, obs_dim):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('data', json.dumps({'observation_space': {'_shape': [obs_dim]}}))


def test_reads_obs_dim_from_checkpoint_metadata(tmp_path):
    good = tmp_path / 'model.zip'
    _fake_checkpoint(str(good), 463)
    assert cg._checkpoint_obs_dim(str(good)) == 463

    broken = tmp_path / 'broken.zip'
    broken.write_bytes(b'not a zip')
    assert cg._checkpoint_obs_dim(str(broken)) is None


def test_menu_skips_checkpoints_for_another_issue_set(tmp_path, monkeypatch):
    runs = tmp_path / 'runs'
    _fake_checkpoint(str(runs / 'current' / 'model.zip'), OBS_DIM)
    _fake_checkpoint(str(runs / 'old_issues' / 'model.zip'), OBS_DIM - 5)
    _fake_checkpoint(str(runs / 'smoke_test' / 'model.zip'), OBS_DIM)
    monkeypatch.setattr(cg, '__file__', str(tmp_path / 'CampaignGame.py'))
    monkeypatch.setattr(cg, 'AI_STRATEGIES', {})
    cg._discover_neural_checkpoints()
    assert set(cg.AI_STRATEGIES) == {'Neural: current'}


def test_default_neural_model_matches_the_encoder():
    from rl import realgame_strategy
    path = realgame_strategy._default_model_path() + '.zip'
    if not os.path.isfile(path):
        pytest.skip('default model not checked out')
    assert cg._checkpoint_obs_dim(path) == OBS_DIM
