# Campaign LAN save server

A tiny Flask app that the game's `RemoteSaveLoad` client talks to. Use it to
host networked games on a local network without going through the public
`s1.drewpolasky.com` server.

## One-time setup on the host

Pick whichever computer should be the server (it can be one of the players'
machines or a third box).

```sh
cd server
pip install -r requirements.txt
```

Pick a shared API key — anything random and not "changeme":

```sh
export CAMPAIGN_API_KEY="some-shared-secret"   # macOS / Linux / WSL
# or on Windows PowerShell:
$Env:CAMPAIGN_API_KEY = "some-shared-secret"
```

Run the server:

```sh
python campaign_save_server.py
```

You should see:

```
Campaign Save Server
  Listening on  http://0.0.0.0:8080
  Save dir       <repo>/server/saves
  API key        (custom)
```

It serves the same endpoints the game already uses
(`GET/POST/DELETE /campaign_saves[/<name>]`), so no client changes are
needed beyond pointing at it.

### Optional environment overrides

| Variable | Default | What it does |
|---|---|---|
| `CAMPAIGN_API_KEY` | `changeme` | Shared secret. Required header on every request. |
| `CAMPAIGN_PORT` | `8080` | TCP port to bind. |
| `CAMPAIGN_HOST` | `0.0.0.0` | Bind address. Set to `127.0.0.1` to limit to local. |
| `CAMPAIGN_SAVE_DIR` | `./saves` | Where save files live on disk. |

## Find the host's LAN IP

The other computer needs to reach the server, so you need the host's IP
on your network (not 127.0.0.1).

- **Linux / WSL / macOS:** `ip addr` (look for `inet 192.168.x.x`) or
  `ifconfig`.
- **Windows:** `ipconfig` (look for "IPv4 Address" under your active
  adapter).

If your firewall asks whether to allow incoming connections on port 8080,
say yes (private network only is fine).

## Configure each client

Edit `remote_config.json` in the project root on every machine that will
play (host included, since the host is also a client):

```json
{
  "server_url": "http://192.168.1.42:8080",
  "api_key":    "some-shared-secret"
}
```

Replace `192.168.1.42` with whatever the host's LAN IP is, and use the
same `api_key` you set on the server.

## Smoke test

From any client, hit the open health endpoint:

```sh
curl http://192.168.1.42:8080/health
```

You should get something like:

```json
{"port": 8080, "save_dir": ".../saves", "status": "ok"}
```

If that times out, the server isn't reachable — check the host's firewall
or that the server process is actually running.

Then verify the API key works (the listing endpoint requires it):

```sh
curl -H "X-API-Key: some-shared-secret" http://192.168.1.42:8080/campaign_saves
```

You should get `[]` on a fresh server.

## Play a networked game

1. **Host** clicks **New Networked Game** in the main menu, runs through
   normal new-game setup configuring all the players (this includes
   picking AI/human and stances for everyone). On the seat-picker screen,
   they check the boxes for whichever seats they'll play.
2. **Host** notes the 6-character match ID shown on the seat-picker and
   shares it with the other player.
3. **Joiner** clicks **Join Networked Game**, types in the match ID, and
   on the seat-picker checks off whichever seats are theirs (different
   from the host's).
4. Whichever side has the active seat plays first; the other waits on the
   *Waiting for Opponent* screen, which polls the server every 3 seconds
   for an updated state.

## Notes

- **`/health` is unauthenticated** — anyone on the LAN can probe whether
  the server is up, but they can't read or write saves without the key.
- **Multiple concurrent games** are fine; each match has a unique ID and
  lives at `lan_<id>.save` in the saves directory.
- **Stale saves** accumulate forever right now. To clean up, delete the
  files in `server/saves/` (or hit `DELETE /campaign_saves/<name>` with
  the API key).
- **Flask's dev server** is fine for small group play. For anything more
  serious, throw it behind `gunicorn` / `waitress` and a reverse proxy.
