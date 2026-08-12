"""Momentum crediting in split states.

A state's delegates come in two blocks: each district's winner takes that
district's share (2/3 of its population), and the state's at-large block (the
remaining 1/3, summed) goes to whoever wins the aggregate vote. Momentum is
then handed out in proportion to the delegates each player won.

Regression guard: the at-large block's momentum used to be credited to the
leftover district-loop variable, i.e. to whoever won the LAST district iterated,
so in a split state it could land on a player who lost the state outright.

Run:  python -m pytest tests/test_momentum.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine  # noqa: E402
from State import State, District  # noqa: E402
from Player import Player  # noqa: E402


class _FixedRng:
    """Deterministic stand-in: a district's vote draw is exactly its polling."""

    def gauss(self, mu, sigma):
        return mu

    def randint(self, a, b):
        return a


def _split_state_game():
    """One state, two districts, two players. Player 1 takes the big district
    and the state on aggregate votes; player 2 takes the small district, which
    is deliberately iterated LAST."""
    st = State('Testland', [0] * 8)
    st.positions = [0] * 8
    big = District('Big', 30, 'Testland')
    small = District('Small', 3, 'Testland')
    big.pollingAverage = [80.0, 20.0]
    small.pollingAverage = [40.0, 60.0]
    for d in (big, small):
        d.support = [0, 0]
        d.campaigningThisTurn = [0, 0]
        d.adsThisTurn = [0, 0]
        st.addDistrict(d)
    st.organizations = [1, 1]
    # Keep the fixed polling above; don't let the engine recompute it.
    st.calculatePollingAverage = lambda *a, **k: None

    players = {}
    for i in (1, 2):
        p = Player(i)
        p.publicName = 'P{}'.format(i)
        p.momentum = 0
        p.positions = [0] * 8
        players[i] = p

    gs = engine.GameState({'Testland': st}, players, [('Testland', 1)],
                          current_date=2, num_turns=8, event_of_week=0,
                          issues_mode=False, past_elections={}, rng=_FixedRng())
    return gs, players


def test_split_state_momentum_follows_the_state_winner():
    gs, players = _split_state_game()
    week_results = engine.decide_contests(gs)

    # Sanity: the districts really did split, and player 1 won the state.
    assert week_results['_state_results']['Testland']['winner'] == 1
    assert 'Big' in week_results[1]['districts']
    assert 'Small' in week_results[2]['districts']

    d1 = week_results[1]['delegates']
    d2 = week_results[2]['delegates']
    m1 = players[1].momentum
    m2 = players[2].momentum

    # Player 1 won the state, so the at-large block is theirs: they should hold
    # the large majority of both delegates and momentum.
    assert d1 > d2
    assert m1 > m2
    # Momentum share should track delegate share closely (same proportional
    # split of the weekly pool). Before the fix this was 60/40 against a 94/6
    # delegate split.
    delegate_share = d1 / (d1 + d2)
    momentum_share = m1 / (m1 + m2)
    assert abs(momentum_share - delegate_share) < 0.05, \
        'momentum {:.3f} should track delegates {:.3f}'.format(momentum_share, delegate_share)
