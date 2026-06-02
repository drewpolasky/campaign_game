"""Action encoding: discrete RL action -> sim resource allocation.

Bootstrap encoding (MultiDiscrete, 4 components):
    target_state       : 50  (which active state to push hardest)
    aggression         :  4  (100/70/50/30% of campaign+ad budget to target)
    ad_vs_org_lean     :  3  (lean ads / balanced / lean orgs)
    fundraising_bucket :  4  (0 / 20 / 40 / 60 hours fundraising; rest campaigning)

Decoded into:
    fundraising_hours      (returned)
    per-district campaigning hours  (written to district.campaigningThisTurn)
    per-district ad spend           (written to district.adsThisTurn)
    per-state org investment        (written to state.organizations + cost paid)

The decoder reuses the heuristic primitives in sim_balance:
    _spend_money_on_orgs, _greedy_spend_ads, _greedy_spend_time
applied with policy-emitted scoring biases. Only an *active* state (primary
not yet held) is a valid target; we mask invalid targets in the env.
"""
from dataclasses import dataclass

import sim_balance as _sb


# Layout of the MultiDiscrete action; consumers can read this for action mask
# construction and policy head sizing.
NUM_TARGET_STATES = 50
NUM_AGGRESSION = 4
NUM_LEAN = 3
NUM_FUNDRAISING_BUCKETS = 4

ACTION_NVEC = (NUM_TARGET_STATES, NUM_AGGRESSION, NUM_LEAN, NUM_FUNDRAISING_BUCKETS)
ACTION_DIM = sum(ACTION_NVEC)  # for one-hot encoding if a flat policy head is used

# Toggle: print a message every time an org is built. Set by
# realgame_strategy when the user is playing the real game so they can
# see in real time which states the AI is investing in.
_LOG_ORG_BUILDS = False

# Toggle: at the end of every decoded turn, print a summary of where the
# agent spent campaign hours and ad money, alongside the org tier in
# each state. A `[LEAK]` tag flags any state with a non-zero spend but
# zero org — those should never happen via our filtered decoders, so an
# occurrence indicates a bug worth tracking down.
_LOG_SPEND = False


def set_log_org_builds(enabled: bool):
    global _LOG_ORG_BUILDS
    _LOG_ORG_BUILDS = bool(enabled)


def set_log_spend(enabled: bool):
    global _LOG_SPEND
    _LOG_SPEND = bool(enabled)


def _log_post_decode_spend(sim, p_idx, fundraising_hours):
    """Walk every state and emit one line per state with non-zero spend
    this turn. Tag with [LEAK] if there's spend but org tier is 0."""
    if not _LOG_SPEND:
        return
    total_hrs = 0
    total_ads = 0
    print('[NeuralPPO spend turn={}]  fundraising_hrs={}'.format(
        sim.current_date, fundraising_hours))
    for state_name, st in sim.states.items():
        camp = 0
        ads = 0
        for d in st.districts:
            try:
                camp += d.campaigningThisTurn[p_idx]
                ads += d.adsThisTurn[p_idx]
            except (IndexError, AttributeError):
                continue
        if camp == 0 and ads == 0:
            continue
        try:
            org = st.organizations[p_idx]
        except (IndexError, AttributeError):
            org = 0
        tag = '  [LEAK org=0]' if org == 0 else ''
        print('  {:22s}  org={}  camp_hrs={}  ads=${}{}'.format(
            state_name, org, camp, ads, tag))
        total_hrs += camp
        total_ads += ads
    print('  total: {} camp_hrs, ${} ads'.format(total_hrs, total_ads))

AGGRESSION_FRACTIONS = (1.0, 0.7, 0.5, 0.3)
FUNDRAISING_HOURS = (0, 20, 40, 60)
LEAN_AD_WEIGHTS = (1.4, 1.0, 0.6)   # ads multiplier
LEAN_ORG_WEIGHTS = (0.6, 1.0, 1.4)  # org multiplier


@dataclass
class DecodedAction:
    target_state: str             # the canonical state name, or '' if no active state
    aggression: float
    ad_weight: float
    org_weight: float
    fundraising_hours: int


def _calendar_state_order(sim):
    """States in calendar order — matches the obs encoding's per-state slots."""
    order = []
    seen = set()
    for name, _ in sim.calendar:
        if name not in seen and name in sim.states:
            order.append(name)
            seen.add(name)
    # Trail any states not on the calendar (shouldn't happen).
    for name in sim.states:
        if name not in seen:
            order.append(name)
    return order


