"""Admin endpoint tests: auth gating, match listing, unredacted logs, and
killing a match.

Run:  python -m pytest server/tests/test_admin.py
"""
import os
import sqlite3
import sys
import tempfile

# Point the DB at a throwaway file BEFORE importing the app.
_TMP_DB = os.path.join(tempfile.mkdtemp(), 'test_admin.db')
os.environ['CAMPAIGN_DB'] = _TMP_DB

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server import db  # noqa: E402
from server.app import app  # noqa: E402

ADMIN_KEY = 'test-admin-secret'

CONFIG = {
    'num_turns': 8,
    'issues_mode': False,
    'seats': [
        {'name': 'Alice', 'controller': 'human'},
        {'name': 'AI-1', 'controller': 'ai', 'ai_strategy': 'Default'},
    ],
    'seed': 99,
}


def _client_and_match():
    client = app.test_client()
    r = client.post('/api/matches', json={'config': CONFIG})
    assert r.status_code == 201, r.get_data(as_text=True)
    created = r.get_json()
    return client, created['match_id'], created['seat_tokens']['1']


def test_admin_disabled_without_env(monkeypatch):
    monkeypatch.delenv('CAMPAIGN_ADMIN_KEY', raising=False)
    client = app.test_client()
    r = client.get('/api/admin/matches', headers={'X-Admin-Key': 'anything'})
    assert r.status_code == 403
    assert 'not enabled' in r.get_json()['error']


def test_admin_rejects_bad_key(monkeypatch):
    monkeypatch.setenv('CAMPAIGN_ADMIN_KEY', ADMIN_KEY)
    client = app.test_client()
    assert client.get('/api/admin/matches').status_code == 403
    assert client.get('/api/admin/matches',
                      headers={'X-Admin-Key': 'wrong'}).status_code == 403


def test_seat_tokens_never_leak_to_players():
    """Magic links are admin-only: the player-facing endpoints must not echo
    any seat token, least of all another seat's."""
    client = app.test_client()
    r = client.post('/api/matches', json={'config': {
        'num_turns': 8, 'issues_mode': False, 'seed': 1,
        'seats': [{'name': 'A', 'controller': 'human'},
                  {'name': 'B', 'controller': 'human'}],
    }})
    created = r.get_json()
    mid = created['match_id']
    t1, t2 = created['seat_tokens']['1'], created['seat_tokens']['2']
    for path in ('state', 'status', 'log'):
        body = client.get('/api/matches/{}/{}?token={}'.format(mid, path, t1)).get_data(as_text=True)
        assert t2 not in body, "{} leaked the other seat's token".format(path)
        assert t1 not in body, '{} echoed a seat token'.format(path)


