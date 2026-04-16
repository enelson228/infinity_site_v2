# infinity_site_v2

**Purpose:** Personal homelab dashboard (current deployed version) — telemetry, file uploads, AI terminal, aircraft/satellite tracking, and admin control panel.
**Status:** Active
**Last updated:** 2026-04-16

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
- Forge image generation, auth integration, and cleanup of deprecated Overwatch routes/assets

## Dev Notes
- Run: `gunicorn` or `flask run`
- Deployed behind Nginx
