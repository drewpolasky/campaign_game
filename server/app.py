"""Unified server: the existing save-blob endpoints + the new JSON match API.

Run:
    cd server && python app.py
    # or:  python -m server.app   (from the repo root)

The blob endpoints (/campaign_saves, /health) are inherited unchanged from
campaign_save_server so the desktop client keeps working. The new endpoints
under /api/ drive server-authoritative browser matches:

    POST /api/matches                      create a match -> match_id + seat links
    GET  /api/matches/<id>/state?token=    a seat's view of the current state
    POST /api/matches/<id>/moves?token=    submit this seat's week (auto-resolves)
    GET  /api/matches/<id>/status?token=   poll: week / status / who's submitted
    POST /api/matches/<id>/advance?token=  step an AI-only / ready match one week

Auth for /api is the per-seat magic-link token (opaque, unguessable). The
blob endpoints keep their own X-API-Key auth.
"""
import hashlib
import os
import random
import secrets
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from flask import request, jsonify, send_from_directory, Response  # noqa: E402

from server.campaign_save_server import app  # noqa: E402  (reuse blob app + endpoints)
from server import db, game_service, state_schema  # noqa: E402
import state_issues  # noqa: E402

db.init_db()
db.prune_finished()  # drop long-finished matches so the DB doesn't grow forever

# Reject oversized request bodies (JSON moves/configs are tiny; this just caps
# a memory-exhaustion vector on a public URL).
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('CAMPAIGN_MAX_BODY', str(8 * 1024 * 1024)))

# Built React bundle (produced by `cd web && npm run build`). Served
# same-origin in production so there's no CORS and magic links resolve against
# the same host as the API.
_WEB_DIST = os.path.join(_REPO_ROOT, 'web', 'dist')

# Optional shared passphrase required to CREATE a match. Playing an existing
# seat via its magic link is never gated by this — only creation. Unset/empty
# means creation is open (fine for local dev / a private URL).
CREATE_KEY = os.environ.get('CAMPAIGN_CREATE_KEY', '')

# The legacy /campaign_saves blob endpoints (desktop LAN save relay) are NOT
# used by the web game and default to a weak shared key, so they're disabled in
# this unified server unless explicitly enabled. Run campaign_save_server.py
# standalone, or set CAMPAIGN_ENABLE_BLOB=1 (with a strong CAMPAIGN_API_KEY), if
# you actually need them.
BLOB_ENABLED = os.environ.get('CAMPAIGN_ENABLE_BLOB', '') not in ('', '0', 'false', 'False')

# Secret mixed into the per-week contest RNG so a player can't predict the
# random vote draws from the (semi-guessable) match id. Each week resolves
# exactly once and the result is persisted, so this need not survive restarts —
# a fresh random secret per process is fine; set CAMPAIGN_RNG_SECRET to pin it.
_RNG_SECRET = os.environ.get('CAMPAIGN_RNG_SECRET') or secrets.token_hex(16)


# --- CORS (dev: the Vite dev server is a different origin) -----------------
@app.before_request
def _guard_blob():
    # Legacy save-relay endpoints stay off unless explicitly enabled.
    if not BLOB_ENABLED and request.path.startswith('/campaign_saves'):
        return jsonify({'error': 'not found'}), 404


@app.before_request
def _cors_preflight():
    # Answer any CORS preflight uniformly (the client sends a JSON Content-Type
    # header, which makes even GETs non-simple). after_request adds the headers.
    if request.method == 'OPTIONS':
        return Response(status=204)


@app.after_request
def _cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = os.environ.get('CAMPAIGN_CORS_ORIGIN', '*')
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return resp


# --- helpers ---------------------------------------------------------------

def _resolve_rng(match_id, week):
    """Per-(match, week) rng, seeded with a server secret so the draws aren't
    predictable from the match id."""
    seed = int.from_bytes(
        hashlib.sha256('{}:{}:{}'.format(_RNG_SECRET, match_id, week).encode()).digest()[:8], 'big')
    return random.Random(seed)


