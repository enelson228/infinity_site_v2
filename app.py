import os
import threading
import time
import hashlib
import urllib.request
from flask import Flask, render_template, url_for
import psutil
import config
import database
from auth import auth_bp, admin_required
from blueprints.admin import admin_bp
from blueprints.uplink import uplink_bp
from blueprints.telemetry import telemetry_bp
from blueprints.terminal import terminal_bp
from blueprints.overwatch import overwatch_bp
from blueprints.projects import projects_bp

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

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(uplink_bp)
app.register_blueprint(telemetry_bp)
app.register_blueprint(terminal_bp)
app.register_blueprint(overwatch_bp)
app.register_blueprint(projects_bp)

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
        "connect-src 'self' https://api.cesium.com;"
    )
    return response

def get_static_hash(filename):
    full_path = os.path.join(app.root_path, 'static', filename)
    if not os.path.exists(full_path):
        return "notfound"
    with open(full_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()[:8]

@app.context_processor
def inject_static_version():
    def static_versioned(filename):
        h = get_static_hash(filename)
        return f"{url_for('static', filename=filename)}?v={h}"
    return dict(static_versioned=static_versioned)

# ── Background Monitoring Task ───────────────────────────────────────────

def background_monitor():
    """Background thread to ping projects and log telemetry history."""
    last_ping_time = 0
    last_telemetry_time = 0
    
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
    app.run(debug=True, host='0.0.0.0', port=5173)