def active_state_mask(sim):
    """Boolean mask of length NUM_TARGET_STATES — True if state's primary is
    still upcoming. Used by the policy to mask invalid target_state actions."""
    order = _calendar_state_order(sim)
    mask = [False] * NUM_TARGET_STATES
    for i, name in enumerate(order[:NUM_TARGET_STATES]):
        for ename, week in sim.calendar:
            if ename == name:
                if week - sim.current_date >= 0:
                    mask[i] = True
                break
    return mask


def decode_action(sim, p_idx, action):
    """Apply `action` for player p_idx. Mutates the sim. Returns
    fundraising_hours (int)."""
    target_idx, aggr_idx, lean_idx, fund_idx = (int(a) for a in action)

    order = _calendar_state_order(sim)
    target_name = ''
    if 0 <= target_idx < min(len(order), NUM_TARGET_STATES):
        cand = order[target_idx]
        # If the chosen state has already finished, fall back to first active.
        for ename, week in sim.calendar:
            if ename == cand and week - sim.current_date >= 0:
                target_name = cand
                break
    if not target_name:
        for name in order:
            for ename, week in sim.calendar:
                if ename == name and week - sim.current_date >= 0:
                    target_name = name
                    break
            if target_name:
                break

    aggression = AGGRESSION_FRACTIONS[aggr_idx]
    ad_w = LEAN_AD_WEIGHTS[lean_idx]
    org_w = LEAN_ORG_WEIGHTS[lean_idx]
    fundraising_hours = FUNDRAISING_HOURS[fund_idx]

    p = sim.players[p_idx]

    # --- Org spending: prioritize the target state, then nearby contests ---
    # Scoring is the existing heuristic, with a bonus for the target.
    for state_name, st in sim.states.items():
        tte = _sb.time_to_election(sim, state_name)
        if tte < 0 or tte > 8:
            continue
        org_level = st.organizations[p_idx]
        cost = max(10000, 10000 * org_level)
        state_delegates = sum(
            d.population - (d.population * 2) / 3 for d in st.districts)
        # Org-value bonus for target; baseline matches sim_balance threshold=18.
        org_value = state_delegates * (1.0 + max(0, 6 - tte))
        threshold = 18.0 / max(org_w, 0.01)
        if state_name == target_name:
            org_value *= (1.0 + aggression)
        if org_value > (org_level + 1) * threshold and p.resources[1] >= cost:
            p.resources[1] -= cost
            st.organizations[p_idx] += 1
            p.money_on_org += cost
            if _LOG_ORG_BUILDS:
                print(f'[NeuralPPO] +1 org in {state_name} '
                      f'(now tier {st.organizations[p_idx]}, '
                      f'spent ${cost}, ${p.resources[1]} left)')

    # --- Build a scored district list with target bias ---
    def urgency_curve(t):
        # Mild ramp-up as election nears, similar to strat_default.
        if t <= 0:
            return 1.5
        if t <= 1:
            return 1.3
        if t <= 3:
            return 1.0
        return 0.6

    scored = _sb._scored_districts(sim, p_idx, urgency_curve,
                                   closeness_w=1.0, delegates_w=1.0,
                                   runaway_floor=-25, jitter=0.0,
                                   only_imminent_weeks=99)
    # Apply target-state bias and lean weighting (orgs handled above; ad/time
    # weights tilt allocation between the two channels).
    for entry in scored:
        if entry[3] == target_name:
            entry[0] *= (1.0 + aggression * 1.5)

    # --- Fundraising allotment ---
    # Cap at available hours.
    fundraising_hours = min(fundraising_hours, p.resources[0])
    p.resources[0] -= fundraising_hours

    # --- Ad spending: greedy on scored, weighted by ad lean ---
    # Make a copy so time scoring isn't degraded by ad multiplier decay.
    ad_scored = [list(e) for e in scored]
    for e in ad_scored:
        e[0] *= ad_w
    _sb._greedy_spend_ads(sim, p_idx, ad_scored)

    # --- Time spending: greedy on the original scored list ---
    leftover_fundraising = _sb._greedy_spend_time(sim, p_idx, scored,
                                                  fundraise_cutoff=2.0)
    fundraising_hours += leftover_fundraising

    _log_post_decode_spend(sim, p_idx, fundraising_hours)
    return fundraising_hours


def random_action(rng):
    """Sample a uniform random MultiDiscrete action."""
    return (rng.randrange(NUM_TARGET_STATES),
            rng.randrange(NUM_AGGRESSION),
            rng.randrange(NUM_LEAN),
            rng.randrange(NUM_FUNDRAISING_BUCKETS))


