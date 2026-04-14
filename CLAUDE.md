# infinity_site_v2

**Purpose:** Personal homelab dashboard (current deployed version) — telemetry, file uploads, AI terminal, aircraft/satellite tracking, and admin control panel.
**Status:** Active
**Last updated:** 2026-04-12

## Key Decisions
- Flask blueprints for route organization
- SQLite for all data persistence
- Anthropic API powers the AI terminal
- v2 supersedes infinity_site — prefer working here over the original

## Critical Files
- `app.py` — Flask app entry point
- `database.py` — DB schema and queries
- `blueprints/` — route handlers per feature
- `requirements.txt` — Flask, anthropic, werkzeug, psutil
- `projects.json` — homelab service configuration

## Do Not Touch
- *(update as needed)*

## Current Focus
- *(update when working on this project)*

## Dev Notes
- Run: `gunicorn` or `flask run`
- Deployed behind Nginx
- `SESSION_COOKIE_SECURE` defaults to `True` (correct for production). For local HTTP dev, set `SESSION_COOKIE_SECURE=false` in your environment or the session cookie won't be sent and all authenticated routes will fail silently.
