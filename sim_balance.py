"""
Headless game simulator + AI tournament harness.

Mirrors the game's support / contest / fundraising formulas so we can run
hundreds of full games in a few seconds and compare AI strategies head-to-head.
Drops a set of plots into balance_plots/ai_*.

Strategies are pluggable: each is a function (sim, player_idx) that fills the
player's allocations for the turn and returns how many hours of the player's
time go to fundraising. Add a new strategy and it joins the round-robin.
"""
import math
import os
import random
from collections import defaultdict, Counter

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from State import State, District
import state_issues

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'balance_plots')
os.makedirs(OUT_DIR, exist_ok=True)


# --- Game data (extracted from CampaignGame.py) ---

CALENDAR = [
    ('Iowa', 4), ('New Hampshire', 5), ('Nevada', 7), ('South Carolina', 8),
    ('Minnesota', 9), ('Alabama', 9), ('Arkansas', 9), ('Colorado', 9),
    ('Georgia', 9), ('Massachusetts', 9), ('North Dakota', 9), ('Oklahoma', 9),
    ('Tennessee', 9), ('Texas', 9), ('Vermont', 9), ('Virginia', 9),
    ('Kansas', 10), ('Kentucky', 10), ('Louisiana', 10), ('Maine', 10),
    ('Nebraska', 10), ('Hawaii', 10), ('Michigan', 10), ('Mississippi', 10),
    ('Wyoming', 11), ('Florida', 11), ('Illinois', 11), ('Missouri', 11),
    ('North Carolina', 11), ('Ohio', 11), ('Arizona', 12), ('Idaho', 12),
    ('Utah', 12), ('Alaska', 13), ('Washington', 13), ('Wisconsin', 14),
    ('New Jersey', 15), ('New York', 15), ('Connecticut', 15), ('Delaware', 15),
    ('Maryland', 15), ('Pennsylvania', 15), ('Rhode Island', 15),
    ('Indiana', 16), ('West Virginia', 16), ('Oregon', 17), ('California', 19),
    ('Montana', 19), ('New Mexico', 19), ('South Dakota', 19),
]


def load_calendar(num_turns):
    """Match CampaignGame.setCalendar()."""
    if num_turns == 20:
        return list(CALENDAR)
    cal = []
    fname = 'shortSchedule.txt' if num_turns == 10 else '8weekSchedule.txt'
    with open(fname, 'r') as f:
        for line in f:
            parts = line.split(',')
            cal.append((parts[0], int(parts[1])))
    return cal


def load_states():
    states = {}
    with open('statesPositions.txt', 'r') as f:
        for line in f:
            parts = line.split(',')
            if parts[0] != 'State Name':
                states[parts[0]] = State(parts[0], parts[1:])
    with open('districts.txt', 'r') as f:
        for line in f:
            parts = line.split(',')
            d = District(parts[1].strip(), int(parts[2].strip()) * 3, parts[0])
            states[parts[0]].addDistrict(d)
    for name, st in states.items():
        st.positions = state_issues.get_state_positions(name)
    return states


# --- Sim state container ---

class SimPlayer:
    def __init__(self, idx, name, strategy_fn, positions):
        self.idx = idx                # 0-based
        self.name = name
        self.strategy_fn = strategy_fn
        self.positions = positions    # length = len(state_issues.ISSUES)
        self.resources = [80, 100000]
        self.delegate_count = 0
        self.momentum = 0
        # End-of-game tracking.
        self.support_from_org = 0.0
        self.support_from_camp = 0.0
        self.support_from_ads = 0.0
        self.money_on_ads = 0
        self.money_on_org = 0
        self.fundraising_hours_total = 0
        self.campaign_hours_total = 0
        self.income_total = 0
        self.states_won = []
        self.districts_won = 0


class Sim:
    def __init__(self, strategies, num_turns=20, seed=0, randomize_positions=True):
        self.rng = random.Random(seed)
        self.states = load_states()
        self.calendar = load_calendar(num_turns)
        self.num_turns = num_turns
        self.current_date = 1
        self.event_of_week = self.rng.randint(0, len(state_issues.ISSUES) - 1)
        self.past_elections = {}

        n_issues = len(state_issues.ISSUES)
        self.players = []
        for i, (name, fn) in enumerate(strategies):
            if randomize_positions:
                positions = [self.rng.choice([-1, 0, 1]) for _ in range(n_issues)]
            else:
                positions = [0] * n_issues
            self.players.append(SimPlayer(i, name, fn, positions))
        self.num_players = len(self.players)

        for st in self.states.values():
            for i in range(self.num_players):
                st.setOrganization(i, 0)
                for d in st.districts:
                    d.setSupport(i, 0)
                    d.setCampaigningThisTurn(i, 0)
                    d.setAdsThisTurn(i, 0)
        for st in self.states.values():
            st.updateSupport(self.num_players, self.calendar, self.current_date)


# --- Game logic mirrors ---