def _auth(match_id):
    """Return the seat dict for the request's ?token=, or (None, error_response)."""
    token = request.args.get('token', '')
    seat = db.seat_for_token(token)
    if seat is None or seat['match_id'] != match_id:
        return None, (jsonify({'error': 'invalid token for this match'}), 403)
    return seat, None


def _public_status(match):
    seats = db.get_seats(match['id'])
    week = match['current_week']
    submitted = db.submitted_seats(match['id'], week)
    humans = [s['seat_no'] for s in seats if s['controller'] == 'human']
    return {
        'match_id': match['id'],
        'current_week': week,
        'num_turns': match['doc']['config']['num_turns'],
        'status': match['status'],
        'game_over': match['status'] == 'finished',
        'seats': [{'seat': s['seat_no'], 'name': s['display_name'],
                   'controller': s['controller'],
                   'submitted': s['seat_no'] in submitted} for s in seats],
        'waiting_on': sorted(set(humans) - submitted),
    }


def _maybe_resolve(match_id):
    """If every human seat has submitted for the current week (or there are no
    human seats), resolve the week and persist. Returns True if it resolved."""
    with db.resolve_lock:
        match = db.get_match(match_id)
        if match is None or match['status'] != 'active':
            return False
        week = match['current_week']
        humans = db.human_seats(match_id)
        submitted = db.submitted_seats(match_id, week)
        if humans and not set(humans).issubset(submitted):
            return False  # still waiting on a human

        human_moves = db.get_submissions(match_id, week)
        gs, _ = state_schema.match_from_dict(match['doc'])
        week_results, all_moves = game_service.resolve_turn(
            gs, human_moves, _resolve_rng(match_id, week))
        status = 'finished' if game_service.is_game_over(gs) else 'active'
        new_doc = state_schema.match_to_dict(
            gs, match_id=match_id, week_results=week_results, whose_turn=None)
        db.save_match_state(match_id, new_doc, status)
        db.log_week(match_id, week, week_results, all_moves)
        db.clear_submissions(match_id, week)
        return True


# --- endpoints -------------------------------------------------------------

@app.route('/api/config', methods=['GET'])
def public_config():
    """Client-visible server config: whether creating a match needs a passphrase
    (so the lobby only shows the field when it's actually required)."""
    return jsonify({'create_gated': bool(CREATE_KEY)})


@app.route('/api/issues', methods=['GET'])
def issues():
    """Static issue metadata (name + per-side labels), so the lobby can offer
    per-issue position pickers before a match exists."""
    return jsonify(state_issues.ISSUES)


@app.route('/api/matches', methods=['POST'])
def create_match():
    body = request.get_json(silent=True) or {}
    if CREATE_KEY and body.get('create_key', '') != CREATE_KEY:
        return jsonify({'error': 'A valid create passphrase is required to start a game.'}), 403
    config = body.get('config')
    if not config or not config.get('seats'):
        return jsonify({'error': 'config with seats is required'}), 400
    try:
        doc, seat_tokens, spectator_token = game_service.create_match(config)
    except (ValueError, KeyError) as e:
        return jsonify({'error': str(e)}), 400
    db.create_match(doc, seat_tokens, spectator_token)
    return jsonify({
        'match_id': doc['match_id'],
        'seats': doc['config']['seats'],
        # Magic links are relative; the client composes the full URL.
        'seat_links': {str(seat): '/play/{}'.format(tok)
                       for seat, tok in seat_tokens.items()},
        'seat_tokens': {str(seat): tok for seat, tok in seat_tokens.items()},
        'spectator_link': '/play/{}'.format(spectator_token),
        'spectator_token': spectator_token,
    }), 201


@app.route('/api/resolve-token', methods=['GET'])
def resolve_token():
    """A magic link carries only a seat token. This maps the token to its match
    + seat so the client can drive the rest of the (match_id-based) API."""
    token = request.args.get('token', '')
    seat = db.seat_for_token(token)
    if seat is None:
        return jsonify({'error': 'invalid token'}), 403
    return jsonify({
        'match_id': seat['match_id'],
        'seat': seat['seat_no'],
        'controller': seat['controller'],
        'name': seat['display_name'],
    })


