"""End-to-end smoke test for the rl/ scaffolding.

Runs N random-action games for the agent vs. scripted opponents and prints:
  - obs/action shapes match expectations
  - episode lengths == num_turns
  - agent win-rate (should be near 1/num_players for random vs. heuristic)
  - games per second through the env
"""
import random
import time

import numpy as np

from .env import CampaignGameEnv
from .opponent import named_scripted
from . import actions as _actions
from . import obs as _obs


def run(num_games=20, num_turns=8, seed=42):
    rng = random.Random(seed)
    opponents = [named_scripted('Default'), named_scripted('Balanced')]
    env = CampaignGameEnv(opponents=opponents, num_turns=num_turns, seed=seed)

    obs0 = env.reset()
    assert obs0.shape == (_obs.OBS_DIM,), \
        f'obs shape {obs0.shape} != ({_obs.OBS_DIM},)'
    assert obs0.dtype == np.float32

    wins = 0
    total_steps = 0
    t0 = time.perf_counter()
    for g in range(num_games):
        env.reset()
        steps = 0
        while True:
            mask = env.action_mask()
            valid = [i for i, m in enumerate(mask) if m]
            target = rng.choice(valid) if valid else 0
            action = (target,
                      rng.randrange(_actions.NUM_AGGRESSION),
                      rng.randrange(_actions.NUM_LEAN),
                      rng.randrange(_actions.NUM_FUNDRAISING_BUCKETS))
            obs, reward, done, info = env.step(action)
            assert obs.shape == (_obs.OBS_DIM,)
            steps += 1
            if done:
                break
        total_steps += steps
        assert steps == num_turns, f'episode {g} ran {steps} turns, want {num_turns}'
        agent_d = info['agent_delegates']
        opp_d = info['opp_delegates']
        if agent_d > max(opp_d):
            wins += 1
    elapsed = time.perf_counter() - t0

    print(f'OBS_DIM = {_obs.OBS_DIM}')
    print(f'ACTION_NVEC = {_actions.ACTION_NVEC} (total {np.prod(_actions.ACTION_NVEC)} actions)')
    print(f'Ran {num_games} games of {num_turns} turns each: '
          f'{total_steps} steps in {elapsed:.2f}s '
          f'({num_games / elapsed:.1f} games/s, '
          f'{total_steps / elapsed:.0f} steps/s)')
    print(f'Agent win-rate (random vs Default+Balanced): {wins}/{num_games} '
          f'= {wins/num_games:.0%}')


if __name__ == '__main__':
    run()
