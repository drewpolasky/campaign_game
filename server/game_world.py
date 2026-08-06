"""Build a fresh match world from a config dict, headlessly.

Reuses the sim's data-file loaders (``sim_balance.load_states`` /
``load_calendar``) so the server builds exactly the same map/calendar the
game and RL harness use — no third copy of the setup logic. Those loaders read
data files relative to the process cwd, so we run them with cwd pinned to the
repo root.

Config shape (all keys optional except seats):

    {
      "num_turns": 20,            # 8 | 10 | 20
      "issues_mode": false,
      "seats": [
        {"name": "Alice", "controller": "human"},
        {"name": "The Machine", "controller": "ai", "ai_strategy": "Aggressive"},
        ...
      ],
      "seed": 12345               # optional; seeds event-of-week + positions
    }

Returns an ``engine.GameState`` for a week-1 fresh game. Serialize it with
``state_schema.match_to_dict``.
"""
import contextlib
import os
import random
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import sim_balance  # noqa: E402  (reused world/calendar loaders)
import state_issues  # noqa: E402
import engine  # noqa: E402
from Player import Player  # noqa: E402

VALID_TURN_LENGTHS = (8, 10, 20)
DEFAULT_AI_STRATEGY = 'Default'


@contextlib.contextmanager
def _cwd(path):
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def build_match(config, rng=None):
    """Construct a fresh, week-1 GameState from ``config``.

    ``rng`` (a random.Random) makes creation reproducible: it seeds the
    event-of-week roll and any randomized issue positions. If omitted, one is
    derived from ``config['seed']`` when present, else a fresh Random().
    """
    if rng is None:
        seed = config.get('seed')
        rng = random.Random(seed) if seed is not None else random.Random()

    seats = config['seats']
    num_players = len(seats)
    if num_players < 2 or num_players > 10:
        raise ValueError('a match needs between 2 and 10 seats')

    num_turns = config.get('num_turns', 20)
    if num_turns not in VALID_TURN_LENGTHS:
        raise ValueError('num_turns must be one of {}'.format(VALID_TURN_LENGTHS))

    issues_mode = bool(config.get('issues_mode', False))
    n_issues = len(state_issues.ISSUES)

    # World + calendar from the shared data-file loaders (cwd-pinned). When
    # randomize_calendar is set, build a randomized primary schedule (small
    # states first, ramping up) via the shared engine helper instead — the
    # same code the desktop uses, so both versions behave identically. The
    # resulting calendar is persisted in the match doc, so reloads are stable.
    with _cwd(_REPO_ROOT):
        states = sim_balance.load_states()
        if config.get('randomize_calendar'):
            calendar = engine.randomize_calendar(states, num_turns, rng)
        else:
            calendar = sim_balance.load_calendar(num_turns)

    # Players (1-based dict), zero-initialized.
    players = {}
    for i, seat_cfg in enumerate(seats):
        seat = i + 1
        p = Player('P{}'.format(seat))
        p.publicName = seat_cfg.get('name') or 'Candidate {}'.format(seat)
        controller = seat_cfg.get('controller', 'human')
        p.isHuman = 'human' if controller == 'human' else 'AI'
        p.aiStrategy = seat_cfg.get('ai_strategy') or DEFAULT_AI_STRATEGY
        # Issue positions:
        #   explicit config          -> use as given
        #   no issues mode           -> neutral
        #   AI in issues mode        -> randomized server-side
        #   human in issues mode     -> LEFT EMPTY; the player picks their own
        #                               platform when they first open their seat.
        if seat_cfg.get('positions') is not None:
            p.positions = list(seat_cfg['positions'])
        elif not issues_mode:
            p.positions = [0] * n_issues
        elif controller == 'ai':
            p.positions = [rng.choice([-1, 0, 1]) for _ in range(n_issues)]
        else:
            p.positions = []
        players[seat] = p

    # Zero-init per-state organizations and per-district allocations/support.
    for st in states.values():
        for i in range(num_players):
            st.setOrganization(i, 0)
            for d in st.districts:
                d.setSupport(i, 0)
                d.setCampaigningThisTurn(i, 0)
                d.setAdsThisTurn(i, 0)

    gs = engine.GameState(
        states=states,
        players=players,
        calendar=calendar,
        current_date=1,
        num_turns=num_turns,
        event_of_week=rng.randint(0, n_issues - 1),
        issues_mode=issues_mode,
        past_elections={},
        rng=rng,
    )

    # Prime polling averages the way the game does before the first turn.
    for st in gs.states.values():
        st.updateSupport(gs.num_players, gs.calendar, gs.current_date)

    return gs