def time_to_election(sim, state_name):
    for s, w in sim.calendar:
        if s == state_name:
            return w - sim.current_date
    return 99


def calc_state_opinions(sim):
    """Apply support gains for the past turn (mirrors calculateStateOpinions)."""
    for i, p in enumerate(sim.players):
        for state_name, st in sim.states.items():
            org = st.organizations[i]
            if org == 0:
                # Not on the ballot, no support gain.
                continue
            # Election-week bonus.
            tte = time_to_election(sim, state_name)
            mult_time = 1.2 if tte == 0 else (1.1 if tte == 1 else 1.0)
            mult_mom = 1.0 + p.momentum / 50.0
            # Issue alignment.
            try:
                state_pos = st.positions[sim.event_of_week]
            except (IndexError, AttributeError):
                state_pos = 0
            player_pos = p.positions[sim.event_of_week]
            if state_pos == 0:
                issue_mult = 1.0
            elif player_pos == state_pos:
                issue_mult = 1.33
            else:
                issue_mult = max(0.25, 1.0 - 0.16 * abs(player_pos - state_pos))
            mult = mult_time * mult_mom * issue_mult

            for d in st.districts:
                hours = d.campaigningThisTurn[i]
                ads = d.adsThisTurn[i]
                ads_total = sum(d.adsThisTurn)
                # Match the rebalanced game formula:
                # - org tier -> +5/numTurns per turn (so cumulative passive is
                #   ~5 per tier per district regardless of game length)
                # - campaign hours -> +3.0 each (was 1.5)
                # - ad intensity exponent back to 0.55
                org_sup = org * (5.0 / sim.num_turns) * mult
                camp_sup = hours * 3.0 * mult
                ad_sup = (ads / float(ads_total + 1)) * (ads_total / 100.0) ** 0.55 * mult
                gain = org_sup + camp_sup + ad_sup
                p.support_from_org += org_sup
                p.support_from_camp += camp_sup
                p.support_from_ads += ad_sup
                d.setSupport(i, d.support[i] + int(round(gain)))
        for st in sim.states.values():
            st.updateSupport(sim.num_players, sim.calendar, sim.current_date)


def calc_end_turn(sim, p_idx, fundraising_hours):
    """Mirrors calcEndTurn. Mutates player's resources for next week."""
    p = sim.players[p_idx]
    p.resources[0] = 80
    local = 0.0
    for st in sim.states.values():
        for d in st.districts:
            org = st.organizations[p_idx]
            base = (1.5 + org / 10.0)
            number = 1 - base ** (d.support[p_idx] / -50.0)
            mom_factor = 2 - math.exp(p.momentum / -50.0)
            local += number * d.population * 500 * mom_factor
    local = round(local)
    fundraising_income = fundraising_hours * 4000 + 20000
    p.resources[1] += fundraising_income + local
    p.income_total += fundraising_income + local
    p.fundraising_hours_total += fundraising_hours
    p.momentum /= 2.0


def decide_contests(sim):
    """Mirrors decideContests. Awards delegates for any contest that voted."""
    for state_name, week in sim.calendar:
        if week + 1 != sim.current_date:
            continue
        st = sim.states[state_name]
        st.calculatePollingAverage(sim.calendar, sim.current_date)
        state_votes = [0] * sim.num_players
        state_delegates = 0
        for d in st.districts:
            district_delegates = (d.population * 2) / 3
            state_delegates += d.population - district_delegates
            winner = -1
            most_votes = 0
            for i in range(sim.num_players):
                if st.organizations[i] > 0:
                    votes = sim.rng.gauss(d.pollingAverage[i], 3) * d.population * 150000
                    if votes < 0:
                        votes = 1
                        sim.players[i].momentum -= 2
                    if votes > most_votes:
                        winner = i
                        most_votes = votes
                    state_votes[i] += votes * d.population
            if winner < 0:
                winner = sim.rng.randrange(sim.num_players)
            sim.players[winner].delegate_count += district_delegates
            sim.players[winner].momentum += district_delegates / 4.0
            sim.players[winner].districts_won += 1
        state_winner = state_votes.index(max(state_votes))
        sim.players[state_winner].delegate_count += state_delegates
        sim.players[state_winner].momentum += state_delegates / 2.0
        sim.players[state_winner].states_won.append(state_name)
        sim.past_elections[state_name] = state_winner


def reset_weekly(sim):
    for st in sim.states.values():
        for d in st.districts:
            for i in range(sim.num_players):
                d.setCampaigningThisTurn(i, 0)
                d.setAdsThisTurn(i, 0)


def run_game(strategies, num_turns=20, seed=0):
    sim = Sim(strategies, num_turns=num_turns, seed=seed)
    while sim.current_date <= sim.num_turns:
        for p in sim.players:
            fundraising = p.strategy_fn(sim, p.idx)
            calc_end_turn(sim, p.idx, fundraising)
            p.campaign_hours_total += sum(
                d.campaigningThisTurn[p.idx] for st in sim.states.values() for d in st.districts)
        calc_state_opinions(sim)
        decide_contests(sim)
        sim.current_date += 1
        sim.event_of_week = sim.rng.randint(0, len(state_issues.ISSUES) - 1)
        reset_weekly(sim)
    return sim


