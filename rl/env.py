"""Single-agent Gym-style environment around the headless sim.

The learning agent occupies seat 0 (player index 0). All other seats are
filled by `Opponent` instances supplied at construction. Each `step` advances
exactly one weekly turn:

    1. Agent's action is decoded into resource allocations.
    2. Each opponent's `act` is called and resource allocations are written.
       (sim_balance's calc_end_turn runs as each player acts so fundraising
       income for the week is realized before opinions are calculated; we
       call calc_end_turn for the agent ourselves after `decode_action`.)
    3. World physics: calc_state_opinions, decide_contests, advance date,
       roll new event_of_week, reset weekly per-district counters.
    4. Compute reward and observation; episode ends when the calendar runs
       out.

The class doesn't import `gymnasium` so this stays a zero-dep module. A
gymnasium Env wrapper is a 10-line shim added later.
"""
import random

import numpy as np

from . import obs as _obs
from . import actions as _actions
from . import sim as _sim
from .opponent import Opponent


REWARD_DELEGATE_SCALE = 1.0 / 100.0   # +1 per ~100 delegates won that turn
REWARD_WIN_BONUS = 5.0
REWARD_LOSS_PENALTY = -5.0
# Shaping: reward each state-primary won (encourages contesting early small
# states whose delegate count alone wouldn't move the delegate-scale reward)
REWARD_STATE_WON = 0.5
# Shaping: reward momentum gain per turn (encourages the snowballing dynamic
# the heuristic agents exploit via early wins)
REWARD_MOMENTUM_SCALE = 1.0 / 30.0     # ~1 reward per +30 momentum


class CampaignGameEnv:
    """Gym-style API: reset() -> obs; step(action) -> (obs, reward, done, info)."""

    def __init__(self, opponents, num_turns=20, seed=None,
                 randomize_positions=True, action_kind='discrete'):
        """
        action_kind: 'discrete' (MultiDiscrete bootstrap) or 'continuous' (Box).
            Affects which decoder is used in step().
        """
        if not opponents:
            raise ValueError('CampaignGameEnv needs at least one opponent.')
        if action_kind not in ('discrete', 'continuous'):
            raise ValueError(f'unknown action_kind: {action_kind}')
        self.opponents = list(opponents)
        self.num_players = 1 + len(self.opponents)
        if self.num_players > _obs.MAX_PLAYERS:
            raise ValueError(
                f'too many players ({self.num_players}); '
                f'MAX_PLAYERS={_obs.MAX_PLAYERS}')
        self.num_turns = num_turns
        self.randomize_positions = randomize_positions
        self.action_kind = action_kind
        self.base_seed = seed if seed is not None else random.randrange(1 << 30)
        self.episode_count = 0
        self.sim = None
        self.last_delegates = 0

    @property
    def observation_dim(self):
        return _obs.OBS_DIM

    @property
    def action_nvec(self):
        return _actions.ACTION_NVEC

    def reset(self):
        # The agent's "strategy_fn" is a no-op stub; we never call it because
        # the env applies the agent's action manually before stepping the
        # opponents. Sim still needs *something* in that slot.
        agent_stub = ('Agent', _agent_stub_strategy)
        strategies = [agent_stub] + [(opp.name, _opp_stub) for opp in self.opponents]
        seed = self.base_seed + self.episode_count
        self.episode_count += 1
        self.sim = _sim.Sim(strategies, num_turns=self.num_turns, seed=seed,
                            randomize_positions=self.randomize_positions)
        for opp in self.opponents:
            opp.reset()
        self.last_delegates = 0
        self.last_momentum = 0.0
        self.last_states_won = 0
        return _obs.encode_obs(self.sim, agent_idx=0)

    def step(self, action):
        sim = self.sim
        if sim is None:
            raise RuntimeError('reset() must be called before step().')
        if sim.current_date > sim.num_turns:
            raise RuntimeError('episode already ended; call reset().')

        # 1. Apply agent action and book its end-of-turn fundraising.
        if self.action_kind == 'continuous':
            agent_fundraising = _actions.decode_continuous_action(sim, 0, action)
        else:
            agent_fundraising = _actions.decode_action(sim, 0, action)
        _sim.calc_end_turn(sim, 0, agent_fundraising)
        sim.players[0].campaign_hours_total += sum(
            d.campaigningThisTurn[0]
            for st in sim.states.values() for d in st.districts)

        # 2. Apply each opponent and book their end-of-turn fundraising.
        for slot, opp in enumerate(self.opponents, start=1):
            fundraising = opp.act(sim, slot)
            _sim.calc_end_turn(sim, slot, fundraising)
            sim.players[slot].campaign_hours_total += sum(
                d.campaigningThisTurn[slot]
                for st in sim.states.values() for d in st.districts)

        # 3. World physics for the week.
        _sim.calc_state_opinions(sim)
        _sim.decide_contests(sim)

        # 4. Compute reward.
        agent = sim.players[0]
        cur = agent.delegate_count
        delegates_this_turn = cur - self.last_delegates
        self.last_delegates = cur
        reward = delegates_this_turn * REWARD_DELEGATE_SCALE

        # Shaping: credit state-primary wins (helps the agent value early
        # small-state contests for their state-win bonus, not just delegates).
        states_won_now = len(agent.states_won)
        states_won_this_turn = states_won_now - self.last_states_won
        self.last_states_won = states_won_now
        reward += states_won_this_turn * REWARD_STATE_WON

        # Shaping: credit momentum changes (rewards the snowball — winning
        # early gives durable momentum that boosts future support).
        cur_mom = agent.momentum
        d_mom = cur_mom - self.last_momentum
        self.last_momentum = cur_mom
        reward += d_mom * REWARD_MOMENTUM_SCALE

        # 5. Advance.
        sim.current_date += 1
        import state_issues
        sim.event_of_week = sim.rng.randint(0, len(state_issues.ISSUES) - 1)
        _sim.reset_weekly(sim)

        done = sim.current_date > sim.num_turns
        if done:
            ranks = sorted(range(self.num_players),
                           key=lambda i: sim.players[i].delegate_count,
                           reverse=True)
            if ranks[0] == 0:
                reward += REWARD_WIN_BONUS
            else:
                reward += REWARD_LOSS_PENALTY

        next_obs = _obs.encode_obs(sim, agent_idx=0)
        info = {
            'agent_delegates': sim.players[0].delegate_count,
            'opp_delegates': [sim.players[i].delegate_count
                              for i in range(1, self.num_players)],
            'turn': sim.current_date - 1,
        }
        if done:
            # For opponent-pool training: log which opponent variant we
            # actually faced this episode.
            opp = self.opponents[0]
            info['opponent_name'] = (
                getattr(opp, 'current_name', None) or
                getattr(opp, 'name', 'unknown')
            )
        return next_obs, float(reward), done, info

    def action_mask(self):
        """Boolean mask over target_state component of the action."""
        return _actions.active_state_mask(self.sim)


# Strategy stubs the Sim's run_game would call. The env never invokes
# run_game, so these only exist so the Sim ctor's strategy bookkeeping is
# satisfied. They return 0 fundraising hours and write no allocations.
def _agent_stub_strategy(sim, p_idx):
    return 0


def _opp_stub(sim, p_idx):
    return 0
