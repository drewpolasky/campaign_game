"""gymnasium.Env wrapper around CampaignGameEnv.

Adapts the project's zero-dep env to gymnasium's API so stable-baselines3
can train on it. Uses MultiDiscrete for the action space (matches
actions.ACTION_NVEC). Observation is a flat Box of float32.
"""
import numpy as np
import gymnasium as gym
from gymnasium import spaces

from . import obs as _obs
from . import actions as _actions
from .env import CampaignGameEnv
from .opponent import named_scripted


class CampaignGymEnv(gym.Env):
    """Gymnasium-compatible wrapper. Each `step` is one weekly turn."""

    metadata = {'render_modes': []}

    def __init__(self, opponent_names=('Default', 'Default'), num_turns=8,
                 seed=None, randomize_positions=True, opponent_factory=None,
                 action_kind='discrete'):
        """
        opponent_names: tuple of strategy names; only used when
            `opponent_factory` is None.
        opponent_factory: optional callable (env_seed) -> list[Opponent].
            Use for self-play, where opponents need to be sampled per
            env (e.g. opponent pool with its own RNG).
        action_kind: 'discrete' or 'continuous' — selects which action space
            and decoder are used.
        """
        super().__init__()
        self.opponent_names = tuple(opponent_names)
        self.num_turns = num_turns
        self._seed = seed
        self.randomize_positions = randomize_positions
        self.opponent_factory = opponent_factory
        self.action_kind = action_kind

        self.observation_space = spaces.Box(
            low=-5.0, high=5.0, shape=(_obs.OBS_DIM,), dtype=np.float32)
        if action_kind == 'continuous':
            self.action_space = spaces.Box(
                low=_actions.CONT_ACTION_LOW,
                high=_actions.CONT_ACTION_HIGH,
                shape=(_actions.CONT_ACTION_DIM,),
                dtype=np.float32,
            )
        else:
            self.action_space = spaces.MultiDiscrete(_actions.ACTION_NVEC)

        self._inner = None

    def _build(self):
        if self.opponent_factory is not None:
            opponents = self.opponent_factory(self._seed)
        else:
            opponents = [named_scripted(n) for n in self.opponent_names]
        return CampaignGameEnv(
            opponents=opponents,
            num_turns=self.num_turns,
            seed=self._seed,
            randomize_positions=self.randomize_positions,
            action_kind=self.action_kind,
        )

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._seed = seed
        if self._inner is None:
            self._inner = self._build()
        obs = self._inner.reset()
        return obs, {}

    def step(self, action):
        obs, reward, done, info = self._inner.step(action)
        # gymnasium splits done into terminated + truncated; the campaign
        # always ends when the calendar runs out, so terminated=done and
        # truncated is always False.
        return obs, reward, done, False, info

    def action_mask(self):
        return np.array(self._inner.action_mask(), dtype=bool)
