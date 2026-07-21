"""Verify: build a fresh match, serialize to JSON, rebuild, and confirm the
GameState survives the round-trip and is still resolvable by the engine.

Run:  python3 server/tests/test_state_roundtrip.py
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import engine  # noqa: E402
from server import game_world, state_schema  # noqa: E402

CONFIG = {
    'num_turns': 20,
    'issues_mode': True,
    'seats': [
        {'name': 'Alice', 'controller': 'human'},
        {'name': 'The Machine', 'controller': 'ai', 'ai_strategy': 'Aggressive'},
        {'name': 'Carol', 'controller': 'human'},
    ],
    'seed': 4242,
}


def test_build_and_roundtrip():
    gs = game_world.build_match(CONFIG, rng=random.Random(4242))

    # Basic shape of the freshly built world.
    assert gs.num_players == 3
    assert gs.num_turns == 20
    assert gs.current_date == 1
    assert gs.issues_mode is True
    assert len(gs.states) > 40, 'expected the full US map'
    assert all(len(p.resources) == 2 for p in gs.players.values())

    # Serialize -> JSON string -> back to dict -> rebuild GameState.
    doc = state_schema.match_to_dict(gs, match_id='TEST01', week_results={}, whose_turn=1)
    blob = json.dumps(doc)              # must be JSON-safe
    doc2 = json.loads(blob)
    gs2, meta = state_schema.match_from_dict(doc2, rng=random.Random(999))

    assert meta['match_id'] == 'TEST01'
    assert gs2.num_players == gs.num_players
    assert gs2.num_turns == gs.num_turns
    assert gs2.current_date == gs.current_date
    assert gs2.event_of_week == gs.event_of_week
    assert gs2.issues_mode == gs.issues_mode
    assert gs2.calendar == gs.calendar
    assert set(gs2.states.keys()) == set(gs.states.keys())

    # Deep field checks on a sample state + player.
    for name in list(gs.states.keys())[:5]:
        a, b = gs.states[name], gs2.states[name]
        assert a.organizations == b.organizations
        assert [d.name for d in a.districts] == [d.name for d in b.districts]
        for da, db in zip(a.districts, b.districts):
            assert da.population == db.population
            assert da.support == db.support
    for seat in gs.players:
        assert gs.players[seat].resources == gs2.players[seat].resources
        assert gs.players[seat].positions == gs2.players[seat].positions
        assert gs.players[seat].publicName == gs2.players[seat].publicName

    # The rebuilt state must still be resolvable by the engine (no crash,
    # week advances, delegates get awarded over a few weeks).
    for _ in range(6):
        engine.calc_state_opinions(gs2)
        gs2.current_date += 1
        engine.decide_contests(gs2)
        engine.reset_weekly(gs2)
    total_delegates = sum(p.delegateCount for p in gs2.players.values())
    assert total_delegates > 0, 'contests should have awarded delegates'


if __name__ == '__main__':
    test_build_and_roundtrip()
    print('OK: match builds, JSON round-trips, and stays engine-resolvable.')
