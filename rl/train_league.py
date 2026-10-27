"""League-lite training entry point.

Each episode the worker env samples its opponent from one of three
buckets at configurable proportions:

    scripted  : pre-built heuristic opponents (always-spend strategies)
    anchor    : frozen checkpoints of prior strong models
    manifest  : rolling snapshots of the in-training policy (self-play)

Defaults bias toward scripted (55%) and anchor (30%) so the agent
constantly faces opponents that actually spend on ads and hours — that
prevents the v14 Nash-collapse where pure self-play converges to "don't
spend at all". Self-play snapshots stay in the mix at 15% so the
policy still co-adapts with newer versions of itself.

Anchors and --init-from must match the current observation size (it grows
with the issue count), so checkpoints from before an issue-set change can't
be used.

Usage (how v20 was trained — warm-started from v18 with a fresh, capped
policy std, mixed game lengths, half the games on a shuffled primary
calendar, and the decoder's ballot-access floor off; the game plays it with
the floor on, which evaluated best):
    python -m rl.train_league --steps 2000000 --envs 7 --subproc \\
        --action-kind coupled --net-arch 256 256 --num-turns 8 10 20 \\
        --scripted FocusedDefault EarlyIgnorer UpcomingFocus \\
                   BigStateFocus BigStateRush LateBlitz \\
                   AdMaximizer FundraiseHoarder \\
        --anchors runs/v18_issues8/model \\
        --init-from runs/v18_issues8/model --reset-std 10 --max-std 20 \\
        --ballot-floor-weeks -1 \\
        --bucket-weights 0.7 0.1 0.2 --random-calendar-prob 0.5 \\
        --snapshot-every 200000 --seed 18 --out runs/v20_mixed_lengths

Without --reset-std/--max-std, a warm start keeps the checkpoint's std and
can let it run away (see StdCapCallback).
"""
import argparse
import math
import os
import time

import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

from .gym_env import CampaignGymEnv
from .opponent import named_scripted
from .selfplay_pool import LeaguePool, SnapshotCallback


class StdCapCallback(BaseCallback):
    """Cap the Gaussian policy's std after every PPO update.

    Box actions are clipped to [-5, 5] before they reach the decoder, so once
    samples saturate, a wider std costs nothing in reward and an entropy bonus
    pushes it up without limit (v19 ended at std ~25,000). At that point the
    rollouts are coin flips per knob and the policy stops learning.
    """

    def __init__(self, max_std):
        super().__init__()
        self.max_log_std = math.log(max_std)

    def _on_rollout_start(self):
        with torch.no_grad():
            self.model.policy.log_std.clamp_(max=self.max_log_std)

    def _on_step(self):
        return True


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
    p.add_argument('--num-turns', type=int, nargs='+', default=[10],
                   help='Game length in weeks; several values pick one per '
                        'episode (the game offers 8, 10 and 20).')
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
    p.add_argument('--random-calendar-prob', type=float, default=0.0,
                   help='Chance each episode uses a shuffled primary calendar '
                        '(same as the game randomize-calendar option). 0.5 '
                        'trains on both fixed and shuffled schedules.')
    p.add_argument('--subproc', action='store_true',
                   help='Run envs in parallel processes (SubprocVecEnv). '
                        'Self-play snapshots still propagate via the manifest file.')
    p.add_argument('--ent-coef', type=float, default=None,
                   help='Entropy bonus. Default 0.01 for discrete actions, 0 for '
                        'the clipped Box ones (see StdCapCallback). Also '
                        'overrides the value saved in an --init-from model.')
    p.add_argument('--reset-std', type=float, default=None,
                   help='With --init-from: restart the policy std at this value.')
    p.add_argument('--max-std', type=float, default=None,
                   help='Cap the policy std after every update (Box actions).')
    p.add_argument('--ballot-floor-weeks', type=int, default=None,
                   help='Override rl.actions.BALLOT_FLOOR_WEEKS while training; '
                        '-1 turns the coupled decoder\'s ballot-access floor off.')
    args = p.parse_args()
    if args.ent_coef is None:
        args.ent_coef = 0.01 if args.action_kind == 'discrete' else 0.0
    box_actions = args.action_kind != 'discrete'
    if not box_actions and (args.reset_std or args.max_std):
        p.error('--reset-std/--max-std only apply to continuous/coupled actions')

    os.makedirs(args.out, exist_ok=True)
    snapshot_dir = os.path.join(args.out, 'snapshots')
    manifest_path = os.path.join(args.out, 'pool_manifest.txt')

    factory = make_factory(args.scripted, args.anchors, manifest_path,
                           tuple(args.bucket_weights))

    def make_env(env_seed):
        def _thunk():
            # Runs inside each SubprocVecEnv worker, so the override reaches
            # every decoder there (the agent's and the frozen opponents').
            if args.ballot_floor_weeks is not None:
                from . import actions
                actions.BALLOT_FLOOR_WEEKS = args.ballot_floor_weeks
            return CampaignGymEnv(num_turns=tuple(args.num_turns), seed=env_seed,
                                  opponent_factory=factory,
                                  action_kind=args.action_kind,
                                  random_calendar_prob=args.random_calendar_prob,
                                  seed_stride=args.envs)
        return _thunk

    vec_cls = SubprocVecEnv if args.subproc and args.envs > 1 else DummyVecEnv
    venv = vec_cls([make_env(args.seed + i) for i in range(args.envs)])

    if args.init_from:
        print('warm-starting from {}'.format(args.init_from))
        # Pass the seed through: otherwise load() re-seeds the envs and the
        # torch/numpy RNGs with the checkpoint's saved seed and --seed is ignored.
        model = PPO.load(args.init_from, env=venv, device='cpu', seed=args.seed)
        model.ent_coef = args.ent_coef
        if args.reset_std:
            with torch.no_grad():
                model.policy.log_std.fill_(math.log(args.reset_std))
    else:
        model = PPO(
            'MlpPolicy', venv,
            n_steps=args.n_steps,
            batch_size=min(256, args.envs * args.n_steps),
            learning_rate=3e-4, gamma=0.995, gae_lambda=0.95, ent_coef=args.ent_coef,
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
    print('  random calendar prob: {}'.format(args.random_calendar_prob))
    print('  game lengths: {}'.format(', '.join(map(str, args.num_turns))))
    print('  entropy coef: {}'.format(args.ent_coef))
    if args.ballot_floor_weeks is not None:
        print('  ballot floor weeks: {}'.format(args.ballot_floor_weeks))
    if box_actions:
        print('  policy std: start {:.1f}, cap {}'.format(
            float(model.policy.log_std.detach().exp().median()), args.max_std or 'none'))

    callbacks = [snapshot_cb]
    if args.max_std:
        callbacks.append(StdCapCallback(args.max_std))

    t0 = time.perf_counter()
    model.learn(total_timesteps=args.steps,
                callback=CallbackList(callbacks),
                progress_bar=False)
    elapsed = time.perf_counter() - t0
    print('Trained {:,} steps in {:.1f}s ({:.0f} steps/s)'.format(
        args.steps, elapsed, args.steps / elapsed))

    save_path = os.path.join(args.out, 'model')
    model.save(save_path)
    print('Saved final model to {}.zip'.format(save_path))


if __name__ == '__main__':
    main()
