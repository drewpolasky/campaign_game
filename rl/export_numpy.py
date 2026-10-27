"""Export a coupled-action PPO checkpoint's actor for rl.numpy_policy.

    python -m rl.export_numpy runs/v20_mixed_lengths/model

writes runs/v20_mixed_lengths/policy.npz, which the web server plays with
numpy alone. Needs torch and stable-baselines3. Re-run it whenever the
default model changes.

Before writing, the numpy network is checked against SB3's deterministic
predict on observations from real games (both calendars, every length), so a
policy layout this exporter doesn't understand fails here rather than in a
live match.
"""
import argparse
import os
import tempfile

import numpy as np
import torch
from gymnasium.spaces import Box
from stable_baselines3 import PPO
from stable_baselines3.common.torch_layers import FlattenExtractor

from .gym_env import CampaignGymEnv
from .numpy_policy import NumpyPolicy, checkpoint_sha256

_ACTIVATION_NAMES = {torch.nn.Tanh: 'tanh', torch.nn.ReLU: 'relu'}
CHECK_OPPONENTS = (('Default',), ('AdMaximizer',), ('LateBlitz', 'BigStateFocus'))
CHECK_LENGTHS = (8, 10, 20)
TOLERANCE = 1e-4


def _actor_arrays(model):
    policy = model.policy
    if not isinstance(model.action_space, Box) or policy.squash_output:
        raise SystemExit('only unsquashed Box-action (continuous/coupled) policies export')
    extractor = getattr(policy, 'pi_features_extractor', policy.features_extractor)
    if not isinstance(extractor, FlattenExtractor):
        raise SystemExit('unsupported features extractor {}'.format(type(extractor).__name__))

    layers = []
    activation = None
    for module in policy.mlp_extractor.policy_net:
        if isinstance(module, torch.nn.Linear):
            layers.append(module)
        elif type(module) in _ACTIVATION_NAMES and activation in (None, _ACTIVATION_NAMES[type(module)]):
            activation = _ACTIVATION_NAMES[type(module)]
        else:
            raise SystemExit('unsupported policy layer {}'.format(module))
    layers.append(policy.action_net)

    arrays = {
        'n_layers': np.array(len(layers)),
        'activation': np.array(activation or 'tanh'),
        'action_low': model.action_space.low.astype(np.float32),
        'action_high': model.action_space.high.astype(np.float32),
    }
    for i, linear in enumerate(layers):
        arrays['w{}'.format(i)] = linear.weight.detach().cpu().numpy().astype(np.float32)
        arrays['b{}'.format(i)] = linear.bias.detach().cpu().numpy().astype(np.float32)
    return arrays


def _check(model, policy, seed):
    """Largest |numpy - SB3| action gap over a set of real-game observations."""
    worst = 0.0
    n = 0
    for k, opponents in enumerate(CHECK_OPPONENTS):
        for num_turns in CHECK_LENGTHS:
            env = CampaignGymEnv(opponent_names=opponents, num_turns=num_turns,
                                 seed=seed + k, action_kind='coupled',
                                 random_calendar_prob=0.5)
            for _ in range(2):
                obs, _ = env.reset()
                done = False
                while not done:
                    action, _ = model.predict(obs, deterministic=True)
                    worst = max(worst, float(np.abs(policy.predict(obs) - action).max()))
                    n += 1
                    obs, _, done, _, _ = env.step(action)
    return worst, n


def main():
    p = argparse.ArgumentParser()
    p.add_argument('model', help='checkpoint path (with or without .zip)')
    p.add_argument('--out', default=None,
                   help='output .npz (default: policy.npz beside the model)')
    p.add_argument('--seed', type=int, default=0)
    args = p.parse_args()

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.model)), 'policy.npz')
    model = PPO.load(args.model, device='cpu')
    arrays = _actor_arrays(model)
    arrays['source_sha256'] = np.array(checkpoint_sha256(args.model))

    # Write to a temp file, check it, then move it into place.
    fd, tmp = tempfile.mkstemp(suffix='.npz', dir=os.path.dirname(out) or '.')
    os.close(fd)
    try:
        np.savez(tmp, **arrays)
        worst, n = _check(model, NumpyPolicy(tmp), args.seed)
        if worst > TOLERANCE:
            raise SystemExit('numpy policy differs from SB3 by {:.2e} (> {:.0e}); '
                             'not writing {}'.format(worst, TOLERANCE, out))
        os.replace(tmp, out)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print('wrote {} ({:,} bytes); max action gap vs SB3 {:.1e} over {} turns'.format(
        out, os.path.getsize(out), worst, n))


if __name__ == '__main__':
    main()