# Fog-of-war: fields a player keeps private from opponents during an active
# game. Positions, momentum, and delegate_count stay public — the desktop game
# exposes those ("View Opponents' Stances", standings) — but cash on hand and
# end-of-game stats are hidden until the game is over.
_PRIVATE_PLAYER_FIELDS = ('resources', 'history', 'stats')


def _game_over(doc):
    return doc['current_date'] > doc['config']['num_turns']


def _redact_state_for_seat(doc, viewer_seat):
    if _game_over(doc):
        return doc
    players = {}
    for sid, p in doc['players'].items():
        players[sid] = p if int(sid) == viewer_seat else {
            k: v for k, v in p.items() if k not in _PRIVATE_PLAYER_FIELDS}
    return {**doc, 'players': players}


def _redact_log_for_seat(doc, log, viewer_seat):
    """During play, a viewer sees only their own moves (plus the public results);
    opponents' past moves are revealed once the game ends."""
    if _game_over(doc):
        return log
    key = str(viewer_seat)
    return [{**e, 'moves': ({key: e['moves'][key]} if key in e['moves'] else {})} for e in log]


@app.route('/api/matches/<match_id>/state', methods=['GET'])
def get_state(match_id):
    seat, err = _auth(match_id)
    if err:
        return err
    match = db.get_match(match_id)
    if match is None:
        return jsonify({'error': 'no such match'}), 404
    return jsonify({
        'you': {'seat': seat['seat_no'], 'controller': seat['controller'],
                'name': seat['display_name']},
        'state': _redact_state_for_seat(match['doc'], seat['seat_no']),
        'status': _public_status(match),
    })


@app.route('/api/matches/<match_id>/positions', methods=['POST'])
def set_positions(match_id):
    """A human seat chooses its issue platform the first time it opens the seat
    link (issues mode only). Settable once, while it's still empty."""
    seat, err = _auth(match_id)
    if err:
        return err
    if seat['controller'] != 'human':
        return jsonify({'error': 'seat is not human-controlled'}), 400
    positions = (request.get_json(silent=True) or {}).get('positions')
    n = len(state_issues.ISSUES)
    if not isinstance(positions, list) or len(positions) != n or not all(p in (-1, 0, 1) for p in positions):
        return jsonify({'error': 'positions must be a list of {} values in -1/0/1'.format(n)}), 400
    with db.resolve_lock:
        match = db.get_match(match_id)
        if match is None:
            return jsonify({'error': 'no such match'}), 404
        pdata = match['doc']['players'].get(str(seat['seat_no']))
        if pdata is None:
            return jsonify({'error': 'no such seat'}), 404
        if pdata.get('positions'):
            return jsonify({'error': 'platform already set'}), 409
        pdata['positions'] = [int(p) for p in positions]
        db.save_match_state(match_id, match['doc'])
    return jsonify({'ok': True})


@app.route('/api/matches/<match_id>/moves', methods=['POST'])
def submit_move(match_id):
    seat, err = _auth(match_id)
    if err:
        return err
    if seat['controller'] != 'human':
        return jsonify({'error': 'seat is not human-controlled'}), 400

    match = db.get_match(match_id)
    if match is None:
        return jsonify({'error': 'no such match'}), 404
    if match['status'] != 'active':
        return jsonify({'error': 'match is not active'}), 409
    # In issues mode a player must pick their platform before playing.
    if match['doc']['config']['issues_mode']:
        pdata = match['doc']['players'].get(str(seat['seat_no']))
        if pdata is not None and not pdata.get('positions'):
            return jsonify({'error': 'choose your platform first'}), 409

    week = match['current_week']
    if seat['seat_no'] in db.submitted_seats(match_id, week):
        return jsonify({'error': 'already submitted this week'}), 409

    move = (request.get_json(silent=True) or {}).get('move', {})
    gs, _ = state_schema.match_from_dict(match['doc'])
    ok, verr = game_service.validate_move(gs, seat['seat_no'], move)
    if not ok:
        return jsonify({'error': 'invalid move: {}'.format(verr)}), 400

    db.record_submission(match_id, seat['seat_no'], week, move)
    resolved = _maybe_resolve(match_id)

    match = db.get_match(match_id)
    return jsonify({
        'result': 'resolved' if resolved else 'submitted',
        'status': _public_status(match),
    })