# ---------------------------------------------------------------------------
# Continuous (Box) action space
#
# Layout: 50 + 50 + 50 + 1 = 151 floats, each in [-5, 5] post-clip:
#   [0:50]    campaign-priority logits per state
#   [50:100]  ad-priority logits per state
#   [100:150] org-priority logits per state
#   [150]     fundraising fraction logit (sigmoided to [0, 1])
#
# Decoded into the same effects as the MultiDiscrete decoder. Each channel's
# logits are softmaxed across active states (mask finished ones), then the
# softmax weights bias `_scored_districts` for that channel. Org investment
# uses the org-priority weight as a multiplier on the existing threshold.
# ---------------------------------------------------------------------------

CONT_ACTION_DIM = 3 * NUM_TARGET_STATES + 1   # 151
CONT_ACTION_LOW = -5.0
CONT_ACTION_HIGH = 5.0


def _softmax_masked(logits, mask):
    import numpy as np
    masked = np.where(mask, logits, -np.inf)
    if not np.any(np.isfinite(masked)):
        # All finished — fall back to uniform over everything.
        return np.full_like(logits, 1.0 / len(logits))
    m = np.max(masked[np.isfinite(masked)])
    e = np.exp(masked - m)
    e = np.where(mask, e, 0.0)
    s = e.sum()
    return e / s if s > 0 else np.full_like(logits, 1.0 / len(logits))


def decode_continuous_action(sim, p_idx, action):
    """Apply a continuous action vector (length CONT_ACTION_DIM) for player
    p_idx. Mutates the sim. Returns fundraising_hours (int)."""
    import math
    import numpy as np

    action = np.asarray(action, dtype=np.float32)
    camp_logits = action[0:NUM_TARGET_STATES]
    ad_logits = action[NUM_TARGET_STATES:2 * NUM_TARGET_STATES]
    org_logits = action[2 * NUM_TARGET_STATES:3 * NUM_TARGET_STATES]
    fund_logit = float(action[3 * NUM_TARGET_STATES])

    order = _calendar_state_order(sim)
    mask = np.array(active_state_mask(sim), dtype=bool)
    name_to_pos = {name: i for i, name in enumerate(order[:NUM_TARGET_STATES])}

    camp_w = _softmax_masked(camp_logits, mask)
    ad_w = _softmax_masked(ad_logits, mask)
    org_w = _softmax_masked(org_logits, mask)

    p = sim.players[p_idx]

    # --- Org investment: scale the existing threshold by 1/org_weight (so
    # higher weight = lower threshold to invest). Bound to keep behaviour sane. ---
    for state_name, st in sim.states.items():
        tte = _sb.time_to_election(sim, state_name)
        if tte < 0 or tte > 8:
            continue
        pos = name_to_pos.get(state_name)
        if pos is None:
            continue
        weight = float(org_w[pos])
        # Average weight under uniform over k active states is 1/k. We want a
        # weight of ~1/k to roughly match the heuristic threshold; lower
        # weight => higher threshold (skip), higher => lower threshold (invest).
        n_active = max(1, int(mask.sum()))
        scaled = weight * n_active  # ~1.0 at neutral
        threshold = 18.0 / max(scaled, 0.05)
        org_level = st.organizations[p_idx]
        cost = max(10000, 10000 * org_level)
        state_delegates = sum(
            d.population - (d.population * 2) / 3 for d in st.districts)
        org_value = state_delegates * (1.0 + max(0, 6 - tte))
        if org_value > (org_level + 1) * threshold and p.resources[1] >= cost:
            p.resources[1] -= cost
            st.organizations[p_idx] += 1
            p.money_on_org += cost
            if _LOG_ORG_BUILDS:
                print(f'[NeuralPPO] +1 org in {state_name} '
                      f'(now tier {st.organizations[p_idx]}, '
                      f'spent ${cost}, ${p.resources[1]} left)')

    # --- Build scored districts and apply per-state weight biases per channel ---
    def urgency_curve(t):
        if t <= 0:
            return 1.5
        if t <= 1:
            return 1.3
        if t <= 3:
            return 1.0
        return 0.6

    scored = _sb._scored_districts(sim, p_idx, urgency_curve,
                                   closeness_w=1.0, delegates_w=1.0,
                                   runaway_floor=-25, jitter=0.0,
                                   only_imminent_weeks=99)

    # Time-channel scoring: bias by campaign weight × n_active (1.0 at neutral).
    n_active = max(1, int(mask.sum()))
    time_scored = []
    for entry in scored:
        pos = name_to_pos.get(entry[3])
        bias = float(camp_w[pos]) * n_active if pos is not None else 1.0
        time_scored.append([entry[0] * bias, entry[1], entry[2], entry[3]])

    # Ad-channel scoring: bias by ad weight × n_active.
    ad_scored = []
    for entry in scored:
        pos = name_to_pos.get(entry[3])
        bias = float(ad_w[pos]) * n_active if pos is not None else 1.0
        ad_scored.append([entry[0] * bias, entry[1], entry[2], entry[3]])

    # --- Fundraising allotment ---
    fund_frac = 1.0 / (1.0 + math.exp(-fund_logit))
    fundraising_hours = int(round(fund_frac * 60))
    fundraising_hours = min(fundraising_hours, p.resources[0])
    p.resources[0] -= fundraising_hours

    # --- Spend ads, then time ---
    _sb._greedy_spend_ads(sim, p_idx, ad_scored)
    leftover = _sb._greedy_spend_time(sim, p_idx, time_scored,
                                      fundraise_cutoff=2.0)
    fundraising_hours += leftover

    _log_post_decode_spend(sim, p_idx, fundraising_hours)
    return fundraising_hours


