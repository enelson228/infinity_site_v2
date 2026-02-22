import os
import json
import uuid
import time
import psutil
import fcntl
import threading
import urllib.request
import urllib.error
import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify, session,
    redirect, url_for, send_from_directory
)
from werkzeug.security import check_password_hash, generate_password_hash
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

# Anthropic client — single instance shared across all requests
_anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# Ensure upload folder exists
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

# Simple file metadata storage (JSON file instead of SQLite for simplicity)
METADATA_FILE = os.path.join(app.instance_path, 'files_metadata.json')
METADATA_LOCK_FILE = os.path.join(app.instance_path, 'files_metadata.lock')
os.makedirs(app.instance_path, exist_ok=True)

# User DB (SQLite)
USER_DB_PATH = os.path.join(app.instance_path, 'users.db')


def _db_conn():
    conn = sqlite3.connect(USER_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_user_db():
    with _db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                actor_user_id INTEGER,
                target_user_id INTEGER,
                ip TEXT,
                detail TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

        # Add disabled column for existing installs
        cur = conn.execute("PRAGMA table_info(users)")
        cols = {row["name"] for row in cur.fetchall()}
        if "disabled" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
            conn.commit()

        cur = conn.execute("SELECT COUNT(*) AS c FROM users")
        if cur.fetchone()["c"] == 0:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, created_at, disabled)
                VALUES (?, ?, ?, ?, 0)
                """,
                ("john117", config.UPLINK_PASSWORD_HASH, "admin", datetime.now().isoformat()),
            )
            conn.commit()


def _get_user_by_username(username: str):
    with _db_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()


def _get_user_by_id(user_id: int):
    with _db_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()


def _list_memories(user_id: int):
    with _db_conn() as conn:
        cur = conn.execute(
            "SELECT id, content, created_at FROM memories WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def _append_audit(event_type: str, actor_user_id=None, target_user_id=None, detail: str = ''):
    with _db_conn() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (event_type, actor_user_id, target_user_id, ip, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_type, actor_user_id, target_user_id, client_ip(), detail, datetime.now().isoformat()),
        )
        conn.commit()


_init_user_db()

# In-memory rate limit buckets (per process)
RATE_LIMIT_BUCKETS = {}
RATE_LIMIT_LOCK = threading.Lock()


def client_ip() -> str:
    """Return the real client IP, respecting TRUSTED_PROXIES reverse-proxy hops."""
    if config.TRUSTED_PROXIES > 0:
        forwarded = request.headers.get('X-Forwarded-For', '')
        if forwarded:
            parts = [p.strip() for p in forwarded.split(',')]
            idx = max(0, len(parts) - config.TRUSTED_PROXIES)
            return parts[idx]
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
        user_id = session.get('claude_user_id')
        if not user_id:
            return redirect(url_for('terminal_login'))
        auth_time_str = session.get('claude_auth_time', '')
        try:
            auth_time = datetime.fromisoformat(auth_time_str)
            if datetime.now() - auth_time > timedelta(hours=config.SESSION_LIFETIME_HOURS):
                session.pop('claude_user_id', None)
                session.pop('claude_username', None)
                session.pop('claude_role', None)
                session.pop('claude_auth_time', None)
                return redirect(url_for('terminal_login'))
        except (ValueError, TypeError):
            return redirect(url_for('terminal_login'))
        if not _get_user_by_id(int(user_id)):
            session.pop('claude_user_id', None)
            session.pop('claude_username', None)
            session.pop('claude_role', None)
            session.pop('claude_auth_time', None)
            return redirect(url_for('terminal_login'))
        return f(*args, **kwargs)
    return decorated_function


def auth_required(f):
    """Decorator to require authentication for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
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

        if not _get_user_by_id(int(user_id)):
            session.clear()
            return redirect(url_for('uplink_login'))

        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Require authenticated admin user (Uplink session)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('uplink_login'))
        user = _get_user_by_id(int(user_id))
        if not user or user['role'] != 'admin':
            return jsonify({'error': 'Admin required'}), 403
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


@app.route('/projects/rowboat')
def project_rowboat():
    return render_template('project_rowboat.html')


@app.route('/uplink')
@auth_required
def uplink():
    return render_template('uplink.html')