@app.route('/api/matches/<match_id>/moves', methods=['DELETE'])
def unsubmit_move(match_id):
    """Retract this seat's submitted move for the current week so the player can
    edit and resubmit. Only possible while the week is unresolved — once every
    human seat has submitted the week resolves (clearing submissions and
    advancing), after which there's nothing to unsubmit. The resolve_lock makes
    the check-and-delete atomic against a concurrent resolve."""
    seat, err = _auth(match_id)
    if err:
        return err
    if seat['controller'] != 'human':
        return jsonify({'error': 'seat is not human-controlled'}), 400
    with db.resolve_lock:
        match = db.get_match(match_id)
        if match is None:
            return jsonify({'error': 'no such match'}), 404
        if match['status'] != 'active':
            return jsonify({'error': 'match is not active'}), 409
        week = match['current_week']
        if seat['seat_no'] not in db.submitted_seats(match_id, week):
            return jsonify({'error': 'nothing to unsubmit (the week may have already resolved)'}), 409
        db.delete_submission(match_id, seat['seat_no'], week)
        match = db.get_match(match_id)
    return jsonify({'result': 'unsubmitted', 'status': _public_status(match)})


@app.route('/api/matches/<match_id>/advance', methods=['POST'])
def advance(match_id):
    """Step a ready match one week. Useful for AI-only matches (no human to
    trigger a resolve) or to force a resolve once all humans are in."""
    seat, err = _auth(match_id)
    if err:
        return err
    resolved = _maybe_resolve(match_id)
    match = db.get_match(match_id)
    return jsonify({'result': 'resolved' if resolved else 'waiting',
                    'status': _public_status(match)})


@app.route('/api/matches/<match_id>/log', methods=['GET'])
def game_log(match_id):
    """Per-week history: each resolved week's results + moves. During an active
    game a viewer sees only their own moves; opponents' are revealed at game end."""
    seat, err = _auth(match_id)
    if err:
        return err
    match = db.get_match(match_id)
    if match is None:
        return jsonify({'error': 'no such match'}), 404
    log = _redact_log_for_seat(match['doc'], db.get_log(match_id), seat['seat_no'])
    return jsonify({'log': log})


@app.route('/api/matches/<match_id>/status', methods=['GET'])
def status(match_id):
    seat, err = _auth(match_id)
    if err:
        return err
    match = db.get_match(match_id)
    if match is None:
        return jsonify({'error': 'no such match'}), 404
    out = _public_status(match)
    out['last_week_results'] = match['doc'].get('week_results', {})
    return jsonify(out)


# --- Serve the built React SPA (production) --------------------------------
# The API/blob routes above are more specific, so Werkzeug matches them first;
# everything else falls through here. A real file in the bundle is served as-is
# (JS/CSS/assets); any other path returns index.html so client-side routes like
# /play/<token> work on refresh/deep-link.
@app.route('/', defaults={'reqpath': ''})
@app.route('/<path:reqpath>')
def spa(reqpath):
    if reqpath:
        candidate = os.path.normpath(os.path.join(_WEB_DIST, reqpath))
        # Stay strictly inside the bundle dir (guards ../ traversal).
        if (candidate == _WEB_DIST or candidate.startswith(_WEB_DIST + os.sep)) and os.path.isfile(candidate):
            return send_from_directory(_WEB_DIST, reqpath)
    if os.path.isfile(os.path.join(_WEB_DIST, 'index.html')):
        return send_from_directory(_WEB_DIST, 'index.html')
    return ('Frontend not built. Run: cd web && npm run build', 404)


if __name__ == '__main__':
    host = os.environ.get('CAMPAIGN_HOST', '0.0.0.0')
    port = int(os.environ.get('CAMPAIGN_PORT', '8080'))
    print('Campaign server (blob + match API) on http://{}:{}'.format(host, port))
    app.run(host=host, port=port)
