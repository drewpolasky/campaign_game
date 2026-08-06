"""Canonical headless game engine for Campaign Game.

This module is the single source of truth for the game *rules* — support
gains, contest resolution, and fundraising/money. It has no dependency on
Tkinter or on module-level globals: every function operates on an explicit
``GameState`` context passed in by the caller.

Both callers use it:

* ``CampaignGame.py`` (the real game) binds its module globals into a
  ``GameState`` and delegates ``calculateStateOpinions`` / ``decideContests``
  / ``calcEndTurn`` here.
* ``sim_balance.py`` / ``rl/`` (the headless RL + balance harness) build a
  ``GameState`` directly.

The logic here is transcribed verbatim from the shipped ``CampaignGame.py``
so behavior is identical to the real game. Any rule change now happens in one
place. See ``docs/engine_migration.md`` for the history and the drift this
replaced.

Data classes used by the engine live in the already-UI-free modules:
``State`` / ``District`` (State.py) and ``Player`` (Player.py).
"""
import math


class GameState:
    """Explicit container for everything the rules need.

    Mirrors the CampaignGame.py module globals, but passed around explicitly
    instead of read from module scope:

    * ``states``         dict: state name -> State
    * ``players``        dict: 1-based player id -> Player
    * ``calendar``       list of (state_name, week) contest dates
                         (CampaignGame's ``calendarOfContests``)
    * ``current_date``   current week (``currentDate``)
    * ``num_turns``      total weeks in the game (``numTurns``)
    * ``event_of_week``  issue index in effect this week (``eventOfTheWeek``)
    * ``issues_mode``    whether issue alignment is active (``issuesMode``)
    * ``past_elections`` dict: state name -> winning player id (mutated here)
    * ``rng``            a ``random.Random`` instance OR the ``random`` module;
                         anything exposing ``gauss``/``randint``. The real game
                         passes the ``random`` module; the sim passes a seeded
                         ``random.Random`` for reproducibility.

    ``num_players`` is derived from ``players`` so the two never disagree.
    """

    def __init__(self, states, players, calendar, current_date, num_turns,
                 event_of_week, issues_mode, past_elections, rng):
        self.states = states
        self.players = players
        self.calendar = calendar
        self.current_date = current_date
        self.num_turns = num_turns
        self.event_of_week = event_of_week
        self.issues_mode = issues_mode
        self.past_elections = past_elections
        self.rng = rng

    @property
    def num_players(self):
        return len(self.players)


class _NullHooks:
    """No-op diagnostic hooks. The real game injects a hooks object that
    routes to its DEBUG logging; the sim leaves these as no-ops. Using hooks
    keeps all the debug/reporting code out of the engine core while
    reproducing the real game's output exactly when enabled."""

    def pre_support_snapshot(self, gs):
        return None

    def week_summary(self, gs, snap):
        pass

    def contests_header(self, gs):
        pass

    def state_resolved(self, gs, state_name, state_votes, district_winners,
                       state_winner, total_state_votes):
        pass


NULL_HOOKS = _NullHooks()


