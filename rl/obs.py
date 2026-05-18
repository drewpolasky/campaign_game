"""Observation encoding: Sim state -> flat numpy float vector.

Layout (all values pre-normalized to roughly [-1, 1] or [0, 1]):

  globals (10):
    turn / num_turns
    num_turns / 20
    n_active_players / MAX_PLAYERS
    event_of_week one-hot (NUM_ISSUES = 7)

  per-state (NUM_STATES * 8 = 400):
    time_to_election / num_turns (clipped to [-1, 1.5])
    finished flag (0 or 1)
    self_org / 5
    max_opp_org / 5
    self_avg_district_support / 100
    max_opp_avg_district_support / 100
    state_position_on_event_issue (-1, 0, 1)
    state_total_delegates / 60     (rough scale: top states ~50)

  per-player slot (MAX_PLAYERS * 11 = 44):
    valid (1 if seat is filled, else 0 — agent self always valid)
    delegate_count / 1000
    momentum / 100  (clipped)
    money / 100000
    hours / 80
    positions (NUM_ISSUES = 7) as -1/0/1

The agent always occupies slot 0; opponents fill 1..MAX_PLAYERS-1 in their
sim-order, padded with zero/invalid slots so the network sees a fixed
shape regardless of player count.
"""
import numpy as np

import state_issues

NUM_STATES = 50
NUM_ISSUES = len(state_issues.ISSUES)
MAX_PLAYERS = 4

GLOBAL_DIM = 3 + NUM_ISSUES                # 10
STATE_FEATURES = 8
PLAYER_SLOT_FEATURES = 4 + NUM_ISSUES      # valid+deleg+mom+money+hours + positions = 4 + 7? -> 11
# (4 = valid, delegate, momentum, money, hours? that's 5. We want 4 scalars + valid = 5.)
# Recount carefully:
#   valid, delegates, momentum, money, hours = 5 scalars
#   + NUM_ISSUES position scalars = 5 + 7 = 12
PLAYER_SLOT_FEATURES = 5 + NUM_ISSUES      # 12

OBS_DIM = (GLOBAL_DIM
           + NUM_STATES * STATE_FEATURES
           + MAX_PLAYERS * PLAYER_SLOT_FEATURES)


def _district_avg_support(state, p_idx):
    if not state.districts:
        return 0.0
    return sum(d.support[p_idx] for d in state.districts) / len(state.districts)


def encode_obs(sim, agent_idx):
    """Return a fixed-length float32 vector describing the world from
    `agent_idx`'s perspective."""
    out = np.zeros(OBS_DIM, dtype=np.float32)
    cursor = 0

    # --- Globals ---
    out[cursor + 0] = sim.current_date / max(sim.num_turns, 1)
    out[cursor + 1] = sim.num_turns / 20.0
    out[cursor + 2] = sim.num_players / float(MAX_PLAYERS)
    if 0 <= sim.event_of_week < NUM_ISSUES:
        out[cursor + 3 + sim.event_of_week] = 1.0
    cursor += GLOBAL_DIM

    # --- Per-state ---
    state_names = list(sim.states.keys())
    # Stable order by calendar (matches the canonical CALENDAR ordering).
    cal_index = {name: i for i, (name, _) in enumerate(sim.calendar)}
    state_names.sort(key=lambda n: cal_index.get(n, 999))
    # If for some reason fewer than NUM_STATES states are present, the rest
    # stays zero.
    for s_idx, name in enumerate(state_names[:NUM_STATES]):
        st = sim.states[name]
        # time-to-election: positive = upcoming, negative = past, clip.
        for ename, week in sim.calendar:
            if ename == name:
                tte = week - sim.current_date
                break
        else:
            tte = 99
        finished = 1.0 if tte < 0 else 0.0
        norm_tte = max(-1.0, min(1.5, tte / max(sim.num_turns, 1)))
        self_org = st.organizations[agent_idx] / 5.0
        opp_orgs = [st.organizations[j] for j in range(sim.num_players) if j != agent_idx]
        max_opp_org = (max(opp_orgs) if opp_orgs else 0) / 5.0
        self_sup = _district_avg_support(st, agent_idx) / 100.0
        opp_sups = [_district_avg_support(st, j) for j in range(sim.num_players) if j != agent_idx]
        max_opp_sup = (max(opp_sups) if opp_sups else 0.0) / 100.0
        try:
            state_pos_on_event = float(st.positions[sim.event_of_week])
        except (IndexError, AttributeError, TypeError):
            state_pos_on_event = 0.0
        total_delegates = sum(d.population for d in st.districts) / 60.0

        base = cursor + s_idx * STATE_FEATURES
        out[base + 0] = norm_tte
        out[base + 1] = finished
        out[base + 2] = self_org
        out[base + 3] = max_opp_org
        out[base + 4] = self_sup
        out[base + 5] = max_opp_sup
        out[base + 6] = state_pos_on_event
        out[base + 7] = total_delegates
    cursor += NUM_STATES * STATE_FEATURES

    # --- Players, agent first ---
    order = [agent_idx] + [j for j in range(sim.num_players) if j != agent_idx]
    for slot, p_idx in enumerate(order[:MAX_PLAYERS]):
        p = sim.players[p_idx]
        base = cursor + slot * PLAYER_SLOT_FEATURES
        out[base + 0] = 1.0  # valid
        out[base + 1] = p.delegate_count / 1000.0
        out[base + 2] = max(-2.0, min(2.0, p.momentum / 100.0))
        out[base + 3] = p.resources[1] / 100000.0
        out[base + 4] = p.resources[0] / 80.0
        for k in range(NUM_ISSUES):
            try:
                out[base + 5 + k] = float(p.positions[k])
            except (IndexError, TypeError):
                pass
    # Remaining slots stay zero (valid=0).

    return out


assert OBS_DIM == GLOBAL_DIM + NUM_STATES * STATE_FEATURES + MAX_PLAYERS * PLAYER_SLOT_FEATURES
