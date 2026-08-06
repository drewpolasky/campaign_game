"""Server-authoritative game orchestration.

Pure game logic over an ``engine.GameState`` — no Flask, no DB. The API/DB
layer persists the JSON docs (via ``state_schema``) and decides *when* to call
``resolve_turn``; this module decides *what happens*.

Turn model (simultaneous / "Live"): every seat plays the same week from the
same week-start state. A seat's move is validated and stashed; once every
human seat has submitted, ``resolve_turn`` fills AI seats, applies all moves,
runs the engine once, and advances the week. This is the desktop Live mode's
``_sim_do_resolution`` (CampaignGame.py:4458) made authoritative.

A **move payload** for one seat:

    { "campaigning": { "<state>": { "<district>": hours, ... }, ... },
      "ads":         { "<state>": { "<district>": dollars, ... }, ... },
      "orgs":        { "<state>": build_count, ... },
      "fundraising": <ignored — see note> }

Note on fundraising: the desktop rolls ALL non-campaign time into fundraising
at End Turn (CampaignGame.endTurn), so effective fundraising is deterministic:
``80 - total_campaign_hours``. We derive it that way and don't trust a
client-supplied value. Org build cost scales per tier (0->1 and 1->2 cost
$10k each, tier k>=2 costs $10k*k), matching getOnBallot (CampaignGame.py:3857).
"""
import os
import secrets
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import engine  # noqa: E402
import state_issues  # noqa: E402
from server import ai, game_world, state_schema  # noqa: E402

WEEKLY_TIME = 80
ORG_BASE_COST = 10000
MATCH_ID_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no confusable 0/O/1/I
MATCH_ID_LEN = 6


# --- creation -------------------------------------------------------------

def generate_match_id(rng=secrets):
    return ''.join(MATCH_ID_ALPHABET[secrets.randbelow(len(MATCH_ID_ALPHABET))]
                   for _ in range(MATCH_ID_LEN))


def create_match(config):
    """Build a fresh match from ``config`` (see game_world.build_match).

    Returns (doc, seat_tokens, spectator_token) where doc is the JSON match
    document, seat_tokens is {seat: token} for **human** seats (the magic-link
    secrets; AI seats get none), and spectator_token is a read-only link secret.
    """
    gs = game_world.build_match(config)
    match_id = generate_match_id()
    doc = state_schema.match_to_dict(gs, match_id=match_id, week_results={}, whose_turn=None)

    seat_tokens = {}
    for seat_cfg in doc['config']['seats']:
        if seat_cfg['controller'] == 'human':
            seat_tokens[seat_cfg['seat']] = secrets.token_urlsafe(16)
    spectator_token = secrets.token_urlsafe(16)
    return doc, seat_tokens, spectator_token


# --- move cost / validation ----------------------------------------------

def org_build_cost(from_tier, count, base=ORG_BASE_COST):
    """Total $ to build ``count`` org tiers starting at ``from_tier``.
    Tiers 0->1 and 1->2 cost ``base`` each; tier k>=2 costs ``base``*k. ``base``
    is the state's size-scaled cost (engine.org_base_cost); it defaults to the
    medium $10k so callers that don't care about size still work."""
    total = 0
    tier = from_tier
    for _ in range(count):
        total += base if tier <= 1 else base * tier
        tier += 1
    return total


def _contest_week(gs, state_name):
    for name, week in gs.calendar:
        if name == state_name:
            return week
    return None


def _sum_campaign_hours(move):
    return sum(h for dists in move.get('campaigning', {}).values() for h in dists.values())


def validate_move(gs, seat, move):
    """Return (ok: bool, error: str|None). Server-authoritative — the client's
    own checks are UX only."""
    if seat not in gs.players:
        return False, 'no such seat {}'.format(seat)
    idx = seat - 1
    money = gs.players[seat].resources[1]

    campaigning = move.get('campaigning', {}) or {}
    ads = move.get('ads', {}) or {}
    orgs = move.get('orgs', {}) or {}

    # Referenced states/districts must exist.
    for smap, label in ((campaigning, 'campaigning'), (ads, 'ads')):
        for state_name, dists in smap.items():
            if state_name not in gs.states:
                return False, 'unknown state {!r} in {}'.format(state_name, label)
            valid_dnames = {d.name for d in gs.states[state_name].districts}
            for dname, val in dists.items():
                if dname not in valid_dnames:
                    return False, 'unknown district {!r} in {}'.format(dname, state_name)
                if not isinstance(val, int) or val < 0:
                    return False, 'bad {} value for {}/{}'.format(label, state_name, dname)

    # Time: campaign hours (the rest of the 80h auto-fundraises).
    total_hours = _sum_campaign_hours(move)
    if total_hours > WEEKLY_TIME:
        return False, 'campaign hours {} exceed weekly {}'.format(total_hours, WEEKLY_TIME)

    # Money: ads + org builds must fit the current bankroll, and org buys must
    # respect the "on the ballot before the contest is over" rule.
    total_ads = sum(v for dists in ads.values() for v in dists.values())
    total_org_cost = 0
    for state_name, count in orgs.items():
        if state_name not in gs.states:
            return False, 'unknown state {!r} in orgs'.format(state_name)
        if not isinstance(count, int) or count < 0:
            return False, 'bad org build count for {}'.format(state_name)
        if count == 0:
            continue
        cur_tier = gs.states[state_name].organizations[idx]
        cw = _contest_week(gs, state_name)
        if cur_tier == 0 and cw is not None and gs.current_date > cw:
            return False, 'too late to get on the ballot in {}'.format(state_name)
        total_org_cost += org_build_cost(cur_tier, count, base=engine.org_base_cost(gs.states[state_name]))

    if total_ads + total_org_cost > money:
        return False, 'insufficient funds: need {}, have {}'.format(total_ads + total_org_cost, money)

    return True, None