def calc_state_opinions(gs, hooks=None):
    """Apply this week's support gains for every player in every district.

    Transcribed from ``CampaignGame.calculateStateOpinions`` (the
    ``currentDate != 0`` branch — the ``currentDate == 0`` case in the real
    game is pure UI/flow, not a rule, so it stays in CampaignGame).

    A player gains support from three sources, each scaled by ``mult``:
      * org passive support  (0 when not on the ballot)
      * campaigning hours
      * ad spend (share of the district's ad market, sub-linear intensity)
    ``mult`` folds in momentum, the election-proximity bonus, and issue
    alignment. Note org-0 players still gain campaign/ad support here (which
    then feeds fundraising) — matching the shipped game.
    """
    hooks = hooks or NULL_HOOKS
    players = gs.players
    states = gs.states
    snap = hooks.pre_support_snapshot(gs)
    for i in range(len(players)):
        for state in states:
            org = states[state].organizations[i]
            # In the 2 weeks before a state's election, campaigning there is
            # more effective: election week +20%, one week before +10%.
            contest_week = None
            for date in gs.calendar:
                if date[0] == state:
                    contest_week = date[1]
                    break
            if contest_week == gs.current_date:
                time_mult = 1.2
            elif contest_week == gs.current_date + 1:
                time_mult = 1.1
            else:
                time_mult = 1.0
            for district in states[state].districts:
                campaingingTime = district.campaigningThisTurn[i]
                adBuy = district.adsThisTurn[i]
                adsTotal = sum(district.adsThisTurn)
                # Momentum boost: 50 momentum ~= +30% support. Recomputed from
                # time_mult each district so momentum isn't applied
                # cumulatively across the district loop.
                mult = (1 + float(players[i + 1].momentum) / 167.0) * time_mult

                # Issue-of-the-week alignment uses the STATE's position.
                # Matching stance makes support easier; clashing makes it
                # harder. Disabled in non-issues mode.
                issueMult = 1
                state_pos = 0
                if gs.issues_mode:
                    try:
                        state_pos = states[state].positions[gs.event_of_week]
                    except (IndexError, AttributeError, TypeError):
                        state_pos = 0
                pp_list = players[i + 1].positions or []
                player_pos = pp_list[gs.event_of_week] if 0 <= gs.event_of_week < len(pp_list) else 0
                if state_pos == 0:
                    pass  # state has no strong stance, no bonus or penalty
                elif player_pos == state_pos:
                    issueMult += 0.33
                else:
                    issueMult -= 0.16 * abs(player_pos - state_pos)

                if issueMult <= 0.25:
                    issueMult = 0.25
                mult = issueMult * mult

                # Three support sources, tracked separately for the
                # end-of-game breakdown. Org passive support scales inversely
                # with game length so cumulative org payoff is ~constant
                # across 8/10/20-turn games.
                nt = gs.num_turns if gs.num_turns and gs.num_turns > 0 else 10
                org_support = org * (5.0 / nt) * mult
                campaign_support = campaingingTime * 3.0 * mult
                # +1 avoids dividing by 0 when there's no advertising.
                ad_support = (float(adBuy) / float(adsTotal + 1)) * (adsTotal / 100.0) ** 0.55 * mult
                support = org_support + campaign_support + ad_support
                try:
                    players[i + 1].addStat('support_from_org', org_support)
                    players[i + 1].addStat('support_from_campaign', campaign_support)
                    players[i + 1].addStat('support_from_ads', ad_support)
                except AttributeError:
                    pass
                support = round(support)
                district.setSupport(i, support)
            states[state].updateSupport(gs.num_players, gs.calendar, gs.current_date)
    hooks.week_summary(gs, snap)


def calc_end_turn(gs, player_idx, fundraising):
    """Compute a player's resources for the coming week.

    Transcribed from ``CampaignGame.calcEndTurn`` (``player_idx`` replaces the
    global ``player``). Resets time to 80, adds fundraising + baseline +
    local (organization/support driven, momentum-boosted) money, decays
    momentum to 1/4 (contest wins are added back later in
    ``decide_contests``), and records the turn on the Player for stats.
    """
    players = gs.players
    states = gs.states
    resources = players[player_idx].resources

    # time
    resources[0] = 80
    # money: remaining + fundraising + baseline + momentum + from states org
    localFundraising = 0
    for state in states:
        for district in states[state].districts:
            # expected number donating 0-.45 given support 0-150
            numberDonating = 1 - (1.5 + states[state].organizations[player_idx - 1] / 10.0) ** (district.support[player_idx - 1] / -50.0)
            localFundraising += numberDonating * district.population * 500 * (2 - math.exp(players[player_idx].momentum / -50.0))

    localFundraising = round(localFundraising)
    resources[1] = resources[1] + fundraising * 4000 + 20000 + localFundraising
    # Momentum decays steeply each week — keep only the last 1/4. Wins from
    # the contests decided later this week are added on top in decide_contests.
    players[player_idx].momentum = players[player_idx].momentum / 4.0

    # Time/money this player actually committed to campaigning and ads this
    # turn (district allocations aren't reset until the week rolls over, so
    # they're still accurate here).
    campaign_hours = 0
    ad_spend = 0
    for s in states:
        for d in states[s].districts:
            try:
                campaign_hours += d.campaigningThisTurn[player_idx - 1]
                ad_spend += d.adsThisTurn[player_idx - 1]
            except (IndexError, TypeError):
                pass
    players[player_idx].endTurn(gs.current_date, fundraising * 4000 + 20000, localFundraising,
                                fundraisingHours=fundraising,
                                campaigningHours=campaign_hours,
                                adSpend=ad_spend)


