"""Opponent abstractions used by the RL env.

An Opponent's job is to fill in resource allocations for one player on its
turn. The env calls `opp.act(sim, p_idx)` and expects fundraising_hours back.
This matches the contract of sim_balance's strategy functions, which means
existing scripted strategies adapt with one wrapper.
"""
from typing import Callable

import sim_balance as _sb


class Opponent:
    """Abstract base. Subclasses must implement `act`."""
    name = 'Base'

    def act(self, sim, p_idx) -> int:
        raise NotImplementedError

    def reset(self):
        """Optional: called by env at episode reset for stateful opponents."""
        pass


class ScriptedOpponent(Opponent):
    """Wraps any sim_balance-style (sim, p_idx) -> fundraising_hours fn."""

    def __init__(self, name: str, strategy_fn: Callable):
        self.name = name
        self.fn = strategy_fn

    def act(self, sim, p_idx) -> int:
        return self.fn(sim, p_idx)


class RandomOpponent(Opponent):
    """Uses our discrete action decoder with uniform random actions. Useful
    as a sanity-check baseline opponent."""
    name = 'Random'

    def __init__(self, seed: int = 0):
        import random
        self.rng = random.Random(seed)

    def act(self, sim, p_idx) -> int:
        from . import actions as _actions
        a = _actions.random_action(self.rng)
        return _actions.decode_action(sim, p_idx, a)


class FocusedScriptedOpponent(Opponent):
    """A scripted opponent that *also* uses our action decoder, so the
    learning agent isn't getting a free advantage just from target-focusing.

    Picks the most urgent active state as its target each turn, with full
    aggression. Calibrated to be a stronger baseline than the bare
    ScriptedOpponent for evaluating whether an RL policy is actually
    learning, not just exploiting an asymmetry in the action decoder.
    """
    name = 'FocusedDefault'

    def act(self, sim, p_idx) -> int:
        from . import actions as _actions
        # Pick the active state nearest to its primary.
        order = _actions._calendar_state_order(sim)
        target_idx = 0
        best_tte = 999
        for i, name in enumerate(order[:_actions.NUM_TARGET_STATES]):
            for ename, week in sim.calendar:
                if ename == name:
                    tte = week - sim.current_date
                    if 0 <= tte < best_tte:
                        best_tte = tte
                        target_idx = i
                    break
        # Aggression: 100% to target. Lean: balanced. Fundraising: 20 hours.
        action = (target_idx, 0, 1, 1)
        return _actions.decode_action(sim, p_idx, action)


class EarlyIgnorerOpponent(Opponent):
    """Opponent that deliberately skips the earliest contests, focusing
    only on states whose primary is at least `skip_weeks` weeks out.

    Purpose during training: give the learning agent a counterparty it
    can actually beat in the early states. Against FocusedDefault the
    learner always loses Iowa / NH / Nevada / SC and so learns that
    they're not worth investing in. Mixing this opponent in flips the
    payoff — early-state contests become winnable, which gives the agent
    a reason to actually compete for them.

    Implementation note: we bypass the shared discrete decoder because it
    would happily build orgs / spend ads in any state that crosses the
    threshold, regardless of the chosen target. Here we want a hard
    "never touch early states" guarantee.
    """
    name = 'EarlyIgnorer'

    def __init__(self, skip_weeks: int = 4):
        self.skip_weeks = skip_weeks

    def _allowed(self, sim, state_name):
        for ename, week in sim.calendar:
            if ename == state_name:
                tte = week - sim.current_date
                return tte >= self.skip_weeks
        return False

    def act(self, sim, p_idx) -> int:
        import sim_balance as _sb
        p = sim.players[p_idx]

        # Org investment — only in non-early states.
        for state_name, st in sim.states.items():
            tte = _sb.time_to_election(sim, state_name)
            if tte < self.skip_weeks or tte > 8:
                continue
            org_level = st.organizations[p_idx]
            cost = max(10000, 10000 * org_level)
            state_delegates = sum(
                d.population - (d.population * 2) / 3 for d in st.districts)
            org_value = state_delegates * (1.0 + max(0, 6 - tte))
            if org_value > (org_level + 1) * 18.0 and p.resources[1] >= cost:
                p.resources[1] -= cost
                st.organizations[p_idx] += 1
                p.money_on_org += cost

        # Build a scored district list restricted to allowed states.
        def urgency_curve(t):
            if t <= self.skip_weeks:
                return 0.0
            if t <= self.skip_weeks + 1:
                return 1.3
            if t <= self.skip_weeks + 3:
                return 1.0
            return 0.6

        scored = _sb._scored_districts(sim, p_idx, urgency_curve,
                                       closeness_w=1.0, delegates_w=1.0,
                                       runaway_floor=-25, jitter=0.0,
                                       only_imminent_weeks=99)
        # Drop any entry whose state is inside the skip window. Belt-and-
        # suspenders on top of urgency_curve returning 0 for those.
        scored = [e for e in scored if self._allowed(sim, e[3])]

        _sb._greedy_spend_ads(sim, p_idx, [list(e) for e in scored])
        return _sb._greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=2.0)


