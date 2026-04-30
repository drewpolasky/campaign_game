"""
State-level positions on each campaign issue.

Each state has one position per issue: -1 (oppose), 0 (neutral), or +1 (support).
Positions are calibrated to real-world political leanings and tuned so the
delegate-weighted total of supporters and opponents is roughly balanced for
each issue. Use `compute_balance(state_delegates)` to verify or to tune
further data changes.

Issues (must match issueNames order in CampaignGame.py):
    Climate Change, Abortion, Taxes-Government Spending,
    Gun Control, Healthcare, Regulation, Trade
"""

ISSUE_NAMES = [
    'Climate Change',
    'Abortion',
    'Taxes-Government Spending',
    'Gun Control',
    'Healthcare',
    'Regulation',
    'Trade',
]

# Headlines pool, indexed by issue then position-of-the-news. The "news angle"
# for the week is randomized to add flavor; the underlying issue index is what
# drives gameplay alignment.
ISSUE_HEADLINES = {
    'Climate Change': [
        'Devastating wildfires reignite climate debate',
        'New study warns of accelerating sea level rise',
        'Industry groups push back on emissions rules',
        'Activists stage nationwide climate march',
    ],
    'Abortion': [
        'Supreme Court takes up high-profile abortion case',
        'State legislature debates new abortion restrictions',
        'Massive rallies on both sides over reproductive rights',
        'Polls show abortion stays a top voter concern',
    ],
    'Taxes-Government Spending': [
        'Congress fights over sweeping budget proposal',
        'CBO releases new deficit projections',
        'Debate flares over tax breaks for the wealthy',
        'Cities push for more federal spending on infrastructure',
    ],
    'Gun Control': [
        'Latest mass shooting renews calls for new gun laws',
        'Supreme Court weighs Second Amendment challenge',
        'Governors split on universal background checks',
        'Gun rights advocates mobilize after new state law',
    ],
    'Healthcare': [
        'Insurance premiums spike, reigniting healthcare debate',
        'Hospital closures hit rural communities hard',
        'Drug pricing fight heats up in Washington',
        'States split over Medicaid expansion plans',
    ],
    'Regulation': [
        'Major industry hit with sweeping new regulations',
        'Small business owners protest red tape',
        'Federal agency rolls back environmental rules',
        'Workers rally for stronger workplace protections',
    ],
    'Trade': [
        'Tariff fight escalates with major trading partner',
        'Manufacturing towns demand stronger trade protections',
        'Farmers warn of trade war fallout',
        'New trade deal stalls in Senate',
    ],
}


