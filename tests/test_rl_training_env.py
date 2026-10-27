"""RL training env: shuffled calendars, mixed game lengths, and scripted
opponents paying the real (size-scaled) org prices.

These are the knobs the neural AI is trained with, so a silent break here
means the model trains on something other than the game people play.

Run:  python -m pytest tests/test_rl_training_env.py
"""
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

pytest.importorskip('numpy')

import numpy as np  # noqa: E402

import engine  # noqa: E402
import sim_balance  # noqa: E402
from rl import actions  # noqa: E402
from rl.env import CampaignGameEnv  # noqa: E402
from rl.opponent import named_scripted  # noqa: E402


@pytest.fixture(autouse=True)
def _repo_cwd(monkeypatch):
    # The sim loads its state/calendar files relative to the repo root.
    monkeypatch.chdir(REPO)


def _stub(sim, p_idx):
    return 0


@pytest.mark.parametrize('num_turns', [8, 10, 20])
def test_sim_shuffled_calendar_is_a_valid_schedule(num_turns):
    fixed = sim_balance.load_calendar(num_turns)
    differs = False
    for seed in range(5):
        sim = sim_balance.Sim([('A', _stub), ('B', _stub)], num_turns=num_turns,
                              seed=seed, randomize_calendar=True)
        names = [name for name, _ in sim.calendar]
        assert sorted(names) == sorted(sim.states)          # every state exactly once
        assert all(2 <= week <= num_turns for _, week in sim.calendar)
        again = sim_balance.Sim([('A', _stub), ('B', _stub)], num_turns=num_turns,
                                seed=seed, randomize_calendar=True)
        assert again.calendar == sim.calendar                # reproducible per seed
        differs = differs or sim.calendar != fixed
    assert differs


def test_env_mixes_game_lengths_and_calendars():
    env = CampaignGameEnv([named_scripted('Default')], num_turns=(8, 10, 20), seed=3,
                          action_kind='coupled', random_calendar_prob=0.5, seed_stride=4)
    seen = set()
    for _ in range(40):
        env.reset()
        sim = env.sim
        assert sim.num_turns == env.num_turns
        shuffled = sim.calendar != sim_balance.load_calendar(sim.num_turns)
        seen.add((sim.num_turns, shuffled))
    assert {n for n, _ in seen} == {8, 10, 20}
    assert {s for _, s in seen} == {False, True}


def test_fixed_length_env_keeps_the_fixed_calendar_by_default():
    env = CampaignGameEnv([named_scripted('Default')], num_turns=10, seed=0)
    for _ in range(5):
        env.reset()
        assert env.sim.calendar == sim_balance.load_calendar(10)


@pytest.mark.parametrize('kwargs', [{'random_calendar_prob': -0.1},
                                    {'random_calendar_prob': 1.5},
                                    {'seed_stride': 0},
                                    {'num_turns': ()}])
def test_env_rejects_bad_settings(kwargs):
    with pytest.raises(ValueError):
        CampaignGameEnv([named_scripted('Default')], **kwargs)


def _org_knob_off_action():
    # Uniform state weights, no fundraising, every hour kept for campaigning,
    # and the org-money knob at its floor (~0.7% of cash).
    action = np.zeros(actions.COUPLED_ACTION_DIM, dtype=np.float32)
    action[actions.NUM_TARGET_STATES:] = (-5.0, -5.0, 5.0)
    return action


def test_coupled_decoder_gets_on_the_ballot_where_a_state_votes_this_week():
    # Regression guard: in 20-week games the policy turned the org knob down
    # before the big late states were in org range, then sat on its cash
    # while they voted because ads only go where it is on the ballot.
    sim = sim_balance.Sim([('A', _stub), ('B', _stub)], num_turns=20, seed=2,
                          randomize_calendar=True)
    week = sim.calendar[-1][1]
    sim.current_date = week
    voting = {name for name, w in sim.calendar if w == week}
    p = sim.players[0]
    p.resources[1] = 500000

    actions.decode_coupled_action(sim, 0, _org_knob_off_action())

    for name, st in sim.states.items():
        assert st.organizations[0] == (1 if name in voting else 0), name
    assert p.money_on_org == sum(engine.org_base_cost(sim.states[n]) for n in voting)
    assert p.money_on_ads > 0
    ads = {name: sum(d.adsThisTurn[0] for d in st.districts) for name, st in sim.states.items()}
    assert all(ads[name] == 0 for name in ads if name not in voting)


