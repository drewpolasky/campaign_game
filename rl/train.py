"""PPO training entry point.

Vectorizes CampaignGymEnv across CPUs via SubprocVecEnv and trains with
stable-baselines3 PPO. The default config is tuned for fast iteration on a
desktop CPU — small network, short rollouts, frequent eval.

Usage:
    python -m rl.train --steps 100000 --envs 8 --opponents Default
"""
import argparse
import os
import time

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv
from stable_baselines3.common.callbacks import BaseCallback

from .gym_env import CampaignGymEnv


def make_env(opponent_names, num_turns, seed, action_kind='discrete'):
    def _thunk():
        return CampaignGymEnv(opponent_names=opponent_names,
                              num_turns=num_turns, seed=seed,
                              action_kind=action_kind)
    return _thunk


class WinRateCallback(BaseCallback):
    """Logs agent win-rate over the most recent N episodes."""

    def __init__(self, window=50, verbose=0):
        super().__init__(verbose)
        self.window = window
        self.episode_outcomes = []  # 1 for win, 0 for loss
        self.last_log_step = 0

    def _on_step(self) -> bool:
        for info, done in zip(self.locals['infos'], self.locals['dones']):
            if done and 'agent_delegates' in info:
                won = info['agent_delegates'] > max(info['opp_delegates'])
                self.episode_outcomes.append(1 if won else 0)
                if len(self.episode_outcomes) > self.window:
                    self.episode_outcomes.pop(0)
        if (self.num_timesteps - self.last_log_step) >= 5000:
            self.last_log_step = self.num_timesteps
            if self.episode_outcomes:
                wr = sum(self.episode_outcomes) / len(self.episode_outcomes)
                self.logger.record('rollout/win_rate', wr)
        return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--steps', type=int, default=100_000,
                   help='total PPO timesteps')
    p.add_argument('--envs', type=int, default=8,
                   help='vectorized env count')
    p.add_argument('--num-turns', type=int, default=8)
    p.add_argument('--opponents', nargs='+', default=['Default'],
                   help='one or more opponent names; agent plays vs all of them in one game')
    p.add_argument('--out', default='runs/ppo')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--no-subproc', action='store_true',
                   help='use DummyVecEnv (single process; useful for debugging)')
    p.add_argument('--n-steps', type=int, default=256,
                   help='PPO n_steps per rollout per env')
    p.add_argument('--action-kind', choices=['discrete', 'continuous'],
                   default='discrete')
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)

    env_fns = [make_env(tuple(args.opponents), args.num_turns,
                        args.seed + i, action_kind=args.action_kind)
               for i in range(args.envs)]
    vec_cls = DummyVecEnv if (args.no_subproc or args.envs == 1) else SubprocVecEnv
    venv = vec_cls(env_fns)

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
        policy_kwargs=dict(net_arch=[128, 128]),
    )

    print(f'Training PPO for {args.steps:,} steps on {args.envs} envs '
          f'vs {args.opponents}, num_turns={args.num_turns}')
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