# --- AI strategies ---

def _scored_districts(sim, p_idx, urgency_curve, closeness_w=1.0, delegates_w=1.0,
                      runaway_floor=-25, jitter=0.0, only_imminent_weeks=99):
    """Build [score, id, district, state_name] entries."""
    out = []
    for state_name, st in sim.states.items():
        tte = time_to_election(sim, state_name)
        if tte < 0 or tte > only_imminent_weeks:
            continue
        if st.organizations[p_idx] == 0:
            continue  # can't gain support without being on the ballot
        urgency = urgency_curve(tte)
        state_delegates = sum(d.population - (d.population * 2) / 3 for d in st.districts)
        for d in st.districts:
            my = d.support[p_idx]
            others = [d.support[j] for j in range(sim.num_players) if j != p_idx]
            top_other = max(others) if others else 0
            margin = top_other - my
            closeness = 100.0 / (1.0 + abs(margin) ** 1.2)
            penalty = 1.0
            if margin < runaway_floor:
                penalty = 0.4
            elif margin < runaway_floor + 15:
                penalty = 0.7
            score = urgency * (closeness_w * closeness + delegates_w *
                               (d.population / 3.0 + state_delegates / 6.0)) * penalty
            if jitter:
                score *= sim.rng.uniform(1 - jitter, 1 + jitter)
            out.append([score, id(d), d, state_name])
    return out


def _spend_money_on_orgs(sim, p_idx, urgency_max=8, threshold=18.0):
    """Build orgs while affordable and useful."""
    p = sim.players[p_idx]
    for state_name, st in sim.states.items():
        tte = time_to_election(sim, state_name)
        if tte < 0 or tte > urgency_max:
            continue
        org_level = st.organizations[p_idx]
        cost = max(10000, 10000 * org_level)
        state_delegates = sum(d.population - (d.population * 2) / 3 for d in st.districts)
        org_value = state_delegates * (1.0 + max(0, 6 - tte))
        if org_value > (org_level + 1) * threshold and p.resources[1] >= cost:
            p.resources[1] -= cost
            st.organizations[p_idx] += 1
            p.money_on_org += cost


def _greedy_spend_ads(sim, p_idx, scored, ad_chunk=1000):
    """Greedy ad allocation with diminishing returns."""
    p = sim.players[p_idx]
    while p.resources[1] >= ad_chunk and scored:
        i = max(range(len(scored)), key=lambda k: (scored[k][0], scored[k][1]))
        if scored[i][0] <= 0:
            break
        d = scored[i][2]
        d.setAdsThisTurn(p_idx, d.adsThisTurn[p_idx] + ad_chunk)
        p.resources[1] -= ad_chunk
        p.money_on_ads += ad_chunk
        scored[i][0] *= 0.85


def _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff):
    """Greedy time allocation with a fundraise cutoff. Returns fundraising hours."""
    p = sim.players[p_idx]
    fundraising_hours = 0
    while p.resources[0] > 0 and scored:
        i = max(range(len(scored)), key=lambda k: (scored[k][0], scored[k][1]))
        s = scored[i][0]
        if s < fundraise_cutoff:
            fundraising_hours += p.resources[0]
            p.resources[0] = 0
            break
        d = scored[i][2]
        d.setCampaigningThisTurn(p_idx, d.campaigningThisTurn[p_idx] + 1)
        p.resources[0] -= 1
        scored[i][0] *= 0.9
    return fundraising_hours


# --- Strategy implementations ---

def strat_default(sim, p_idx):
    """Approximation of the in-game personality AI."""
    def urgency(t):
        return {0: 2.4, 1: 1.7, 2: 1.1, 3: 1.1}.get(t, 0.6 if t <= 6 else 0.3)
    _spend_money_on_orgs(sim, p_idx, threshold=18.0)
    scored = _scored_districts(sim, p_idx, urgency, jitter=0.2)
    _greedy_spend_ads(sim, p_idx, scored)
    return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=12.0)


def strat_aggressive(sim, p_idx):
    """Spend everything on imminent contests; build orgs only if voting <= 4 weeks out."""
    def urgency(t):
        return {0: 4.0, 1: 2.5, 2: 1.5}.get(t, 0.2)
    _spend_money_on_orgs(sim, p_idx, urgency_max=4, threshold=14.0)
    scored = _scored_districts(sim, p_idx, urgency, only_imminent_weeks=4)
    _greedy_spend_ads(sim, p_idx, scored)
    return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=8.0)


