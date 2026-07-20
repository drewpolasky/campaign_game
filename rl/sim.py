"""Thin re-export of sim_balance.

Historically this module carried a hand-patched `decide_contests` and a
matching `run_game` to fix momentum divergences vs CampaignGame.py (the sim
used to add momentum directly per-winner instead of pooling `totalMomemtum`
and redistributing by delegate share). That patch was itself not identical to
the real game (it started the pool at 0 instead of 50, and attributed
state-delegate momentum differently).

All of that is obsolete now: the rules live in `engine.py`, transcribed from
CampaignGame.py and shared by the real game and the sim. `sim_balance`'s
`decide_contests` / `run_game` already delegate to the engine (pooled momentum
included) and use the real game's rollover order, so this module just
re-exports them.
"""
from sim_balance import (  # noqa: F401 — re-export
    Sim, SimPlayer, ALL_STRATEGIES, load_calendar, load_states,
    calc_state_opinions, calc_end_turn, decide_contests, reset_weekly,
    time_to_election, run_game,
)