class _IssueAwareOpponent(Opponent):
    """Shared base for opponents that weight state choices by issue
    alignment in addition to whatever else they care about. Subclasses
    define a `state_value(sim, p_idx, st, state_name, tte)` returning a
    raw priority; this base multiplies that by an issue-alignment factor
    pulled from the current event-of-week vs. the state's stance and
    the player's stance.
    """

    def issue_factor(self, sim, p_idx, st):
        event = sim.event_of_week
        try:
            state_pos = st.positions[event]
        except (IndexError, AttributeError, TypeError):
            state_pos = 0
        try:
            player_pos = sim.players[p_idx].positions[event]
        except (IndexError, AttributeError, TypeError):
            player_pos = 0
        if state_pos == 0:
            return 1.0
        if player_pos == state_pos:
            return 1.5
        return 0.55


class UpcomingFocusOpponent(_IssueAwareOpponent):
    """Concentrates on contests in the next ~4 weeks, biased toward big
    delegate prizes and states whose stance on this week's issue aligns
    with the agent's stance. Builds orgs in the top targets, then pours
    time and ads into their districts.

    Differs from FocusedDefault (which dumps everything into a single
    nearest target) by spreading across the near-horizon window. Differs
    from EarlyIgnorer by *focusing* on near-term instead of skipping it.
    """
    name = 'UpcomingFocus'

    HORIZON = 4

    def act(self, sim, p_idx) -> int:
        import sim_balance as _sb
        p = sim.players[p_idx]

        # Score & rank candidate states by (delegates × issue × urgency)
        # within the horizon.
        candidates = []
        for state_name, st in sim.states.items():
            tte = _sb.time_to_election(sim, state_name)
            if tte < 0 or tte > self.HORIZON:
                continue
            delegates = sum(d.population for d in st.districts)
            urgency = 2.0 if tte <= 1 else (1.5 if tte <= 2 else 1.0)
            score = delegates * urgency * self.issue_factor(sim, p_idx, st)
            candidates.append((score, state_name, st, tte))
        candidates.sort(reverse=True, key=lambda c: c[0])

        # Build orgs in the top candidates while cash allows.
        for score, state_name, st, tte in candidates[:8]:
            org_level = st.organizations[p_idx]
            cost = max(10000, 10000 * org_level)
            # Upcoming-focused: more willing to push orgs in matched
            # states near the election.
            if org_level >= 4:
                continue
            if p.resources[1] < cost:
                break
            # Skip 0-cost low-value: require the score to be meaningfully
            # above a floor proportional to org cost.
            if score < 1.5 * (org_level + 1) * 10:
                continue
            p.resources[1] -= cost
            st.organizations[p_idx] += 1
            p.money_on_org += cost

        def urgency_curve(t):
            if t == 0:
                return 2.5
            if t == 1:
                return 2.0
            if t <= 2:
                return 1.5
            if t <= self.HORIZON:
                return 1.0
            return 0.0  # nothing beyond the horizon

        scored = _sb._scored_districts(sim, p_idx, urgency_curve,
                                       closeness_w=1.0, delegates_w=1.0,
                                       runaway_floor=-25, jitter=0.0,
                                       only_imminent_weeks=99)
        # Bias by issue alignment per state.
        for entry in scored:
            st = sim.states.get(entry[3])
            if st is not None:
                entry[0] *= self.issue_factor(sim, p_idx, st)

        _sb._greedy_spend_ads(sim, p_idx, [list(e) for e in scored])
        return _sb._greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=2.0)


