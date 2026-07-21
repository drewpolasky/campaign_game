"""SQLite persistence for server-hosted matches.

Single-file storage, no external service. Three tables:

  matches(id, state_json, current_week, status, num_players, created)
  seats(match_id, seat_no, controller, token, display_name, submitted_week)
  submissions(match_id, seat_no, week, move_json)

The match's authoritative state lives as a JSON document in matches.state_json
(see state_schema). Submissions hold each human seat's pending move for the
current week until the week resolves, then are cleared.
"""
import json
import os
import sqlite3
import threading
import time

_DB_PATH = os.environ.get(
    'CAMPAIGN_DB',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'game.db'))

# Serializes the read-modify-write resolve critical section (see api layer).
resolve_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(_DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL gives better concurrency, but some filesystems (e.g. the 9p mount
    # used when a Windows process opens a \\wsl.localhost path) don't support
    # it — fall back to the default journal there instead of crashing.
    try:
        conn.execute('PRAGMA journal_mode=WAL')
    except sqlite3.OperationalError:
        pass
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS matches (
                id           TEXT PRIMARY KEY,
                state_json   TEXT NOT NULL,
                current_week INTEGER NOT NULL,
                status       TEXT NOT NULL,
                num_players  INTEGER NOT NULL,
                created      REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS seats (
                match_id       TEXT NOT NULL,
                seat_no        INTEGER NOT NULL,
                controller     TEXT NOT NULL,
                token          TEXT,
                display_name   TEXT,
                submitted_week INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (match_id, seat_no)
            );
            CREATE INDEX IF NOT EXISTS idx_seats_token ON seats(token);
            CREATE TABLE IF NOT EXISTS submissions (
                match_id  TEXT NOT NULL,
                seat_no   INTEGER NOT NULL,
                week      INTEGER NOT NULL,
                move_json TEXT NOT NULL,
                PRIMARY KEY (match_id, seat_no, week)
            );
            CREATE TABLE IF NOT EXISTS game_log (
                match_id     TEXT NOT NULL,
                week         INTEGER NOT NULL,
                results_json TEXT NOT NULL,   -- week_results for the week that resolved
                moves_json   TEXT NOT NULL,   -- {seat: move} every seat played that week
                resolved_at  REAL NOT NULL,
                PRIMARY KEY (match_id, week)
            );
            """)


def create_match(doc, seat_tokens, spectator_token=None):
    """Insert a new match: its state doc, one seat row per configured seat, and
    a read-only spectator row (seat_no 0). ``seat_tokens`` is {seat_no: token}
    for human seats."""
    match_id = doc['match_id']
    seats = doc['config']['seats']
    with _connect() as conn:
        conn.execute(
            'INSERT INTO matches (id, state_json, current_week, status, num_players, created)'
            ' VALUES (?, ?, ?, ?, ?, ?)',
            (match_id, json.dumps(doc), doc['current_date'], 'active',
             doc['config']['num_players'], time.time()))
        for s in seats:
            conn.execute(
                'INSERT INTO seats (match_id, seat_no, controller, token, display_name, submitted_week)'
                ' VALUES (?, ?, ?, ?, ?, 0)',
                (match_id, s['seat'], s['controller'],
                 seat_tokens.get(s['seat']), s['name']))
        if spectator_token:
            conn.execute(
                'INSERT INTO seats (match_id, seat_no, controller, token, display_name, submitted_week)'
                ' VALUES (?, 0, ?, ?, ?, 0)',
                (match_id, 'spectator', spectator_token, 'Spectator'))
    return match_id


def get_seats(match_id):
    with _connect() as conn:
        rows = conn.execute(
            'SELECT seat_no, controller, display_name, submitted_week FROM seats'
            ' WHERE match_id = ? AND seat_no > 0 ORDER BY seat_no', (match_id,)).fetchall()
    return [dict(r) for r in rows]


def get_match(match_id):
    with _connect() as conn:
        row = conn.execute('SELECT * FROM matches WHERE id = ?', (match_id,)).fetchone()
    if row is None:
        return None
    return {
        'id': row['id'],
        'doc': json.loads(row['state_json']),
        'current_week': row['current_week'],
        'status': row['status'],
        'num_players': row['num_players'],
    }


def save_match_state(match_id, doc, status=None):
    with _connect() as conn:
        if status is None:
            conn.execute(
                'UPDATE matches SET state_json = ?, current_week = ? WHERE id = ?',
                (json.dumps(doc), doc['current_date'], match_id))
        else:
            conn.execute(
                'UPDATE matches SET state_json = ?, current_week = ?, status = ? WHERE id = ?',
                (json.dumps(doc), doc['current_date'], status, match_id))


def seat_for_token(token):
    """Return {'match_id', 'seat_no', 'controller', 'display_name'} or None."""
    if not token:
        return None
    with _connect() as conn:
        row = conn.execute(
            'SELECT match_id, seat_no, controller, display_name FROM seats WHERE token = ?',
            (token,)).fetchone()
    if row is None:
        return None
    return {'match_id': row['match_id'], 'seat_no': row['seat_no'],
            'controller': row['controller'], 'display_name': row['display_name']}


def human_seats(match_id):
    return [s['seat_no'] for s in get_seats(match_id) if s['controller'] == 'human']


def record_submission(match_id, seat_no, week, move):
    with _connect() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO submissions (match_id, seat_no, week, move_json)'
            ' VALUES (?, ?, ?, ?)',
            (match_id, seat_no, week, json.dumps(move)))
        conn.execute(
            'UPDATE seats SET submitted_week = ? WHERE match_id = ? AND seat_no = ?',
            (week, match_id, seat_no))


def get_submissions(match_id, week):
    """Return {seat_no: move} for the given week."""
    with _connect() as conn:
        rows = conn.execute(
            'SELECT seat_no, move_json FROM submissions WHERE match_id = ? AND week = ?',
            (match_id, week)).fetchall()
    return {r['seat_no']: json.loads(r['move_json']) for r in rows}


def submitted_seats(match_id, week):
    with _connect() as conn:
        rows = conn.execute(
            'SELECT seat_no FROM submissions WHERE match_id = ? AND week = ?',
            (match_id, week)).fetchall()
    return {r['seat_no'] for r in rows}


def clear_submissions(match_id, week):
    with _connect() as conn:
        conn.execute('DELETE FROM submissions WHERE match_id = ? AND week = ?',
                     (match_id, week))


def log_week(match_id, week, results, moves):
    """Record a resolved week's results and every seat's moves for the history."""
    with _connect() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO game_log (match_id, week, results_json, moves_json, resolved_at)'
            ' VALUES (?, ?, ?, ?, ?)',
            (match_id, week, json.dumps(results), json.dumps(moves), time.time()))


def get_log(match_id):
    with _connect() as conn:
        rows = conn.execute(
            'SELECT week, results_json, moves_json, resolved_at FROM game_log'
            ' WHERE match_id = ? ORDER BY week', (match_id,)).fetchall()
    return [{'week': r['week'], 'results': json.loads(r['results_json']),
             'moves': json.loads(r['moves_json']), 'resolved_at': r['resolved_at']}
            for r in rows]


def prune_finished(max_age_days=14):
    """Delete finished matches (and their seats/submissions) created more than
    ``max_age_days`` ago. Called at startup; keeps the DB from growing forever.
    Returns the number of matches removed."""
    cutoff = time.time() - max_age_days * 86400
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id FROM matches WHERE status = 'finished' AND created < ?",
            (cutoff,)).fetchall()
        ids = [r['id'] for r in rows]
        for mid in ids:
            conn.execute('DELETE FROM submissions WHERE match_id = ?', (mid,))
            conn.execute('DELETE FROM game_log WHERE match_id = ?', (mid,))
            conn.execute('DELETE FROM seats WHERE match_id = ?', (mid,))
            conn.execute('DELETE FROM matches WHERE id = ?', (mid,))
    return len(ids)
