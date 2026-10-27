"""Evaluate a trained PPO policy against scripted opponents.

Loads a model from `--model`, plays N games vs the named opponent(s), and
reports win rate, average delegate share, and average reward. The action
space (discrete / continuous / coupled) is read from the model itself.
"""
import argparse
import statistics

from gymnasium.spaces import Box
from stable_baselines3 import PPO

from . import actions as _actions
from .gym_env import CampaignGymEnv


def action_kind_for(model):
    """The env action_kind a saved model was trained with. Box with 53 floats
    is the coupled space; other Box sizes are continuous; MultiDiscrete is
    the discrete bootstrap."""
    if isinstance(model.action_space, Box):
        if model.action_space.shape[0] == _actions.COUPLED_ACTION_DIM:
            return 'coupled'
        return 'continuous'
    return 'discrete'


def evaluate(model_path, opponent_names, num_games=100, num_turns=10, seed=1234,
             random_calendar_prob=0.0):
    model = PPO.load(model_path, device='cpu')
    env = CampaignGymEnv(opponent_names=tuple(opponent_names),
                         num_turns=num_turns, seed=seed,
                         action_kind=action_kind_for(model),
                         random_calendar_prob=random_calendar_prob)

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
    print(f'  Random calendar: {random_calendar_prob:.0%} of games')
    print(f'  Win rate:        {wins / num_games:.1%}')
    print(f'  Mean delegate %: {statistics.mean(delegate_shares):.1%} '
          f'(stdev {statistics.pstdev(delegate_shares):.1%})')
    print(f'  Mean ep reward:  {total_reward / num_games:+.2f}')
    return {'win_rate': wins / num_games,
            'delegate_share': statistics.mean(delegate_shares),
            'reward': total_reward / num_games}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True)
    p.add_argument('--opponents', nargs='+', default=['Default'])
    p.add_argument('--games', type=int, default=100)
    p.add_argument('--num-turns', type=int, default=10)
    p.add_argument('--seed', type=int, default=1234)
    p.add_argument('--random-calendar-prob', type=float, default=0.0,
                   help='Chance each game uses a shuffled primary calendar '
                        '(1.0 = always).')
    args = p.parse_args()
    evaluate(args.model, args.opponents, args.games, args.num_turns, args.seed,
             args.random_calendar_prob)


if __name__ == '__main__':
    main()