class BigStateFocusOpponent(_IssueAwareOpponent):
    """Long-term planner: builds orgs in the largest-delegate states well
    in advance, weighting more heavily for states whose stance aligns
    with the agent on this week's issue. Does NOT chase nearby small
    primaries — willing to skip Iowa and grind toward California / Texas /
    Florida.

    Differs from BigState (sim_balance) by adding issue alignment as a
    first-class score component and by pushing org investment further
    out (up to 12 weeks of lead time).
    """
    name = 'BigStateFocus'

    HORIZON = 12

    def act(self, sim, p_idx) -> int:
        import sim_balance as _sb
        p = sim.players[p_idx]

        # Score states by delegates^1.5 × issue alignment; squaring would
        # over-concentrate, but giving delegates a super-linear weight
        # makes BigState distinct from a delegates-proportional baseline.
        candidates = []
        for state_name, st in sim.states.items():
            tte = _sb.time_to_election(sim, state_name)
            if tte < 0 or tte > self.HORIZON:
                continue
            delegates = sum(d.population for d in st.districts)
            score = (delegates ** 1.5) * self.issue_factor(sim, p_idx, st)
            candidates.append((score, state_name, st, tte))
        candidates.sort(reverse=True, key=lambda c: c[0])

        # Org investment in top-tier states, willing to keep stacking up
        # to tier 5 in the biggest aligned ones.
        for score, state_name, st, tte in candidates[:12]:
            org_level = st.organizations[p_idx]
            cost = max(10000, 10000 * org_level)
            if org_level >= 5:
                continue
            if p.resources[1] < cost:
                break
            # Threshold scales with size — only invest if this is in the
            # truly heavyweight quartile of remaining candidates.
            if score < candidates[len(candidates) // 4][0]:
                continue
            p.resources[1] -= cost
            st.organizations[p_idx] += 1
            p.money_on_org += cost

        def urgency_curve(t):
            # Flatter than UpcomingFocus — big-state planner doesn't care
            # much about timing as long as orgs are built.
            if t <= 1:
                return 1.6
            if t <= 4:
                return 1.2
            if t <= self.HORIZON:
                return 0.9
            return 0.0

        scored = _sb._scored_districts(sim, p_idx, urgency_curve,
                                       closeness_w=1.0, delegates_w=1.5,
                                       runaway_floor=-25, jitter=0.0,
                                       only_imminent_weeks=99)
        # Per-state issue bias.
        for entry in scored:
            st = sim.states.get(entry[3])
            if st is not None:
                entry[0] *= self.issue_factor(sim, p_idx, st)

        _sb._greedy_spend_ads(sim, p_idx, [list(e) for e in scored])
        return _sb._greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=2.0)


