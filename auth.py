import logging
from functools import wraps
from datetime import datetime, timedelta
import secrets
from urllib.parse import urlparse
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template

_log = logging.getLogger(__name__)
from werkzeug.security import check_password_hash
import config
import database
from utils import client_ip, is_rate_limited

auth_bp = Blueprint('auth', __name__)


def _exempt_from_csrf(path: str) -> bool:
    """Paths that don't need CSRF protection (pre-auth endpoints)."""
    return path in ('/api/auth/login', '/api/auth/logout')


def validate_csrf():
    """Before-request CSRF check for all state-changing endpoints."""
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    if _exempt_from_csrf(request.path):
        return
    session_token = session.get('csrf_token', '')
    if not session_token:
        _log.warning('CSRF block (no session token): %s %s', request.method, request.path)
        from flask import abort
        abort(403)
    token = request.headers.get('X-CSRF-Token') or request.form.get('_csrf_token', '')
    if not secrets.compare_digest(token, session_token):
        _log.warning('CSRF FAIL: %s %s | sent=%r session=%r',
                     request.method, request.path, token[:8] if token else '', session_token[:8])
        from flask import abort
        abort(403)
    _log.info('CSRF OK: %s %s', request.method, request.path)

def login_required(f):
    """Decorator to require authentication for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('auth.login', next=request.path))

        # Check session expiry
        auth_time = session.get('auth_time')
        if auth_time:
            auth_datetime = datetime.fromisoformat(auth_time)
            if datetime.now() - auth_datetime > timedelta(hours=config.SESSION_LIFETIME_HOURS):
                session.clear()
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'error': 'Session expired'}), 401
                return redirect(url_for('auth.login', next=request.path))

        user = database.get_user_by_id(int(user_id))
        if not user or user['disabled']:
            session.clear()
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Session expired'}), 401
            return redirect(url_for('auth.login', next=request.path))

        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Require authenticated admin user."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        user = database.get_user_by_id(int(user_id))
        if not user or user['role'] != 'admin':
            return jsonify({'error': 'Admin required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def _safe_next(target: str) -> str:
    ref = urlparse(target)
    if ref.scheme or ref.netloc:
        return url_for('home')
    return target or url_for('home')

@auth_bp.route('/login')
def login():
    if session.get('user_id'):
        return redirect(_safe_next(request.args.get('next', '')))
    return render_template('login.html')

@auth_bp.route('/uplink/login')
def uplink_login():
    """Legacy redirect for old bookmarks."""
    return redirect(url_for('auth.login', next=url_for('uplink.uplink')))

@auth_bp.route('/terminal/login')
def terminal_login():
    """Legacy redirect for old bookmarks."""
    return redirect(url_for('auth.login', next=url_for('terminal.terminal')))

@auth_bp.route('/api/auth/login', methods=['POST'])
def api_login():
    if is_rate_limited(f"login:{client_ip()}"):
        return jsonify({'error': 'Too many login attempts'}), 429
    
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password', '')

    if not username:
        return jsonify({'error': 'Username required'}), 400

    user = database.get_user_by_username(username)
    if not user:
        database.append_audit('login_failure', client_ip(), detail=f'invalid_user username={username}')
        return jsonify({'error': 'Invalid credentials'}), 401

    if user['disabled']:
        database.append_audit('login_failure', client_ip(), detail=f'disabled_user username={username}')
        return jsonify({'error': 'Account disabled'}), 403
    
    if check_password_hash(user['password_hash'], password):
        session.clear()
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session['auth_time'] = datetime.now().isoformat()
        session['csrf_token'] = secrets.token_hex(32)
        database.append_audit('login_success', client_ip(), actor_user_id=user['id'])
        return jsonify({'success': True})

    database.append_audit('login_failure', client_ip(), detail=f'invalid_password username={username}')
    return jsonify({'error': 'Invalid credentials'}), 401

@auth_bp.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})