def apply_move(gs, seat, move):
    """Write ``seat``'s allocations into ``gs`` and deduct money. Assumes the
    move was validated. Mirrors the per-seat splice in
    _merge_seat_from_submission (CampaignGame.py:4421) plus the org/ad money
    deductions the desktop does during a turn."""
    idx = seat - 1
    p = gs.players[seat]

    campaigning = move.get('campaigning', {}) or {}
    ads = move.get('ads', {}) or {}
    orgs = move.get('orgs', {}) or {}

    spend = 0
    # Organizations (cost scales per tier; deduct as we build).
    for state_name, count in orgs.items():
        if not count:
            continue
        st = gs.states[state_name]
        cost = org_build_cost(st.organizations[idx], count, base=engine.org_base_cost(st))
        spend += cost
        st.organizations[idx] += count
        try:
            p.addStat('org_money_total', cost)
            p.addStat('orgs_built', count)
        except AttributeError:
            pass

    # District campaigning + ads.
    for state_name, dists in campaigning.items():
        st = gs.states[state_name]
        by_name = {d.name: d for d in st.districts}
        for dname, hours in dists.items():
            by_name[dname].setCampaigningThisTurn(idx, hours)
    for state_name, dists in ads.items():
        st = gs.states[state_name]
        by_name = {d.name: d for d in st.districts}
        for dname, dollars in dists.items():
            by_name[dname].setAdsThisTurn(idx, dollars)
            spend += dollars

    p.resources[1] -= spend


# --- resolution -----------------------------------------------------------

def resolve_turn(gs, human_moves, rng):
    """Resolve one week. ``human_moves`` maps seat -> move for the human seats
    that submitted; AI seats are filled here. Mutates ``gs`` (advances a week)
    and returns (week_results, all_moves).

    Sequence mirrors the desktop rollover: per-seat calc_end_turn (money for
    next week), then calc_state_opinions, advance the date, decide_contests,
    reset weekly allocations.
    """
    gs.rng = rng

    # 1. Assemble every seat's move from the SAME week-start state (AI decides
    #    from the pristine state, exactly as humans did).
    all_moves = {}
    for seat in range(1, gs.num_players + 1):
        if seat in human_moves:
            all_moves[seat] = human_moves[seat]
        else:
            all_moves[seat] = ai.compute_move(gs, seat, rng=rng)

    # 2. Validate + apply each seat's allocations.
    for seat, move in all_moves.items():
        ok, err = validate_move(gs, seat, move)
        if not ok:
            raise ValueError('seat {} move invalid at resolve: {}'.format(seat, err))
        apply_move(gs, seat, move)

    # 3. Per-seat money step. Effective fundraising = all non-campaign time.
    for seat in range(1, gs.num_players + 1):
        campaign_hours = sum(
            d.campaigningThisTurn[seat - 1]
            for st in gs.states.values() for d in st.districts)
        fundraising = WEEKLY_TIME - campaign_hours
        engine.calc_end_turn(gs, seat, fundraising)

    # 4. World physics for the week (real-game order: apply support, advance,
    #    then resolve contests), then clear weekly allocations.
    engine.calc_state_opinions(gs)
    gs.current_date += 1
    week_results = engine.decide_contests(gs)
    engine.reset_weekly(gs)
    # Roll a fresh issue of the week for the upcoming week (matches the desktop
    # game and the RL sim, both of which re-roll event_of_week each turn).
    gs.event_of_week = rng.randint(0, len(state_issues.ISSUES) - 1)

    return week_results, all_moves


def is_game_over(gs):
    return gs.current_date > gs.num_turns