class BigStateRushOpponent(_IssueAwareOpponent):
    """Aggressively builds high-tier orgs in the biggest delegate states
    (CA, NY, TX, FL, IL, PA) in the first 2 weeks, then defends them
    with concentrated ads + campaign hours for the rest of the game.

    Models the human strategy of grabbing California in week 1 — a
    pattern none of the prior heuristic opponents in the training pool
    exhibit, leaving the learner with no policy response to it.
    """
    name = 'BigStateRush'
    PRIORITY_STATES = (
        'California', 'New York', 'Texas', 'Florida',
        'Illinois', 'Pennsylvania',
    )

    def act(self, sim, p_idx) -> int:
        import sim_balance as _sb
        p = sim.players[p_idx]

        # Aggressive org build: push priority states to tier 3 early,
        # tier 4-5 once we have the cash. Build in the highest-tier-gap
        # state first so a single big primary doesn't starve the others.
        target_tier = 3 if sim.current_date <= 2 else 4
        for state_name in self.PRIORITY_STATES:
            if state_name not in sim.states:
                continue
            st = sim.states[state_name]
            tte = _sb.time_to_election(sim, state_name)
            if tte < 0:
                continue
            while st.organizations[p_idx] < target_tier:
                org_level = st.organizations[p_idx]
                cost = max(10000, 10000 * org_level)
                if p.resources[1] < cost:
                    break
                p.resources[1] -= cost
                st.organizations[p_idx] += 1
                try:
                    p.money_on_org += cost
                except (AttributeError, TypeError):
                    pass

        def urgency_curve(t):
            if t <= 0:
                return 1.5
            if t <= 2:
                return 1.3
            if t <= 5:
                return 1.0
            return 0.7

        scored = _sb._scored_districts(sim, p_idx, urgency_curve,
                                       closeness_w=1.0, delegates_w=1.5,
                                       runaway_floor=-25, jitter=0.0,
                                       only_imminent_weeks=99)
        # Strong bias toward priority states; layer issue factor on top.
        priority_set = set(self.PRIORITY_STATES)
        for entry in scored:
            state_name = entry[3]
            if state_name in priority_set:
                entry[0] *= 3.0
            st = sim.states.get(state_name)
            if st is not None:
                entry[0] *= self.issue_factor(sim, p_idx, st)

        _sb._greedy_spend_ads(sim, p_idx, [list(e) for e in scored])
        return _sb._greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=2.0)


