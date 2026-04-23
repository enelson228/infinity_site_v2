# File Map — infinity_site_v2

## Entry Points
- `app.py` — Flask application entry point and background monitor thread

## Key Directories
- `blueprints/` — feature-specific route handlers
  - `admin.py` — user and memory management
  - `auth.py` — login/logout and session handling
  - `forge.py` — RunPod image generation
  - `monitor.py` — infrastructure dashboard & recommendations
  - `projects.py` — service dashboard
  - `telemetry.py` — system metrics
  - `terminal.py` — AI assistant interface
  - `uplink.py` — file storage
  - `coms_uplink.py` — static tool hosting
- `static/` — CSS, JS, and generated assets (e.g., `forge_outputs/`)
- `templates/` — Jinja2 HTML templates
- `docs/superpowers/` — design specs and implementation plans

## Key Files
- `database.py` — SQLite schema, migrations, and query interface
- `config.py` — environment variable parsing
- `auth.py` — core authentication decorators and CSRF logic
- `recommendations.py` — AI/rule-based insight engine for Monitor
- `requirements.txt` — Python dependencies
- `projects.json` — homelab service configuration (seeds DB)

## Dev
- `python3 -m flask run` or `gunicorn`
- Deployed behind Nginx
- Uses SQLite in `instance/users.db`