def test_coupled_decoder_can_still_bank_money_before_any_contest():
    # Week 1 has no contests; with the org knob down, nothing reachable means
    # the cash carries over (the opening the trained policy relies on).
    sim = sim_balance.Sim([('A', _stub), ('B', _stub)], num_turns=10, seed=2)
    p = sim.players[0]
    start = p.resources[1]
    hours = actions.decode_coupled_action(sim, 0, _org_knob_off_action())
    assert all(st.organizations[0] == 0 for st in sim.states.values())
    assert p.resources[1] == start
    # The hours it kept for campaigning had nowhere to go, so they fundraise
    # (as the real game's end of turn does) instead of vanishing.
    assert hours == 80 and p.resources[0] == 0


@pytest.mark.parametrize('name', ['FocusedDefault', 'EarlyIgnorer', 'UpcomingFocus',
                                  'BigStateFocus', 'BigStateRush', 'LateBlitz',
                                  'AdMaximizer', 'FundraiseHoarder', 'MaxFundraiser'])
@pytest.mark.parametrize('num_turns', [8, 20])
def test_scripted_opponents_use_every_hour(name, num_turns):
    # The real game banks unspent hours as fundraising, so every hour a
    # training opponent doesn't campaign must come back as fundraising.
    opp = named_scripted(name)
    env = CampaignGameEnv([opp], num_turns=num_turns, seed=7, action_kind='coupled',
                          random_calendar_prob=1.0)
    env.reset()
    sim = env.sim
    p = sim.players[1]
    for week in range(1, sim.num_turns + 1):
        hours = opp.act(sim, 1)
        campaigned = sum(d.campaigningThisTurn[1]
                         for st in sim.states.values() for d in st.districts)
        assert hours + campaigned == 80, f'week {week}'
        assert p.resources[1] >= 0, f'week {week}'
        sim_balance.calc_end_turn(sim, 1, hours)
        sim_balance.calc_state_opinions(sim)
        sim.current_date += 1
        sim_balance.decide_contests(sim)
        sim_balance.reset_weekly(sim)


def test_greedy_time_banks_hours_it_cannot_place():
    sim = sim_balance.Sim([('A', _stub), ('B', _stub)], num_turns=10, seed=2)
    p = sim.players[0]
    p.resources[0] = 50
    assert sim_balance._greedy_spend_time(sim, 0, [], fundraise_cutoff=2.0) == 50
    assert p.resources[0] == 0


@pytest.mark.parametrize('name', ['EarlyIgnorer', 'UpcomingFocus', 'BigStateFocus',
                                  'BigStateRush', 'LateBlitz', 'AdMaximizer',
                                  'FundraiseHoarder', 'MaxFundraiser'])
def test_scripted_opponents_pay_engine_org_prices(name):
    # Regression guard: these opponents used to charge a flat
    # max($10k, $10k * tier), so in training they over-built big states and
    # under-built small ones compared with what any real-game AI can afford.
    opp = named_scripted(name)
    env = CampaignGameEnv([opp], num_turns=10, seed=11, action_kind='coupled')
    env.reset()
    sim = env.sim
    p = sim.players[1]
    for week in range(1, sim.num_turns + 1):
        cash, org_spend = p.resources[1], p.money_on_org
        hours = opp.act(sim, 1)
        expected = sum(engine.org_tier_cost(st, tier)
                       for st in sim.states.values()
                       for tier in range(st.organizations[1]))
        assert p.money_on_org == expected, f'week {week}'
        # ...and the money actually left the bank (ads come out of it too).
        assert cash - p.resources[1] >= p.money_on_org - org_spend, f'week {week}'
        sim_balance.calc_end_turn(sim, 1, hours)
        sim_balance.calc_state_opinions(sim)
        sim.current_date += 1
        sim_balance.decide_contests(sim)
        sim_balance.reset_weekly(sim)
    if name in ('LateBlitz', 'FundraiseHoarder'):
        # Their tier-2+ pushes only happen late; make sure the game got there.
        assert max(st.organizations[1] for st in sim.states.values()) >= 2
