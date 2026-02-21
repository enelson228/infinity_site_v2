# Infinity Site

Personal website and homelab dashboard running at [mjolnirarmory.com](https://mjolnirarmory.com).

## Features

- **Home** — Landing page
- **Projects** — Homelab services dashboard (Plex, Pi-hole, Home Assistant, etc.)
- **Telemetry** — Live system metrics dashboard (CPU, RAM, disk, network, load avg) with Halo Reach military HUD aesthetic — glowing amber/cyan readouts and animated progress bars
- **Uplink Cache** — Password-protected file upload/download portal (100MB max per file)

## Stack

- Python 3 / Flask
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

Generate password hashes locally:

```bash
python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password', method='pbkdf2:sha256'))"
```

Optional config:
- `TELEMETRY_PUBLIC` (`true`/`false`)
- `LOGIN_RATE_LIMIT_MAX_ATTEMPTS` (default `10`)
- `LOGIN_RATE_LIMIT_WINDOW_SECONDS` (default `600`)
- `UPLOAD_ALLOWED_EXTENSIONS` (comma-separated, e.g. `zip,pdf,txt`)

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

## Projects dashboard

Edit `projects.json` to add, remove, or update homelab services shown on the projects page.