# Positions per state, in the order of ISSUE_NAMES.
# Tuned so net delegate-weighted balance per issue stays modest.
STATE_POSITIONS = {
    # state             CC  Ab  T&GS GC  HC  Reg Trade
    'Alabama':         [-1, -1, -1, -1, -1, -1, -1],
    'Alaska':          [-1,  0, -1, -1, -1, -1,  0],
    'Arizona':         [ 0, -1,  0,  0, -1,  0,  0],
    'Arkansas':        [-1, -1, -1, -1, -1, -1, -1],
    'California':      [ 1,  1,  1,  1,  1,  1,  1],
    'Colorado':        [ 1,  0,  0,  1,  0,  0,  0],
    'Connecticut':     [ 1,  1,  1,  1,  1,  1,  1],
    'Delaware':        [ 1,  1,  0,  1,  0,  0,  0],
    'Florida':         [-1, -1,  0, -1, -1,  0,  0],
    'Georgia':         [-1, -1,  0,  0, -1,  0, -1],
    'Hawaii':          [ 1,  1,  0,  1,  1,  0,  0],
    'Idaho':           [-1, -1, -1, -1, -1, -1,  0],
    'Illinois':        [ 1,  1,  0,  1,  1,  0,  0],
    'Indiana':         [-1, -1, -1, -1, -1, -1, -1],
    'Iowa':            [ 0,  0,  0,  0, -1,  0,  1],
    'Kansas':          [-1, -1, -1, -1, -1, -1,  1],
    'Kentucky':        [-1, -1, -1, -1, -1, -1, -1],
    'Louisiana':       [-1, -1, -1, -1, -1, -1,  0],
    'Maine':           [ 1,  0,  0,  0,  1,  0,  0],
    'Maryland':        [ 1,  1,  1,  1,  1,  1,  0],
    'Massachusetts':   [ 1,  1,  1,  1,  1,  1,  1],
    'Michigan':        [ 0,  0,  0,  0,  0,  0, -1],
    'Minnesota':       [ 1,  0,  0,  1,  0,  0,  0],
    'Mississippi':     [-1, -1, -1, -1, -1, -1,  0],
    'Missouri':        [-1, -1, -1, -1, -1, -1, -1],
    'Montana':         [-1,  0,  0, -1, -1,  0,  1],
    'Nebraska':        [-1, -1, -1, -1, -1, -1,  1],
    'Nevada':          [ 0,  0,  0,  0,  0,  0,  0],
    'New Hampshire':   [ 1,  0,  0,  0,  1,  0,  0],
    'New Jersey':      [ 1,  1,  1,  1,  1,  1,  1],
    'New Mexico':      [ 1,  0,  0,  0,  1,  0,  0],
    'New York':        [ 1,  1,  1,  1,  1,  1,  1],
    'North Carolina':  [-1, -1,  0,  0, -1,  0, -1],
    'North Dakota':    [-1, -1, -1, -1, -1, -1,  1],
    'Ohio':            [ 0,  0,  0,  0,  0,  0, -1],
    'Oklahoma':        [-1, -1, -1, -1, -1, -1,  0],
    'Oregon':          [ 1,  1,  1,  1,  1,  1,  0],
    'Pennsylvania':    [ 0,  0,  0,  0,  0,  0, -1],
    'Rhode Island':    [ 1,  1,  0,  1,  1,  0,  0],
    'South Carolina':  [-1, -1, -1, -1, -1, -1, -1],
    'South Dakota':    [-1, -1, -1, -1, -1, -1,  1],
    'Tennessee':       [-1, -1, -1, -1, -1, -1, -1],
    'Texas':           [-1, -1, -1, -1, -1, -1,  1],
    'Utah':            [-1, -1, -1, -1, -1, -1,  0],
    'Vermont':         [ 1,  1,  1,  1,  1,  1,  0],
    'Virginia':        [ 0,  0,  0,  0,  0,  0, -1],
    'Washington':      [ 1,  1,  1,  1,  1,  1,  0],
    'West Virginia':   [-1, -1, -1, -1, -1, -1, -1],
    'Wisconsin':       [ 0,  0,  0,  0,  0,  0, -1],
    'Wyoming':         [-1, -1, -1, -1, -1, -1,  0],
}


def get_state_positions(state_name):
    """Return [pos1, pos2, ...] for the given state, or all zeros if unknown."""
    if state_name in STATE_POSITIONS:
        return list(STATE_POSITIONS[state_name])
    return [0] * len(ISSUE_NAMES)


def compute_balance(state_delegates):
    """Return delegate-weighted net (sum of position * delegates) per issue.

    state_delegates: dict of state_name -> total delegates (district populations).
    Returns dict of issue_name -> (support_total, oppose_total, neutral_total, net).
    """
    result = {}
    for i, issue in enumerate(ISSUE_NAMES):
        support = oppose = neutral = 0
        for state, positions in STATE_POSITIONS.items():
            d = state_delegates.get(state, 0)
            p = positions[i]
            if p > 0:
                support += d
            elif p < 0:
                oppose += d
            else:
                neutral += d
        result[issue] = {
            'support': support,
            'oppose': oppose,
            'neutral': neutral,
            'net': support - oppose,
        }
    return result


if __name__ == '__main__':
    # Quick sanity check using the canonical districts.txt delegate counts.
    import os
    delegates = {}
    path = os.path.join(os.path.dirname(__file__), 'districts.txt')
    with open(path) as f:
        for line in f:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 3 and parts[2].isdigit():
                delegates[parts[0]] = delegates.get(parts[0], 0) + int(parts[2])
    bal = compute_balance(delegates)
    total = sum(delegates.values())
    print('Total delegates: {}'.format(total))
    for issue, r in bal.items():
        print('  {:30s}  +{:3d} / -{:3d} / 0:{:3d}  net={:+d}'.format(
            issue, r['support'], r['oppose'], r['neutral'], r['net']))
