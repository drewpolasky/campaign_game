"""League-lite training entry point.

Each episode the worker env samples its opponent from one of three
buckets at configurable proportions:

    scripted  : pre-built heuristic opponents (always-spend strategies)
    anchor    : frozen checkpoints of prior strong models (v8, v11, v13)
    manifest  : rolling snapshots of the in-training policy (self-play)

Defaults bias toward scripted (55%) and anchor (30%) so the agent
constantly faces opponents that actually spend on ads and hours — that
prevents the v14 Nash-collapse where pure self-play converges to "don't
spend at all". Self-play snapshots stay in the mix at 15% so the
policy still co-adapts with newer versions of itself.

Usage:
    python -m rl.train_league --steps 3000000 \\
        --action-kind coupled --net-arch 256 256 \\
        --scripted FocusedDefault EarlyIgnorer UpcomingFocus \\
                   BigStateFocus BigStateRush LateBlitz \\
                   AdMaximizer FundraiseHoarder \\
        --anchors runs/v8_rebalanced/model runs/v11_diverse/model \\
                  runs/v13_rush_blitz/model \\
        --init-from runs/v13_rush_blitz/model \\
        --out runs/v15_league
"""
import argparse
import os
import time

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

from .gym_env import CampaignGymEnv
from .opponent import named_scripted
from .selfplay_pool import LeaguePool, SnapshotCallback


def make_factory(scripted_names, anchor_paths, manifest_path,
                 bucket_weights):
    """Builds the per-env opponent factory. Each env gets its own
    LeaguePool with an independent RNG seed; all share the same
    manifest file so a fresh self-play snapshot becomes visible to all
    workers on their next reset."""
    # Build the scripted opponent instances once at factory creation —
    # they're stateless, no reason for each env to instantiate its own.
    scripted_instances = [(name, named_scripted(name)) for name in scripted_names]

    def factory(env_seed):
        pool = LeaguePool(
            scripted_opponents=scripted_instances,
            anchor_paths=anchor_paths,
            manifest_path=manifest_path,
            bucket_weights=bucket_weights,
            seed=env_seed,
        )
        return [pool]
    return factory


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--steps', type=int, default=3_000_000)
    p.add_argument('--envs', type=int, default=4)
    p.add_argument('--num-turns', type=int, default=10)
    p.add_argument('--action-kind',
                   choices=['discrete', 'continuous', 'coupled'],
                   default='coupled')
    p.add_argument('--net-arch', nargs='+', type=int, default=[256, 256])
    p.add_argument('--scripted', nargs='+', required=True,
                   help='Scripted-opponent names to include in the pool.')
    p.add_argument('--anchors', nargs='+', default=[],
                   help='Frozen-checkpoint paths to anchor against.')
    p.add_argument('--bucket-weights', nargs=3, type=float,
                   default=[0.55, 0.30, 0.15],
                   help='(scripted, anchor, manifest) sample weights.')
    p.add_argument('--snapshot-every', type=int, default=100_000,
                   help='Save a new self-play snapshot every N steps.')
    p.add_argument('--max-pool-size', type=int, default=10,
                   help='Maximum rolling snapshots to keep in manifest.')
    p.add_argument('--init-from', default=None)
    p.add_argument('--out', default='runs/v15_league')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--n-steps', type=int, default=256)
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    snapshot_dir = os.path.join(args.out, 'snapshots')
    manifest_path = os.path.join(args.out, 'pool_manifest.txt')

    factory = make_factory(args.scripted, args.anchors, manifest_path,
                           tuple(args.bucket_weights))

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
            'MlpPolicy', venv,
            n_steps=args.n_steps,
            batch_size=min(256, args.envs * args.n_steps),
            learning_rate=3e-4, gamma=0.995, gae_lambda=0.95, ent_coef=0.01,
            verbose=1, seed=args.seed,
            policy_kwargs=dict(net_arch=list(args.net_arch)),
        )

    # Manifest starts empty — self-play bucket is dormant until the
    # first snapshot lands. The bucket-weight redistribution in
    # LeaguePool handles that automatically.
    snapshot_cb = SnapshotCallback(
        manifest_path=manifest_path,
        snapshot_dir=snapshot_dir,
        every_steps=args.snapshot_every,
        max_keep=args.max_pool_size,
        seed_paths=[],
        verbose=1,
    )

    print('League PPO: {:,} steps × {} envs, action_kind={}'.format(
        args.steps, args.envs, args.action_kind))
    print('  bucket weights: scripted={}, anchor={}, manifest={}'.format(
        *args.bucket_weights))
    print('  scripted opponents: {}'.format(', '.join(args.scripted)))
    print('  anchor checkpoints: {}'.format(', '.join(args.anchors) or '(none)'))

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