class LateBlitzOpponent(_IssueAwareOpponent):
    """Hoards money for the first ~2/3 of the game, then unloads it all
    on near-term states in the final 2-3 weeks. Builds only the minimum
    org footprint to stay relevant mid-game (tier 1 in top-delegate
    states), then ramps to tier 3+ as primaries approach.

    Models the human 'final-week blitz' pattern (e.g. the user's week-10
    $565k+80hr California push) which no other training opponent does.
    """
    name = 'LateBlitz'

    def _phase(self, sim):
        """Return 'early', 'mid', or 'late' based on game progress."""
        nt = max(sim.num_turns, 1)
        if sim.current_date <= nt // 3:
            return 'early'
        if sim.current_date >= nt - 2:
            return 'late'
        return 'mid'

    def act(self, sim, p_idx) -> int:
        import sim_balance as _sb
        p = sim.players[p_idx]
        phase = self._phase(sim)

        # --- Org investment per phase ---
        if phase == 'early':
            # Only build tier-1 orgs in the 4 biggest near-term states.
            candidates = []
            for name, st in sim.states.items():
                tte = _sb.time_to_election(sim, name)
                if tte < 0 or tte > 8:
                    continue
                delegates = sum(d.population for d in st.districts)
                candidates.append((delegates, name, st))
            candidates.sort(reverse=True)
            for delegates, state_name, st in candidates[:4]:
                if st.organizations[p_idx] >= 1:
                    continue
                cost = 10000
                if p.resources[1] < cost:
                    break
                p.resources[1] -= cost
                st.organizations[p_idx] += 1
                try:
                    p.money_on_org += cost
                except (AttributeError, TypeError):
                    pass
        elif phase == 'late':
            # Push tier 3+ in every imminent state we can afford.
            for state_name, st in sim.states.items():
                tte = _sb.time_to_election(sim, state_name)
                if tte < 0 or tte > 2:
                    continue
                while st.organizations[p_idx] < 3:
                    org_level = st.organizations[p_idx]
                    cost = max(10000, 10000 * org_level)
                    if p.resources[1] < cost:
                        break
                    p.resources[1] -= cost
                    st.organizations[p_idx] += 1
                    try:
                        p.money_on_org += cost
                    except (AttributeError, TypeError):
                        pass
        # mid: no org spending, save cash

        # --- Spending allocation per phase ---
        if phase == 'early':
            # Skip ads/time entirely; fundraise hard.
            fundraising = min(p.resources[0], 60)
            p.resources[0] -= fundraising
            return fundraising

        if phase == 'mid':
            # Mid-phase: spend conservatively. Lock most of the cash so
            # _greedy_spend_ads can't burn through it.
            money_reserve = max(0, p.resources[1] - 30000)
            p.resources[1] -= money_reserve

            def urgency_curve(t):
                if t <= 0:
                    return 1.5
                if t <= 2:
                    return 1.0
                return 0.4

            scored = _sb._scored_districts(sim, p_idx, urgency_curve,
                                           closeness_w=1.0, delegates_w=1.0,
                                           runaway_floor=-25, jitter=0.0,
                                           only_imminent_weeks=99)
            for entry in scored:
                st = sim.states.get(entry[3])
                if st is not None:
                    entry[0] *= self.issue_factor(sim, p_idx, st)
            _sb._greedy_spend_ads(sim, p_idx, [list(e) for e in scored])
            leftover = _sb._greedy_spend_time(sim, p_idx, scored,
                                              fundraise_cutoff=8.0)
            # Restore the reserved cash for next turn.
            p.resources[1] += money_reserve
            return leftover + min(p.resources[0], 20)

        # late: empty the bank account on near-term states.
        def urgency_curve(t):
            if t <= 0:
                return 3.0
            if t <= 1:
                return 2.5
            if t <= 2:
                return 1.8
            return 0.8

        scored = _sb._scored_districts(sim, p_idx, urgency_curve,
                                       closeness_w=1.0, delegates_w=1.0,
                                       runaway_floor=-25, jitter=0.0,
                                       only_imminent_weeks=99)
        for entry in scored:
            st = sim.states.get(entry[3])
            if st is not None:
                entry[0] *= self.issue_factor(sim, p_idx, st)
        _sb._greedy_spend_ads(sim, p_idx, [list(e) for e in scored])
        return _sb._greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=1.0)


class AdMaximizerOpponent(_IssueAwareOpponent):
    """Maximizes ad spending. Builds tier-1 orgs only in the largest
    upcoming-state delegate prizes (just enough to be on the ballot),
    then dumps all available money into ads concentrated on those same
    states. Models a 'media blitz' human play style that v14's pure
    self-play training never encountered — the Nash equilibrium it
    collapsed to (build orgs, spend nothing) loses every game to this
    opponent type, which is the whole point of including it in v15's
    training pool.
    """
    name = 'AdMaximizer'

    def act(self, sim, p_idx) -> int:
        import sim_balance as _sb
        p = sim.players[p_idx]

        # Just-tier-1 ballot access in the top 10 upcoming delegate
        # prizes, weighted by issue alignment so resources go where ads
        # will compound the most.
        candidates = []
        for state_name, st in sim.states.items():
            tte = _sb.time_to_election(sim, state_name)
            if tte < 0 or tte > 8:
                continue
            delegates = sum(d.population for d in st.districts)
            score = delegates * self.issue_factor(sim, p_idx, st)
            candidates.append((score, state_name, st, tte))
        candidates.sort(reverse=True, key=lambda c: c[0])
        for _, state_name, st, tte in candidates[:10]:
            if st.organizations[p_idx] >= 1:
                continue
            cost = 10000
            if p.resources[1] < cost:
                break
            p.resources[1] -= cost
            st.organizations[p_idx] += 1
            try:
                p.money_on_org += cost
            except (AttributeError, TypeError):
                pass

        # Ad-only spending — no campaign hours, no fundraising prep.
        def urgency_curve(t):
            if t <= 0:
                return 2.0
            if t <= 2:
                return 1.7
            if t <= 4:
                return 1.3
            if t <= 6:
                return 1.0
            return 0.5

        scored = _sb._scored_districts(sim, p_idx, urgency_curve,
                                       closeness_w=1.0, delegates_w=1.5,
                                       runaway_floor=-25, jitter=0.0,
                                       only_imminent_weeks=99)
        for entry in scored:
            st = sim.states.get(entry[3])
            if st is not None:
                entry[0] *= self.issue_factor(sim, p_idx, st)
        _sb._greedy_spend_ads(sim, p_idx, [list(e) for e in scored])

        # Skip campaign-hour spending entirely; fundraise with all hours.
        # (Returning hours = fundraising hours.)
        return p.resources[0]


