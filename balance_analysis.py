"""
Game-balance analysis plots.

Reads the actual formulas from CampaignGame.py (calculateStateOpinions,
calcEndTurn) and generates plots so you can see how much support a unit of
each resource buys, how that scales with situation, and where the
diminishing-returns / breakpoints are.

Run:  python balance_analysis.py
Outputs PNG files into balance_plots/.
"""
import math
import os

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'balance_plots')
os.makedirs(OUT_DIR, exist_ok=True)


# --- Live formulas from CampaignGame.py, kept inline so this is standalone ---

def time_multiplier(weeks_to_election):
    """The +10% / +20% bonus in the last 2 weeks before voting."""
    if weeks_to_election == 1:
        return 1.1
    if weeks_to_election == 0:
        return 1.2
    return 1.0


def momentum_multiplier(momentum):
    return 1.0 + momentum / 50.0


def issue_multiplier(state_pos, player_pos):
    """+33% if matched, -16% per stance step apart, floored at 0.25."""
    if state_pos == 0:
        return 1.0
    if player_pos == state_pos:
        return 1.33
    return max(0.25, 1.0 - 0.16 * abs(player_pos - state_pos))


def support_from_org(org_level, mult=1.0):
    return org_level * 2 * mult


def support_from_campaign(hours, mult=1.0):
    return hours * 3.0 * mult


def support_from_ads(my_ad_dollars, others_ad_dollars, mult=1.0):
    """The ad share term: (my_ads / (total_ads + 1)) * (total_ads / 100)^0.55."""
    total = my_ad_dollars + others_ad_dollars
    share = my_ad_dollars / float(total + 1)
    intensity = (total / 100.0) ** 0.55
    return share * intensity * mult


def fundraising_income(hours):
    return hours * 4000 + 20000


def local_fundraising_per_district(support, org_level, momentum, population):
    """A single district's contribution to local fundraising (calcEndTurn)."""
    base = (1.5 + org_level / 10.0)
    number_donating = 1 - base ** (support / -50.0)
    momentum_factor = 2 - math.exp(momentum / -50.0)
    return number_donating * population * 500 * momentum_factor


def org_cost(current_tier):
    return max(10000, 10000 * current_tier)


# --------- Plots ---------

