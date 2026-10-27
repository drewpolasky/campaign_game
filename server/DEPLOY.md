# Deploying the browser game

The server serves **both** the JSON match API and the built React app from one
origin, so in production there's no CORS and magic links resolve against the
same host. Put it behind your existing nginx/TLS.

## 0. Packages, a service user, and the code (fresh Ubuntu box)

As root (or with sudo):

```sh
apt update
apt install -y git python3 python3-venv nginx certbot python3-certbot-nginx
# Node 22 for the frontend build (Ubuntu's own nodejs package is too old)
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs
node --version             # v22.22 or later
```

Node is only needed to build the frontend. If you'd rather not install it on
the server, build on another machine and copy `web/dist/` over (step 1).

Run the game as its own unprivileged user, which owns the checkout. The
server writes inside it (`server/game.db` plus its `-wal`/`-shm` files, and
`server/saves/`), so don't clone as root or run the smoke test as root:

```sh
adduser --disabled-password --gecos '' campaign
sudo -iu campaign git clone https://github.com/drewpolasky/campaign_game.git
sudo -iu campaign          # the rest of steps 1-3 run as this user, in ~/campaign_game
```

Already have a checkout under another user? Use that user and path instead
of `campaign` and `/home/campaign/campaign_game` below.

## 1. Build the frontend

Needs Node 22.22+ (react-router 8 requires it; only to build, the server
itself is pure Python).

```sh
cd ~/campaign_game/web
npm ci
npm run build      # -> web/dist/  (static bundle the server serves)
```

Rebuild this whenever the frontend changes. `web/dist/` is gitignored, so it's
produced on the deploy host (or built elsewhere and copied over).

## 2. Install the server

```sh
cd ~/campaign_game         # repo root
python3 -m venv .venv
. .venv/bin/activate
pip install -r server/requirements.txt   # flask, gunicorn, numpy
```

All three are required. The trained **Neural** AI runs with numpy from
`runs/v20_mixed_lengths/policy.npz` (committed with the model); PyTorch is not
needed on the server. If that file is missing or was exported for a different
issue set, the server still runs and just leaves Neural out of the lobby.

## 3. Run it (gunicorn)

From the **repo root** (so `server.app` and the sibling modules import):

```sh
gunicorn -w 1 --threads 8 -b 127.0.0.1:8080 server.app:app
```

> **Use a single worker (`-w 1`) with threads.** Week resolution is guarded by
> an in-process lock, and match state is a single SQLite file. One worker with
> threads is plenty for small group play and keeps that lock effective. If you
> ever need multiple worker processes, move the resolve guard to a DB-level
> lock first (a `BEGIN IMMEDIATE` transaction around read-modify-write).

Environment variables:

| Var | Default | Purpose |
|---|---|---|
| `CAMPAIGN_DB` | `server/game.db` | SQLite match database (put it on a persistent, local disk — WAL needs a real filesystem). |
| `CAMPAIGN_ENABLE_BLOB` | (unset → off) | Legacy `/campaign_saves` blob endpoints are disabled unless this is set. The web game doesn't need them; leave off. |
| `CAMPAIGN_API_KEY` | `changeme` | Shared secret for the legacy `/campaign_saves` blob endpoints (only when `CAMPAIGN_ENABLE_BLOB` is on). The `/api` match endpoints use per-seat tokens instead. |
| `CAMPAIGN_CREATE_KEY` | (unset) | If set, a shared passphrase is required to **create** a match (the lobby shows a passphrase field). Playing an existing seat via its magic link is never gated by this. Leave unset to allow anyone who can reach the site to create games. |
| `CAMPAIGN_ADMIN_KEY` | (unset → admin off) | Password for the **admin page at `/admin`**: lists every match (active + finished, who's submitted, who's waiting), shows each game's full unredacted move log, and can kill (delete) games. The key is sent in the `X-Admin-Key` header — never a URL — so it stays out of access logs. Unset disables the admin endpoints entirely. |
| `CAMPAIGN_RNG_SECRET` | (random per start) | Secret mixed into the per-week contest RNG so outcomes can't be predicted from the match id. A fresh random value each start is fine; pin it only if you want reproducible resolutions across restarts. |
| `CAMPAIGN_MAX_BODY` | `8388608` (8 MB) | Max request body size; rejects oversized uploads. |
| `CAMPAIGN_NEURAL_POLICY` | `runs/v20_mixed_lengths/policy.npz` | Exported weights for the Neural AI (made with `python -m rl.export_numpy <model>`). |
| `CAMPAIGN_CORS_ORIGIN` | `*` | Only matters if you serve the frontend from a different origin; unused for same-origin prod. |

Smoke test locally: `curl http://127.0.0.1:8080/` should return the app's
`index.html`, `curl http://127.0.0.1:8080/health` should return `ok`, and
`curl http://127.0.0.1:8080/api/config` should list `"Neural"` among the
`ai_strategies`. If it doesn't, the server log says why (a line starting
`Neural AI unavailable`).

## 4. nginx reverse proxy

