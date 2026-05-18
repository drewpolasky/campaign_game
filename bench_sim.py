"""Throughput + profile benchmark for sim_balance.run_game.

Times the headless simulator across player counts and game lengths to
estimate how many games/sec we can produce for self-play RL.
"""
import cProfile
import pstats
import time
import sys

import sim_balance as sb


def bench(strategies, num_turns, n_games, label):
    seed = 0
    t0 = time.perf_counter()
    for i in range(n_games):
        sb.run_game(strategies, num_turns=num_turns, seed=seed + i)
    dt = time.perf_counter() - t0
    gps = n_games / dt
    turns = n_games * num_turns
    tps = turns / dt
    print(f'{label:30s}  {n_games:>5d} games  {dt:6.2f}s  '
          f'{gps:7.1f} games/s  {tps:8.1f} player-turns/s')
    return gps


def profile(strategies, num_turns, n_games, label):
    print(f'\n--- cProfile: {label} ({n_games} games, {num_turns} turns) ---')
    pr = cProfile.Profile()
    pr.enable()
    for i in range(n_games):
        sb.run_game(strategies, num_turns=num_turns, seed=i)
    pr.disable()
    stats = pstats.Stats(pr).sort_stats('cumulative')
    stats.print_stats(15)


def main():
    strategies_2p = [sb.ALL_STRATEGIES[0], sb.ALL_STRATEGIES[5]]  # Default, Balanced
    strategies_4p = sb.ALL_STRATEGIES[:4]

    print(f'Python {sys.version.split()[0]}')
    print('Throughput (single-threaded):')
    print('-' * 90)
    bench(strategies_2p, 20, 200, '2 players, 20 turns')
    bench(strategies_2p, 10, 400, '2 players, 10 turns')
    bench(strategies_2p,  8, 500, '2 players,  8 turns')
    bench(strategies_4p, 20, 100, '4 players, 20 turns')
    bench(strategies_4p, 10, 200, '4 players, 10 turns')
    bench(strategies_4p,  8, 250, '4 players,  8 turns')

    profile(strategies_2p, 20, 50, '2p/20t')
    profile(strategies_4p, 20, 50, '4p/20t')


if __name__ == '__main__':
    main()