def strat_big_state(sim, p_idx):
    """Heavily weight state size over closeness."""
    def urgency(t):
        return 1.0 if t < 0 else 1.5 if t <= 6 else 0.6
    _spend_money_on_orgs(sim, p_idx, threshold=12.0)
    scored = _scored_districts(sim, p_idx, urgency, closeness_w=0.4, delegates_w=2.0)
    _greedy_spend_ads(sim, p_idx, scored)
    return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=10.0)


def strat_close_only(sim, p_idx):
    """Pour into close races, ignore blowouts."""
    def urgency(t):
        return 1.0 if t <= 6 else 0.4
    _spend_money_on_orgs(sim, p_idx, threshold=20.0)
    scored = _scored_districts(sim, p_idx, urgency, closeness_w=2.5, delegates_w=0.6, runaway_floor=-15)
    _greedy_spend_ads(sim, p_idx, scored)
    return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=14.0)


def strat_money_machine(sim, p_idx):
    """Build orgs everywhere early, fundraise heavily, big late push."""
    def urgency(t):
        return 1.0 if t <= 4 else (0.6 if t <= 8 else 0.2)
    _spend_money_on_orgs(sim, p_idx, urgency_max=12, threshold=10.0)
    scored = _scored_districts(sim, p_idx, urgency)
    _greedy_spend_ads(sim, p_idx, scored)
    return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=18.0)


def strat_balanced(sim, p_idx):
    """Even spread, modest fundraise threshold."""
    def urgency(t):
        return 1.0 if t <= 8 else 0.5
    _spend_money_on_orgs(sim, p_idx, threshold=15.0)
    scored = _scored_districts(sim, p_idx, urgency, closeness_w=1.0, delegates_w=1.0)
    _greedy_spend_ads(sim, p_idx, scored)
    return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=11.0)


def strat_no_org(sim, p_idx):
    """Skip org building entirely (can never get on the ballot - control case)."""
    # Just dump everything into fundraising.
    sim.players[p_idx].resources[1] += 0  # no-op
    return sim.players[p_idx].resources[0]


# --- Tournament harness ---

ALL_STRATEGIES = [
    ('Default', strat_default),
    ('Aggressive', strat_aggressive),
    ('BigState', strat_big_state),
    ('CloseOnly', strat_close_only),
    ('MoneyMachine', strat_money_machine),
    ('Balanced', strat_balanced),
]


def run_tournament(strategy_pool, n_games_per_seat=20, num_turns=20, seed_base=1000, seats=4):  # noqa: E501
    """Each strategy runs many games, in different seat positions, against
    randomly-chosen others. Returns one row per (game, strategy) with stats."""
    rows = []
    rng = random.Random(seed_base)
    for game_id in range(n_games_per_seat * seats):
        # Randomly pick 'seats' strategies for this game.
        pick = rng.sample(strategy_pool, seats)
        seed = rng.randrange(1 << 30)
        sim = run_game(pick, num_turns=num_turns, seed=seed)
        delegates_sorted = sorted(
            ((p.delegate_count, idx, p) for idx, p in enumerate(sim.players)),
            reverse=True)
        for rank, (deleg, idx, p) in enumerate(delegates_sorted):
            rows.append({
                'game': game_id,
                'name': p.name,
                'seat': idx,
                'rank': rank + 1,
                'delegates': deleg,
                'win': 1 if rank == 0 else 0,
                'states_won': len(p.states_won),
                'sup_org': p.support_from_org,
                'sup_camp': p.support_from_camp,
                'sup_ads': p.support_from_ads,
                'money_ads': p.money_on_ads,
                'money_org': p.money_on_org,
                'income': p.income_total,
                'fundraising_hours': p.fundraising_hours_total,
            })
    return rows


def aggregate(rows):
    by_strat = defaultdict(list)
    for r in rows:
        by_strat[r['name']].append(r)
    agg = {}
    for name, rs in by_strat.items():
        n = len(rs)
        agg[name] = {
            'n': n,
            'win_rate': sum(r['win'] for r in rs) / n,
            'avg_delegates': np.mean([r['delegates'] for r in rs]),
            'std_delegates': np.std([r['delegates'] for r in rs]),
            'avg_states_won': np.mean([r['states_won'] for r in rs]),
            'avg_sup_org': np.mean([r['sup_org'] for r in rs]),
            'avg_sup_camp': np.mean([r['sup_camp'] for r in rs]),
            'avg_sup_ads': np.mean([r['sup_ads'] for r in rs]),
            'avg_money_ads': np.mean([r['money_ads'] for r in rs]),
            'avg_money_org': np.mean([r['money_org'] for r in rs]),
            'avg_income': np.mean([r['income'] for r in rs]),
            'avg_fundraising_hours': np.mean([r['fundraising_hours'] for r in rs]),
            'avg_rank': np.mean([r['rank'] for r in rs]),
        }
    return agg