def random_continuous_action(rng):
    import numpy as np
    return np.array([rng.gauss(0, 1) for _ in range(CONT_ACTION_DIM)],
                    dtype=np.float32)


# ---------------------------------------------------------------------------
# Coupled (Box) action space — v12+
#
# Game-log analysis of v11 showed the agent was building tier-1 orgs in
# 30+ states without backing them up with ads or campaign hours. Root
# cause: the original continuous decoder emits three INDEPENDENT softmax
# distributions (one each for camp / ad / org), so "where to build org"
# and "where to spend ads" can diverge — the agent ends up with org
# scaffolding all over the map but no concentrated investment anywhere.
#
# Coupled action space fixes this by emitting ONE per-state importance
# vector that drives all three channels simultaneously. The mix between
# channels is controlled by 3 scalar knobs:
#   [0:50]   state_importance logits (softmax-masked to active states)
#   [50]     fundraising_fraction logit (sigmoid -> 0..1 of hours)
#   [51]     org_money_fraction logit (sigmoid -> 0..1 of money)
#   [52]     ads_vs_time_fraction logit (sigmoid -> 0..1 of remaining hours
#            kept for campaigning; the complement is folded back into
#            fundraising in case the policy wants to fundraise the rest)
# Total: 53 floats.
# ---------------------------------------------------------------------------

COUPLED_ACTION_DIM = NUM_TARGET_STATES + 3   # 53
COUPLED_ACTION_LOW = -5.0
COUPLED_ACTION_HIGH = 5.0