def plot_support_per_dollar_ads():
    """How much support per $1 of ad spend depends on what the OTHER players
    have already poured into the same district. Diminishing share + diminishing
    intensity make late-game arms-races a money sink."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    my_spends = [1000, 5000, 10000, 25000, 50000]
    others = [0, 1000, 5000, 10000, 25000, 50000, 100000]

    ax = axes[0]
    for my in my_spends:
        sup = [support_from_ads(my, o) for o in others]
        ax.plot(others, [s / (my / 1000.0) for s in sup], marker='o',
                label='My spend = ${:,}'.format(my))
    ax.set_xlabel("Other players' ad total in this district ($)")
    ax.set_ylabel('Support gained per $1k of my ads')
    ax.set_title('Ad efficiency vs. opponent spend')
    ax.set_xscale('log')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    ax = axes[1]
    spends = list(range(1000, 101000, 2000))
    for o in (0, 5000, 25000, 100000):
        sup = [support_from_ads(s, o) for s in spends]
        ax.plot(spends, sup, label="Others spent ${:,}".format(o))
    ax.set_xlabel('My ad spend ($)')
    ax.set_ylabel('Total support from ads (raw)')
    ax.set_title('Total ad support vs. my spend')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    fig.suptitle('Support from ad buys', fontsize=13)
    fig.tight_layout()
    out = os.path.join(OUT_DIR, 'support_from_ads.png')
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def plot_support_per_hour_vs_time():
    """Campaigning hour value scales linearly with the time-to-election
    multiplier (+10%, +20% in the last two weeks). Org and ads scale the
    same way - this plot just makes the spike visible."""
    fig, ax = plt.subplots(figsize=(9, 5))
    weeks = list(range(0, 9))
    # 1 hour at each time-to-election, in a neutral state with no other ads.
    bars = [support_from_campaign(1, time_multiplier(w)) for w in weeks]
    ax.bar(weeks, bars, color=['#c0392b' if w <= 1 else '#3498db' for w in weeks])
    for x, y in zip(weeks, bars):
        ax.text(x, y + 0.02, '{:.2f}'.format(y), ha='center', fontsize=9)
    ax.set_xlabel('Weeks until this state votes')
    ax.set_ylabel('Support per campaign hour (raw)')
    ax.set_title('Last-2-weeks bonus on campaigning')
    ax.invert_xaxis()  # 0 weeks = election week, on the right reads naturally
    ax.grid(True, alpha=0.3, axis='y')
    fig.tight_layout()
    out = os.path.join(OUT_DIR, 'support_per_hour_vs_time.png')
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def plot_org_value():
    """Per-turn passive support from organization tier, plus 'turns to break
    even' as a function of how many turns are left until you vote."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    ax = axes[0]
    tiers = list(range(0, 8))
    sup = [support_from_org(t) for t in tiers]
    ax.bar(tiers, sup, color='#27ae60')
    for x, y in zip(tiers, sup):
        ax.text(x, y + 0.2, '{:.0f}'.format(y), ha='center')
    ax.set_xlabel('Organization tier')
    ax.set_ylabel('Passive support per district per turn')
    ax.set_title('Organization tier -> passive support')
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1]
    # Cost to go from tier t to t+1, vs. cumulative support from the new tier
    # over the remaining turns.
    weeks_left = list(range(1, 12))
    for tier in (0, 1, 2, 3):
        cost = org_cost(tier)
        # Each new tier adds 2 support per district per turn. Average state
        # has ~3 districts (varies, but use 3 as a rough number).
        added_per_turn = 2 * 3
        cumulative = [added_per_turn * w for w in weeks_left]
        ax.plot(weeks_left, [c / (cost / 1000.0) for c in cumulative], marker='o',
                label='Tier {}->{} (cost ${:,})'.format(tier, tier + 1, cost))
    ax.set_xlabel('Turns of org left before this state votes')
    ax.set_ylabel('Cumulative support per $1k spent')
    ax.set_title('Org build value by lead time (3-district state)')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    fig.suptitle('Organization economics', fontsize=13)
    fig.tight_layout()
    out = os.path.join(OUT_DIR, 'org_value.png')
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def plot_resource_comparison():
    """Per-turn support per $1 of money equivalent, comparing:
       - Ads: one $1000 chunk in a district where opponents have $X.
       - Org build: one tier (cost = 10k * current_tier).
       - Campaign time: one hour, costing $0 in money but ~$4000 in
         opportunity cost (forgone fundraising).
    Across a range of weeks to election."""
    fig, ax = plt.subplots(figsize=(10, 5.5))

    weeks = list(range(0, 9))
    ad_eff_solo = [support_from_ads(1000, 0, time_multiplier(w)) / 1.0 for w in weeks]
    ad_eff_busy = [support_from_ads(1000, 25000, time_multiplier(w)) / 1.0 for w in weeks]
    # Org tier 0->1 costs $10k, gives 2/turn for the remaining turns.
    org_eff = []
    for w in weeks:
        turns_left = max(0, w + 1)  # spend now -> count this turn through election
        org_total = support_from_org(1) * turns_left * sum(time_multiplier(t) for t in range(w + 1)) / max(1, w + 1)
        org_eff.append(org_total / 10.0)  # support per $1k spent
    # Campaign hour is "free" of money; convert with $4k/hr opportunity cost.
    camp_eff = [support_from_campaign(1, time_multiplier(w)) / 4.0 for w in weeks]

    ax.plot(weeks, ad_eff_solo, marker='o', label=r'Ads \$1k (no opponents)')
    ax.plot(weeks, ad_eff_busy, marker='o', label=r'Ads \$1k (opponents already \$25k)')
    ax.plot(weeks, org_eff, marker='s', label=r'Org tier 0->1, summed over remaining turns')
    ax.plot(weeks, camp_eff, marker='^', label=r'1 campaign hr (vs \$4k of fundraising)')

    ax.set_xlabel('Weeks until this state votes (0 = election week)')
    ax.set_ylabel(r'Support per \$1k of investment')
    ax.set_title(r'Where does my next \$1k buy the most support?')
    ax.invert_xaxis()
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    out = os.path.join(OUT_DIR, 'resource_comparison.png')
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def plot_issue_alignment():
    """How issueMult and momentum scale the underlying support gain."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    ax = axes[0]
    matrix = [[issue_multiplier(s, p) for p in (-1, 0, 1)] for s in (-1, 0, 1)]
    im = ax.imshow(matrix, cmap='RdYlGn', vmin=0.5, vmax=1.4)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(['Player -1', 'Player 0', 'Player +1'])
    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(['State -1', 'State 0', 'State +1'])
    for i in range(3):
        for j in range(3):
            ax.text(j, i, '{:.2f}x'.format(matrix[i][j]),
                    ha='center', va='center', fontsize=11,
                    color='black')
    ax.set_title('Issue alignment multiplier')
    plt.colorbar(im, ax=ax, fraction=0.046)

    ax = axes[1]
    momentums = list(range(-50, 151, 10))
    mults = [momentum_multiplier(m) for m in momentums]
    ax.plot(momentums, mults, marker='o')
    ax.axhline(1.0, color='gray', linestyle='--', alpha=0.5)
    ax.set_xlabel('Momentum')
    ax.set_ylabel('Support multiplier')
    ax.set_title('Momentum -> support multiplier')
    ax.grid(True, alpha=0.3)

    fig.suptitle('Multipliers stacked on top of base support', fontsize=13)
    fig.tight_layout()
    out = os.path.join(OUT_DIR, 'multipliers.png')
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def plot_fundraising_income():
    """Money in vs hours of fundraising, plus how local fundraising scales
    with support and momentum. Helps decide when fundraising is worth it
    vs. campaigning."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    ax = axes[0]
    hours = list(range(0, 81, 5))
    ax.plot(hours, [fundraising_income(h) for h in hours], marker='o')
    ax.set_xlabel('Hours spent fundraising')
    ax.set_ylabel('Income from fundraising-time + baseline ($)')
    ax.set_title('Direct income from the fundraising slider')
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    supports = list(range(0, 200, 10))
    pop = 9  # pretend a typical district size in delegates
    for momentum, color in [(0, 'tab:blue'), (50, 'tab:orange'), (150, 'tab:red')]:
        for org, ls in [(0, ':'), (1, '-'), (3, '--')]:
            vals = [local_fundraising_per_district(s, org, momentum, pop) for s in supports]
            ax.plot(supports, vals, color=color, linestyle=ls,
                    label='org={}, momentum={}'.format(org, momentum))
    ax.set_xlabel('Your district support level')
    ax.set_ylabel('Local fundraising per district per turn ($)')
    ax.set_title('Local fundraising scaling')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7, ncol=3)

    fig.suptitle('Where does the money come from?', fontsize=13)
    fig.tight_layout()
    out = os.path.join(OUT_DIR, 'fundraising.png')
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def main():
    paths = [
        plot_support_per_dollar_ads(),
        plot_support_per_hour_vs_time(),
        plot_org_value(),
        plot_resource_comparison(),
        plot_issue_alignment(),
        plot_fundraising_income(),
    ]
    for p in paths:
        print('wrote', p)


if __name__ == '__main__':
    main()
