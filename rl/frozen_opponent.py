"""Opponent that wraps a frozen PPO checkpoint, plus a pool sampler.

Used for self-play training: each env episode samples one opponent from a
pool that includes the current strongest baseline plus a rolling window of
prior PPO snapshots. This stops the learning agent from forgetting how to
beat earlier versions of itself ("rock-paper-scissors cycles").
"""
import os
import random

from . import obs as _obs
from . import actions as _actions
from .opponent import Opponent


class FrozenPolicyOpponent(Opponent):
    """Wraps a saved PPO model. The model is loaded once on first use and
    shared across episodes — important so we don't pay torch import per
    `act` call."""

    def __init__(self, model_path: str, name: str = None, device: str = 'cpu'):
        self.model_path = model_path
        self.name = name or f'Frozen<{os.path.basename(model_path)}>'
        self.device = device
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from stable_baselines3 import PPO
            self._model = PPO.load(self.model_path, device=self.device)
        return self._model

    def act(self, sim, p_idx) -> int:
        model = self._ensure_model()
        obs = _obs.encode_obs(sim, agent_idx=p_idx)
        action, _ = model.predict(obs, deterministic=True)
        # Dispatch on the frozen model's own action space so a continuous
        # checkpoint and a discrete checkpoint can sit in the same pool.
        from gymnasium.spaces import Box
        if isinstance(model.action_space, Box):
            return _actions.decode_continuous_action(sim, p_idx, action)
        return _actions.decode_action(sim, p_idx, action)


class OpponentPool(Opponent):
    """An Opponent that delegates each turn to a sampled member of a pool.
    Sampling happens on `reset()` so one episode is consistent.

    Members are (name, opponent_factory_or_instance) pairs. Factories are
    called once and the result is cached, so loading torch models doesn't
    happen mid-episode.

    `weights` (optional) is a list of float weights matching `members`. Default
    is uniform.
    """

    name = 'OpponentPool'

    def __init__(self, members, weights=None, seed: int = None):
        self.members = []
        for entry in members:
            if isinstance(entry, tuple):
                name, op = entry
            else:
                op = entry
                name = getattr(op, 'name', 'unknown')
            self.members.append((name, op))
        if weights is None:
            self.weights = [1.0] * len(self.members)
        else:
            assert len(weights) == len(self.members)
            self.weights = list(weights)
        self.rng = random.Random(seed)
        self._current = None
        self._current_name = None

    def reset(self):
        names = [n for n, _ in self.members]
        opps = [o for _, o in self.members]
        idx = self._weighted_choice()
        self._current = opps[idx]
        self._current_name = names[idx]
        if hasattr(self._current, 'reset'):
            self._current.reset()

    def _weighted_choice(self):
        return self.rng.choices(range(len(self.members)), weights=self.weights, k=1)[0]

    def act(self, sim, p_idx) -> int:
        if self._current is None:
            self.reset()
        return self._current.act(sim, p_idx)

    @property
    def current_name(self):
        return self._current_name