def decode_coupled_action(sim, p_idx, action):
    """Apply a coupled action vector (length COUPLED_ACTION_DIM) for
    player p_idx. Mutates the sim. Returns fundraising_hours (int).

    Spreads orgs, ads, and campaign hours along the SAME per-state
    importance ranking so the agent can't decouple "build org here" from
    "spend ads here"."""
    import math
    import numpy as np

    action = np.asarray(action, dtype=np.float32)
    state_logits = action[0:NUM_TARGET_STATES]
    fund_logit = float(action[NUM_TARGET_STATES])
    org_money_logit = float(action[NUM_TARGET_STATES + 1])
    camp_keep_logit = float(action[NUM_TARGET_STATES + 2])

    order = _calendar_state_order(sim)
    mask = np.array(active_state_mask(sim), dtype=bool)
    name_to_pos = {name: i for i, name in enumerate(order[:NUM_TARGET_STATES])}

    state_w = _softmax_masked(state_logits, mask)
    fund_frac = 1.0 / (1.0 + math.exp(-fund_logit))
    org_money_frac = 1.0 / (1.0 + math.exp(-org_money_logit))
    camp_keep_frac = 1.0 / (1.0 + math.exp(-camp_keep_logit))

    p = sim.players[p_idx]
    n_active = max(1, int(mask.sum()))

    # --- Resource splits ---
    start_money = p.resources[1]
    start_hours = p.resources[0]
    fundraising_hours = int(round(fund_frac * start_hours))
    fundraising_hours = max(0, min(fundraising_hours, start_hours))
    # Hours left after the fundraising decision; camp_keep_frac decides
    # how much of THAT to keep for campaigning vs convert back to
    # fundraising. This gives the policy a graceful way to fundraise
    # more than the primary slider would naively allow if its state
    # weights all collapsed to zero.
    leftover_hours_pool = start_hours - fundraising_hours
    campaign_budget_hours = int(round(camp_keep_frac * leftover_hours_pool))
    fundraising_hours += leftover_hours_pool - campaign_budget_hours
    p.resources[0] = campaign_budget_hours

    org_budget = int(round(org_money_frac * start_money))
    org_budget = max(0, min(org_budget, start_money))

    # --- Org investment, ordered by state importance ---
    # Build orgs in highest-weight states first, paying for each tier
    # out of org_budget. Stops when budget runs out or no remaining state
    # clears a usefulness check.
    ranked = sorted(
        ((float(state_w[name_to_pos[n]]) if n in name_to_pos else 0.0, n)
         for n, _ in sim.states.items()),
        reverse=True)
    for weight, state_name in ranked:
        if org_budget <= 0:
            break
        if weight <= 0:
            break
        st = sim.states[state_name]
        tte = _sb.time_to_election(sim, state_name)
        if tte < 0 or tte > 9:
            continue
        org_level = st.organizations[p_idx]
        if org_level >= 5:
            continue
        cost = max(10000, 10000 * org_level)
        if org_budget < cost:
            continue
        state_delegates = sum(
            d.population - (d.population * 2) / 3 for d in st.districts)
        # Importance threshold: only build if the agent put real weight
        # on this state (>= half the uniform share).
        if weight * n_active < 0.5:
            continue
        # NOTE: an earlier version of this decoder skipped same-week
        # (tte == 0) org builds on the assumption that the contest had
        # already resolved. That was wrong — the sim/live game's step
        # order is (agent acts -> calc_state_opinions -> decide_contests),
        # so a tier-1 org built in the voting week DOES participate in
        # that week's support calculation and contest resolution. The
        # check is removed; agents can now buy ballot access in the
        # voting week itself, which is a legal and sometimes decisive
        # move for the final turn.
        org_budget -= cost
        st.organizations[p_idx] += 1
        try:
            p.money_on_org += cost
        except (AttributeError, TypeError):
            pass

    # --- Ad money: leftover after org spending ---
    ad_budget = (start_money - (start_money - p.resources[1])) - (org_money_frac * start_money - org_budget)
    # Simpler: ad_budget = whatever money is left now.
    ad_budget = p.resources[1] - (org_money_frac * start_money - org_budget)
    # Cleanest: account for what we already spent on orgs and base ads
    # on the post-org cash. But the org loop already decremented
    # resources via `p.money_on_org +=` (which doesn't actually mutate
    # resources, that's the _PlayerView discard). Real resources mutation
    # happened via the `cost` accounting above through org_budget; we
    # need to mirror that into p.resources[1].
    # Reset and do it the explicit way to avoid the confusion above.
    money_spent_on_orgs = (org_money_frac * start_money) - org_budget
    # Clamp in case rounding made it slightly negative.
    money_spent_on_orgs = max(0, int(round(money_spent_on_orgs)))
    p.resources[1] = start_money - money_spent_on_orgs

    # --- Build state-importance-biased scored district list ---
    def urgency_curve(t):
        if t <= 0:
            return 1.6
        if t <= 1:
            return 1.4
        if t <= 3:
            return 1.1
        if t <= 6:
            return 0.9
        return 0.6

    scored = _sb._scored_districts(sim, p_idx, urgency_curve,
                                   closeness_w=1.0, delegates_w=1.0,
                                   runaway_floor=-25, jitter=0.0,
                                   only_imminent_weeks=99)
    # Bias every scored entry by state_importance × n_active so a state
    # with neutral weight (1/n_active) stays at neutral 1.0, and the
    # agent's state-importance preferences push scores up or down.
    for entry in scored:
        pos = name_to_pos.get(entry[3])
        bias = (float(state_w[pos]) * n_active) if pos is not None else 1.0
        entry[0] *= max(bias, 0.0)

    # --- Spend ad money and campaign hours on the same scored list ---
    _sb._greedy_spend_ads(sim, p_idx, [list(e) for e in scored])
    leftover = _sb._greedy_spend_time(sim, p_idx, scored,
                                      fundraise_cutoff=2.0)
    fundraising_hours += leftover

    _log_post_decode_spend(sim, p_idx, fundraising_hours)
    return fundraising_hours


def random_coupled_action(rng):
    import numpy as np
    return np.array([rng.gauss(0, 1) for _ in range(COUPLED_ACTION_DIM)],
                    dtype=np.float32)
