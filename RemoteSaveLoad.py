"""
Client module for remote save/load operations against the Campaign save server.
Uses only stdlib (urllib) so no extra dependencies are needed on the game client.
"""
import json
import os
import urllib.request
import urllib.error

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'remote_config.json')

DEFAULT_CONFIG = {
    'server_url': 'http://87.99.156.199:8080',
    'api_key': '',
}

SAVE_EXT = '.save'


def load_config():
    """Load remote server config from remote_config.json."""
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return dict(DEFAULT_CONFIG)


def save_config(config):
    """Persist config back to remote_config.json."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def _make_request(url, api_key, method='GET', data=None):
    req = urllib.request.Request(url, method=method)
    req.add_header('X-API-Key', api_key)
    if data is not None:
        req.add_header('Content-Type', 'application/octet-stream')
        req.data = data
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read(), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        raise RuntimeError("Server error {}: {}".format(e.code, body))
    except urllib.error.URLError as e:
        raise RuntimeError("Connection failed: {}".format(e.reason))


def list_remote_saves(server_url, api_key):
    url = "{}/campaign_saves".format(server_url.rstrip('/'))
    data, _ = _make_request(url, api_key)
    return json.loads(data)


def upload_save(server_url, api_key, save_name, file_data):
    if not save_name.endswith(SAVE_EXT):
        save_name += SAVE_EXT
    url = "{}/campaign_saves/{}".format(server_url.rstrip('/'), urllib.request.quote(save_name))
    data, _ = _make_request(url, api_key, method='POST', data=file_data)
    return json.loads(data)


def download_save(server_url, api_key, save_name):
    if not save_name.endswith(SAVE_EXT):
        save_name += SAVE_EXT
    url = "{}/campaign_saves/{}".format(server_url.rstrip('/'), urllib.request.quote(save_name))
    data, _ = _make_request(url, api_key)
    return data


def delete_remote_save(server_url, api_key, save_name):
    if not save_name.endswith(SAVE_EXT):
        save_name += SAVE_EXT
    url = "{}/campaign_saves/{}".format(server_url.rstrip('/'), urllib.request.quote(save_name))
    data, _ = _make_request(url, api_key, method='DELETE')
    return json.loads(data)


def sync_saves(server_url, api_key, save_dir):
    """
    Sync the local saves directory with the remote server.
    - Files only on remote -> downloaded locally
    - Files only locally -> uploaded to remote
    - Files in both -> whichever has a newer mtime wins
    Returns a dict with counts: {'uploaded': N, 'downloaded': N, 'up_to_date': N}
    """
    os.makedirs(save_dir, exist_ok=True)

    remote_saves = list_remote_saves(server_url, api_key)
    remote_by_name = {s['name']: s for s in remote_saves}

    local_files = {}
    for f in os.listdir(save_dir):
        if f.endswith(SAVE_EXT):
            filepath = os.path.join(save_dir, f)
            local_files[f] = os.path.getmtime(filepath)

    all_names = set(local_files.keys()) | set(remote_by_name.keys())

    uploaded = 0
    downloaded = 0
    up_to_date = 0

    for name in all_names:
        local_exists = name in local_files
        remote_exists = name in remote_by_name
        local_path = os.path.join(save_dir, name)

        if local_exists and not remote_exists:
            with open(local_path, 'rb') as f:
                upload_save(server_url, api_key, name, f.read())
            uploaded += 1

        elif remote_exists and not local_exists:
            data = download_save(server_url, api_key, name)
            with open(local_path, 'wb') as f:
                f.write(data)
            os.utime(local_path, (remote_by_name[name]['modified'], remote_by_name[name]['modified']))
            downloaded += 1

        else:
            local_mtime = local_files[name]
            remote_mtime = remote_by_name[name]['modified']

            if abs(local_mtime - remote_mtime) < 2:
                up_to_date += 1
            elif local_mtime > remote_mtime:
                with open(local_path, 'rb') as f:
                    upload_save(server_url, api_key, name, f.read())
                uploaded += 1
            else:
                data = download_save(server_url, api_key, name)
                with open(local_path, 'wb') as f:
                    f.write(data)
                os.utime(local_path, (remote_mtime, remote_mtime))
                downloaded += 1

    return {'uploaded': uploaded, 'downloaded': downloaded, 'up_to_date': up_to_date}