@app.route('/control')
@admin_required
def control():
    return render_template('control.html')


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
    username = (data.get('username') or '').strip()
    password = data.get('password', '')

    if not username:
        return jsonify({'error': 'Username required'}), 400

    user = _get_user_by_username(username)
    if user and user['disabled']:
        _append_audit('login_failure', detail=f'uplink disabled username={username}')
        return jsonify({'error': 'Account disabled'}), 403
    if user and check_password_hash(user['password_hash'], password):
        session['authenticated'] = True
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session['auth_time'] = datetime.now().isoformat()
        _append_audit('login_success', actor_user_id=user['id'], detail='uplink')
        return jsonify({'success': True})

    _append_audit('login_failure', detail=f'uplink username={username}')
    return jsonify({'error': 'Invalid password'}), 401


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})


# Admin API
@app.route('/api/admin/users', methods=['GET'])
@admin_required
def api_admin_list_users():
    with _db_conn() as conn:
        cur = conn.execute(
            "SELECT id, username, role, created_at, disabled FROM users ORDER BY id ASC"
        )
        users = [dict(row) for row in cur.fetchall()]
    return jsonify({'users': users})


@app.route('/api/admin/users', methods=['POST'])
@admin_required
def api_admin_create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    role = (data.get('role') or 'user').strip().lower()
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if role not in ('user', 'admin'):
        return jsonify({'error': 'Invalid role'}), 400
    pw_hash = generate_password_hash(password, method='pbkdf2:sha256')
    try:
        with _db_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at, disabled) VALUES (?, ?, ?, ?, 0)",
                (username, pw_hash, role, datetime.now().isoformat()),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username already exists'}), 409
    actor_id = session.get('user_id')
    _append_audit('user_create', actor_user_id=actor_id, detail=f'username={username} role={role}')
    return jsonify({'success': True})


@app.route('/api/admin/users/<int:user_id>/password', methods=['PUT'])
@admin_required
def api_admin_reset_password(user_id: int):
    data = request.get_json(silent=True) or {}
    password = data.get('password') or ''
    if not password:
        return jsonify({'error': 'Password required'}), 400
    pw_hash = generate_password_hash(password, method='pbkdf2:sha256')
    with _db_conn() as conn:
        cur = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'error': 'User not found'}), 404
    actor_id = session.get('user_id')
    _append_audit('password_reset', actor_user_id=actor_id, target_user_id=user_id)
    return jsonify({'success': True})


@app.route('/api/admin/users/<int:user_id>/disable', methods=['PUT'])
@admin_required
def api_admin_disable_user(user_id: int):
    actor_id = session.get('user_id')
    if actor_id and int(actor_id) == user_id:
        return jsonify({'error': 'Cannot disable your own account'}), 400
    with _db_conn() as conn:
        cur = conn.execute("UPDATE users SET disabled = 1 WHERE id = ?", (user_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'error': 'User not found'}), 404
    _append_audit('user_disable', actor_user_id=actor_id, target_user_id=user_id)
    return jsonify({'success': True})


@app.route('/api/admin/users/<int:user_id>/enable', methods=['PUT'])
@admin_required
def api_admin_enable_user(user_id: int):
    with _db_conn() as conn:
        cur = conn.execute("UPDATE users SET disabled = 0 WHERE id = ?", (user_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'error': 'User not found'}), 404
    actor_id = session.get('user_id')
    _append_audit('user_enable', actor_user_id=actor_id, target_user_id=user_id)
    return jsonify({'success': True})


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def api_admin_delete_user(user_id: int):
    actor_id = session.get('user_id')
    if actor_id and int(actor_id) == user_id:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    with _db_conn() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'error': 'User not found'}), 404
    _append_audit('user_delete', actor_user_id=actor_id, target_user_id=user_id)
    return jsonify({'success': True})


@app.route('/api/admin/memory/<int:user_id>', methods=['GET'])
@admin_required
def api_admin_list_memory(user_id: int):
    return jsonify({'memories': _list_memories(user_id)})


@app.route('/api/admin/memory/<int:user_id>', methods=['POST'])
@admin_required
def api_admin_add_memory(user_id: int):
    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'Content required'}), 400
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO memories (user_id, content, created_at) VALUES (?, ?, ?)",
            (user_id, content, datetime.now().isoformat()),
        )
        conn.commit()
    actor_id = session.get('user_id')
    _append_audit('memory_add', actor_user_id=actor_id, target_user_id=user_id)
    return jsonify({'success': True})


