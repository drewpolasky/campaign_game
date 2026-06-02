"""Pure self-play training entry point.

Plays the in-training policy against a rolling pool of its own
snapshots. Every `snapshot_every` steps the current policy is saved and
appended to a manifest file; worker envs re-read the manifest each
episode reset and sample an opponent.

The pool is seeded with one or more "anchor" checkpoints (e.g. v13) so
the agent has something competent to play against before any of its
own snapshots have been written.

Usage:
    python -m rl.train_pure_selfplay --steps 4000000 \\
        --num-turns 10 --action-kind coupled --net-arch 256 256 \\
        --seed-anchors runs/v13_rush_blitz/model \\
        --init-from runs/v13_rush_blitz/model \\
        --out runs/v14_pure_selfplay
"""
import argparse
import os
import time

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

from .gym_env import CampaignGymEnv
from .selfplay_pool import DiskWatchedSelfPlayPool, SnapshotCallback
from .opponent import named_scripted


def make_opponent_factory(manifest_path, fallback_name='FocusedDefault'):
    """Build the closure that each env uses to construct its opponents.
    Every env gets its own SelfPlayPool wrapping the same manifest."""

    fallback = named_scripted(fallback_name)

    def factory(env_seed):
        pool = DiskWatchedSelfPlayPool(
            manifest_path=manifest_path,
            seed=env_seed,
            recent_bias=0.5,  # later snapshots ~2x as likely as oldest
            fallback=fallback,
        )
        return [pool]
    return factory


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--steps', type=int, default=4_000_000)
    p.add_argument('--envs', type=int, default=4)
    p.add_argument('--num-turns', type=int, default=10)
    p.add_argument('--action-kind',
                   choices=['discrete', 'continuous', 'coupled'],
                   default='coupled')
    p.add_argument('--net-arch', nargs='+', type=int, default=[256, 256])
    p.add_argument('--seed-anchors', nargs='+', default=[],
                   help='Initial checkpoint paths to seed the self-play '
                        'manifest with. Typically the best prior model so '
                        'training has a competent opponent on step 1.')
    p.add_argument('--snapshot-every', type=int, default=50_000,
                   help='Save a new snapshot and append to manifest every '
                        'N timesteps.')
    p.add_argument('--max-pool-size', type=int, default=8,
                   help='Maximum number of snapshots to keep in the pool. '
                        'Older snapshots get evicted FIFO.')
    p.add_argument('--init-from', default=None,
                   help='Warm-start the policy from an existing checkpoint. '
                        'Architecture and action space must match.')
    p.add_argument('--out', default='runs/v14_pure_selfplay')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--n-steps', type=int, default=256)
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    snapshot_dir = os.path.join(args.out, 'snapshots')
    manifest_path = os.path.join(args.out, 'pool_manifest.txt')

    factory = make_opponent_factory(manifest_path)

    def make_env(env_seed):
        def _thunk():
            return CampaignGymEnv(num_turns=args.num_turns, seed=env_seed,
                                  opponent_factory=factory,
                                  action_kind=args.action_kind)
        return _thunk

    venv = DummyVecEnv([make_env(args.seed + i) for i in range(args.envs)])

    if args.init_from:
        print('warm-starting from {}'.format(args.init_from))
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

    snapshot_cb = SnapshotCallback(
        manifest_path=manifest_path,
        snapshot_dir=snapshot_dir,
        every_steps=args.snapshot_every,
        max_keep=args.max_pool_size,
        seed_paths=args.seed_anchors,
        verbose=1,
    )

    print('Pure self-play PPO: {:,} steps × {} envs, action_kind={}, '
          'snapshot every {:,} steps, pool size {}'.format(
              args.steps, args.envs, args.action_kind,
              args.snapshot_every, args.max_pool_size))
    if args.seed_anchors:
        print('  seeded with: {}'.format(', '.join(args.seed_anchors)))

    t0 = time.perf_counter()
    model.learn(total_timesteps=args.steps,
                callback=snapshot_cb,
                progress_bar=False)
    elapsed = time.perf_counter() - t0
    print('Trained {:,} steps in {:.1f}s ({:.0f} steps/s)'.format(
        args.steps, elapsed, args.steps / elapsed))

    save_path = os.path.join(args.out, 'model')
    model.save(save_path)
    print('Saved final model to {}.zip'.format(save_path))


if __name__ == '__main__':
    main()
