# Infinity Site

Personal website and homelab dashboard running at [mjolnirarmory.com](https://mjolnirarmory.com).

## Features

- **Home** — Landing page
- **Projects** — Dashboard of internal services and tools
- **Telemetry** — Live system metrics dashboard (CPU, RAM, disk, network, load avg) with Halo Reach military HUD aesthetic
- **Uplink Cache** — Authenticated file upload/download portal (100MB max per file)
- **Terminal** — AI terminal with per-user memory (explicit `REMEMBER` / `RECALL`)
- **Forge** — AI image generation (RunPod serverless; Juggernaut XL and CyberRealistic Pony)
- **Monitor** — Admin-only dashboard for services, GitHub repo status, and AI-driven recommendations
- **COMS-UPLINK** — Radio & electromagnetic spectrum training module
- **Control** — Admin console for user and memory management with audit log

## Stack

- Python 3 / Flask
- SQLite (persistence)
- Gunicorn (WSGI server)
- Nginx (reverse proxy + static files)
- Let's Encrypt SSL

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/enelson228/infinity_site.git
cd infinity_site
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

### 2. Configure (Doppler)

This app expects secrets via environment variables. With Doppler:

```bash
doppler setup
```

Required secrets:
- `SECRET_KEY`
- `UPLINK_PASSWORD_HASH`
- `CLAUDE_PASSWORD_HASH`
- `ANTHROPIC_API_KEY`

Optional config (enables additional features):
- `GITHUB_TOKEN` (Enables GitHub panel in Monitor dashboard)
- `RUNPOD_API_KEY` + `FORGE_ENDPOINT_ID` (Juggernaut XL Forge endpoint)
- `CYBERREALISTIC_PONY_ENDPOINT_ID` (CyberRealistic Pony Forge endpoint)
- `SD_ENDPOINT_ID` / `SDXL_ENDPOINT_ID` (Legacy Forge SDXL endpoint fallback)
- `CESIUM_ION_TOKEN` (Used for mapping tools)
- `TELEMETRY_PUBLIC` (`true`/`false`)
- `LOGIN_RATE_LIMIT_MAX_ATTEMPTS` (default `10`)
- `LOGIN_RATE_LIMIT_WINDOW_SECONDS` (default `600`)
- `UPLOAD_ALLOWED_EXTENSIONS` (comma-separated list)
- `SESSION_COOKIE_SECURE` (set to `false` for local HTTP development)

### 3. Run (development)

```bash
source venv/bin/activate
doppler run -- python3 app.py
```

App runs on `http://localhost:5001`.

### 4. Production (systemd + nginx)

Create `/etc/systemd/system/infinity_site.service` (Doppler-injected env):

```ini
[Unit]
Description=Infinity Site Flask App
After=network.target

[Service]
User=root
WorkingDirectory=/root/infinity_site
ExecStart=/usr/local/bin/doppler run -- /root/infinity_site/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5001 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now infinity_site
```

Configure nginx to proxy to `127.0.0.1:5001` and get SSL with:

```bash
certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

## Managing the service

```bash
# Restart after code changes
systemctl restart infinity_site

# View logs
journalctl -u infinity_site -f

# Check status
systemctl status infinity_site
```

## Forge RunPod Cost Guardrails

Forge is intended to use queue-based RunPod Serverless Flex endpoints for each heavyweight model:

- Set `active_workers=0` so no GPU compute runs while idle.
- Set `max_workers=1` to cap concurrent GPU spend.
- Prefer `L4/A5000/3090 24GB`; use `4090 PRO 24GB` only if availability is poor.
- Keep the endpoint idle timeout short, around `5s`, unless repeated back-to-back generations justify a warmer worker.
- Pin each model to its own endpoint (`FORGE_ENDPOINT_ID` for Juggernaut XL, `CYBERREALISTIC_PONY_ENDPOINT_ID` for CyberRealistic Pony) so cold starts and VRAM stay isolated.

## Projects dashboard

Edit `projects.json` to add, remove, or update homelab services shown on the projects page.

## Authentication + Users

- Logins now use **username + password** (not a single shared password).
- The first admin user is seeded on first boot:
  - Username: `john117`
  - Password hash: `UPLINK_PASSWORD_HASH` (from Doppler)
- Admins can manage accounts at `/control`:
  - Create users
  - Reset passwords
  - Enable/disable/delete accounts
  - Manage per-user memory
  - View audit log (login attempts + user actions)

## Terminal Memory (Per User)

Memory is stored per user and only injected when explicitly requested:

- `REMEMBER <text>` — store memory
- `RECALL <prompt>` — ask with memory injected