def decide_contests(gs, hooks=None):
    """Resolve every contest whose election was last week and award delegates.

    Transcribed from ``CampaignGame.decideContests``. Returns the
    ``weekResults`` structure (per-player delegates/states/districts plus a
    ``'_state_results'`` per-state vote-share breakdown) that the real game's
    start-of-turn report renders; also mutates ``gs.past_elections`` and each
    Player's momentum / delegateCount / stats.

    Momentum model: a base pool of 50 grows with the delegates decided this
    week and, after immediate penalties (negative district votes, being
    overtaken), is distributed proportionally to each player's delegate share.
    """
    hooks = hooks or NULL_HOOKS
    players = gs.players
    states = gs.states
    numPlayers = gs.num_players
    rng = gs.rng

    momentums = []
    weekDelegates = {}
    weekResults = {}
    for i in range(numPlayers):
        momentums.append(0)
        weekDelegates[i + 1] = 0
        weekResults[i + 1] = {'delegates': 0, 'states': [], 'districts': []}
    # Per-state vote-share breakdowns, under a string key so it doesn't
    # collide with the 1-based player ids that own the rest of weekResults.
    weekResults['_state_results'] = {}
    totalMomemtum = 50
    decided_any = False
    for state in gs.calendar:
        if state[1] + 1 == gs.current_date:
            if not decided_any:
                hooks.contests_header(gs)
                decided_any = True
            states[state[0]].calculatePollingAverage(gs.calendar, gs.current_date)  # just in case it isn't up to date

            stateName = state[0]
            orgs = states[stateName].organizations
            stateDelegates = 0
            stateVotes = []
            for i in range(numPlayers):
                stateVotes.append(0)
            _debug_district_winners = []
            for district in states[stateName].districts:
                districtDelegates = (district.population * 2) / 3
                stateDelegates += district.population - districtDelegates
                winner = 0
                mostVotes = 0
                totalVotes = 0
                for i in range(numPlayers):
                    if orgs[i] > 0:  # checking that player is on the ballot
                        votes = rng.gauss(district.pollingAverage[i], 3)
                        votes = votes * district.population * 150000
                        totalVotes += votes
                        if votes < 0:
                            votes = 1
                            players[i + 1].momentum -= 2
                        if votes > mostVotes:
                            if winner != 0:
                                players[winner].momentum -= 1
                            winner = i + 1
                            mostVotes = votes
                        elif votes == mostVotes:
                            winner = rng.randint(1, numPlayers)
                        stateVotes[i] += votes * district.population
                    else:
                        votes = 0

                if winner == 0:
                    winner = rng.randint(1, numPlayers)
                    stateVotes[winner - 1] += 1

                players[winner].delegateCount += districtDelegates
                weekDelegates[winner] += districtDelegates

                _debug_district_winners.append((district.name, winner))
                weekResults[winner]['delegates'] += districtDelegates
                weekResults[winner]['districts'].append(district.name)
                try:
                    players[winner].addStat('districts_won', 1)
                except AttributeError:
                    pass

                totalMomemtum += districtDelegates / 4.0
                momentums[winner - 1] += districtDelegates

            stateWinner = stateVotes.index(max(stateVotes)) + 1
            stateMostVotes = max(stateVotes)

            players[stateWinner].delegateCount += stateDelegates
            weekDelegates[stateWinner] += stateDelegates

            # Credit the state-level delegates to the aggregate stateWinner,
            # not to the leftover district `winner`.
            weekResults[stateWinner]['delegates'] += stateDelegates
            weekResults[stateWinner]['states'].append(stateName)

            totalMomemtum += stateDelegates / 2.0
            momentums[winner - 1] += stateDelegates

            gs.past_elections[stateName] = stateWinner
            try:
                players[stateWinner].addStat('states_won', stateName)
            except AttributeError:
                pass

            stateVotesTotal = sum(stateVotes)
            state_pct = {}
            for i in range(numPlayers):
                if stateVotesTotal > 0:
                    pct = round(float(stateVotes[i]) / float(stateVotesTotal) * 100, 1)
                else:
                    pct = 0.0
                state_pct[i + 1] = pct
            weekResults['_state_results'][stateName] = {
                'winner': stateWinner,
                'percentages': state_pct,
            }
            hooks.state_resolved(gs, stateName, stateVotes,
                                 _debug_district_winners, stateWinner,
                                 stateVotesTotal)

    # (weekResultString in the original was dead code; dropped.)

    # Divvy up the momentum pool by each player's share of delegates won.
    for i in range(len(momentums)):
        players[i + 1].momentum += momentums[i] / float(sum(momentums) + .01) * totalMomemtum
    return weekResults


