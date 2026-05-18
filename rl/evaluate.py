"""Evaluate a trained PPO policy against scripted opponents.

Loads a model from `--model`, plays N games vs the named opponent(s), and
reports win rate, average delegate share, and average reward.
"""
import argparse
import statistics

import numpy as np
from stable_baselines3 import PPO

from .gym_env import CampaignGymEnv


def evaluate(model_path, opponent_names, num_games=100, num_turns=8, seed=1234):
    model = PPO.load(model_path)
    env = CampaignGymEnv(opponent_names=tuple(opponent_names),
                         num_turns=num_turns, seed=seed)

    wins = 0
    total_reward = 0.0
    delegate_shares = []
    for g in range(num_games):
        obs, _ = env.reset(seed=seed + g)
        ep_reward = 0.0
        while True:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, term, trunc, info = env.step(action)
            ep_reward += reward
            if term or trunc:
                break
        agent_d = info['agent_delegates']
        opp_d = info['opp_delegates']
        all_d = agent_d + sum(opp_d)
        delegate_shares.append(agent_d / max(all_d, 1))
        if agent_d > max(opp_d):
            wins += 1
        total_reward += ep_reward

    print(f'\nEval: {model_path} vs {opponent_names}')
    print(f'  Games:           {num_games}')
    print(f'  Win rate:        {wins / num_games:.1%}')
    print(f'  Mean delegate %: {statistics.mean(delegate_shares):.1%} '
          f'(stdev {statistics.pstdev(delegate_shares):.1%})')
    print(f'  Mean ep reward:  {total_reward / num_games:+.2f}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True)
    p.add_argument('--opponents', nargs='+', default=['Default'])
    p.add_argument('--games', type=int, default=100)
    p.add_argument('--num-turns', type=int, default=8)
    p.add_argument('--seed', type=int, default=1234)
    args = p.parse_args()
    evaluate(args.model, args.opponents, args.games, args.num_turns, args.seed)


if __name__ == '__main__':
    main()
