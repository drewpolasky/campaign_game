# Deploying the browser game

The server serves **both** the JSON match API and the built React app from one
origin, so in production there's no CORS and magic links resolve against the
same host. Put it behind your existing nginx/TLS.

## 1. Build the frontend

Needs Node 18+ (only to build — the server itself is pure Python).

```sh
cd web
npm ci
npm run build      # -> web/dist/  (static bundle the server serves)
```

Rebuild this whenever the frontend changes. `web/dist/` is gitignored, so it's
produced on the deploy host (or built elsewhere and copied over).

## 2. Install the server

```sh
cd ..                      # repo root
python3 -m venv .venv
. .venv/bin/activate
pip install -r server/requirements.txt   # flask + gunicorn
```

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
| `CAMPAIGN_RNG_SECRET` | (random per start) | Secret mixed into the per-week contest RNG so outcomes can't be predicted from the match id. A fresh random value each start is fine; pin it only if you want reproducible resolutions across restarts. |
| `CAMPAIGN_MAX_BODY` | `8388608` (8 MB) | Max request body size; rejects oversized uploads. |
| `CAMPAIGN_CORS_ORIGIN` | `*` | Only matters if you serve the frontend from a different origin; unused for same-origin prod. |

Smoke test locally: `curl http://127.0.0.1:8080/` should return the app's
`index.html`, and `curl http://127.0.0.1:8080/health` should return `ok`.

## 4. nginx reverse proxy

Point a server block (e.g. a subdomain like `campaign.drewpolasky.com`, or a
path) at gunicorn. TLS via your existing certs / certbot.

```nginx
server {
    server_name campaign.drewpolasky.com;

    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host $host;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    # (add your listen 443 / ssl_certificate lines, e.g. via certbot)
}
```

Everything (the SPA, its `/assets/*`, and `/api/*`) goes through this one
proxy, so magic links look like `https://campaign.drewpolasky.com/play/<token>`.

## 5. systemd unit (keep it running)

`/etc/systemd/system/campaign.service`:

```ini
[Unit]
Description=Campaign game server
After=network.target

[Service]
WorkingDirectory=/path/to/campaign_game
Environment=CAMPAIGN_DB=/path/to/campaign_game/server/game.db
Environment=CAMPAIGN_API_KEY=change-me-to-something-random
ExecStart=/path/to/campaign_game/.venv/bin/gunicorn -w 1 --threads 8 -b 127.0.0.1:8080 server.app:app
Restart=on-failure
User=youruser

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now campaign
```

## Updating a running deployment

```sh
git pull
cd web && npm ci && npm run build && cd ..
sudo systemctl restart campaign
```

## Security checklist for a public URL

The app is safe to put on an open URL for a small group, provided you do the
following. (Seat/spectator links use 128-bit unguessable tokens; the DB uses
only parameterized SQL; request bodies are capped via `CAMPAIGN_MAX_BODY`,
default 8 MB; the create endpoint can be gated — above.)

- **Set `CAMPAIGN_CREATE_KEY`** so random visitors/bots can't spin up matches.
  (This is the one thing you must actively turn on.)
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

- **Match cleanup**: finished matches accumulate in the DB. Prune old ones
  periodically (e.g. `DELETE FROM matches WHERE status='finished' AND ...`).
- **Neural AI** (`NeuralPPO`) needs `torch` installed server-side; the scripted
  strategies (Default/Aggressive/BigState/CloseOnly/MoneyMachine/Balanced) have
  no extra dependencies and are the default.
- **The desktop client still works** against the same server via the unchanged
  `/campaign_saves` blob endpoints.
