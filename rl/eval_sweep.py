"""Evaluate every saved checkpoint against a fixed baseline panel.

Default panel: Random, Default, FocusedDefault. For multi-player models
(more than one opponent name in the model's training config), we mirror
the player count.

Usage:
    python -m rl.eval_sweep --models runs/v2/model runs/v3_2p10t/model \\
                            --num-turns 10 --games 100
"""
import argparse
import os

from rl.evaluate import evaluate


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--models', nargs='+', required=True,
                   help='paths (without .zip) to PPO checkpoints')
    p.add_argument('--baselines', nargs='+',
                   default=['Random', 'Default', 'FocusedDefault'])
    p.add_argument('--games', type=int, default=100)
    p.add_argument('--num-turns', type=int, default=10)
    p.add_argument('--seed', type=int, default=9999)
    p.add_argument('--num-opps', type=int, default=1,
                   help='number of opponents per game (use to test multi-player generalization)')
    args = p.parse_args()

    print(f'\n{"=" * 70}')
    print(f'Eval sweep: {len(args.models)} model(s) × {len(args.baselines)} baseline(s)')
    print(f'  num_turns={args.num_turns}  games={args.games}  num_opps={args.num_opps}')
    print('=' * 70)

    for model in args.models:
        for opp in args.baselines:
            opp_list = [opp] * args.num_opps
            evaluate(model, opp_list, num_games=args.games,
                     num_turns=args.num_turns, seed=args.seed)


if __name__ == '__main__':
    main()