class FundraiseHoarderOpponent(_IssueAwareOpponent):
    """Maxes out fundraising every turn for the first ~70% of the game
    (no ads, no campaign hours, no orgs beyond bare minimum), then dumps
    the entire bankroll on ads + campaign hours in the closing weeks.
    Tunes for an end-game cash pile of $1.5M+ which is closer to what a
    human grinder actually accumulates — strictly more extreme than
    LateBlitz, which only hoards ~$300k.

    The training-pool point: this opponent has a fundamentally different
    cash trajectory than anything else the agent has seen, so it has to
    learn 'opponent has nothing now but could drop $1M on me later'.
    """
    name = 'FundraiseHoarder'

    HOARD_FRACTION = 0.7  # spend nothing for the first 70% of turns

    def _phase(self, sim):
        nt = max(sim.num_turns, 1)
        cutoff = int(nt * self.HOARD_FRACTION)
        return 'hoard' if sim.current_date <= cutoff else 'blitz'

    def act(self, sim, p_idx) -> int:
        import sim_balance as _sb
        p = sim.players[p_idx]

        if self._phase(sim) == 'hoard':
            # Just-tier-1 ballot access in the 6 biggest near-term
            # prizes (so the eventual blitz has somewhere to spend).
            candidates = []
            for state_name, st in sim.states.items():
                tte = _sb.time_to_election(sim, state_name)
                if tte < 0 or tte > 9:
                    continue
                delegates = sum(d.population for d in st.districts)
                candidates.append((delegates, state_name, st))
            candidates.sort(reverse=True)
            for _, state_name, st in candidates[:6]:
                if st.organizations[p_idx] >= 1:
                    continue
                if p.resources[1] < 10000:
                    break
                p.resources[1] -= 10000
                st.organizations[p_idx] += 1
                try:
                    p.money_on_org += 10000
                except (AttributeError, TypeError):
                    pass
            # All hours to fundraising.
            return p.resources[0]

        # Blitz phase: spend everything, on everything imminent.
        # First push tier 2-3 in any imminent state we can.
        for state_name, st in sim.states.items():
            tte = _sb.time_to_election(sim, state_name)
            if tte < 0 or tte > 2:
                continue
            while st.organizations[p_idx] < 3:
                org_level = st.organizations[p_idx]
                cost = max(10000, 10000 * org_level)
                if p.resources[1] < cost:
                    break
                p.resources[1] -= cost
                st.organizations[p_idx] += 1
                try:
                    p.money_on_org += cost
                except (AttributeError, TypeError):
                    pass

        def urgency_curve(t):
            if t <= 0:
                return 3.0
            if t <= 1:
                return 2.5
            if t <= 2:
                return 2.0
            return 1.0

        scored = _sb._scored_districts(sim, p_idx, urgency_curve,
                                       closeness_w=1.0, delegates_w=1.5,
                                       runaway_floor=-25, jitter=0.0,
                                       only_imminent_weeks=99)
        for entry in scored:
            st = sim.states.get(entry[3])
            if st is not None:
                entry[0] *= self.issue_factor(sim, p_idx, st)

        _sb._greedy_spend_ads(sim, p_idx, [list(e) for e in scored])
        return _sb._greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=1.0)


