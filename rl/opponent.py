"""Opponent abstractions used by the RL env.

An Opponent's job is to fill in resource allocations for one player on its
turn. The env calls `opp.act(sim, p_idx)` and expects fundraising_hours back.
This matches the contract of sim_balance's strategy functions, which means
existing scripted strategies adapt with one wrapper.
"""
from typing import Callable

import sim_balance as _sb


class Opponent:
    """Abstract base. Subclasses must implement `act`."""
    name = 'Base'

    def act(self, sim, p_idx) -> int:
        raise NotImplementedError

    def reset(self):
        """Optional: called by env at episode reset for stateful opponents."""
        pass


class ScriptedOpponent(Opponent):
    """Wraps any sim_balance-style (sim, p_idx) -> fundraising_hours fn."""

    def __init__(self, name: str, strategy_fn: Callable):
        self.name = name
        self.fn = strategy_fn

    def act(self, sim, p_idx) -> int:
        return self.fn(sim, p_idx)


class RandomOpponent(Opponent):
    """Uses our discrete action decoder with uniform random actions. Useful
    as a sanity-check baseline opponent."""
    name = 'Random'

    def __init__(self, seed: int = 0):
        import random
        self.rng = random.Random(seed)

    def act(self, sim, p_idx) -> int:
        from . import actions as _actions
        a = _actions.random_action(self.rng)
        return _actions.decode_action(sim, p_idx, a)


class FocusedScriptedOpponent(Opponent):
    """A scripted opponent that *also* uses our action decoder, so the
    learning agent isn't getting a free advantage just from target-focusing.

    Picks the most urgent active state as its target each turn, with full
    aggression. Calibrated to be a stronger baseline than the bare
    ScriptedOpponent for evaluating whether an RL policy is actually
    learning, not just exploiting an asymmetry in the action decoder.
    """
    name = 'FocusedDefault'

    def act(self, sim, p_idx) -> int:
        from . import actions as _actions
        # Pick the active state nearest to its primary.
        order = _actions._calendar_state_order(sim)
        target_idx = 0
        best_tte = 999
        for i, name in enumerate(order[:_actions.NUM_TARGET_STATES]):
            for ename, week in sim.calendar:
                if ename == name:
                    tte = week - sim.current_date
                    if 0 <= tte < best_tte:
                        best_tte = tte
                        target_idx = i
                    break
        # Aggression: 100% to target. Lean: balanced. Fundraising: 20 hours.
        action = (target_idx, 0, 1, 1)
        return _actions.decode_action(sim, p_idx, action)


def named_scripted(name: str = 'Default') -> Opponent:
    """Look up a strategy by name. Recognizes our own opponent classes too."""
    if name == 'FocusedDefault':
        return FocusedScriptedOpponent()
    if name == 'Random':
        return RandomOpponent()
    for n, fn in _sb.ALL_STRATEGIES:
        if n == name:
            return ScriptedOpponent(n, fn)
    raise KeyError(f'unknown strategy: {name}')
