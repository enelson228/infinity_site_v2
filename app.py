import os
import json
import uuid
import time
import psutil
import fcntl
import threading
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from contextlib import contextmanager
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify, session,
    redirect, url_for, send_from_directory
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
import anthropic

import config

TERMINAL_SYSTEM_PROMPT = (
    "You are INFINITY, an AI assistant integrated into a personal homelab dashboard. "
    "You assist with Linux administration, networking, programming, homelab services, "
    "and general technical questions. Be concise and direct. "
    "You operate in a military-style command terminal interface."
)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

# Ensure upload folder exists
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

# Simple file metadata storage (JSON file instead of SQLite for simplicity)
METADATA_FILE = os.path.join(app.instance_path, 'files_metadata.json')
METADATA_LOCK_FILE = os.path.join(app.instance_path, 'files_metadata.lock')
os.makedirs(app.instance_path, exist_ok=True)

# In-memory rate limit buckets (per process)
RATE_LIMIT_BUCKETS = {}
RATE_LIMIT_LOCK = threading.Lock()


def client_ip() -> str:
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def is_rate_limited(bucket: str) -> bool:
    now = time.time()
    window = config.LOGIN_RATE_LIMIT_WINDOW_SECONDS
    max_attempts = config.LOGIN_RATE_LIMIT_MAX_ATTEMPTS
    with RATE_LIMIT_LOCK:
        attempts = RATE_LIMIT_BUCKETS.get(bucket, [])
        attempts = [ts for ts in attempts if now - ts < window]
        if len(attempts) >= max_attempts:
            RATE_LIMIT_BUCKETS[bucket] = attempts
            return True
        attempts.append(now)
        RATE_LIMIT_BUCKETS[bucket] = attempts
    return False


def is_allowed_upload(filename: str) -> bool:
    if not config.UPLOAD_ALLOWED_EXTENSIONS:
        return True
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in config.UPLOAD_ALLOWED_EXTENSIONS


@contextmanager
def metadata_lock():
    with open(METADATA_LOCK_FILE, 'a') as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def load_metadata():
    """Load file metadata from JSON file."""
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r') as f:
            return json.load(f)
    return {'files': []}


def save_metadata(data):
    """Save file metadata to JSON file."""
    tmp_path = f"{METADATA_FILE}.tmp"
    with open(tmp_path, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, METADATA_FILE)


def claude_auth_required(f):
    """Decorator to require terminal authentication (separate from Uplink Cache)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('claude_authenticated'):
            return redirect(url_for('terminal_login'))
        auth_time_str = session.get('claude_auth_time', '')
        try:
            auth_time = datetime.fromisoformat(auth_time_str)
            if datetime.now() - auth_time > timedelta(hours=config.SESSION_LIFETIME_HOURS):
                session.pop('claude_authenticated', None)
                session.pop('claude_auth_time', None)
                return redirect(url_for('terminal_login'))
        except (ValueError, TypeError):
            return redirect(url_for('terminal_login'))
        return f(*args, **kwargs)
    return decorated_function


def auth_required(f):
    """Decorator to require authentication for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('uplink_login'))

        # Check session expiry
        auth_time = session.get('auth_time')
        if auth_time:
            auth_datetime = datetime.fromisoformat(auth_time)
            if datetime.now() - auth_datetime > timedelta(hours=config.SESSION_LIFETIME_HOURS):
                session.clear()
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'error': 'Session expired'}), 401
                return redirect(url_for('uplink_login'))

        return f(*args, **kwargs)
    return decorated_function


def telemetry_auth_required(f):
    if config.TELEMETRY_PUBLIC:
        return f
    return auth_required(f)


# Page Routes
@app.route('/')
def home():
    return render_template('home.html')


@app.route('/projects')
def projects():
    return render_template('projects.html')


@app.route('/uplink')
@auth_required
def uplink():
    return render_template('uplink.html')


@app.route('/uplink/login')
def uplink_login():
    if session.get('authenticated'):
        return redirect(url_for('uplink'))
    return render_template('uplink_login.html')


# API Routes
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    if is_rate_limited(f"uplink:{client_ip()}"):
        return jsonify({'error': 'Too many login attempts'}), 429
    data = request.get_json(silent=True) or {}
    password = data.get('password', '')

    if check_password_hash(config.UPLINK_PASSWORD_HASH, password):
        session['authenticated'] = True
        session['auth_time'] = datetime.now().isoformat()
        return jsonify({'success': True})

    return jsonify({'error': 'Invalid password'}), 401


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/api/projects')
def api_projects():
    projects_file = os.path.join(os.path.dirname(__file__), 'projects.json')
    with open(projects_file, 'r') as f:
        data = json.load(f)
    return jsonify(data)


@app.route('/api/files')
@auth_required
def api_files():
    with metadata_lock():
        metadata = load_metadata()
    return jsonify(metadata)


