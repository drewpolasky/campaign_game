"""Headless AI move generation for server-side seats.

Reuses the sim's strategy functions (``sim_balance.ALL_STRATEGIES`` —
Default / Aggressive / BigState / CloseOnly / MoneyMachine / Balanced), which
already decide a full week's allocation for a player. We run the chosen
strategy on a *throwaway deep copy* of the world and then read the resulting
allocations off the copy as a move payload — the authoritative GameState is
never touched. The service layer applies that payload through the same
validated path a human submission uses, so AI and human seats are handled
uniformly.

The strategy functions expect a ``Sim``-shaped object; ``_SimView`` /
``_PlayerView`` adapt an ``engine.GameState`` to the handful of attributes they
read (states, calendar, current_date, num_players, rng, and per-player
resources / money counters). State/District mutation happens on the shared,
already-0-based org/support/allocation lists, so no index translation is
needed there — only players are 1-based dict vs 0-based list.
"""
import copy
import os
import random
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import sim_balance  # noqa: E402

STRATEGIES = dict(sim_balance.ALL_STRATEGIES)
STRATEGY_NAMES = [name for name, _ in sim_balance.ALL_STRATEGIES]
DEFAULT_STRATEGY = 'Default'


class _PlayerView:
    """Minimal Sim-player facade over a (copied) Player. Strategies read/mutate
    .resources and accumulate .money_on_ads / .money_on_org."""

    def __init__(self, idx, player):
        self.idx = idx
        self.resources = player.resources     # shared list on the copy
        self.momentum = player.momentum
        self.positions = player.positions
        self.money_on_ads = 0
        self.money_on_org = 0


class _SimView:
    """Minimal Sim facade over a GameState (copied world)."""

    def __init__(self, states, player_views, calendar, current_date,
                 num_turns, event_of_week, past_elections, rng):
        self.states = states
        self.players = player_views
        self.calendar = calendar
        self.current_date = current_date
        self.num_turns = num_turns
        self.event_of_week = event_of_week
        self.past_elections = past_elections
        self.rng = rng
        self.num_players = len(player_views)


def compute_move(gs, seat, rng=None, strategy=None):
    """Return a move payload (see server/game_service.py) for an AI-controlled
    ``seat`` (1-based) in the current week of ``gs``. Pure — does not mutate
    ``gs``.
    """
    if rng is None:
        rng = gs.rng if gs.rng is not None else random.Random()
    seat_idx = seat - 1

    strat_name = strategy or getattr(gs.players[seat], 'aiStrategy', DEFAULT_STRATEGY)
    strat_fn = STRATEGIES.get(strat_name, sim_balance.strat_default)

    # Throwaway copy of the world so strategy side effects don't touch gs.
    states_copy = copy.deepcopy(gs.states)
    players_copy = {seat_no: copy.deepcopy(p) for seat_no, p in gs.players.items()}
    player_views = [_PlayerView(i, players_copy[i + 1]) for i in range(gs.num_players)]

    sim = _SimView(
        states=states_copy,
        player_views=player_views,
        calendar=list(gs.calendar),
        current_date=gs.current_date,
        num_turns=gs.num_turns,
        event_of_week=gs.event_of_week,
        past_elections=dict(gs.past_elections),
        rng=rng,
    )

    fundraising = strat_fn(sim, seat_idx)

    # Read the resulting allocation off the copy as a move payload.
    campaigning = {}
    ads = {}
    orgs = {}
    for name, st in states_copy.items():
        org_delta = st.organizations[seat_idx] - gs.states[name].organizations[seat_idx]
        if org_delta > 0:
            orgs[name] = int(org_delta)
        for d in st.districts:
            hours = d.campaigningThisTurn[seat_idx]
            if hours:
                campaigning.setdefault(name, {})[d.name] = int(hours)
            dollars = d.adsThisTurn[seat_idx]
            if dollars:
                ads.setdefault(name, {})[d.name] = int(dollars)

    return {
        'campaigning': campaigning,
        'ads': ads,
        'orgs': orgs,
        'fundraising': int(fundraising),
    }
