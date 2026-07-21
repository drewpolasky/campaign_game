"""HTTP-level test of the match API via Flask's test client (no network, temp
DB). Creates a match, plays it to completion through the endpoints, and checks
auth + validation error paths.

Run:  python3 server/tests/test_api.py
"""
import os
import sys
import tempfile

# Point the DB at a throwaway file BEFORE importing the app (db reads the env
# var at import time).
_TMP_DB = os.path.join(tempfile.mkdtemp(), 'test_game.db')
os.environ['CAMPAIGN_DB'] = _TMP_DB

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server.app import app  # noqa: E402

CONFIG = {
    'num_turns': 8,
    'issues_mode': False,
    'seats': [
        {'name': 'Alice', 'controller': 'human'},
        {'name': 'AI-1', 'controller': 'ai', 'ai_strategy': 'Default'},
        {'name': 'AI-2', 'controller': 'ai', 'ai_strategy': 'BigState'},
    ],
    'seed': 555,
}


def test_api_full_playthrough():
    client = app.test_client()

    # Create.
    r = client.post('/api/matches', json={'config': CONFIG})
    assert r.status_code == 201, r.get_data(as_text=True)
    created = r.get_json()
    match_id = created['match_id']
    tokens = created['seat_tokens']
    assert set(tokens.keys()) == {'1'}, 'only the human seat gets a token'
    token = tokens['1']

    # Bad token rejected.
    assert client.get('/api/matches/{}/state?token=bogus'.format(match_id)).status_code == 403

    # State fetch works.
    r = client.get('/api/matches/{}/state?token={}'.format(match_id, token))
    assert r.status_code == 200
    state = r.get_json()['state']
    assert state['current_date'] == 1
    assert state['config']['num_players'] == 3

    # Invalid move rejected (over budget).
    first_state = state['config']['calendar'][0][0]
    dname = state['states'][first_state]['districts'][0]['name']
    r = client.post('/api/matches/{}/moves?token={}'.format(match_id, token),
                    json={'move': {'campaigning': {first_state: {dname: 999}}}})
    assert r.status_code == 400 and 'invalid move' in r.get_json()['error']

    # Play to completion: the single human submits each week; submitting the
    # only human triggers the resolve (AI seats auto-filled server-side).
    weeks = 0
    while True:
        r = client.get('/api/matches/{}/status?token={}'.format(match_id, token))
        st = r.get_json()
        if st['game_over']:
            break
        week = st['current_week']
        # Fetch current state to pick a legal district for this week.
        state = client.get('/api/matches/{}/state?token={}'.format(match_id, token)).get_json()['state']
        upcoming = [s for s, w in state['config']['calendar'] if w >= week]
        target = upcoming[0] if upcoming else state['config']['calendar'][0][0]
        dname = state['states'][target]['districts'][0]['name']
        move = {'campaigning': {target: {dname: 6}}}
        if state['players']['1']['resources'][1] >= 10000:
            move['orgs'] = {target: 1}
        r = client.post('/api/matches/{}/moves?token={}'.format(match_id, token),
                        json={'move': move})
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()['result'] == 'resolved'  # 1 human -> resolves immediately
        weeks += 1
        assert weeks <= CONFIG['num_turns'] + 1

    # Final state: game finished with delegates awarded.
    final = client.get('/api/matches/{}/state?token={}'.format(match_id, token)).get_json()
    assert final['status']['status'] == 'finished'
    total = sum(p['delegate_count'] for p in final['state']['players'].values())
    assert total > 0


if __name__ == '__main__':
    test_api_full_playthrough()
    print('OK: match API creates, validates, plays a full game, and finishes.')