@app.route('/api/files/upload', methods=['POST'])
@auth_required
def api_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not is_allowed_upload(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    # Generate unique ID and secure filename
    file_id = str(uuid.uuid4())
    original_filename = secure_filename(file.filename)
    stored_filename = f"{file_id}_{original_filename}"

    # Save file
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
    file.save(filepath)

    # Get file size
    file_size = os.path.getsize(filepath)

    # Save metadata
    with metadata_lock():
        metadata = load_metadata()
        file_entry = {
            'id': file_id,
            'name': original_filename,
            'stored_name': stored_filename,
            'size': file_size,
            'uploaded': datetime.now().isoformat(),
            'uploader': session.get('uploader_name', 'Anonymous')
        }
        metadata['files'].append(file_entry)
        save_metadata(metadata)

    return jsonify({'success': True, 'file': file_entry})


@app.route('/api/files/<file_id>/download')
@auth_required
def api_download(file_id):
    with metadata_lock():
        metadata = load_metadata()
    file_entry = next((f for f in metadata['files'] if f['id'] == file_id), None)

    if not file_entry:
        return jsonify({'error': 'File not found'}), 404

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        file_entry['stored_name'],
        download_name=file_entry['name'],
        as_attachment=True
    )


@app.route('/api/files/<file_id>', methods=['DELETE'])
@auth_required
def api_delete(file_id):
    with metadata_lock():
        metadata = load_metadata()
        file_entry = next((f for f in metadata['files'] if f['id'] == file_id), None)

        if not file_entry:
            return jsonify({'error': 'File not found'}), 404

        # Delete physical file
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file_entry['stored_name'])
        if os.path.exists(filepath):
            os.remove(filepath)

        # Remove from metadata
        metadata['files'] = [f for f in metadata['files'] if f['id'] != file_id]
        save_metadata(metadata)

    return jsonify({'success': True})


@app.route('/telemetry')
@telemetry_auth_required
def telemetry():
    return render_template('telemetry.html')


@app.route('/api/telemetry')
@telemetry_auth_required
def api_telemetry():
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_freq = psutil.cpu_freq()
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    net = psutil.net_io_counters()
    uptime_seconds = int(time.time() - psutil.boot_time())
    load_avg = psutil.getloadavg()

    return jsonify({
        'cpu': {
            'percent': round(cpu_percent, 1),
            'cores_logical': psutil.cpu_count(logical=True),
            'cores_physical': psutil.cpu_count(logical=False),
            'freq_current': round(cpu_freq.current, 0) if cpu_freq else None,
            'freq_max': round(cpu_freq.max, 0) if cpu_freq else None,
        },
        'ram': {
            'total': ram.total,
            'used': ram.used,
            'available': ram.available,
            'percent': round(ram.percent, 1),
        },
        'disk': {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': round(disk.percent, 1),
        },
        'network': {
            'bytes_sent': net.bytes_sent,
            'bytes_recv': net.bytes_recv,
            'packets_sent': net.packets_sent,
            'packets_recv': net.packets_recv,
        },
        'uptime_seconds': uptime_seconds,
        'load_avg': {
            'one': round(load_avg[0], 2),
            'five': round(load_avg[1], 2),
            'fifteen': round(load_avg[2], 2),
        },
        'timestamp': time.time(),
    })


@app.route('/terminal')
@claude_auth_required
def terminal():
    return render_template('terminal.html')


@app.route('/terminal/login')
def terminal_login():
    if session.get('claude_authenticated'):
        return redirect(url_for('terminal'))
    return render_template('terminal_login.html')


@app.route('/api/terminal/login', methods=['POST'])
def api_terminal_login():
    if is_rate_limited(f"terminal:{client_ip()}"):
        return jsonify({'error': 'Too many login attempts'}), 429
    data = request.get_json(silent=True) or {}
    password = data.get('password', '')
    if check_password_hash(config.CLAUDE_PASSWORD_HASH, password):
        session['claude_authenticated'] = True
        session['claude_auth_time'] = datetime.now().isoformat()
        return jsonify({'success': True})
    return jsonify({'error': 'Invalid password'}), 401


@app.route('/api/terminal/logout', methods=['POST'])
def api_terminal_logout():
    session.pop('claude_authenticated', None)
    session.pop('claude_auth_time', None)
    return jsonify({'success': True})


@app.route('/api/claude/chat', methods=['POST'])
@claude_auth_required
def api_claude_chat():
    data = request.get_json()
    messages = data.get('messages', [])
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=8096,
        system=TERMINAL_SYSTEM_PROMPT,
        messages=messages
    )
    return jsonify({'content': response.content[0].text})


@app.route('/overwatch')
def overwatch():
    return render_template('overwatch.html')


@app.route('/api/tle')
def tle_proxy():
    """Proxy Celestrak TLE data to avoid browser CORS restrictions."""
    group = request.args.get('group', 'stations')
    # Sanitize group name to path-safe characters only
    safe_group = ''.join(c for c in group if c.isalnum() or c in '-_')
    # Celestrak new GP data API (replaces deprecated pub/TLE/* paths)
    base = 'https://celestrak.org/NORAD/elements/gp.php'
    url = f'{base}?GROUP={safe_group}&FORMAT=TLE'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode('utf-8', errors='replace')
        return data, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except urllib.error.URLError as e:
        return f'# TLE fetch error: {e.reason}\n', 502, {'Content-Type': 'text/plain'}
    except Exception as e:
        return f'# TLE fetch error: {e}\n', 500, {'Content-Type': 'text/plain'}


if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=5001)