Point a server block (e.g. a subdomain like `campaign.drewpolasky.com`, or a
path) at gunicorn. First add a DNS A record for the name pointing at the
server's IPv4 (and AAAA for IPv6), and allow ports 80 and 443 through any
Hetzner Cloud Firewall or `ufw`. Save this as
`/etc/nginx/sites-available/campaign`:

```nginx
server {
    server_name campaign.drewpolasky.com;

    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host $host;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    # (certbot adds the listen 443 / ssl_certificate lines)
}
```

```sh
sudo ln -s /etc/nginx/sites-available/campaign /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d campaign.drewpolasky.com    # HTTPS + auto-renewal
```

Everything (the SPA, its `/assets/*`, and `/api/*`) goes through this one
proxy, so magic links look like `https://campaign.drewpolasky.com/play/<token>`.

## 5. systemd unit (keep it running)

Keep the secrets in their own root-only file, `/etc/campaign.env`
(`sudo chmod 600 /etc/campaign.env`), instead of the world-readable unit:

```sh
CAMPAIGN_DB=/home/campaign/campaign_game/server/game.db
CAMPAIGN_CREATE_KEY=a-passphrase-you-give-your-players
CAMPAIGN_ADMIN_KEY=something-long-and-random
```

(One `NAME=value` per line, no `export` and no quotes. `openssl rand -hex 24`
makes a good admin key.)

`/etc/systemd/system/campaign.service`:

```ini
[Unit]
Description=Campaign game server
After=network.target

[Service]
WorkingDirectory=/home/campaign/campaign_game
EnvironmentFile=/etc/campaign.env
ExecStart=/home/campaign/campaign_game/.venv/bin/gunicorn -w 1 --threads 8 -b 127.0.0.1:8080 server.app:app
Restart=on-failure
User=campaign

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now campaign
journalctl -u campaign -n 50      # startup log
```

## Updating a running deployment

As the `campaign` user (`sudo -iu campaign`), in `~/campaign_game`:

```sh
git pull
.venv/bin/pip install -r server/requirements.txt   # picks up new dependencies
cd web && npm ci && npm run build && cd ..
```

Then, from your admin account: `sudo systemctl restart campaign`.

## Security checklist for a public URL

The app is safe to put on an open URL for a small group, provided you do the
following. (Seat/spectator links use 128-bit unguessable tokens; the DB uses
only parameterized SQL; request bodies are capped via `CAMPAIGN_MAX_BODY`,
default 8 MB; the create endpoint can be gated — above.)

- **Set `CAMPAIGN_CREATE_KEY`** so random visitors/bots can't spin up matches.
  (This is the one thing you must actively turn on.)
- **Set `CAMPAIGN_ADMIN_KEY` to something long and random** if you want the
  `/admin` page (match overview, full move logs, kill switch). Note the admin
  view exposes every player's moves for active games — treat the key like a
  root password. Leave it unset and the endpoints don't exist.
- **Legacy blob endpoints are already off.** `/campaign_saves` (the desktop
  save relay, unused by the web game) returns 404 in this server unless you set
  `CAMPAIGN_ENABLE_BLOB=1` — so nothing to do here for a normal web deploy. If
  you *do* enable them, also set a strong `CAMPAIGN_API_KEY`.

- **Serve over HTTPS only** (you already have TLS) — tokens travel in URLs.
- **Access logs capture tokens.** nginx logs the `?token=…` query and
  `/play/<token>` paths, so anyone who can read the logs can hijack a seat.
  Keep log access restricted, or drop the query string from the log format.
- Optionally set **`CAMPAIGN_CORS_ORIGIN`** to your exact origin (the default
  `*` is low-risk here since auth is a URL token, not a cookie — there's no
  ambient session to abuse via CSRF — but tightening it is good hygiene).

Opponents' cash on hand, end-of-game stats, and their moves this/prior weeks are
hidden from other players while a game is active, and revealed once it ends.
Public info (polling, delegate standings, momentum, issue positions, and
decided-state results) stays visible throughout — matching the desktop game's
"View Opponents' Stances".

Not covered (fine for friends): there's no rate limiting — add nginx
`limit_req` if you expect abuse.

## Notes / current limits

- **Match cleanup**: each server start deletes finished matches created more
  than 14 days ago (`db.prune_finished`). Active matches are never pruned.
- **AI opponents** on the web are the scripted strategies
  (Default/Aggressive/BigState/CloseOnly/MoneyMachine/Balanced) plus
  **Neural**, the same trained model the desktop's NeuralPPO plays, run with
  numpy. It was trained on 2-player games; in AI-only test matches against the
  scripted strategies it won 94-100% of games with 2, 3, 4 and 6 players, at
  every length and on both calendars. If it ever fails on a turn, that seat
  plays Default for the week and the error goes to the server log.
- **After retraining** the neural AI, re-export its weights where torch is
  installed (`python -m rl.export_numpy runs/<run>/model`) and commit the
  new `policy.npz`; `tests/test_numpy_policy.py` fails if it's missing or out
  of date.
- **The desktop client's save relay** (`/campaign_saves`) is off here by
  default. To use it with this server, set `CAMPAIGN_ENABLE_BLOB=1` and a strong
  `CAMPAIGN_API_KEY` in `/etc/campaign.env`.
