# infinity_site_v2

**Purpose:** Personal homelab dashboard (current deployed version) — telemetry, file uploads, AI terminal, image generation, and admin control panel.
**Status:** Active
**Last updated:** 2026-04-20

## Key Decisions
- Flask blueprints for route organization
- SQLite for all data persistence
- Anthropic API powers the AI terminal and recommendations
- RunPod serverless powers Forge image generation
- v2 supersedes infinity_site — prefer working here over the original

## Critical Files
- `app.py` — Flask app entry point & background tasks
- `database.py` — DB schema, migrations, and queries
- `blueprints/` — feature-specific route handlers
- `auth.py` — authentication and CSRF logic
- `config.py` — environment configuration
- `recommendations.py` — Monitor insight engine

## Do Not Touch
- `instance/` (local database)
- `uploads/` (user files)
- `static/forge_outputs/` (generated images)

## Current Focus
- Forge image generation refinements and Monitor dashboard AI insights.
- Deprecation of legacy Overwatch assets.

## Dev Notes
- Run: `gunicorn` or `flask run`
- Deployed behind Nginx
- `SESSION_COOKIE_SECURE` defaults to `True`. For local HTTP dev, set `SESSION_COOKIE_SECURE=false`.
