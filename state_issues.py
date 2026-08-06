"""
State-level positions on each campaign issue.

Each state has one position per issue: -1 (oppose), 0 (neutral), or +1 (support).
The left/right issues (Climate, Abortion, Taxes) plus Trade are calibrated to
real-world leanings; the cross-cutting issues are split on real data so the
favorable map reshuffles week to week:
    Ag Subsidies      EWG farm subsidies per capita (cumulative 1995-2025)
    Defense Spending  DoD FY2024 'Defense Spending by State', $ per resident
    Federal Land      CRS federal-land-ownership % of each state
    Social Security & Medicare   Census/AHR % of population age 65+

Use `compute_balance(state_delegates)` to verify the delegate split per issue.

Issues (must match issueNames order in CampaignGame.py):
    Climate Action, Abortion, Taxes & Spending, Trade, Ag Subsidies, Defense Spending, Federal Land, Social Security & Medicare
"""

# Each issue has a short name plus labels for the +1/0/-1 sides so the UI
# can describe a stance in plain English. This order is canonical; positions
# in STATE_POSITIONS and Player.positions follow it.
ISSUES = [
    {
        'name': 'Climate Action',
        'pro': 'Aggressive Action',
        'mid': 'Incremental Steps',
        'con': 'Industry First',
    },
    {
        'name': 'Abortion',
        'pro': 'Pro-Choice',
        'mid': 'Compromise',
        'con': 'Pro-Life',
    },
    {
        'name': 'Taxes & Spending',
        'pro': 'Tax & Invest',
        'mid': 'Balanced Budget',
        'con': 'Cut Taxes',
    },
    {
        'name': 'Trade',
        'pro': 'Free Trade',
        'mid': 'Balanced',
        'con': 'Protectionism',
    },
    {
        'name': 'Ag Subsidies',
        'pro': 'Boost Farm Aid',
        'mid': 'Hold Steady',
        'con': 'Cut Subsidies',
    },
    {
        'name': 'Defense Spending',
        'pro': 'Boost Spending',
        'mid': 'Hold Steady',
        'con': 'Cut Spending',
    },
    {
        'name': 'Federal Land',
        'pro': 'Local Control',
        'mid': 'Shared Stewardship',
        'con': 'Federal Control',
    },
    {
        'name': 'Social Security & Medicare',
        'pro': 'Protect & Expand',
        'mid': 'Steady As-Is',
        'con': 'Reform & Cut',
    },
]

ISSUE_NAMES = [issue['name'] for issue in ISSUES]


def side_label(issue_index, position):
    """Return the human label for a position on an issue."""
    if not (0 <= issue_index < len(ISSUES)):
        return 'Neutral'
    issue = ISSUES[issue_index]
    try:
        v = int(round(float(position)))
    except (TypeError, ValueError):
        v = 0
    if v > 0:
        return issue['pro']
    if v < 0:
        return issue['con']
    return issue['mid']