def test_admin_list_log_and_kill(monkeypatch):
    monkeypatch.setenv('CAMPAIGN_ADMIN_KEY', ADMIN_KEY)
    hdrs = {'X-Admin-Key': ADMIN_KEY}
    client, match_id, token = _client_and_match()

    # Listed, active, with seats.
    r = client.get('/api/admin/matches', headers=hdrs)
    assert r.status_code == 200
    matches = {m['id']: m for m in r.get_json()['matches']}
    assert match_id in matches
    m = matches[match_id]
    assert m['status'] == 'active'
    assert {s['name'] for s in m['seats']} == {'Alice', 'AI-1'}
    assert m['waiting_on'] == [1]

    # Magic links are recoverable here: the human seat's link actually works,
    # the AI seat has none, and the spectator link is present.
    by_seat = {s['seat']: s for s in m['seats']}
    assert by_seat[1]['play_path'] == '/play/{}'.format(token)
    assert by_seat[2]['play_path'] is None          # AI seat has no token
    assert 'token' not in by_seat[1]                # raw token isn't echoed twice
    assert m['spectator_path'] and m['spectator_path'].startswith('/play/')
    spec_token = m['spectator_path'].rsplit('/', 1)[1]
    r = client.get('/api/matches/{}/state?token={}'.format(match_id, spec_token))
    assert r.status_code == 200 and r.get_json()['you']['controller'] == 'spectator'

    # Resolve one week (single human submitting triggers it), then the admin
    # log shows BOTH seats' moves, unredacted.
    r = client.post('/api/matches/{}/moves?token={}'.format(match_id, token),
                    json={'move': {}})
    assert r.get_json()['result'] == 'resolved'
    r = client.get('/api/admin/matches/{}/log'.format(match_id), headers=hdrs)
    assert r.status_code == 200
    body = r.get_json()
    assert body['current_week'] == 2
    assert len(body['log']) == 1
    week1 = body['log'][0]
    assert set(week1['moves'].keys()) == {'1', '2'}   # human AND the AI seat
    assert '1' in body['standings'] and body['standings']['1']['name'] == 'Alice'

    # Kill: match vanishes; seat token stops resolving; double-kill 404s.
    r = client.delete('/api/admin/matches/{}'.format(match_id), headers=hdrs)
    assert r.status_code == 200 and r.get_json()['killed'] == match_id
    r = client.get('/api/admin/matches', headers=hdrs)
    assert match_id not in {m['id'] for m in r.get_json()['matches']}
    assert client.get('/api/matches/{}/state?token={}'.format(match_id, token)).status_code == 403
    assert client.delete('/api/admin/matches/{}'.format(match_id), headers=hdrs).status_code == 404


def test_log_records_support_gained(monkeypatch):
    """The admin log has every seat's support gains by state and source; a
    player's own log has only theirs while the game is on."""
    monkeypatch.setenv('CAMPAIGN_ADMIN_KEY', ADMIN_KEY)
    client, match_id, token = _client_and_match()
    state = client.get('/api/matches/{}/state?token={}'.format(match_id, token)).get_json()['state']
    target = [s for s, w in state['config']['calendar'] if w >= state['current_date']][0]
    dname = state['states'][target]['districts'][0]['name']
    move = {'campaigning': {target: {dname: 10}}, 'ads': {target: {dname: 5000}},
            'orgs': {target: 1}}
    r = client.post('/api/matches/{}/moves?token={}'.format(match_id, token), json={'move': move})
    assert r.status_code == 200 and r.get_json()['result'] == 'resolved', r.get_data(as_text=True)

    week1 = client.get('/api/admin/matches/{}/log'.format(match_id),
                       headers={'X-Admin-Key': ADMIN_KEY}).get_json()['log'][0]
    assert set(week1['support']) == {'1', '2'}       # the human AND the AI seat
    mine = week1['support']['1'][target]
    assert mine['campaign'] > 0 and mine['ads'] > 0 and mine['orgs'] > 0

    own = client.get('/api/matches/{}/log?token={}'.format(match_id, token)).get_json()['log'][0]
    assert set(own['support']) == {'1'}
    assert own['support']['1'] == week1['support']['1']


def test_old_database_gains_support_column(tmp_path, monkeypatch):
    """A game_log table from before support was recorded gets the column on
    startup; its earlier weeks read back with no breakdown."""
    path = str(tmp_path / 'old.db')
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE game_log (match_id TEXT NOT NULL, week INTEGER NOT NULL,'
                 ' results_json TEXT NOT NULL, moves_json TEXT NOT NULL,'
                 ' resolved_at REAL NOT NULL, PRIMARY KEY (match_id, week))')
    conn.execute("INSERT INTO game_log VALUES ('OLD', 1, '{}', '{}', 0)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, '_DB_PATH', path)

    db.init_db()
    db.init_db()      # a second start finds the column already there
    db.log_week('OLD', 2, {}, {}, {1: {'Iowa': {'campaign': 1.5, 'ads': 0.0, 'orgs': 0.25}}})
    log = db.get_log('OLD')
    assert log[0]['support'] == {}
    assert log[1]['support'] == {'1': {'Iowa': {'campaign': 1.5, 'ads': 0.0, 'orgs': 0.25}}}
