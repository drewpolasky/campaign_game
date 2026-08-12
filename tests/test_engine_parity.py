"""Parity test: engine.py must reproduce the shipped CampaignGame rules exactly.

Builds a small but non-trivial game world, deep-copies it, and runs one full
week rollover (per-player calcEndTurn -> calculateStateOpinions -> advance week
-> decideContests) two ways:

  * REFERENCE: the actual functions in CampaignGame.py, driven through its
    module globals (this is the shipped behavior we must not change).
  * ENGINE:    engine.calc_end_turn / calc_state_opinions / decide_contests on
    an explicit GameState.

Both share the same rng seed, so the only source of randomness
(decideContests' vote draws) is identical. We then assert district support,
player momentum / delegates / resources, past elections, and the weekResults
report structure all match.

Run directly:  python3 tests/test_engine_parity.py
Or via pytest:  pytest tests/test_engine_parity.py
"""
import copy
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from State import State, District
from Player import Player
import state_issues
import engine

SEED = 12345
NUM_TURNS = 20
CURRENT_DATE = 5
EVENT_OF_WEEK = 0

# Contest resolution fires when `week + 1 == currentDate` AFTER the rollover's
# `currentDate += 1`. The sequence below advances CURRENT_DATE (5) -> 6, so a
# state whose election week is 5 resolves this rollover. StateA (week 5) does;
# StateB (week 9) does not, exercising the skip path. StateA's orgs include a
# 0 (player 2 not on the ballot), exercising the org-gate in the vote loop.
CALENDAR = [('StateA', 5), ('StateB', 9)]


def _build_world():
    """Construct three players and two multi-district states with varied
    orgs / support / allocations, so every branch of the rules gets touched.
    Returns (players_dict_1based, states_dict)."""
    n_issues = len(state_issues.ISSUES)
    num_players = 3

    players = {}
    for pid in range(1, num_players + 1):
        p = Player('P{}'.format(pid))
        p.publicName = 'Candidate {}'.format(pid)
        p.positions = [((pid + k) % 3) - 1 for k in range(n_issues)]  # in {-1,0,1}
        p.momentum = [10.0, -4.0, 25.0][pid - 1]
        p.resources = [80, [50000, 120000, 8000][pid - 1]]
        p.delegateCount = [3, 0, 7][pid - 1]
        players[pid] = p

    # Per-state, per-player organization tiers. Include a 0 so org-0 support
    # (which the real game still grants) is exercised.
    orgs = {
        'StateA': [2, 0, 1],
        'StateB': [1, 3, 0],
    }
    # District definitions: (state, name, population, positions)
    district_defs = {
        'StateA': [('A1', 3, [1, 0, -1]), ('A2', 5, [-1, 1, 0])],
        'StateB': [('B1', 4, [0, -1, 1]), ('B2', 2, [1, 1, -1]), ('B3', 6, [0, 0, 0])],
    }
    # Per (state, district) campaigning hours and ad spend per player.
    camp = {
        ('StateA', 'A1'): [4, 0, 2],
        ('StateA', 'A2'): [0, 3, 1],
        ('StateB', 'B1'): [2, 2, 0],
        ('StateB', 'B2'): [0, 0, 5],
        ('StateB', 'B3'): [1, 0, 0],
    }
    ads = {
        ('StateA', 'A1'): [2000, 0, 1000],
        ('StateA', 'A2'): [0, 3000, 500],
        ('StateB', 'B1'): [1500, 1500, 0],
        ('StateB', 'B2'): [0, 0, 4000],
        ('StateB', 'B3'): [1000, 0, 0],
    }
    seed_support = {
        ('StateA', 'A1'): [40, 10, 25],
        ('StateA', 'A2'): [15, 55, 20],
        ('StateB', 'B1'): [30, 30, 5],
        ('StateB', 'B2'): [5, 8, 60],
        ('StateB', 'B3'): [12, 3, 1],
    }

    states = {}
    for sname in ('StateA', 'StateB'):
        # State positions: length n_issues, mixed stances.
        st = State(sname, [])
        st.setOpinions([0] * n_issues)
        st.positions = [((ord(sname[-1]) + k) % 3) - 1 for k in range(n_issues)]
        for i in range(num_players):
            st.setOrganization(i, orgs[sname][i])
        for (dname, pop, dpos) in district_defs[sname]:
            d = District(dname, pop, sname)
            d.setPositions(dpos)
            for i in range(num_players):
                d.setSupport(i, seed_support[(sname, dname)][i])
                d.setCampaigningThisTurn(i, camp[(sname, dname)][i])
                d.setAdsThisTurn(i, ads[(sname, dname)][i])
            st.addDistrict(d)
        # Prime polling averages the way the game does before a rollover.
        st.updateSupport(num_players, CALENDAR, CURRENT_DATE)
        states[sname] = st

    return players, states


