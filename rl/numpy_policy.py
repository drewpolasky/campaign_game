"""Play a trained coupled-action PPO policy with numpy alone.

The web server runs the neural AI without PyTorch or stable-baselines3:
rl.export_numpy copies the actor network out of a saved PPO checkpoint into
a small .npz next to it, and this module runs that network forward. For a
Box action space, SB3's deterministic predict is the actor's mean clipped to
the action bounds, so both give the same action (export_numpy checks this
before it writes the file).

Usage:
    from rl import numpy_policy
    policy = numpy_policy.load()          # default model's policy.npz
    fundraising = numpy_policy.act(sim, p_idx, policy)
"""
import hashlib
import os
import zipfile

import numpy as np

from . import actions as _actions
from . import obs as _obs

DEFAULT_POLICY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'runs', 'v20_mixed_lengths', 'policy.npz')

_ACTIVATIONS = {
    'tanh': np.tanh,
    'relu': lambda x: np.maximum(x, 0.0),
}


class NumpyPolicy:
    """The actor MLP from a PPO checkpoint: hidden Linear layers with one
    activation between them, then the action head (no activation)."""

    def __init__(self, path):
        with np.load(path) as data:
            n_layers = int(data['n_layers'])
            self.weights = [data['w{}'.format(i)] for i in range(n_layers)]
            self.biases = [data['b{}'.format(i)] for i in range(n_layers)]
            self.activation = str(data['activation'])
            self.action_low = data['action_low']
            self.action_high = data['action_high']
            self.source_sha256 = (str(data['source_sha256'])
                                  if 'source_sha256' in data.files else None)
        if self.activation not in _ACTIVATIONS:
            raise ValueError('unsupported activation {!r}'.format(self.activation))
        self.obs_dim = self.weights[0].shape[1]
        self.action_dim = self.weights[-1].shape[0]

    def predict(self, obs):
        x = np.asarray(obs, dtype=np.float32)
        act = _ACTIVATIONS[self.activation]
        last = len(self.weights) - 1
        for i, (w, b) in enumerate(zip(self.weights, self.biases)):
            x = w @ x + b
            if i < last:
                x = act(x)
        return np.clip(x, self.action_low, self.action_high)


def checkpoint_sha256(model_path):
    """Hash of a PPO checkpoint's weights (the policy.pth inside its zip).
    export_numpy stores it in the .npz, so a test can tell when a retrained
    model wasn't re-exported."""
    zip_path = model_path if model_path.endswith('.zip') else model_path + '.zip'
    with zipfile.ZipFile(zip_path) as z:
        return hashlib.sha256(z.read('policy.pth')).hexdigest()


def load(path=None):
    """Load a policy and check it fits the current observation and coupled
    action sizes. Raises ValueError for a policy built for another issue set
    or action space."""
    policy = NumpyPolicy(path or DEFAULT_POLICY_PATH)
    if policy.obs_dim != _obs.OBS_DIM:
        raise ValueError('policy expects {} inputs, the game now has {} (a '
                         'different issue set?)'.format(policy.obs_dim, _obs.OBS_DIM))
    if policy.action_dim != _actions.COUPLED_ACTION_DIM:
        raise ValueError('policy has {} outputs, the coupled action has {}'.format(
            policy.action_dim, _actions.COUPLED_ACTION_DIM))
    return policy


def act(sim, p_idx, policy):
    """Take player ``p_idx``'s week on a Sim-shaped object: encode the world,
    run the policy, and decode the action onto the sim's states (orgs, ads,
    campaign hours). Returns the fundraising hours, like a sim strategy."""
    action = policy.predict(_obs.encode_obs(sim, agent_idx=p_idx))
    return _actions.decode_coupled_action(sim, p_idx, action)
