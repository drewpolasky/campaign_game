"""Self-play training entry point.

Each env samples its opponent from a pool that mixes scripted baselines
with frozen PPO snapshots. This gives the learning agent a non-stationary
target so it doesn't overfit a single playstyle, and prevents the
"catastrophic forgetting" failure mode where v3 beats v2 but loses to v1.

Pool weights default to favoring the strongest known opponent, with a tail
on weaker / older policies (PFSP-lite). Sampling happens at episode reset.

Usage:
    python -m rl.train_selfplay --steps 200000 --frozen runs/v3_2p10t/model
"""
import argparse
import os
import time

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.callbacks import BaseCallback

from .gym_env import CampaignGymEnv
from .frozen_opponent import FrozenPolicyOpponent, OpponentPool
from .opponent import named_scripted


def make_opponent_pool_factory(scripted_names, frozen_paths, weights=None):
    """Returns a closure that, given a seed, builds a fresh OpponentPool.
    Each env gets its own RNG so opponent sampling is independent."""
    # Pre-load frozen models once; FrozenPolicyOpponent caches the model on
    # first use, so subsequent calls are cheap.
    frozen_opps = [FrozenPolicyOpponent(p, name=f'frozen:{os.path.basename(p)}')
                   for p in frozen_paths]
    members_template = (
        [(n, named_scripted(n)) for n in scripted_names] +
        [(o.name, o) for o in frozen_opps]
    )

    def factory(seed):
        # Single-opponent game: pool selects one each episode.
        pool = OpponentPool(members_template, weights=weights, seed=seed)
        return [pool]
    return factory


class WinRateCallback(BaseCallback):
    """Logs per-opponent win rate so we see where the agent is weakest."""

    def __init__(self, window=100, verbose=0):
        super().__init__(verbose)
        self.window = window
        # name -> list of 1/0 outcomes
        self.outcomes_by_opp = {}
        self.last_log_step = 0

    def _on_step(self) -> bool:
        for info, done in zip(self.locals['infos'], self.locals['dones']):
            if done and 'agent_delegates' in info:
                won = info['agent_delegates'] > max(info['opp_delegates'])
                opp_name = info.get('opponent_name', 'unknown')
                bucket = self.outcomes_by_opp.setdefault(opp_name, [])
                bucket.append(1 if won else 0)
                if len(bucket) > self.window:
                    bucket.pop(0)

        if (self.num_timesteps - self.last_log_step) >= 5000:
            self.last_log_step = self.num_timesteps
            for name, outcomes in self.outcomes_by_opp.items():
                wr = sum(outcomes) / len(outcomes) if outcomes else 0.0
                self.logger.record(f'rollout/win_rate_{name}', wr)
        return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--steps', type=int, default=200_000)
    p.add_argument('--envs', type=int, default=4)
    p.add_argument('--num-turns', type=int, default=10)
    p.add_argument('--scripted', nargs='+',
                   default=['FocusedDefault', 'Default'],
                   help='scripted opponents in the pool')
    p.add_argument('--frozen', nargs='+', default=[],
                   help='paths to frozen model checkpoints to add to the pool')
    p.add_argument('--weights', nargs='+', type=float, default=None,
                   help='sampling weights for [scripted..., frozen...]; uniform if omitted')
    p.add_argument('--init-from', default=None,
                   help='warm-start from an existing checkpoint')
    p.add_argument('--out', default='runs/selfplay')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--n-steps', type=int, default=256)
    p.add_argument('--action-kind', choices=['discrete', 'continuous', 'coupled'],
                   default='discrete',
                   help='action space of the LEARNING agent. Frozen opponents '
                        'auto-dispatch from their own checkpoint.')
    p.add_argument('--net-arch', nargs='+', type=int, default=[128, 128],
                   help='hidden layer sizes for the MLP policy + value heads. '
                        'e.g. --net-arch 256 256 for a wider net.')
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)

    factory = make_opponent_pool_factory(args.scripted, args.frozen, args.weights)

    def make_env(seed):
        def _thunk():
            return CampaignGymEnv(num_turns=args.num_turns, seed=seed,
                                  opponent_factory=factory,
                                  action_kind=args.action_kind)
        return _thunk

    venv = DummyVecEnv([make_env(args.seed + i) for i in range(args.envs)])

    if args.init_from:
        print(f'warm-starting from {args.init_from}')
        model = PPO.load(args.init_from, env=venv, device='cpu')
    else:
        model = PPO(
            'MlpPolicy',
            venv,
            n_steps=args.n_steps,
            batch_size=min(256, args.envs * args.n_steps),
            learning_rate=3e-4,
            gamma=0.995,
            gae_lambda=0.95,
            ent_coef=0.01,
            verbose=1,
            seed=args.seed,
            policy_kwargs=dict(net_arch=list(args.net_arch)),
        )

    print(f'Self-play PPO: {args.steps:,} steps × {args.envs} envs '
          f'vs scripted={args.scripted} + frozen={args.frozen}')
    t0 = time.perf_counter()
    model.learn(total_timesteps=args.steps,
                callback=WinRateCallback(),
                progress_bar=False)
    elapsed = time.perf_counter() - t0
    print(f'Trained {args.steps:,} steps in {elapsed:.1f}s '
          f'({args.steps / elapsed:.0f} steps/s)')

    save_path = os.path.join(args.out, 'model')
    model.save(save_path)
    print(f'Saved model to {save_path}.zip')


if __name__ == '__main__':
    main()
