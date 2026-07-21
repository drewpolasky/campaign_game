"""End-to-end test of the headless game service: create a match, play every
week (AI + a hand-crafted human move), confirm a legal game completes with a
winner, and that move validation rejects illegal submissions.

Run:  python3 server/tests/test_game_service.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server import game_service, state_schema  # noqa: E402

BASE_CONFIG = {
    'num_turns': 10,
    'issues_mode': False,
    'seats': [
        {'name': 'Human', 'controller': 'human'},
        {'name': 'AI-Agg', 'controller': 'ai', 'ai_strategy': 'Aggressive'},
        {'name': 'AI-Big', 'controller': 'ai', 'ai_strategy': 'BigState'},
        {'name': 'AI-Def', 'controller': 'ai', 'ai_strategy': 'Default'},
    ],
    'seed': 20250720,
}


def _fresh_gs():
    doc, tokens, _spectator = game_service.create_match(BASE_CONFIG)
    gs, meta = state_schema.match_from_dict(doc)
    return gs, doc, tokens


def _first_upcoming_state(gs):
    """A state whose contest hasn't happened yet, with its districts."""
    for name, week in gs.calendar:
        if week >= gs.current_date and name in gs.states:
            return name
    return next(iter(gs.states))


def test_create_match():
    gs, doc, tokens = _fresh_gs()
    assert doc['match_id'] and len(doc['match_id']) == game_service.MATCH_ID_LEN
    # Exactly the human seats get magic-link tokens.
    assert set(tokens.keys()) == {1}
    assert gs.num_players == 4
    assert gs.current_date == 1


def test_org_cost_curve():
    # 0->1 and 1->2 are $10k each; tier 2 is $20k, tier 3 is $30k.
    assert game_service.org_build_cost(0, 1) == 10000
    assert game_service.org_build_cost(0, 2) == 20000
    assert game_service.org_build_cost(0, 3) == 40000   # 10k+10k+20k
    assert game_service.org_build_cost(2, 1) == 20000


def test_human_move_applies():
    gs, _, _ = _fresh_gs()
    state = _first_upcoming_state(gs)
    dnames = [d.name for d in gs.states[state].districts]
    money_before = gs.players[1].resources[1]

    move = {
        'campaigning': {state: {dnames[0]: 10}},
        'ads': {state: {dnames[0]: 5000}},
        'orgs': {state: 1},
    }
    ok, err = game_service.validate_move(gs, 1, move)
    assert ok, err
    game_service.apply_move(gs, 1, move)

    assert gs.states[state].organizations[0] == 1               # org built
    assert gs.states[state].districts[0].campaigningThisTurn[0] == 10
    assert gs.states[state].districts[0].adsThisTurn[0] == 5000
    assert gs.players[1].resources[1] == money_before - 5000 - 10000  # ads + org


def test_validation_rejects():
    gs, _, _ = _fresh_gs()
    state = _first_upcoming_state(gs)
    dnames = [d.name for d in gs.states[state].districts]

    # Over time budget.
    ok, err = game_service.validate_move(gs, 1, {'campaigning': {state: {dnames[0]: 999}}})
    assert not ok and 'hours' in err

    # Over money budget.
    ok, err = game_service.validate_move(gs, 1, {'ads': {state: {dnames[0]: 10**9}}})
    assert not ok and 'funds' in err

    # Too late to get on the ballot: find a state whose contest already passed.
    past_state = None
    for name, week in gs.calendar:
        if week < gs.current_date:
            past_state = name
            break
    if past_state is None:
        # Advance a couple weeks so some contests are in the past, then retry.
        for _ in range(6):
            game_service.resolve_turn(gs, {}, random.Random(1))
        for name, week in gs.calendar:
            if week < gs.current_date and gs.states[name].organizations[0] == 0:
                past_state = name
                break
    assert past_state is not None
    ok, err = game_service.validate_move(gs, 1, {'orgs': {past_state: 1}})
    assert not ok and 'ballot' in err


def test_full_game_completes():
    gs, _, _ = _fresh_gs()
    rng = random.Random(777)
    weeks_played = 0
    while not game_service.is_game_over(gs):
        # Human seat plays a small legal move each week; AI seats auto-fill.
        state = _first_upcoming_state(gs)
        dnames = [d.name for d in gs.states[state].districts]
        human_money = gs.players[1].resources[1]
        move = {'campaigning': {state: {dnames[0]: 8}}}
        if human_money >= 10000:
            move['orgs'] = {state: 1}
        wr, all_moves = game_service.resolve_turn(gs, {1: move}, rng)
        assert set(all_moves.keys()) == {1, 2, 3, 4}
        weeks_played += 1
        assert weeks_played <= gs.num_turns + 1

    assert gs.current_date > gs.num_turns
    total_delegates = sum(p.delegateCount for p in gs.players.values())
    assert total_delegates > 0
    winner = max(gs.players.values(), key=lambda p: p.delegateCount)
    assert winner.delegateCount > 0


if __name__ == '__main__':
    test_create_match()
    test_org_cost_curve()
    test_human_move_applies()
    test_validation_rejects()
    test_full_game_completes()
    print('OK: match creation, move validation/apply, and a full 4-seat game all pass.')
