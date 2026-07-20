# Phase 1 — canonical headless engine

Goal: extract the game rules into one `engine.py` module that operates on an
explicit state object (no Tkinter, no module globals), and have **both** the
real game (`CampaignGame.py`) and the RL/balance harness (`sim_balance.py`,
`rl/`) call into it. This kills the current situation where the rules exist in
two hand-maintained copies that have drifted apart.

## Where the rules live today

| Concern | Real game (`CampaignGame.py`) | Sim copy (`sim_balance.py`) |
|---|---|---|
| Support math | `calculateStateOpinions()` (1426) | `calc_state_opinions(sim)` (143) |
| Contest resolution | `decideContests()` (1531) | `decide_contests(sim)` (212) |
| Money / fundraising | `calcEndTurn()` (1193) | `calc_end_turn(sim, ...)` (191) |
| Weekly reset | inline in `endTurn()` (4171) | `reset_weekly(sim)` (248) |
| State/District math | `State.py` (already UI-free, shared) | same |
| Player state | `Player.py` (already UI-free) | `SimPlayer` (parallel class) |

The sim already uses the target shape — an explicit `Sim` context passed into
each function. The real game uses module globals (`players`, `states`,
`currentDate`, `numPlayers`, `numTurns`, `calendarOfContests`, `issuesMode`,
`eventOfTheWeek`, `pastElections`, `weekResults`). The engine boundary will
look like the sim's, and the real game will bind its globals to it.

## The drift: how the two copies differ TODAY

### 1. Org-0 support gating
- **Real game**: a player with organization level 0 in a state still gains
  campaign/ad support there (only `org_support` is zero; `campaign_support`
  and `ad_support` still apply). That support feeds fundraising in
  `calcEndTurn`, so org-0 activity is *not* wasted. (CampaignGame.py:1461)
- **Sim**: `if org == 0: continue` — skips the district entirely, so a player
  gains nothing without an org. (sim_balance.py:148)

### 2. Momentum mechanics (biggest difference)
- **Real game** (`decideContests`, 1568–1654):
  - starts each week with a base pool `totalMomemtum = 50`,
  - grows the pool by `districtDelegates/4` per district and
    `stateDelegates/2` per state decided,
  - applies immediate penalties: `-2` momentum when a player's district votes
    come out negative, `-1` when a player is overtaken as district leader,
  - at week end, distributes the whole pool **proportionally to each player's
    share** of delegates won that week.
  - (Quirk preserved as canonical: state-level delegates add to `momentums`
    for the *last district's* winner, not the aggregate state winner — a
    latent bug, but it's what the shipped game does.)
- **Sim** (`decide_contests`, 238–243): awards momentum **directly** —
  `+districtDelegates/4` to each district winner, `+stateDelegates/2` to the
  state winner. No base pool, no proportional redistribution, no overtake/
  negative penalties.

These produce quite different momentum trajectories, which then feed back into
support (`mult_mom`) and fundraising (`2 - exp(momentum/-50)`).

### 3. Contest-resolution timing (off-by-one)
- **Real game** (`endTurn`, 4165–4167): `calculateStateOpinions()` →
  `currentDate += 1` → `decideContests()`. A contest scheduled for calendar
  week *W* resolves in the same rollover that applies week-*W* campaigning —
  i.e. campaigning right up to election day counts, and nothing after.
- **Sim** (`run_game`, 264–266): `calc_state_opinions()` → `decide_contests()`
  → `current_date += 1`. Because the sim checks `week + 1 == current_date`
  *before* incrementing, each contest resolves one iteration later than the
  real game — after an **extra** application of support. (In practice the AI
  stops campaigning in a state once its election passes, so the extra week
  mostly adds org-passive support, but it is a real difference and will be
  pinned down exactly with a differential test during extraction.)

### Minor (bookkeeping, not gameplay)
- Player stat tracking differs (real `Player.stats` dict + `history` vs
  `SimPlayer`'s flat attributes). The engine will keep the real game's
  `Player` as canonical; the sim's per-player counters map onto it.
- The real game emits a rich `weekResults` structure (per-state vote-share
  breakdown for the start-of-turn report) and optional DEBUG logging; the sim
  emits nothing. The engine will *return* a structured week-result object;
  callers that don't need it can ignore it.

## Decision (made)
**Match the real game exactly; no behavior flags.** The engine replicates the
shipped `CampaignGame.py` rules, and the sim/RL adopt them. RL/balance baselines
shift (org-0 support, pooled momentum, contest timing) and models will want
retraining — accepted, since those numbers were only ever an approximation of
the real game anyway.

There turned out to be a THIRD copy: `rl/sim.py` carried a hand-patched
`decide_contests` that tried to fix the momentum drift but was itself not
identical to the real game (it started the momentum pool at 0 instead of 50 and
attributed state-delegate momentum to a different player). The engine replaces
all three copies.

## Status: DONE

1. **`engine.py`** — `GameState` container + `calc_state_opinions`,
   `decide_contests` (returns week-results), `calc_end_turn`, `reset_weekly`,
   transcribed verbatim from the real game. Debug logging via optional hooks.
2. **`tests/test_engine_parity.py`** — verified the engine reproduces the
   ORIGINAL shipped functions byte-for-byte on a seeded scenario where a
   contest actually resolves (covering the momentum-pool + random-draw paths),
   and locks the canonical outputs with a golden-value regression test.
3. **`CampaignGame.py`** — `calculateStateOpinions` / `decideContests` /
   `calcEndTurn` now delegate to the engine via a thin `_engine_state()`
   binding + `_EngineHooks` (routes to the existing DEBUG logging). The
   `currentDate == 0` UI branch stays in CampaignGame. ~296 net lines removed.
4. **`sim_balance.py`** — the four rule functions keep their `(sim, ...)`
   signatures but delegate to the engine; `SimPlayer` gained the small
   Player-shaped API the engine writes to (`delegateCount`, `addStat`,
   `endTurn`). `run_game` reordered to advance the week before resolving
   contests (the timing fix). **`rl/sim.py`** is now a thin re-export (its
   momentum patch is obsolete). **`rl/env.py`** step() reordered to match.
5. **Verified**: engine parity + golden tests pass; `sim_balance.run_game`, a
   tournament (`run_tournament`/`aggregate`/`print_table`), and a full RL env
   rollout (`rl.smoke_test`, 20 games) all run on the engine. `CampaignGame`
   imports headlessly. (`torch`/`gymnasium`/`stable_baselines3` aren't
   installed in this dev env, so `gym_env.py`/`selfplay_pool.py`/`diag.py`
   can't import here — unrelated to this change.)

## Follow-ups (not part of Phase 1)
* Retrain the PPO opponents against the corrected rules and re-run the balance
  tournament to establish new baselines.
* Consider unifying `SimPlayer` onto the canonical `Player` class (Phase 1 only
  unified the *rules*, not the player representation).
