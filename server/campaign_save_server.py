"""
Campaign Save Server - Flask API the game's RemoteSaveLoad client talks to.

Run on whichever computer should host LAN games:

    pip install flask
    CAMPAIGN_API_KEY=your-shared-secret python campaign_save_server.py

Then on every client (the same machine or another on the LAN), set
remote_config.json:

    {
      "server_url": "http://<server-LAN-IP>:8080",
      "api_key":    "your-shared-secret"
    }

Endpoints:

    GET    /campaign_saves          list saves (name, size, modified)
    GET    /campaign_saves/<name>   download a save
    POST   /campaign_saves/<name>   upload a save (raw .save bytes in body)
    DELETE /campaign_saves/<name>   delete a save

All endpoints require the X-API-Key header.

The same server can also coexist with the existing s1 save server on a
different port (default here is 8080; override with CAMPAIGN_PORT).
"""
import os
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

SAVE_DIR = os.environ.get(
    'CAMPAIGN_SAVE_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves'))
API_KEY = os.environ.get('CAMPAIGN_API_KEY', 'changeme')
PORT = int(os.environ.get('CAMPAIGN_PORT', '8080'))
HOST = os.environ.get('CAMPAIGN_HOST', '0.0.0.0')
SAVE_EXT = '.save'

os.makedirs(SAVE_DIR, exist_ok=True)


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key', '')
        if key != API_KEY:
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated


def _safe(name):
    """Reject path traversal attempts; force the .save extension."""
    name = os.path.basename(name)
    if not name:
        return None
    if not name.endswith(SAVE_EXT):
        name += SAVE_EXT
    return name


@app.route('/campaign_saves', methods=['GET'])
@require_api_key
def list_saves():
    out = []
    for fn in os.listdir(SAVE_DIR):
        if fn.endswith(SAVE_EXT):
            stat = os.stat(os.path.join(SAVE_DIR, fn))
            out.append({
                'name': fn,
                'size': stat.st_size,
                'modified': stat.st_mtime,
            })
    out.sort(key=lambda s: s['modified'], reverse=True)
    return jsonify(out)


@app.route('/campaign_saves/<name>', methods=['POST'])
@require_api_key
def upload_save(name):
    safe = _safe(name)
    if safe is None:
        return jsonify({'error': 'Invalid filename'}), 400
    data = request.get_data()
    if not data:
        return jsonify({'error': 'No data received'}), 400
    with open(os.path.join(SAVE_DIR, safe), 'wb') as f:
        f.write(data)
    return jsonify({'name': safe, 'size': len(data)}), 201


@app.route('/campaign_saves/<name>', methods=['GET'])
@require_api_key
def download_save(name):
    safe = _safe(name)
    if safe is None:
        return jsonify({'error': 'Invalid filename'}), 400
    if not os.path.isfile(os.path.join(SAVE_DIR, safe)):
        return jsonify({'error': 'Save not found'}), 404
    return send_from_directory(SAVE_DIR, safe, as_attachment=True)


@app.route('/campaign_saves/<name>', methods=['DELETE'])
@require_api_key
def delete_save(name):
    safe = _safe(name)
    if safe is None:
        return jsonify({'error': 'Invalid filename'}), 400
    path = os.path.join(SAVE_DIR, safe)
    if not os.path.isfile(path):
        return jsonify({'error': 'Save not found'}), 404
    os.remove(path)
    return jsonify({'deleted': safe})


@app.route('/health', methods=['GET'])
def health():
    """Open endpoint so clients can probe connectivity without an API key."""
    return jsonify({'status': 'ok', 'save_dir': SAVE_DIR, 'port': PORT})


if __name__ == '__main__':
    print('Campaign Save Server')
    print('  Listening on  http://{}:{}'.format(HOST, PORT))
    print('  Save dir       {}'.format(SAVE_DIR))
    print('  API key        {}'.format('(set via CAMPAIGN_API_KEY)' if API_KEY == 'changeme' else '(custom)'))
    if API_KEY == 'changeme':
        print('  WARNING: using default API key. Set CAMPAIGN_API_KEY before exposing this on a real network.')
    app.run(host=HOST, port=PORT)
