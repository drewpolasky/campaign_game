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


def set_log_org_builds(enabled: bool):
    global _LOG_ORG_BUILDS
    _LOG_ORG_BUILDS = bool(enabled)

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

    return fundraising_hours


def random_continuous_action(rng):
    import numpy as np
    return np.array([rng.gauss(0, 1) for _ in range(CONT_ACTION_DIM)],
                    dtype=np.float32)