@app.route('/api/admin/memory/<int:memory_id>', methods=['DELETE'])
@admin_required
def api_admin_delete_memory(memory_id: int):
    with _db_conn() as conn:
        cur = conn.execute("SELECT user_id FROM memories WHERE id = ?", (memory_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Memory not found'}), 404
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
    actor_id = session.get('user_id')
    _append_audit('memory_delete', actor_user_id=actor_id, target_user_id=row['user_id'])
    return jsonify({'success': True})


@app.route('/api/admin/audit', methods=['GET'])
@admin_required
def api_admin_audit():
    with _db_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, event_type, actor_user_id, target_user_id, ip, detail, created_at
            FROM audit_log
            ORDER BY id DESC
            LIMIT 200
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    return jsonify({'events': rows})


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
    username = (data.get('username') or '').strip()
    password = data.get('password', '')
    if not username:
        return jsonify({'error': 'Username required'}), 400
    user = _get_user_by_username(username)
    if user and user['disabled']:
        _append_audit('login_failure', detail=f'terminal disabled username={username}')
        return jsonify({'error': 'Account disabled'}), 403
    if user and check_password_hash(user['password_hash'], password):
        session['claude_authenticated'] = True
        session['claude_user_id'] = user['id']
        session['claude_username'] = user['username']
        session['claude_role'] = user['role']
        session['claude_auth_time'] = datetime.now().isoformat()
        _append_audit('login_success', actor_user_id=user['id'], detail='terminal')
        return jsonify({'success': True})
    _append_audit('login_failure', detail=f'terminal username={username}')
    return jsonify({'error': 'Invalid password'}), 401


@app.route('/api/terminal/logout', methods=['POST'])
def api_terminal_logout():
    session.pop('claude_authenticated', None)
    session.pop('claude_user_id', None)
    session.pop('claude_username', None)
    session.pop('claude_role', None)
    session.pop('claude_auth_time', None)
    return jsonify({'success': True})


# Terminal Memory (per user, explicit opt-in)
@app.route('/api/memory', methods=['GET'])
@claude_auth_required
def api_memory_list():
    user_id = int(session.get('claude_user_id'))
    return jsonify({'memories': _list_memories(user_id)})


@app.route('/api/memory', methods=['POST'])
@claude_auth_required
def api_memory_add():
    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'Content required'}), 400
    user_id = int(session.get('claude_user_id'))
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO memories (user_id, content, created_at) VALUES (?, ?, ?)",
            (user_id, content, datetime.now().isoformat()),
        )
        conn.commit()
    _append_audit('memory_add', actor_user_id=user_id, target_user_id=user_id)
    return jsonify({'success': True})


_CHAT_MAX_MESSAGES = 40
_CHAT_MAX_MESSAGE_CHARS = 8000

@app.route('/api/claude/chat', methods=['POST'])
@claude_auth_required
def api_claude_chat():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid request body'}), 400

    messages = data.get('messages', [])
    if not isinstance(messages, list) or len(messages) > _CHAT_MAX_MESSAGES:
        return jsonify({'error': 'Invalid messages'}), 400

    sanitized = []
    for msg in messages:
        if not isinstance(msg, dict):
            return jsonify({'error': 'Invalid message format'}), 400
        role = msg.get('role', '')
        content = msg.get('content', '')
        if role not in ('user', 'assistant') or not isinstance(content, str):
            return jsonify({'error': 'Invalid message format'}), 400
        sanitized.append({'role': role, 'content': content[:_CHAT_MAX_MESSAGE_CHARS]})

    try:
        system_prompt = TERMINAL_SYSTEM_PROMPT
        if data.get('include_memory'):
            user_id = int(session.get('claude_user_id'))
            memories = _list_memories(user_id)
            if memories:
                mem_lines = '\n'.join(f"- {m['content']}" for m in memories)
                system_prompt = (
                    TERMINAL_SYSTEM_PROMPT +
                    "\n\nUSER MEMORY (explicitly requested):\n" +
                    mem_lines
                )
        response = _anthropic_client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=8096,
            system=system_prompt,
            messages=sanitized,
        )
        content_blocks = response.content
        if not content_blocks or not hasattr(content_blocks[0], 'text'):
            return jsonify({'error': 'Unexpected response format from AI'}), 502
        return jsonify({'content': content_blocks[0].text})
    except anthropic.APIStatusError as e:
        app.logger.error('Anthropic API error: %s', e)
        return jsonify({'error': 'AI service error'}), 502
    except Exception:
        app.logger.exception('Unexpected error in claude chat')
        return jsonify({'error': 'Internal error'}), 500


@app.route('/overwatch')
def overwatch():
    return render_template('overwatch.html', cesium_token=config.CESIUM_ION_TOKEN)


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
