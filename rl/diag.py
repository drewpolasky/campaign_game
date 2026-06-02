"""Per-turn behavior diagnostic for a trained model.

The original diagnostic in the eval scripts had a bug: it read
`district.campaigningThisTurn` and `district.adsThisTurn` AFTER
`env.step()` returned, but step()'s final action is `reset_weekly(sim)`
which zeroes both fields. So every diagnostic line showed `camp_hrs=0
ads=$0` even when the agent was actively spending — wrongly looking
like a Nash collapse.

This module reads the cumulative trackers (`p.campaign_hours_total`,
`p.money_on_ads`, `p.money_on_org`) which are not reset and reports
per-turn deltas. Also tracks remaining cash + hours after each turn.

Usage:
    from rl.diag import run_diagnostic
    run_diagnostic('runs/v15_league/model', 'FocusedDefault',
                   num_turns=10, action_kind='coupled')
"""
from stable_baselines3 import PPO

from .gym_env import CampaignGymEnv
from .opponent import named_scripted


def run_diagnostic(model_path, opponent_name, num_turns=10, seed=0,
                   action_kind='coupled'):
    """Print a per-turn breakdown of the agent's spending vs an opponent."""

    def factory(s):
        return [named_scripted(opponent_name)]

    env = CampaignGymEnv(num_turns=num_turns, seed=seed,
                         opponent_factory=factory, action_kind=action_kind)
    obs, _ = env.reset(seed=seed)
    model = PPO.load(model_path, device='cpu')

    sim = env._inner.sim
    agent = sim.players[0]

    print('=== Diagnostic: {} vs {} (num_turns={}, seed={}) ==='.format(
        model_path, opponent_name, num_turns, seed))
    print('  turn | camp_hrs |   ad_spend |  org_spend |  fundraised |'
          '  cash_left | hours_left | total_orgs')
    print('  ' + '-' * 100)

    prev_camp = 0
    prev_ad = 0
    prev_org = 0
    prev_fund_hrs = 0

    for t in range(num_turns):
        action, _ = model.predict(obs, deterministic=True)
        obs, r, term, trunc, info = env.step(action)

        # Cumulative trackers survive reset_weekly.
        camp_now = getattr(agent, 'campaign_hours_total', 0)
        ad_now = getattr(agent, 'money_on_ads', 0)
        org_now = getattr(agent, 'money_on_org', 0)
        fund_hrs_now = getattr(agent, 'fundraising_hours_total', 0)

        d_camp = camp_now - prev_camp
        d_ad = ad_now - prev_ad
        d_org = org_now - prev_org
        d_fund_hrs = fund_hrs_now - prev_fund_hrs

        total_orgs = sum(st.organizations[0] for st in sim.states.values())

        print('  {:>4d} | {:>8d} | ${:>9,d} | ${:>9,d} | {:>8d} hrs |'
              ' ${:>9,d} | {:>10d} | {:>10d}'.format(
                  t + 1, int(d_camp), int(d_ad), int(d_org),
                  int(d_fund_hrs), int(agent.resources[1]),
                  int(agent.resources[0]), int(total_orgs)))

        prev_camp = camp_now
        prev_ad = ad_now
        prev_org = org_now
        prev_fund_hrs = fund_hrs_now

        if term or trunc:
            break

    print('  Final: agent={}  opp={}'.format(
        agent.delegate_count, info['opp_delegates']))


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True)
    p.add_argument('--opponent', default='FocusedDefault')
    p.add_argument('--num-turns', type=int, default=10)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--action-kind', default='coupled')
    args = p.parse_args()
    run_diagnostic(args.model, args.opponent, args.num_turns, args.seed,
                   args.action_kind)
