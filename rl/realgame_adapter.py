"""Adapter that wraps CampaignGame.py's globals as a sim-like object.

The headless `Sim` and the real game's globals carry the same data — same
State / District objects, same calendar shape, same per-player resources —
but use different attribute names. This module presents a unified view so
the obs encoder and action decoder can run unchanged against a live game.

Layout differences this adapter normalizes:
    sim.calendar            <- CampaignGame.calendarOfContests
    sim.current_date        <- CampaignGame.currentDate
    sim.event_of_week       <- CampaignGame.eventOfTheWeek
    sim.num_turns           <- CampaignGame.numTurns
    sim.num_players         <- CampaignGame.numPlayers
    sim.states              <- CampaignGame.states (already a name->State dict)
    sim.players[i]          <- CampaignGame.players[i+1] wrapped
        .delegate_count     <- .delegateCount
        .momentum           <- .momentum
        .resources          <- .resources (mutable list, write-through)
        .positions          <- .positions
"""
import random


class _PlayerView:
    """Read/write proxy: attribute access reads the wrapped Player; writes
    propagate back. Resources are a shared list (Python list aliasing) so
    spending lands on the real Player without extra plumbing."""

    __slots__ = ('_p',)

    def __init__(self, real_player):
        object.__setattr__(self, '_p', real_player)

    @property
    def delegate_count(self):
        return getattr(self._p, 'delegateCount', 0)

    @delegate_count.setter
    def delegate_count(self, v):
        self._p.delegateCount = v

    @property
    def momentum(self):
        return getattr(self._p, 'momentum', 0.0)

    @momentum.setter
    def momentum(self, v):
        self._p.momentum = v

    @property
    def resources(self):
        return self._p.resources

    @resources.setter
    def resources(self, v):
        self._p.resources = v

    @property
    def positions(self):
        return self._p.positions

    # The sim's heuristic decoders track spending via `p.money_on_org += cost`
    # and `p.money_on_ads += cost`. Because our getters always return 0, the
    # `+=` desugars to `setter(0 + cost) = setter(cost)`. So each setter call
    # receives exactly the per-action cost (one org tier built, or one ad
    # chunk spent). We forward those into the real game's `addStat` system
    # so the end-of-game report credits the neural agent correctly.
    @property
    def money_on_org(self):
        return 0

    @money_on_org.setter
    def money_on_org(self, v):
        try:
            self._p.addStat('org_money_total', int(v))
            self._p.addStat('orgs_built', 1)
        except AttributeError:
            pass

    @property
    def money_on_ads(self):
        return 0

    @money_on_ads.setter
    def money_on_ads(self, v):
        try:
            self._p.addStat('ad_money_total', int(v))
        except AttributeError:
            pass


class RealGameSimView:
    """Sim-shaped view of CampaignGame's globals. Construct each turn so
    `current_date` and `event_of_week` reflect the latest world state."""

    def __init__(self, calendar, current_date, event_of_week, num_turns,
                 num_players, states, players_dict, rng=None):
        self.calendar = calendar
        self.current_date = current_date
        self.event_of_week = event_of_week
        self.num_turns = num_turns
        self.num_players = num_players
        self.states = states
        # Real game uses 1-indexed dict normally, but be defensive: discover
        # the actual keys, sort them, and take the first num_players.
        keys = sorted(players_dict.keys())
        if len(keys) < num_players:
            raise RuntimeError(
                f'players_dict has only {len(keys)} entries '
                f'(keys={keys}) but num_players={num_players}')
        self.players = [_PlayerView(players_dict[k]) for k in keys[:num_players]]
        self._player_keys = keys[:num_players]
        self.rng = rng if rng is not None else random.Random()

    @classmethod
    def from_module(cls, cg_module, rng=None):
        """Build from the CampaignGame module's current globals."""
        return cls(
            calendar=cg_module.calendarOfContests,
            current_date=cg_module.currentDate,
            event_of_week=cg_module.eventOfTheWeek,
            num_turns=cg_module.numTurns,
            num_players=cg_module.numPlayers,
            states=cg_module.states,
            players_dict=cg_module.players,
            rng=rng,
        )