def print_table(agg, label):
    print('\n=== {} ==='.format(label))
    head = '{:<14} {:>5} {:>9} {:>10} {:>9} {:>8} {:>8} {:>8} {:>10} {:>10} {:>11}'.format(
        'Strategy', 'N', 'Win%', 'AvgDel', 'AvgRank', 'StWon', 'Sup_Org', 'Sup_Cmp', 'Sup_Ads', 'AdSpend', 'Income')
    print(head)
    print('-' * len(head))
    for name in sorted(agg.keys(), key=lambda n: -agg[n]['win_rate']):
        a = agg[name]
        print('{:<14} {:>5d} {:>8.1%} {:>10.0f} {:>9.2f} {:>8.1f} {:>8.0f} {:>8.0f} {:>8.0f} {:>10.0f} {:>11.0f}'.format(
            name, a['n'], a['win_rate'], a['avg_delegates'], a['avg_rank'],
            a['avg_states_won'], a['avg_sup_org'], a['avg_sup_camp'],
            a['avg_sup_ads'], a['avg_money_ads'], a['avg_income']))


def plot_round(agg, rows, suffix):
    names = sorted(agg.keys(), key=lambda n: -agg[n]['win_rate'])

    # Win rate + average delegates.
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    ax.barh(names, [agg[n]['win_rate'] for n in names], color='#3498db')
    for i, n in enumerate(names):
        ax.text(agg[n]['win_rate'] + 0.005, i, '{:.1%}'.format(agg[n]['win_rate']),
                va='center', fontsize=9)
    ax.set_xlabel('Win rate')
    ax.set_title('Win rate by strategy')
    ax.invert_yaxis()
    ax.grid(True, axis='x', alpha=0.3)

    ax = axes[1]
    ax.barh(names, [agg[n]['avg_delegates'] for n in names], color='#27ae60',
            xerr=[agg[n]['std_delegates'] for n in names],
            error_kw={'capsize': 3, 'alpha': 0.5})
    ax.set_xlabel('Average delegates won')
    ax.set_title('Mean +/- 1 std delegates')
    ax.invert_yaxis()
    ax.grid(True, axis='x', alpha=0.3)
    fig.suptitle('AI tournament: {}'.format(suffix), fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'ai_winrate_{}.png'.format(suffix)), dpi=110)
    plt.close(fig)

    # Resource usage breakdown (stacked bars: money on ads vs org, support breakdown).
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    money_ads = [agg[n]['avg_money_ads'] for n in names]
    money_org = [agg[n]['avg_money_org'] for n in names]
    income = [agg[n]['avg_income'] for n in names]
    x = np.arange(len(names))
    ax.bar(x - 0.25, money_ads, width=0.25, label='Avg ad spend')
    ax.bar(x, money_org, width=0.25, label='Avg org spend')
    ax.bar(x + 0.25, income, width=0.25, label='Avg income')
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=20, ha='right')
    ax.set_ylabel('Dollars')
    ax.set_title('Money flow per strategy')
    ax.legend(fontsize=9)
    ax.grid(True, axis='y', alpha=0.3)

    ax = axes[1]
    sup_org = [agg[n]['avg_sup_org'] for n in names]
    sup_camp = [agg[n]['avg_sup_camp'] for n in names]
    sup_ads = [agg[n]['avg_sup_ads'] for n in names]
    bottom = np.zeros(len(names))
    for vals, label, color in [(sup_org, 'Org', '#27ae60'),
                                (sup_camp, 'Campaign', '#f39c12'),
                                (sup_ads, 'Ads', '#3498db')]:
        ax.bar(names, vals, bottom=bottom, label=label, color=color)
        bottom += np.array(vals)
    ax.set_ylabel('Avg total support gained')
    ax.set_title('Support sources per strategy')
    ax.legend(fontsize=9)
    plt.setp(ax.get_xticklabels(), rotation=20, ha='right')
    fig.suptitle('AI tournament: {}'.format(suffix), fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'ai_resources_{}.png'.format(suffix)), dpi=110)
    plt.close(fig)


def head_to_head(rows):
    """For every pair of strategies, what's the win rate when both appear in
    the same game? Returns a dict of (a, b) -> win rate of a over b."""
    games = defaultdict(list)
    for r in rows:
        games[r['game']].append(r)
    pair_wins = defaultdict(lambda: [0, 0])  # (a,b) -> [a wins, total games together]
    for game_id, players in games.items():
        for i in range(len(players)):
            for j in range(len(players)):
                if i == j:
                    continue
                key = (players[i]['name'], players[j]['name'])
                pair_wins[key][1] += 1
                if players[i]['delegates'] > players[j]['delegates']:
                    pair_wins[key][0] += 1
    return {k: (v[0] / v[1]) if v[1] else 0.0 for k, v in pair_wins.items()}