class MaxFundraiserOpponent(_IssueAwareOpponent):
    """A 'smart human' opponent that:
      - Contests early states (no skip-Iowa)
      - Each turn, hardest focus is on contests THIS week (tte=0) and
        next week (tte=1)
      - Reinforces states it's already winning only modestly — won't
        burn $80k of ads in a state where it's already up 100 support
      - Hammers states where the race is close AND voting soon
      - Banks aggressive fundraising hours so it has a large mid-late
        game ad bankroll (closer to $2-3M than LateBlitz's ~$1M)

    Designed to match the human play pattern the user uses: take the
    early states, fundraise hard while doing it, then concentrate
    spending on imminent close races. Adds to v15's training pool a
    style of play none of the existing scripted opponents represent.
    """
    name = 'MaxFundraiser'

    # How many hours per turn to commit to fundraising before spending
    # any on campaigning (until the late-game blitz phase).
    EARLY_FUND_HOURS = 60
    MID_FUND_HOURS = 40
    LATE_FUND_HOURS = 0  # late game, spend everything

    AHEAD_BIG_THRESHOLD = 80   # margin above this -> ease off this state
    CLOSE_RACE_THRESHOLD = 40  # |margin| <= this -> push hard

    def _phase(self, sim):
        nt = max(sim.num_turns, 1)
        if sim.current_date <= nt // 3:
            return 'early'
        if sim.current_date >= nt - 2:
            return 'late'
        return 'mid'

    def _state_margins(self, sim, p_idx):
        """For each upcoming state, return (margin, tte, st). margin is
        positive when we're ahead, negative when behind, 0 if tied."""
        out = {}
        for state_name, st in sim.states.items():
            import sim_balance as _sb
            tte = _sb.time_to_election(sim, state_name)
            if tte < 0:
                continue
            my_sup = sum(d.support[p_idx] for d in st.districts)
            opp_sup_max = 0
            for j in range(sim.num_players):
                if j == p_idx:
                    continue
                opp = sum(d.support[j] for d in st.districts)
                if opp > opp_sup_max:
                    opp_sup_max = opp
            out[state_name] = (my_sup - opp_sup_max, tte, st)
        return out

    def act(self, sim, p_idx) -> int:
        import sim_balance as _sb
        p = sim.players[p_idx]
        phase = self._phase(sim)
        status = self._state_margins(sim, p_idx)

        # --- Org investment: ballot access + tier-2/3 push in tight
        # near-term races. Always include early states (the early-state
        # taking the user asked for). ---
        # Order: nearest-tte first, so the cash goes to the most
        # imminent contests before the budget is exhausted.
        for state_name in sorted(status, key=lambda n: status[n][1]):
            margin, tte, st = status[state_name]
            if tte > 5:
                continue
            org_level = st.organizations[p_idx]
            if org_level == 0:
                # Get on the ballot — cheapest org tier costs $10k.
                if p.resources[1] >= 10000 and tte <= 4:
                    p.resources[1] -= 10000
                    st.organizations[p_idx] += 1
                    try:
                        p.money_on_org += 10000
                    except (AttributeError, TypeError):
                        pass
            elif tte <= 2 and margin > -self.AHEAD_BIG_THRESHOLD \
                    and margin < self.AHEAD_BIG_THRESHOLD:
                # Race is contested and voting soon — push tier 2 or 3.
                target_tier = 3 if margin <= 0 else 2
                while st.organizations[p_idx] < target_tier:
                    org_level = st.organizations[p_idx]
                    cost = max(10000, 10000 * org_level)
                    if p.resources[1] < cost:
                        break
                    p.resources[1] -= cost
                    st.organizations[p_idx] += 1
                    try:
                        p.money_on_org += cost
                    except (AttributeError, TypeError):
                        pass

        # --- Score districts with strong urgency on this week + next
        # week, plus margin-aware bias (push close, ease off blowouts). ---
        def urgency_curve(t):
            if t == 0:
                return 3.5  # voting THIS week — hammer it
            if t == 1:
                return 2.7  # voting next week — heavy focus
            if t == 2:
                return 1.6
            if t == 3:
                return 1.1
            if t <= 5:
                return 0.7
            return 0.3

        scored = _sb._scored_districts(sim, p_idx, urgency_curve,
                                       closeness_w=2.0, delegates_w=1.0,
                                       runaway_floor=-25, jitter=0.0,
                                       only_imminent_weeks=99)
        for entry in scored:
            state_name = entry[3]
            st = sim.states.get(state_name)
            if st is not None:
                entry[0] *= self.issue_factor(sim, p_idx, st)
            st_info = status.get(state_name)
            if st_info is not None:
                margin, tte, _ = st_info
                if margin > self.AHEAD_BIG_THRESHOLD:
                    # Already winning by a lot — drop priority sharply.
                    entry[0] *= 0.20
                elif abs(margin) <= self.CLOSE_RACE_THRESHOLD and tte <= 2:
                    # Close race and voting imminent — push HARD.
                    entry[0] *= 2.5
                elif margin < -self.AHEAD_BIG_THRESHOLD and tte > 2:
                    # Far behind and not voting soon — cut losses.
                    entry[0] *= 0.4

        # --- Decide hour split: fundraise hard early/mid, blitz late ---
        if phase == 'early':
            fund_hours_target = self.EARLY_FUND_HOURS
            money_reserve = max(0, p.resources[1] - 80000)
        elif phase == 'mid':
            fund_hours_target = self.MID_FUND_HOURS
            money_reserve = max(0, p.resources[1] - 200000)
        else:  # late
            fund_hours_target = self.LATE_FUND_HOURS
            money_reserve = 0

        # Cap the hours we're willing to commit to fundraising up front
        # so there's still time left for campaigning in tight races.
        fund_hours_now = min(p.resources[0], fund_hours_target)
        p.resources[0] -= fund_hours_now
        fundraising_hours = fund_hours_now

        # --- Ad spending, holding back the reserve ---
        if money_reserve > 0:
            p.resources[1] -= money_reserve
        _sb._greedy_spend_ads(sim, p_idx, [list(e) for e in scored])
        if money_reserve > 0:
            p.resources[1] += money_reserve

        # --- Campaign hours on the same scored list ---
        leftover = _sb._greedy_spend_time(sim, p_idx, scored,
                                          fundraise_cutoff=1.5)
        fundraising_hours += leftover
        return fundraising_hours


def named_scripted(name: str = 'Default') -> Opponent:
    """Look up a strategy by name. Recognizes our own opponent classes too."""
    if name == 'FocusedDefault':
        return FocusedScriptedOpponent()
    if name == 'EarlyIgnorer':
        return EarlyIgnorerOpponent()
    if name == 'UpcomingFocus':
        return UpcomingFocusOpponent()
    if name == 'BigStateFocus':
        return BigStateFocusOpponent()
    if name == 'BigStateRush':
        return BigStateRushOpponent()
    if name == 'LateBlitz':
        return LateBlitzOpponent()
    if name == 'AdMaximizer':
        return AdMaximizerOpponent()
    if name == 'FundraiseHoarder':
        return FundraiseHoarderOpponent()
    if name == 'MaxFundraiser':
        return MaxFundraiserOpponent()
    if name == 'Random':
        return RandomOpponent()
    for n, fn in _sb.ALL_STRATEGIES:
        if n == name:
            return ScriptedOpponent(n, fn)
    raise KeyError(f'unknown strategy: {name}')
