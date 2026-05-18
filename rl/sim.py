"""Sim wrapper that fixes momentum divergences vs CampaignGame.py.

`sim_balance.decide_contests` adds momentum directly per-winner, but the real
game pools `totalMomemtum` across all contests in a week and redistributes by
each player's share of `momentums[i]` (raw delegates won that week).
See CampaignGame.py:1355-1392. Sim and real match when one player sweeps a
week; they diverge when district winners and state winners are different
players.

This module re-exports sim_balance with a corrected `decide_contests` and a
`run_game` that uses it, leaving the original module untouched so the
existing tournament harness keeps producing the same numbers.
"""
import sim_balance as _sb
from sim_balance import (  # noqa: F401 — re-export
    Sim, SimPlayer, ALL_STRATEGIES, load_calendar, load_states,
    calc_state_opinions, calc_end_turn, reset_weekly,
    time_to_election,
)


def decide_contests(sim):
    """Mirrors CampaignGame.decideContests including pooled momentum."""
    momentums = [0.0] * sim.num_players
    total_momentum = 0.0

    for state_name, week in sim.calendar:
        if week + 1 != sim.current_date:
            continue
        st = sim.states[state_name]
        st.calculatePollingAverage(sim.calendar, sim.current_date)
        state_votes = [0] * sim.num_players
        state_delegates = 0

        for d in st.districts:
            district_delegates = (d.population * 2) / 3
            state_delegates += d.population - district_delegates
            winner = -1
            most_votes = 0
            for i in range(sim.num_players):
                if st.organizations[i] > 0:
                    votes = sim.rng.gauss(d.pollingAverage[i], 3) * d.population * 150000
                    if votes < 0:
                        votes = 1
                        sim.players[i].momentum -= 2
                    if votes > most_votes:
                        if winner >= 0:
                            sim.players[winner].momentum -= 1
                        winner = i
                        most_votes = votes
                    elif votes == most_votes:
                        winner = sim.rng.randrange(sim.num_players)
                    state_votes[i] += votes * d.population
            if winner < 0:
                winner = sim.rng.randrange(sim.num_players)
            sim.players[winner].delegate_count += district_delegates
            sim.players[winner].districts_won += 1
            total_momentum += district_delegates / 4.0
            momentums[winner] += district_delegates

        state_winner = state_votes.index(max(state_votes))
        sim.players[state_winner].delegate_count += state_delegates
        sim.players[state_winner].states_won.append(state_name)
        total_momentum += state_delegates / 2.0
        momentums[state_winner] += state_delegates

        sim.past_elections[state_name] = state_winner

    denom = sum(momentums) + 0.01
    for i, m in enumerate(momentums):
        sim.players[i].momentum += m / denom * total_momentum


def run_game(strategies, num_turns=20, seed=0):
    """Match sim_balance.run_game but with the patched decide_contests."""
    sim = Sim(strategies, num_turns=num_turns, seed=seed)
    while sim.current_date <= sim.num_turns:
        for p in sim.players:
            fundraising = p.strategy_fn(sim, p.idx)
            calc_end_turn(sim, p.idx, fundraising)
            p.campaign_hours_total += sum(
                d.campaigningThisTurn[p.idx]
                for st in sim.states.values() for d in st.districts)
        calc_state_opinions(sim)
        decide_contests(sim)
        sim.current_date += 1
        sim.event_of_week = sim.rng.randint(0, len(_sb.state_issues.ISSUES) - 1)
        reset_weekly(sim)
    return sim
