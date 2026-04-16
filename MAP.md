# File Map — infinity_site_v2

## Entry Points
- `app.py` — Flask application entry point

## Key Directories
- `blueprints/` — route handlers, one per feature

## Key Files
- `database.py` — SQLite schema and queries
- `requirements.txt` — Python dependencies
- `projects.json` — homelab service configuration

## Dev
- `python3 -m flask run` or `gunicorn`
- Deployed behind Nginx