def reset_weekly(gs):
    """Clear each district's per-player campaigning/ad allocations for the
    next week. In the real game this runs inline at the end of ``endTurn``."""
    for state in gs.states:
        for district in gs.states[state].districts:
            for i in range(gs.num_players):
                district.setCampaigningThisTurn(i, 0)
                district.setAdsThisTurn(i, 0)


def randomize_calendar(states, num_turns, rng, first_week=2):
    """Build a randomized primary calendar: list of (state_name, week).

    Shared by both the desktop game (CampaignGame.setCalendar) and the web
    server (server/game_world.build_match) so the two produce the same shape.

    The schedule keeps the real primary's feel: the first couple of weeks hold
    only a few small states, and both the number of contests and their size
    ramp up week over week. States are ordered smallest-to-largest by delegate
    count with a bit of jitter (so it differs each game), then mapped onto the
    contest weeks with a concave curve that packs more — and larger — states
    into the later weeks.

    ``states``     dict of name -> State (uses each State's district populations
                   only for RELATIVE sizing, so the desktop's *1 and the sim's
                   *3 district-population scaling both work).
    ``num_turns``  total weeks; contests run from ``first_week`` through it.
    ``rng``        a random.Random (or the random module) exposing uniform().
    """
    names = list(states.keys())
    n = len(names)
    if n == 0:
        return []

    last_week = max(first_week, num_turns)

    size = {name: sum(d.population for d in states[name].districts) for name in names}
    # Rank smallest -> largest, then jitter each rank by up to ~12% of the field
    # so the ordering (and thus the calendar) varies game to game without losing
    # the small-first trend.
    by_size = sorted(names, key=lambda name: size[name])
    rank = {name: i for i, name in enumerate(by_size)}
    jitter = max(1.0, n * 0.12)
    seq = sorted(names, key=lambda name: rank[name] + rng.uniform(-jitter, jitter))

    # Map ordinal position (0 = smallest-ish) to a week. Exponent < 1 makes the
    # curve concave: early ordinals spread across the opening weeks a few at a
    # time, later ordinals compress into the final weeks many at a time.
    span = last_week - first_week
    p = 0.62
    calendar = []
    for i, name in enumerate(seq):
        frac = (i / (n - 1)) if n > 1 else 0.0
        week = first_week + span * (frac ** p)
        week = int(round(week))
        week = max(first_week, min(last_week, week))
        calendar.append((name, week))

    # Guarantee the opening: the first two contest weeks should each have at
    # least one small state (a lone empty opening week reads oddly). If either
    # is empty, pull it from the earliest over-full later week.
    if span >= 1:
        weeks_used = {}
        for name, wk in calendar:
            weeks_used.setdefault(wk, []).append(name)
        for target in (first_week, first_week + 1):
            if target > last_week:
                break
            if weeks_used.get(target):
                continue
            donor_wk = next((w for w in sorted(weeks_used)
                             if w > target and len(weeks_used[w]) > 1), None)
            if donor_wk is None:
                continue
            # Move the smallest state from the donor week down to the empty week.
            mover = min(weeks_used[donor_wk], key=lambda name: size[name])
            weeks_used[donor_wk].remove(mover)
            weeks_used.setdefault(target, []).append(mover)
            calendar = [(nm, target if nm == mover else wk) for nm, wk in calendar]

    return calendar
