"""The numpy copy of the default neural policy, which the web server plays.

Run:  python -m pytest tests/test_numpy_policy.py
"""
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

np = pytest.importorskip('numpy')

from rl import numpy_policy, realgame_strategy  # noqa: E402
from rl.actions import COUPLED_ACTION_DIM  # noqa: E402
from rl.obs import OBS_DIM  # noqa: E402

MODEL = os.path.join(REPO, 'runs', 'v20_mixed_lengths', 'model')


def _require_policy():
    if not os.path.isfile(MODEL + '.zip'):
        pytest.skip('default model not checked out')
    # The web server's copy is committed with the model; without it the
    # server quietly drops Neural from the lobby.
    assert os.path.isfile(numpy_policy.DEFAULT_POLICY_PATH), (
        'run `python -m rl.export_numpy {}` and commit policy.npz'.format(
            os.path.relpath(MODEL, REPO)))
    return numpy_policy.load()


def test_policy_fits_the_encoder_and_decoder():
    policy = _require_policy()
    assert policy.obs_dim == OBS_DIM
    assert policy.action_dim == COUPLED_ACTION_DIM


def test_policy_is_exported_from_the_desktop_default_model(monkeypatch):
    # The web and desktop games should play the same model: the .npz sits
    # beside the desktop's default checkpoint and was exported from it (re-run
    # `python -m rl.export_numpy <model>` after retraining).
    policy = _require_policy()
    monkeypatch.delenv('CAMPAIGN_RL_MODEL', raising=False)
    default_model = realgame_strategy._default_model_path()
    assert os.path.dirname(numpy_policy.DEFAULT_POLICY_PATH) == os.path.dirname(default_model)
    assert policy.source_sha256 == numpy_policy.checkpoint_sha256(default_model)


def test_load_rejects_a_policy_for_another_issue_set(tmp_path):
    rng = np.random.default_rng(0)
    path = str(tmp_path / 'old.npz')
    np.savez(path, n_layers=np.array(2), activation=np.array('tanh'),
             w0=rng.normal(size=(8, OBS_DIM - 5)).astype(np.float32),
             b0=np.zeros(8, np.float32),
             w1=rng.normal(size=(COUPLED_ACTION_DIM, 8)).astype(np.float32),
             b1=np.zeros(COUPLED_ACTION_DIM, np.float32),
             action_low=np.full(COUPLED_ACTION_DIM, -5, np.float32),
             action_high=np.full(COUPLED_ACTION_DIM, 5, np.float32))
    with pytest.raises(ValueError, match='issue set'):
        numpy_policy.load(path)


def test_matches_stable_baselines_predict():
    # Only where the training stack is installed (not needed on the server).
    pytest.importorskip('torch')
    sb3 = pytest.importorskip('stable_baselines3')
    from rl.gym_env import CampaignGymEnv

    policy = _require_policy()
    model = sb3.PPO.load(MODEL, device='cpu')
    env = CampaignGymEnv(opponent_names=('BigStateFocus',), num_turns=20, seed=3,
                         action_kind='coupled', random_calendar_prob=1.0)
    obs, _ = env.reset()
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        np.testing.assert_allclose(policy.predict(obs), action, atol=1e-4)
        obs, _, done, _, _ = env.step(action)
