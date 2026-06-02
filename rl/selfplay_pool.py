"""Pure self-play infrastructure.

A `DiskWatchedSelfPlayPool` reads its list of frozen-opponent checkpoints
from a manifest file on disk every episode reset. That lets a training
callback (`SnapshotCallback`) periodically save new policy snapshots and
just append them to the manifest — worker envs pick the change up on
their next reset without needing any direct reference plumbing.

This is the AlphaGo-style rolling-checkpoint setup: the agent plays
mostly against recent versions of itself, but a small tail of older
snapshots stays in the pool to keep the policy from forgetting older
strategies (the "rock-paper-scissors" failure mode of pure self-play).
"""
import os
import random
import time

from stable_baselines3.common.callbacks import BaseCallback

from .frozen_opponent import FrozenPolicyOpponent
from .opponent import Opponent


def _atomic_write(path, contents):
    """Write text via tmp + rename so concurrent readers don't see a
    half-written manifest."""
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(contents)
    os.replace(tmp, path)


def _read_manifest(path):
    try:
        with open(path) as f:
            return [line.strip() for line in f if line.strip()]
    except OSError:
        return []


class DiskWatchedSelfPlayPool(Opponent):
    """Opponent that, on each `reset()`, re-reads a manifest file and
    samples one checkpoint to be its opponent for this episode.

    Sampling is weighted toward more-recently-added checkpoints so the
    learner spends most of its time playing against near-current
    versions of itself, with a steady tail on older snapshots.

    Loaded models are cached in-process, so re-sampling a snapshot we've
    already seen is free. The cache is bounded — old entries get
    evicted when the manifest drops them.
    """

    name = 'SelfPlayPool'

    def __init__(self, manifest_path: str, seed: int = None,
                 recent_bias: float = 0.4, fallback: Opponent = None):
        """
        manifest_path : path to a newline-separated list of checkpoint
            paths (without the .zip suffix — same shape that
            PPO.load expects).
        recent_bias : per-rank weight bonus, so checkpoint i gets weight
            1 + recent_bias * i. Higher = more emphasis on the newest
            snapshots. 0 = uniform.
        fallback : opponent to fall back on if the manifest is empty
            (e.g. before the first snapshot has been written).
        """
        self.manifest_path = manifest_path
        self.recent_bias = recent_bias
        self.fallback = fallback
        self.rng = random.Random(seed)
        self._cache: dict = {}
        self._current = None
        self._current_name = None

    def _refresh_cache(self, paths):
        """Drop cached entries that are no longer in the manifest."""
        valid = set(paths)
        for stale in list(self._cache.keys()):
            if stale not in valid:
                self._cache.pop(stale, None)

    def reset(self):
        paths = _read_manifest(self.manifest_path)
        self._refresh_cache(paths)
        if not paths:
            self._current = self.fallback
            self._current_name = (
                getattr(self.fallback, 'name', 'empty') if self.fallback
                else 'empty')
            if self._current is not None and hasattr(self._current, 'reset'):
                self._current.reset()
            return

        weights = [1.0 + self.recent_bias * i for i in range(len(paths))]
        idx = self.rng.choices(range(len(paths)), weights=weights, k=1)[0]
        path = paths[idx]
        if path not in self._cache:
            try:
                self._cache[path] = FrozenPolicyOpponent(
                    path, name='self_{}'.format(idx))
            except Exception:
                # Bad checkpoint — fall back rather than crashing the env.
                self._current = self.fallback
                self._current_name = 'load_failed'
                return
        self._current = self._cache[path]
        self._current_name = 'self_ckpt_{}'.format(idx)
        if hasattr(self._current, 'reset'):
            self._current.reset()

    def act(self, sim, p_idx) -> int:
        if self._current is None:
            self.reset()
        return self._current.act(sim, p_idx)

    @property
    def current_name(self):
        return self._current_name