def _run_reference(players, states):
    """Drive the shipped CampaignGame functions via its module globals."""
    import CampaignGame as cg

    cg.players = players
    cg.states = states
    cg.numPlayers = len(players)
    cg.numTurns = NUM_TURNS
    cg.currentDate = CURRENT_DATE
    cg.calendarOfContests = CALENDAR
    cg.issuesMode = True
    cg.eventOfTheWeek = EVENT_OF_WEEK
    cg.pastElections = {}
    cg.weekResults = {}

    random.seed(SEED)
    # Per-player money step (uses global `player`).
    fundraising = {1: 20, 2: 40, 3: 0}
    for pid in range(1, len(players) + 1):
        cg.player = pid
        cg.calcEndTurn(fundraising[pid])
    cg.calculateStateOpinions()
    cg.currentDate += 1
    cg.decideContests()

    return {
        'week_results': cg.weekResults,
        'past_elections': cg.pastElections,
    }


def _run_engine(players, states):
    """Drive engine.py on an explicit GameState. Uses the `random` module as
    the rng (re-seeded to SEED) so the draw sequence matches the reference."""
    gs = engine.GameState(
        states=states,
        players=players,
        calendar=CALENDAR,
        current_date=CURRENT_DATE,
        num_turns=NUM_TURNS,
        event_of_week=EVENT_OF_WEEK,
        issues_mode=True,
        past_elections={},
        rng=random,
    )

    random.seed(SEED)
    fundraising = {1: 20, 2: 40, 3: 0}
    for pid in range(1, len(players) + 1):
        engine.calc_end_turn(gs, pid, fundraising[pid])
    engine.calc_state_opinions(gs)
    gs.current_date += 1
    week_results = engine.decide_contests(gs)

    return {
        'week_results': week_results,
        'past_elections': gs.past_elections,
    }


def _snapshot(players, states):
    """Flatten the mutable game state into comparable primitives."""
    snap = {'players': {}, 'districts': {}}
    for pid, p in players.items():
        snap['players'][pid] = {
            'momentum': p.momentum,
            'delegateCount': p.delegateCount,
            'resources': list(p.resources),
        }
    for sname, st in states.items():
        for d in st.districts:
            snap['districts'][(sname, d.name)] = {
                'support': list(d.support),
                'polling': list(d.pollingAverage),
            }
    return snap


def _assert_close(a, b, path):
    if isinstance(a, float) or isinstance(b, float):
        assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9), \
            '{}: {} != {}'.format(path, a, b)
    else:
        assert a == b, '{}: {} != {}'.format(path, a, b)


