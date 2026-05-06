import logging
import os
import threading
import time
import hashlib
import urllib.request
from flask import Flask, render_template, url_for, jsonify, request

logging.basicConfig(level=logging.INFO)
import psutil
import config
import database
from auth import auth_bp, admin_required, validate_csrf
from blueprints.admin import admin_bp

from blueprints.uplink import uplink_bp
from blueprints.telemetry import telemetry_bp
from blueprints.terminal import terminal_bp
from blueprints.projects import projects_bp
from blueprints.monitor import monitor_bp
from blueprints.forge import forge_bp
from blueprints.storytell_proxy import storytell_proxy_bp
from blueprints.coms_uplink import coms_uplink_bp
try:
    from blueprints.osint import osint_bp
except ModuleNotFoundError:
    osint_bp = None

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = config.SESSION_COOKIE_HTTPONLY
app.config['SESSION_COOKIE_SAMESITE'] = config.SESSION_COOKIE_SAMESITE
app.config['SESSION_COOKIE_SECURE'] = config.SESSION_COOKIE_SECURE
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

# Initialize database
database.init_db()

# Ensure upload folder exists
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(app.instance_path, exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'forge_outputs'), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'forge_videos'), exist_ok=True)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(uplink_bp)
app.register_blueprint(telemetry_bp)
app.register_blueprint(terminal_bp)
app.register_blueprint(projects_bp)
app.register_blueprint(monitor_bp)
app.register_blueprint(forge_bp)
app.register_blueprint(storytell_proxy_bp)
app.register_blueprint(coms_uplink_bp)
if osint_bp is not None:
    app.register_blueprint(osint_bp)

@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cesium.com https://cdn.cesium.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "video-src 'self' data: blob:; "
        "media-src 'self' data: blob:; "
        "connect-src 'self' https://api.cesium.com https://ion.cesium.com "
        "https://assets.cesium.com https://opensky-network.org; "
        "frame-ancestors 'none';"
    )
    return response

def get_static_hash(filename):
    full_path = os.path.join(app.root_path, 'static', filename)
    if not os.path.exists(full_path):
        return "notfound"
    with open(full_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()[:8]

app.before_request(validate_csrf)

@app.context_processor
def inject_static_version():
    def static_versioned(filename):
        h = get_static_hash(filename)
        return f"{url_for('static', filename=filename)}?v={h}"
    return dict(static_versioned=static_versioned)

@app.context_processor
def inject_csrf_token():
    from flask import session as _session
    return dict(csrf_token=_session.get('csrf_token', ''))

# ── Background Monitoring Task ───────────────────────────────────────────

def _poll_github_repo(owner: str, repo: str, repo_id: str, token: str):
    """Fetch GitHub repo status and store in DB. Called from background thread."""
    import json as _json
    base_url = f'https://api.github.com/repos/{owner}/{repo}'
    headers = {
        'Authorization': f'token {token}',
        'User-Agent': 'InfinityMonitor/1.0',
        'Accept': 'application/vnd.github.v3+json',
    }

    def gh_get(url):
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return _json.loads(resp.read().decode())

    # Latest commit — guard against empty repos and error-shape API responses
    commits = gh_get(f'{base_url}/commits?per_page=1')
    first = commits[0] if isinstance(commits, list) and commits else None
    last_commit_at = (
        (first.get('commit') or {}).get('committer', {}).get('date')
        if first else None
    )
    raw_msg = ((first.get('commit') or {}).get('message') or '') if first else ''
    last_commit_msg = raw_msg.split('\n')[0][:120] or None

    # Open PR count — guard against error-shape responses (dicts instead of lists)
    prs = gh_get(f'{base_url}/pulls?state=open&per_page=100')
    open_prs = len(prs) if isinstance(prs, list) else 0

    # Latest CI run status
    ci_status = 'none'
    try:
        runs = gh_get(f'{base_url}/actions/runs?per_page=1')
        workflow_runs = runs.get('workflow_runs', [])
        if workflow_runs:
            ci_status = workflow_runs[0].get('conclusion') or workflow_runs[0].get('status', 'none')
    except Exception:
        pass  # No CI configured for this repo

    from datetime import datetime as _dt
    database.upsert_github_repo_status(
        repo_id=repo_id,
        last_commit_at=last_commit_at,
        last_commit_msg=last_commit_msg,
        open_prs=open_prs,
        ci_status=ci_status,
        fetched_at=_dt.now().isoformat(),
    )

def background_monitor():
    """Background thread to ping projects and log telemetry history."""
    last_ping_time = 0
    last_telemetry_time = 0
    last_github_time = 0
    last_prune_time = 0
    last_recommendations_time = 0
    
    while True:
        now = time.time()
        
        # Ping projects every 5 minutes
        if now - last_ping_time >= 300:
            try:
                projects = database.list_projects()
                for p in projects:
                    url = p['url']
                    if not url or url == '#' or url.startswith('/'):
                        continue
                    
                    start = time.time()
                    try:
                        req = urllib.request.Request(url, headers={'User-Agent': 'InfinityMonitor/1.0'})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            status = 'online' if resp.status < 400 else 'error'
                    except Exception:
                        status = 'offline'
                    
                    elapsed_ms = int((time.time() - start) * 1000)
                    database.update_project_status(p['id'], status, elapsed_ms)
            except Exception as e:
                app.logger.error(f"Monitoring error (ping): {e}")
            last_ping_time = now

        # Log telemetry every 1 minute
        if now - last_telemetry_time >= 60:
            try:
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                database.add_telemetry_history(cpu, ram)
            except Exception as e:
                app.logger.error(f"Monitoring error (telemetry): {e}")
            last_telemetry_time = now

        # Poll GitHub every 10 minutes
        if now - last_github_time >= 600:
            if config.GITHUB_TOKEN:
                try:
                    repos = database.list_github_repos()
                except Exception as e:
                    app.logger.error(f"Monitoring error (github list): {e}")
                    repos = []
                for r in repos:
                    try:
                        _poll_github_repo(r['owner'], r['repo'], r['id'], config.GITHUB_TOKEN)
                    except Exception as e:
                        app.logger.error(f"Monitoring error (github {r.get('id')}): {e}")
            last_github_time = now

        # Prune old data once per day
        if now - last_prune_time >= 86400:
            try:
                database.prune_old_data()
            except Exception as e:
                app.logger.error(f"Monitoring error (prune): {e}")
            last_prune_time = now

        # Refresh recommendations every 30 minutes
        if now - last_recommendations_time >= 1800:
            try:
                import recommendations as rec_engine
                rec_engine.refresh_recommendations()
            except Exception as e:
                app.logger.error(f"Monitoring error (recommendations): {e}")
            last_recommendations_time = now

        time.sleep(10)

# Start background monitor
monitor_thread = threading.Thread(target=background_monitor, daemon=True)
monitor_thread.start()

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/control')
@admin_required
def control():
    return render_template('control.html')

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', '0') == '1', host='127.0.0.1', port=5173)
