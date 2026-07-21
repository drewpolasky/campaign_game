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
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from flask import request, jsonify  # noqa: E402

from flask import Response  # noqa: E402

from server.campaign_save_server import app  # noqa: E402  (reuse blob app + endpoints)
from server import db, game_service, state_schema  # noqa: E402

db.init_db()


# --- CORS (dev: the Vite dev server is a different origin) -----------------
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
    """Deterministic, reproducible rng per (match, week)."""
    seed = int.from_bytes(
        hashlib.sha256('{}:{}'.format(match_id, week).encode()).digest()[:8], 'big')
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
        week_results, _moves = game_service.resolve_turn(
            gs, human_moves, _resolve_rng(match_id, week))
        status = 'finished' if game_service.is_game_over(gs) else 'active'
        new_doc = state_schema.match_to_dict(
            gs, match_id=match_id, week_results=week_results, whose_turn=None)
        db.save_match_state(match_id, new_doc, status)
        db.clear_submissions(match_id, week)
        return True


# --- endpoints -------------------------------------------------------------

@app.route('/api/matches', methods=['POST'])
def create_match():
    body = request.get_json(silent=True) or {}
    config = body.get('config')
    if not config or not config.get('seats'):
        return jsonify({'error': 'config with seats is required'}), 400
    try:
        doc, seat_tokens = game_service.create_match(config)
    except (ValueError, KeyError) as e:
        return jsonify({'error': str(e)}), 400
    db.create_match(doc, seat_tokens)
    return jsonify({
        'match_id': doc['match_id'],
        'seats': doc['config']['seats'],
        # Magic links are relative; the client composes the full URL.
        'seat_links': {str(seat): '/play/{}'.format(tok)
                       for seat, tok in seat_tokens.items()},
        'seat_tokens': {str(seat): tok for seat, tok in seat_tokens.items()},
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
        'state': match['doc'],
        'status': _public_status(match),
    })


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


if __name__ == '__main__':
    host = os.environ.get('CAMPAIGN_HOST', '0.0.0.0')
    port = int(os.environ.get('CAMPAIGN_PORT', '8080'))
    print('Campaign server (blob + match API) on http://{}:{}'.format(host, port))
    app.run(host=host, port=port)
