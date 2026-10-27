"""The trained neural AI as a server-side seat: it's offered when its weights
load, plays legal moves through the same path as the scripted AIs, falls back
to Default for a week if it fails, and beats Default.

Run:  python3 server/tests/test_neural_ai.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest  # noqa: E402

from server import ai, game_service, state_schema  # noqa: E402

pytestmark = pytest.mark.skipif(
    ai.NEURAL_STRATEGY not in ai.STRATEGIES,
    reason='neural AI not available (numpy or runs/v20_mixed_lengths/policy.npz missing)')


def _match(seats, num_turns=10, randomize_calendar=False, seed=1, issues_mode=True):
    cfg = {'num_turns': num_turns, 'issues_mode': issues_mode,
           'randomize_calendar': randomize_calendar, 'seed': seed,
           'seats': [{'name': s, 'controller': 'ai', 'ai_strategy': s} for s in seats]}
    doc, _, _ = game_service.create_match(cfg)
    gs, _ = state_schema.match_from_dict(doc)
    return gs


def _play_out(gs, seed, on_week=None):
    """Resolve every week with a JSON round trip in between, as the server
    does. ``on_week(gs)`` runs at the start of each week."""
    week = 0
    while not game_service.is_game_over(gs):
        if on_week is not None:
            on_week(gs)
        game_service.resolve_turn(gs, {}, random.Random(seed * 100 + week))
        gs, _ = state_schema.match_from_dict(state_schema.match_to_dict(gs))
        week += 1
    return gs


def test_neural_is_offered():
    assert ai.NEURAL_STRATEGY in ai.STRATEGY_NAMES


@pytest.mark.parametrize('seats,num_turns,shuffled,issues_mode', [
    (['Neural', 'Default'], 8, False, True),
    (['Aggressive', 'Neural'], 10, True, True),
    (['BigState', 'Neural', 'MoneyMachine'], 20, True, True),
    (['Neural', 'Balanced', 'CloseOnly', 'Neural'], 10, False, False),
])
def test_neural_plays_legal_moves_every_week(seats, num_turns, shuffled, issues_mode):
    gs = _match(seats, num_turns, shuffled, seed=num_turns, issues_mode=issues_mode)
    neural_seats = [i + 1 for i, s in enumerate(seats) if s == ai.NEURAL_STRATEGY]
    spent = {seat: 0 for seat in neural_seats}

    def check(gs):
        for seat in neural_seats:
            rng = random.Random(gs.current_date)
            # Straight from the policy, so a failure isn't hidden by the
            # Default fallback in compute_move.
            ai._play_on_copy(gs, seat - 1, ai.STRATEGIES[ai.NEURAL_STRATEGY], rng)
            move = ai.compute_move(gs, seat, rng=rng)
            ok, err = game_service.validate_move(gs, seat, move)
            assert ok, err
            spent[seat] += sum(move['orgs'].values()) + sum(
                h for d in move['campaigning'].values() for h in d.values())

    gs = _play_out(gs, seed=num_turns, on_week=check)
    assert all(spent.values()), spent  # it actually campaigns and builds orgs
    assert sum(p.delegateCount for p in gs.players.values()) > 0


def test_neural_beats_default():
    wins = 0
    for g in range(4):
        seats = ['Neural', 'Default'] if g % 2 == 0 else ['Default', 'Neural']
        gs = _play_out(_match(seats, num_turns=10, randomize_calendar=g >= 2, seed=40 + g), seed=40 + g)
        neural = gs.players[seats.index('Neural') + 1].delegateCount
        default = gs.players[seats.index('Default') + 1].delegateCount
        wins += neural > default
    assert wins == 4


def test_failing_ai_plays_default_for_the_week(monkeypatch):
    gs = _match(['Neural', 'Default'])

    def broken(sim, p_idx):
        sim.states[next(iter(sim.states))].organizations[p_idx] += 3  # partial work
        raise RuntimeError('policy blew up')

    monkeypatch.setitem(ai.STRATEGIES, ai.NEURAL_STRATEGY, broken)
    move = ai.compute_move(gs, 1, rng=random.Random(5))
    assert move == ai.compute_move(gs, 1, rng=random.Random(5), strategy='Default')


def test_unknown_ai_strategy_is_rejected():
    with pytest.raises(ValueError, match='unknown AI strategy'):
        _match(['Default', 'NoSuchAI'])


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