def plot_head_to_head(rows, suffix):
    names = sorted({r['name'] for r in rows})
    h2h = head_to_head(rows)
    matrix = np.zeros((len(names), len(names)))
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if a == b:
                matrix[i, j] = 0.5
            else:
                matrix[i, j] = h2h.get((a, b), 0.5)

    fig, ax = plt.subplots(figsize=(8, 6.5))
    im = ax.imshow(matrix, cmap='RdYlGn', vmin=0.2, vmax=0.8)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=35, ha='right')
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    for i in range(len(names)):
        for j in range(len(names)):
            ax.text(j, i, '{:.0%}'.format(matrix[i, j]), ha='center', va='center',
                    fontsize=9)
    plt.colorbar(im, ax=ax, fraction=0.046).set_label('Row beats Column')
    ax.set_title('Head-to-head win rate ({})'.format(suffix))
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'ai_h2h_{}.png'.format(suffix)), dpi=110)
    plt.close(fig)


# --- Iterated runs ---

def round1():
    """Initial broad sweep with the original strategies."""
    print('\n############ ROUND 1: baseline strategies ############')
    rows = run_tournament(ALL_STRATEGIES, n_games_per_seat=15, seats=4, seed_base=1)
    agg = aggregate(rows)
    print_table(agg, 'Round 1 results')
    plot_round(agg, rows, 'round1')
    plot_head_to_head(rows, 'round1')
    return agg


def round2():
    """Refine the laggards. The default already adapts (jitter + balanced
    weights). For round 2 we tune the most extreme strategies (CloseOnly
    raised its closeness weight too high; MoneyMachine builds way too many
    orgs)."""
    def strat_close_v2(sim, p_idx):
        def urgency(t):
            return 1.0 if t <= 5 else 0.4
        _spend_money_on_orgs(sim, p_idx, threshold=16.0)
        scored = _scored_districts(sim, p_idx, urgency, closeness_w=1.6, delegates_w=1.0,
                                    runaway_floor=-12)
        _greedy_spend_ads(sim, p_idx, scored)
        return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=12.0)

    def strat_money_v2(sim, p_idx):
        def urgency(t):
            return 1.4 if t <= 6 else 0.4
        # Less aggressive org build, higher fundraise cutoff.
        _spend_money_on_orgs(sim, p_idx, urgency_max=10, threshold=14.0)
        scored = _scored_districts(sim, p_idx, urgency)
        _greedy_spend_ads(sim, p_idx, scored)
        return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=15.0)

    def strat_late_push(sim, p_idx):
        """Hold cash early, dump in the last 5 weeks."""
        def urgency(t):
            return 3.0 if t <= 3 else (1.0 if t <= 6 else 0.3)
        # Build orgs only when an election is close.
        _spend_money_on_orgs(sim, p_idx, urgency_max=5, threshold=12.0)
        # Reserve most money for the closing weeks: only spend ads if score
        # is pretty high.
        scored = _scored_districts(sim, p_idx, urgency)
        # Filter to high-score-only ads to save cash for late game.
        high = [r for r in scored if r[0] > 60]
        _greedy_spend_ads(sim, p_idx, high)
        return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=12.0)

    print('\n############ ROUND 2: refined strategies ############')
    pool = list(ALL_STRATEGIES) + [
        ('Close_v2', strat_close_v2),
        ('Money_v2', strat_money_v2),
        ('LatePush', strat_late_push),
    ]
    rows = run_tournament(pool, n_games_per_seat=12, seats=4, seed_base=2)
    agg = aggregate(rows)
    print_table(agg, 'Round 2 results')
    plot_round(agg, rows, 'round2')
    plot_head_to_head(rows, 'round2')
    return agg


def round3():
    """Top-N showdown: the winners from round 2 in head-to-head head matchups
    so we get cleaner pairwise data."""
    # Hardcoded top performers from round 2 inspection.
    def strat_aggressive(sim, p_idx):  # local alias for round 3 only
        def urgency(t):
            return {0: 4.0, 1: 2.5, 2: 1.5}.get(t, 0.2)
        _spend_money_on_orgs(sim, p_idx, urgency_max=4, threshold=14.0)
        scored = _scored_districts(sim, p_idx, urgency, only_imminent_weeks=4)
        _greedy_spend_ads(sim, p_idx, scored)
        return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=8.0)

    def strat_balanced_v2(sim, p_idx):
        def urgency(t):
            return {0: 2.0, 1: 1.5, 2: 1.2, 3: 1.0}.get(t, 0.6 if t <= 6 else 0.3)
        _spend_money_on_orgs(sim, p_idx, threshold=16.0)
        scored = _scored_districts(sim, p_idx, urgency, jitter=0.15)
        _greedy_spend_ads(sim, p_idx, scored)
        return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=11.0)

    def strat_money_v3(sim, p_idx):
        """Reserve more cash, but actually spend it close to election week."""
        def urgency(t):
            return 2.0 if t <= 4 else (0.8 if t <= 8 else 0.3)
        _spend_money_on_orgs(sim, p_idx, urgency_max=8, threshold=14.0)
        scored = _scored_districts(sim, p_idx, urgency)
        # Spend ads aggressively if election within 4 weeks; otherwise hoard.
        scored_now = [r for r in scored if r[0] > 50]
        _greedy_spend_ads(sim, p_idx, scored_now)
        return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=14.0)

    print('\n############ ROUND 3: top strategies, more seats per game ############')
    pool = [
        ('Default', strat_default),
        ('Aggressive', strat_aggressive),
        ('BigState', strat_big_state),
        ('Balanced_v2', strat_balanced_v2),
        ('Money_v3', strat_money_v3),
    ]
    rows = run_tournament(pool, n_games_per_seat=25, seats=4, seed_base=3)
    agg = aggregate(rows)
    print_table(agg, 'Round 3 results')
    plot_round(agg, rows, 'round3')
    plot_head_to_head(rows, 'round3')
    return agg