def test_engine_matches_shipped_rules():
    base_players, base_states = _build_world()

    ref_players = copy.deepcopy(base_players)
    ref_states = copy.deepcopy(base_states)
    eng_players = copy.deepcopy(base_players)
    eng_states = copy.deepcopy(base_states)

    ref_out = _run_reference(ref_players, ref_states)
    eng_out = _run_engine(eng_players, eng_states)

    ref_snap = _snapshot(ref_players, ref_states)
    eng_snap = _snapshot(eng_players, eng_states)

    # Player-level state.
    for pid in ref_snap['players']:
        for key in ('momentum', 'delegateCount'):
            _assert_close(ref_snap['players'][pid][key],
                          eng_snap['players'][pid][key],
                          'player {} {}'.format(pid, key))
        assert ref_snap['players'][pid]['resources'] == eng_snap['players'][pid]['resources'], \
            'player {} resources: {} != {}'.format(
                pid, ref_snap['players'][pid]['resources'],
                eng_snap['players'][pid]['resources'])

    # District-level support + polling.
    for key in ref_snap['districts']:
        assert ref_snap['districts'][key]['support'] == eng_snap['districts'][key]['support'], \
            '{} support: {} != {}'.format(key, ref_snap['districts'][key]['support'],
                                          eng_snap['districts'][key]['support'])
        for a, b in zip(ref_snap['districts'][key]['polling'],
                        eng_snap['districts'][key]['polling']):
            _assert_close(a, b, '{} polling'.format(key))

    # Contest outcomes.
    assert ref_out['past_elections'] == eng_out['past_elections'], \
        'past_elections: {} != {}'.format(ref_out['past_elections'], eng_out['past_elections'])
    assert ref_out['week_results'] == eng_out['week_results'], \
        'week_results mismatch:\n  ref={}\n  eng={}'.format(
            ref_out['week_results'], eng_out['week_results'])


# Golden snapshot of the engine's output for the fixed world above. Because
# CampaignGame now delegates to the engine, the parity test alone can no longer
# catch an accidental change to the engine's numbers (both sides would move
# together). This locks the canonical values so any rule change is deliberate.
# Verified equal to the ORIGINAL shipped CampaignGame code at extraction time.
# Momentum for players 1 and 3 was re-recorded when the at-large momentum block
# was fixed to credit the aggregate state winner instead of the leftover
# district-loop `winner`. StateA splits its districts and is won by player 1, so
# its at-large momentum moved from player 3 to player 1; the pool total is
# unchanged (60.35 either way), as are delegates, money, support, and the winner.
GOLDEN_PLAYERS = {
    1: {'momentum': 32.183867387987235, 'delegateCount': 7.666666666666666, 'resources': [80, 152060]},
    2: {'momentum': -1.0, 'delegateCount': 0, 'resources': [80, 301654]},
    3: {'momentum': 28.167048134276605, 'delegateCount': 10.333333333333334, 'resources': [80, 29716]},
}
GOLDEN_SUPPORT = {
    ('StateA', 'A1'): [57, 10, 32],
    ('StateA', 'A2'): [16, 79, 24],
    ('StateB', 'B1'): [38, 37, 5],
    ('StateB', 'B2'): [5, 9, 91],
    ('StateB', 'B3'): [18, 4, 1],
}
GOLDEN_PAST_ELECTIONS = {'StateA': 1}


def test_engine_golden_values():
    players, states = _build_world()
    out = _run_engine(players, states)
    snap = _snapshot(players, states)

    for pid, exp in GOLDEN_PLAYERS.items():
        got = snap['players'][pid]
        _assert_close(exp['momentum'], got['momentum'], 'golden player {} momentum'.format(pid))
        _assert_close(exp['delegateCount'], got['delegateCount'], 'golden player {} delegates'.format(pid))
        assert exp['resources'] == got['resources'], \
            'golden player {} resources: {} != {}'.format(pid, exp['resources'], got['resources'])

    for key, exp in GOLDEN_SUPPORT.items():
        assert snap['districts'][key]['support'] == exp, \
            'golden {} support: {} != {}'.format(key, snap['districts'][key]['support'], exp)

    assert out['past_elections'] == GOLDEN_PAST_ELECTIONS, \
        'golden past_elections: {} != {}'.format(out['past_elections'], GOLDEN_PAST_ELECTIONS)


if __name__ == '__main__':
    test_engine_matches_shipped_rules()
    test_engine_golden_values()
    print('OK: engine.py matches shipped CampaignGame rules exactly.')
    print('OK: engine.py golden values locked.')
