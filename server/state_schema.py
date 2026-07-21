"""JSON (de)serialization for a full match state.

Replaces the desktop game's pickle-of-live-class-instances save format with a
plain-dict / JSON representation that:

* a browser client can consume, and
* round-trips losslessly through ``engine.GameState`` + the ``State`` /
  ``District`` / ``Player`` data classes.

It also fixes the gaps in the pickle save (which drops ``issues_mode``,
``event_of_week``, ``calendar`` and ``num_players``): the match document here
carries everything needed to rebuild a game exactly.

The match document shape (see ``match_to_dict``):

    {
      "match_id": "AB12CD",
      "config": {
        "num_turns": 20,
        "num_players": 3,
        "issues_mode": false,
        "calendar": [["Iowa", 4], ...],
        "seats": [
          {"seat": 1, "name": "Alice", "controller": "human", "ai_strategy": null,
           "positions": [ ... ]},
          ...
        ]
      },
      "current_date": 5,
      "event_of_week": 2,
      "past_elections": {"Iowa": 1, ...},
      "week_results": { ... },       # last resolved week's report (engine output)
      "players": { "1": {player_dict}, ... },   # 1-based seat -> Player
      "states":  { "Iowa": {state_dict}, ... }
    }

``rng`` is intentionally NOT serialized — it's a runtime concern. The service
layer seeds a fresh deterministic rng per (match, week) when resolving.
"""
import os
import sys

# Server modules live in a subdirectory; make the repo-root modules importable
# regardless of the working directory the server is launched from.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from State import State, District  # noqa: E402
from Player import Player  # noqa: E402
import engine  # noqa: E402
import state_issues  # noqa: E402


# --- Player ---------------------------------------------------------------

def player_to_dict(p):
    return {
        'name': p.name,
        'public_name': p.publicName,
        'is_human': p.isHuman,
        'ai_strategy': getattr(p, 'aiStrategy', 'Default'),
        'resources': list(p.resources),
        'positions': list(p.positions),
        'delegate_count': p.delegateCount,
        'momentum': p.momentum,
        'history': p.history,
        'stats': getattr(p, 'stats', None),
    }


def player_from_dict(d):
    p = Player(d['name'])
    p.publicName = d.get('public_name', '')
    p.isHuman = d.get('is_human', 'human')
    p.aiStrategy = d.get('ai_strategy', 'Default')
    p.resources = list(d.get('resources', [80, 100000]))
    p.positions = list(d.get('positions', []))
    p.delegateCount = d.get('delegate_count', 0)
    p.momentum = d.get('momentum', 0)
    p.history = d.get('history', {}) or {}
    stats = d.get('stats')
    if stats is not None:
        p.stats = stats
    p._ensure_stats()
    return p


# --- District / State -----------------------------------------------------

def district_to_dict(d):
    return {
        'name': d.name,
        'population': d.population,
        'state': d.state,
        'positions': list(d.positions),
        'support': list(d.support),
        'polling_average': list(d.pollingAverage),
        'campaigning_this_turn': list(d.campaigningThisTurn),
        'ads_this_turn': list(d.adsThisTurn),
    }


def district_from_dict(d):
    dist = District(d['name'], d['population'], d['state'])
    dist.positions = list(d.get('positions', []))
    dist.support = list(d.get('support', []))
    dist.pollingAverage = list(d.get('polling_average', []))
    dist.campaigningThisTurn = list(d.get('campaigning_this_turn', []))
    dist.adsThisTurn = list(d.get('ads_this_turn', []))
    return dist


def state_to_dict(s):
    return {
        'name': s.name,
        'positions': list(s.positions),
        'opinions': list(s.opinions),
        'support': list(s.support),
        'organizations': list(s.organizations),
        'polling_average': list(s.pollingAverage),
        'districts': [district_to_dict(d) for d in s.districts],
    }


def state_from_dict(d):
    s = State(d['name'], list(d.get('positions', [])))
    s.positions = list(d.get('positions', []))
    s.opinions = list(d.get('opinions', []))
    s.support = list(d.get('support', []))
    s.organizations = list(d.get('organizations', []))
    s.pollingAverage = list(d.get('polling_average', []))
    s.districts = [district_from_dict(dd) for dd in d.get('districts', [])]
    return s


# --- Full match document --------------------------------------------------

def _seats_config(players):
    """Client-friendly per-seat metadata, derived from the Player objects
    (which stay the single source of truth)."""
    seats = []
    for seat in sorted(players.keys()):
        p = players[seat]
        controller = 'human' if p.isHuman == 'human' else 'ai'
        seats.append({
            'seat': seat,
            'name': p.publicName or p.name,
            'controller': controller,
            'ai_strategy': None if controller == 'human' else getattr(p, 'aiStrategy', 'Default'),
            'positions': list(p.positions),
        })
    return seats


def match_to_dict(gs, match_id=None, week_results=None, whose_turn=None):
    """Serialize an engine.GameState (+ a little match metadata) to a dict."""
    players = gs.players
    return {
        'match_id': match_id,
        'config': {
            'num_turns': gs.num_turns,
            'num_players': gs.num_players,
            'issues_mode': gs.issues_mode,
            'calendar': [list(c) for c in gs.calendar],
            'seats': _seats_config(players),
            # Static issue metadata (name + per-side labels), so the client can
            # render the issue-of-the-week and each player/state stance in plain
            # English. Index order matches Player.positions / State.positions.
            'issues': [dict(i) for i in state_issues.ISSUES],
        },
        'current_date': gs.current_date,
        'event_of_week': gs.event_of_week,
        'past_elections': dict(gs.past_elections),
        'week_results': week_results if week_results is not None else {},
        'whose_turn': whose_turn,
        'players': {str(seat): player_to_dict(p) for seat, p in players.items()},
        'states': {name: state_to_dict(s) for name, s in gs.states.items()},
    }


def match_from_dict(doc, rng=None):
    """Rebuild an engine.GameState from a match document. ``rng`` is left to
    the caller (the service seeds it per resolve); pass one if you intend to
    resolve immediately.

    Returns (gamestate, meta) where meta carries the non-GameState fields
    (match_id, week_results, whose_turn)."""
    players = {int(seat): player_from_dict(pd) for seat, pd in doc['players'].items()}
    states = {name: state_from_dict(sd) for name, sd in doc['states'].items()}
    cfg = doc['config']
    gs = engine.GameState(
        states=states,
        players=players,
        calendar=[tuple(c) for c in cfg['calendar']],
        current_date=doc['current_date'],
        num_turns=cfg['num_turns'],
        event_of_week=doc['event_of_week'],
        issues_mode=cfg['issues_mode'],
        past_elections=dict(doc.get('past_elections', {})),
        rng=rng,
    )
    meta = {
        'match_id': doc.get('match_id'),
        'week_results': doc.get('week_results', {}),
        'whose_turn': doc.get('whose_turn'),
    }
    return gs, meta