def round4():
    """Round 1 said MoneyMachine is unbeatable. Is that real, or just because
    the other AIs leave free states on the table that MoneyMachine sweeps?
    Test by giving each strategy its own dose of org-everywhere logic at
    different intensities."""
    def make_org_variant(threshold, urgency_max, fundraise_cutoff, label):
        def fn(sim, p_idx):
            def urgency(t):
                return 1.0 if t <= 6 else 0.4
            _spend_money_on_orgs(sim, p_idx, urgency_max=urgency_max, threshold=threshold)
            scored = _scored_districts(sim, p_idx, urgency)
            _greedy_spend_ads(sim, p_idx, scored)
            return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=fundraise_cutoff)
        fn.__name__ = label
        return fn

    pool = [
        ('Org_Cheap',  make_org_variant(threshold=8.0,  urgency_max=15, fundraise_cutoff=18.0, label='Org_Cheap')),
        ('Org_Cheap2', make_org_variant(threshold=10.0, urgency_max=12, fundraise_cutoff=18.0, label='Org_Cheap2')),
        ('Org_Med',    make_org_variant(threshold=15.0, urgency_max=10, fundraise_cutoff=14.0, label='Org_Med')),
        ('Org_Tight',  make_org_variant(threshold=22.0, urgency_max=8,  fundraise_cutoff=10.0, label='Org_Tight')),
        ('Org_None',   strat_no_org),
    ]
    print('\n############ ROUND 4: org-build threshold sweep ############')
    rows = run_tournament(pool, n_games_per_seat=20, seats=4, seed_base=4)
    agg = aggregate(rows)
    print_table(agg, 'Round 4 (org sweep)')
    plot_round(agg, rows, 'round4')
    plot_head_to_head(rows, 'round4')
    return agg


def round5():
    """Add issue-aware strategies. The state issue alignment multiplier ranges
    from 0.68 to 1.33 -- a ~2x swing. Does choosing where to spend based on
    state alignment with your stances actually win games?"""

    def issue_alignment_factor(sim, st, p):
        """Return the issue multiplier for THIS player on THIS state for the
        current event of the week. Used as an extra score weight."""
        try:
            state_pos = st.positions[sim.event_of_week]
        except (IndexError, AttributeError):
            return 1.0
        player_pos = p.positions[sim.event_of_week]
        if state_pos == 0:
            return 1.0
        if state_pos == player_pos:
            return 1.33
        return max(0.25, 1.0 - 0.16 * abs(player_pos - state_pos))

    def make_issue_strategy(weight, label):
        """weight = how much to amplify scores in aligned states.
        weight=1 = ignore alignment. >1 = lean into matched states."""
        def fn(sim, p_idx):
            p = sim.players[p_idx]
            def urgency(t):
                return 1.0 if t <= 6 else 0.4
            _spend_money_on_orgs(sim, p_idx, threshold=12.0)
            scored = _scored_districts(sim, p_idx, urgency)
            # Scale each district's score by how aligned its state is.
            for entry in scored:
                st = sim.states[entry[3]]
                align = issue_alignment_factor(sim, st, p)
                if weight >= 0:
                    entry[0] *= 1.0 + (align - 1.0) * weight
                else:
                    entry[0] *= 1.0 + (align - 1.0) * weight
            _greedy_spend_ads(sim, p_idx, scored)
            return _greedy_spend_time(sim, p_idx, scored, fundraise_cutoff=12.0)
        fn.__name__ = label
        return fn

    # Use the same money-aware base everyone gets so the org effect is
    # neutralized and we isolate the issue-targeting effect.
    pool = [
        ('IssueIgnore',     make_issue_strategy(0.0,  'IssueIgnore')),
        ('IssueLean',       make_issue_strategy(1.0,  'IssueLean')),
        ('IssueAllIn',      make_issue_strategy(2.5,  'IssueAllIn')),
        ('IssueAvoid',      make_issue_strategy(-1.0, 'IssueAvoid')),
        ('Default',         strat_default),
    ]
    print('\n############ ROUND 5: issue-aware targeting ############')
    rows = run_tournament(pool, n_games_per_seat=25, seats=4, seed_base=5)
    agg = aggregate(rows)
    print_table(agg, 'Round 5 (issue weighting)')
    plot_round(agg, rows, 'round5')
    plot_head_to_head(rows, 'round5')
    return agg