# Headlines pool, indexed by issue name. The news 'angle' for the week is
# flavor; the issue index is what drives gameplay alignment.
ISSUE_HEADLINES = {
    'Climate Action': [
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
    'Taxes & Spending': [
        'Congress fights over sweeping budget proposal',
        'CBO releases new deficit projections',
        'Debate flares over tax breaks for the wealthy',
        'Cities push for more federal spending on infrastructure',
    ],
    'Trade': [
        'Tariff fight escalates with major trading partner',
        'Manufacturing towns demand stronger trade protections',
        'Farmers warn of trade war fallout',
        'New trade deal stalls in Senate',
    ],
    'Ag Subsidies': [
        'Farm bill fight splits Congress over subsidy programs',
        'Commodity prices crash as growers press for support',
        'Watchdog slams payouts flowing to the largest agribusinesses',
        'Historic drought devastates crops across the heartland',
    ],
    'Defense Spending': [
        'Pentagon unveils a record defense budget request',
        'Proposed base closures rattle local economies',
        'Lawmakers clash over a costly new weapons program',
        'Contractors and veterans rally against Pentagon cuts',
    ],
    'Federal Land': [
        'Standoff over federal control of Western public lands',
        'Push to hand federal land to the states gains steam',
        'Ranchers and conservationists clash over grazing rules',
        'New national monument sparks a local backlash',
    ],
    'Social Security & Medicare': [
        'Trustees warn the Social Security trust fund nears a shortfall',
        'Seniors mobilize against proposed benefit cuts',
        'Debate erupts over raising the retirement age',
        'Medicare drug-pricing fight returns to Washington',
    ],
}


# Positions per state, in the order of ISSUE_NAMES.
# order: Climate  Abortion  Taxes  Trade  Ag  Defense  FedLand  SS/Medicare
STATE_POSITIONS = {
    'Alabama':          [-1, -1, -1, -1,  0,  1,  0,  0],
    'Alaska':           [-1,  0, -1,  0, -1,  1,  1, -1],
    'Arizona':          [ 0, -1,  0,  0, -1,  1,  1,  1],
    'Arkansas':         [-1, -1, -1, -1,  1, -1,  0,  0],
    'California':       [ 1,  1,  1,  1,  0,  1,  1, -1],
    'Colorado':         [ 1,  0,  0,  0,  1,  1,  1, -1],
    'Connecticut':      [ 1,  1,  1,  1, -1,  1, -1,  1],
    'Delaware':         [ 1,  1,  0,  0, -1, -1, -1,  1],
    'Florida':          [-1, -1,  0,  0, -1,  0,  1,  1],
    'Georgia':          [-1, -1,  0, -1,  0,  0,  0, -1],
    'Hawaii':           [ 1,  1,  0,  0, -1,  1,  1,  1],
    'Idaho':            [-1, -1, -1,  0,  1, -1,  1,  0],
    'Illinois':         [ 1,  1,  0,  0,  1, -1, -1,  0],
    'Indiana':          [-1, -1, -1, -1,  1, -1, -1, -1],
    'Iowa':             [ 0,  0,  0,  1,  1,  0, -1,  1],
    'Kansas':           [-1, -1, -1,  1,  1,  0, -1,  0],
    'Kentucky':         [-1, -1, -1, -1,  1,  1,  0,  0],
    'Louisiana':        [-1, -1, -1,  0,  1, -1,  0,  0],
    'Maine':            [ 1,  0,  0,  0, -1,  1, -1,  1],
    'Maryland':         [ 1,  1,  1,  0, -1,  1,  0,  0],
    'Massachusetts':    [ 1,  1,  1,  1, -1,  1, -1,  0],
    'Michigan':         [ 0,  0,  0, -1,  0, -1,  1,  1],
    'Minnesota':        [ 1,  0,  0,  0,  1, -1,  0,  0],
    'Mississippi':      [-1, -1, -1,  0,  1,  1,  0,  0],
    'Missouri':         [-1, -1, -1, -1,  1,  1,  0,  0],
    'Montana':          [-1,  0,  0,  1,  1, -1,  1,  1],
    'Nebraska':         [-1, -1, -1,  1,  1, -1, -1, -1],
    'Nevada':           [ 0,  0,  0,  0, -1, -1,  1,  0],
    'New Hampshire':    [ 1,  0,  0,  0, -1,  1,  1,  1],
    'New Jersey':       [ 1,  1,  1,  1, -1, -1,  0,  0],
    'New Mexico':       [ 1,  0,  0,  0,  1,  1,  1,  1],
    'New York':         [ 1,  1,  1,  1, -1, -1, -1,  1],
    'North Carolina':   [-1, -1,  0, -1,  0,  0,  0,  0],
    'North Dakota':     [-1, -1, -1,  1,  1,  0,  0, -1],
    'Ohio':             [ 0,  0,  0, -1,  1, -1, -1,  1],
    'Oklahoma':         [-1, -1, -1,  0,  1,  1, -1, -1],
    'Oregon':           [ 1,  1,  1,  0,  0, -1,  1,  1],
    'Pennsylvania':     [ 0,  0,  0, -1, -1,  1, -1,  1],
    'Rhode Island':     [ 1,  1,  0,  0, -1,  1, -1,  1],
    'South Carolina':   [-1, -1, -1, -1,  0,  0,  0,  1],
    'South Dakota':     [-1, -1, -1,  1,  1,  0,  0,  0],
    'Tennessee':        [-1, -1, -1, -1,  0, -1,  0,  0],
    'Texas':            [-1, -1, -1,  1,  1,  0, -1, -1],
    'Utah':             [-1, -1, -1,  0, -1,  1,  1, -1],
    'Vermont':          [ 1,  1,  1,  0,  0,  0,  0,  1],
    'Virginia':         [ 0,  0,  0, -1, -1,  1,  1, -1],
    'Washington':       [ 1,  1,  1,  0,  0,  1,  1, -1],
    'West Virginia':    [-1, -1, -1, -1, -1, -1,  0,  1],
    'Wisconsin':        [ 0,  0,  0, -1,  1, -1,  1,  1],
    'Wyoming':          [-1, -1, -1,  0,  1,  0,  1,  1],
}


def get_state_positions(state_name):
    """Return [pos1, pos2, ...] for the given state, or all zeros if unknown."""
    if state_name in STATE_POSITIONS:
        return list(STATE_POSITIONS[state_name])
    return [0] * len(ISSUE_NAMES)


def compute_balance(state_delegates):
    """Return delegate-weighted support/oppose/neutral totals per issue."""
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