class LeaguePool(Opponent):
    """Mixed pool that samples each episode's opponent from one of three
    buckets at configurable proportions:
        scripted  — pre-built heuristic opponents (deterministic, diverse)
        anchor    — frozen PPO checkpoints of prior strong models (e.g. v13)
        manifest  — rolling self-play snapshots read from a disk manifest
                    (updated by SnapshotCallback during training)

    Designed to dodge the v14 pure-self-play Nash collapse: when the
    majority of episodes are vs scripted opponents that DO spend on ads
    and hours, the agent can never converge to "spend nothing" — that
    policy loses to AdMaximizer / FundraiseHoarder / BigStateRush every
    time. Self-play snapshots stay in the mix to keep the policy
    co-adapting with itself, but as a minority.

    Per-episode the bucket is sampled by `bucket_weights`, then the
    specific opponent within the bucket is uniform-random.
    """

    name = 'LeaguePool'

    def __init__(self, scripted_opponents, anchor_paths, manifest_path,
                 bucket_weights=(0.55, 0.30, 0.15), seed=None,
                 manifest_recent_bias=0.4):
        """
        scripted_opponents : list of (name, Opponent) pairs.
        anchor_paths       : list of frozen PPO checkpoint paths (no .zip).
        manifest_path      : path to the self-play snapshot manifest file.
        bucket_weights     : (scripted, anchor, manifest) — must be >= 0.
        manifest_recent_bias : within the manifest bucket, weight later
            entries more heavily (newer snapshots = more relevant).
        """
        self.scripted = list(scripted_opponents)
        self.anchor_paths = list(anchor_paths)
        self.manifest_path = manifest_path
        self.bucket_weights = list(bucket_weights)
        self.manifest_recent_bias = manifest_recent_bias
        self.rng = random.Random(seed)
        self._cache: dict = {}
        self._current = None
        self._current_name = None

    def _maybe_cache_frozen(self, path, display_name):
        if path not in self._cache:
            try:
                self._cache[path] = FrozenPolicyOpponent(path, name=display_name)
            except Exception:
                return None
        return self._cache[path]

    def reset(self):
        manifest_paths = _read_manifest(self.manifest_path)
        # Build the per-bucket effective weights, zeroing out buckets
        # that have no entries available.
        weights = list(self.bucket_weights)
        if not self.scripted:
            weights[0] = 0
        if not self.anchor_paths:
            weights[1] = 0
        if not manifest_paths:
            weights[2] = 0
        if sum(weights) <= 0:
            # No opponents available at all — punt.
            self._current = None
            self._current_name = 'empty'
            return

        bucket = self.rng.choices(
            ['scripted', 'anchor', 'manifest'], weights=weights, k=1)[0]

        if bucket == 'scripted':
            name, opp = self.rng.choice(self.scripted)
            self._current = opp
            self._current_name = 'scripted:{}'.format(name)
        elif bucket == 'anchor':
            path = self.rng.choice(self.anchor_paths)
            display = 'anchor:{}'.format(os.path.basename(os.path.dirname(path)))
            self._current = self._maybe_cache_frozen(path, display)
            self._current_name = display
            if self._current is None:
                # Failed load — fall back to a random scripted.
                if self.scripted:
                    name, opp = self.rng.choice(self.scripted)
                    self._current = opp
                    self._current_name = 'scripted:{}'.format(name)
        else:  # manifest
            n = len(manifest_paths)
            sample_weights = [
                1.0 + self.manifest_recent_bias * i for i in range(n)]
            idx = self.rng.choices(
                range(n), weights=sample_weights, k=1)[0]
            path = manifest_paths[idx]
            display = 'selfplay:{}'.format(idx)
            self._current = self._maybe_cache_frozen(path, display)
            self._current_name = display
            if self._current is None and self.scripted:
                name, opp = self.rng.choice(self.scripted)
                self._current = opp
                self._current_name = 'scripted:{}'.format(name)

        if self._current is not None and hasattr(self._current, 'reset'):
            self._current.reset()

    def act(self, sim, p_idx) -> int:
        if self._current is None:
            self.reset()
        if self._current is None:
            return 0  # truly empty pool — no-op
        return self._current.act(sim, p_idx)

    @property
    def current_name(self):
        return self._current_name


class SnapshotCallback(BaseCallback):
    """Periodically save the in-training policy to disk and append the
    new path to the self-play manifest. Worker envs pick up the new
    snapshot on their next episode reset.

    Old snapshots stay in the manifest (up to `max_keep`) so the agent
    keeps playing against earlier versions of itself in addition to the
    latest one. That tail is what prevents pure self-play from cycling.
    """

    def __init__(self, manifest_path: str, snapshot_dir: str,
                 every_steps: int = 50000, max_keep: int = 8,
                 seed_paths=None, verbose: int = 0):
        super().__init__(verbose)
        self.manifest_path = manifest_path
        self.snapshot_dir = snapshot_dir
        self.every_steps = every_steps
        self.max_keep = max_keep
        self.last_save_step = 0
        os.makedirs(snapshot_dir, exist_ok=True)
        # Seed the manifest. Seed entries can be older "anchor" models
        # (e.g. v13) that we want to keep facing throughout training to
        # keep the agent grounded against known-good baselines.
        seed_paths = list(seed_paths or [])
        _atomic_write(manifest_path, '\n'.join(seed_paths) + '\n')

    def _on_step(self) -> bool:
        if self.num_timesteps - self.last_save_step < self.every_steps:
            return True
        self.last_save_step = self.num_timesteps

        ts = time.strftime('%Y%m%d_%H%M%S')
        snap_path = os.path.join(
            self.snapshot_dir,
            'snapshot_{:09d}_{}'.format(self.num_timesteps, ts))
        try:
            self.model.save(snap_path)
        except Exception as e:
            if self.verbose:
                print('[SnapshotCallback] save failed: {}'.format(e))
            return True

        current = _read_manifest(self.manifest_path)
        current.append(snap_path)
        # Keep the most recent `max_keep` entries. Earlier entries
        # (including seed paths) at the front are evicted first as the
        # pool fills up.
        if len(current) > self.max_keep:
            current = current[-self.max_keep:]
        _atomic_write(self.manifest_path, '\n'.join(current) + '\n')

        if self.verbose:
            print('[SnapshotCallback] step={:,}  saved {}  pool size={}'.format(
                self.num_timesteps, os.path.basename(snap_path), len(current)))
        return True