def round_lengths(seats=4, seed_offset=0, label_suffix=''):
    """Run the same strategy pool across the three game lengths and compare."""
    print('\n############ ROUND L: per-game-length tournament ({} players) ############'.format(seats))
    results = {}
    for nt in (8, 10, 20):
        rows = run_tournament(ALL_STRATEGIES, n_games_per_seat=20, seats=seats,
                              seed_base=900 + nt + seed_offset, num_turns=nt)
        agg = aggregate(rows)
        results[nt] = (agg, rows)
        print_table(agg, 'Game length = {} turns ({} players)'.format(nt, seats))

    plot_length_comparison(results, suffix=label_suffix or '{}p'.format(seats))
    return results


def plot_length_comparison(results, suffix='4p'):
    """Side-by-side win-rate bars across the three lengths."""
    lengths = sorted(results.keys())
    names = sorted({n for nt in lengths for n in results[nt][0].keys()})

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    # Win rate by length.
    ax = axes[0]
    width = 0.25
    x = np.arange(len(names))
    for i, nt in enumerate(lengths):
        agg = results[nt][0]
        vals = [agg.get(n, {'win_rate': 0})['win_rate'] for n in names]
        ax.bar(x + (i - 1) * width, vals, width, label='{} turns'.format(nt))
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=20, ha='right')
    ax.set_ylabel('Win rate')
    ax.set_title('Win rate by strategy and game length')
    ax.legend()
    ax.grid(True, axis='y', alpha=0.3)

    # Avg delegates by length.
    ax = axes[1]
    for i, nt in enumerate(lengths):
        agg = results[nt][0]
        vals = [agg.get(n, {'avg_delegates': 0})['avg_delegates'] for n in names]
        ax.bar(x + (i - 1) * width, vals, width, label='{} turns'.format(nt))
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=20, ha='right')
    ax.set_ylabel('Average delegates won')
    ax.set_title('Average delegates by strategy and game length')
    ax.legend()
    ax.grid(True, axis='y', alpha=0.3)

    fig.suptitle('Strategy performance across game lengths ({})'.format(suffix))
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'ai_lengths_{}.png'.format(suffix)), dpi=110)
    plt.close(fig)


def plot_seats_comparison(results_3p, results_4p):
    """For each game length, plot 3p vs 4p win rate per strategy."""
    lengths = sorted(set(results_3p.keys()) | set(results_4p.keys()))
    names = sorted({n for nt in lengths for n in results_4p.get(nt, ({},))[0].keys()})

    fig, axes = plt.subplots(1, len(lengths), figsize=(5 * len(lengths), 5), sharey=True)
    if len(lengths) == 1:
        axes = [axes]
    width = 0.4
    for ax, nt in zip(axes, lengths):
        agg3 = results_3p.get(nt, ({}, None))[0]
        agg4 = results_4p.get(nt, ({}, None))[0]
        x = np.arange(len(names))
        ax.bar(x - width / 2, [agg3.get(n, {'win_rate': 0})['win_rate'] for n in names],
               width, label='3 players')
        ax.bar(x + width / 2, [agg4.get(n, {'win_rate': 0})['win_rate'] for n in names],
               width, label='4 players')
        ax.set_xticks(x)
        ax.set_xticklabels(names, rotation=25, ha='right')
        ax.set_title('{} turns'.format(nt))
        ax.grid(True, axis='y', alpha=0.3)
        if ax is axes[0]:
            ax.set_ylabel('Win rate')
            ax.legend()
    fig.suptitle('Win rate: 3 vs 4 players, by game length')
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'ai_seats_compare.png'), dpi=110)
    plt.close(fig)


def round_seats():
    """Compare 3-player vs 4-player tournaments at all three game lengths."""
    results_3p = round_lengths(seats=3, seed_offset=300, label_suffix='3p')
    results_4p = round_lengths(seats=4, seed_offset=400, label_suffix='4p')
    plot_seats_comparison(results_3p, results_4p)
    return results_3p, results_4p


def round6():
    """After the org rebalance (0.5/tier instead of 2.0), re-run the strategy
    pool to confirm no single approach dominates."""
    print('\n############ ROUND 6: rebalanced org constant (0.5/tier) ############')
    rows = run_tournament(ALL_STRATEGIES, n_games_per_seat=20, seats=4, seed_base=6)
    agg = aggregate(rows)
    print_table(agg, 'Round 6 (post-rebalance)')
    plot_round(agg, rows, 'round6')
    plot_head_to_head(rows, 'round6')
    return agg


def main():
    round1()
    round2()
    round3()
    round4()
    round5()
    round6()
    print('\nAll plots in', OUT_DIR)


if __name__ == '__main__':
    main()
