"""Unsubmit returns the retracted move so the player keeps their plan.

Run:  python -m pytest server/tests/test_unsubmit.py
"""
import os
import sys
import tempfile

os.environ['CAMPAIGN_DB'] = os.path.join(tempfile.mkdtemp(), 'test_unsubmit.db')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server.app import app  # noqa: E402

CONFIG = {'num_turns': 8, 'issues_mode': False, 'seed': 11,
          'seats': [{'name': 'A', 'controller': 'human'},
                    {'name': 'B', 'controller': 'human'}]}


def test_unsubmit_returns_move_and_blocks_after_resolve():
    c = app.test_client()
    d = c.post('/api/matches', json={'config': CONFIG}).get_json()
    mid, t1, t2 = d['match_id'], d['seat_tokens']['1'], d['seat_tokens']['2']

    state = c.get('/api/matches/{}/state?token={}'.format(mid, t1)).get_json()['state']
    st_name = state['config']['calendar'][0][0]
    dname = state['states'][st_name]['districts'][0]['name']
    move = {'campaigning': {st_name: {dname: 12}},
            'ads': {st_name: {dname: 3000}},
            'orgs': {st_name: 1}}

    r = c.post('/api/matches/{}/moves?token={}'.format(mid, t1), json={'move': move})
    assert r.get_json()['result'] == 'submitted'

    # Unsubmit hands back exactly what was submitted.
    r = c.delete('/api/matches/{}/moves?token={}'.format(mid, t1))
    assert r.status_code == 200
    assert r.get_json()['move'] == move
    assert 1 in r.get_json()['status']['waiting_on']

    # Nothing left to retract a second time.
    assert c.delete('/api/matches/{}/moves?token={}'.format(mid, t1)).status_code == 409

    # Edit and resubmit, then both players in -> resolves; unsubmit now refused.
    move['campaigning'][st_name][dname] = 20
    c.post('/api/matches/{}/moves?token={}'.format(mid, t1), json={'move': move})
    r = c.post('/api/matches/{}/moves?token={}'.format(mid, t2), json={'move': {}})
    assert r.get_json()['result'] == 'resolved'
    assert c.delete('/api/matches/{}/moves?token={}'.format(mid, t1)).status_code == 409
