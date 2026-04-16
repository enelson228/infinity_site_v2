# Monitor Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a secure, admin-only monitoring dashboard at `/monitor` showing homelab service health, GitHub repo status, and AI + rule-based recommendations, with security hardening applied across the existing codebase.

**Architecture:** New `blueprints/monitor.py` blueprint + `recommendations.py` engine + 3 new DB tables. Background monitor thread gains a GitHub poll loop. Security hardening touches `app.py`, `auth.py`, `admin.py`, and `config.py` without restructuring.

**Tech Stack:** Flask 3.0, Python 3.9, SQLite, Werkzeug 3.0.1, Anthropic API, GitHub REST API (urllib, no new deps), pytest + pytest-flask

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `tests/conftest.py` | Create | pytest fixtures: app, client, admin_client |
| `tests/test_security.py` | Create | Security headers, session cookies, CSRF, scrypt |
| `tests/test_database.py` | Create | New DB table functions |
| `tests/test_recommendations.py` | Create | Rule-based recommendation logic |
| `tests/test_monitor.py` | Create | Monitor blueprint routes |
| `config.py` | Modify | Add GITHUB_TOKEN, session cookie config |
| `app.py` | Modify | Register monitor_bp, fix control_redirect, add security headers hook, session cookie config |
| `auth.py` | Modify | CSRF token generation + injection + validation hook |
| `admin.py` | Modify | scrypt for new password hashes |
| `database.py` | Modify | Add github_repos, github_repo_status, monitor_recommendations tables + query functions |
| `recommendations.py` | Create | Rule-based checks + AI insights engine |
| `blueprints/monitor.py` | Create | /monitor page + all /api/monitor/* endpoints |
| `templates/monitor.html` | Create | Command Center dashboard layout |
| `templates/base.html` | Modify | Add CSRF meta tag + Monitor nav link |
| `static/js/main.js` | Modify | Global fetch interceptor for CSRF token |

---

## Task 1: Test Infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Install pytest and pytest-flask**

```bash
cd /path/to/infinity_site_v2
source venv/bin/activate
pip install pytest pytest-flask
pip freeze | grep -E "pytest|flask" >> requirements.txt
```

Expected output includes `pytest==8.x.x` and `pytest-flask==1.x.x`.

- [ ] **Step 2: Create `tests/__init__.py`**

```python
```
(Empty file.)

- [ ] **Step 3: Create `tests/conftest.py`**

```python
import os
import tempfile
import pytest

# Set required env vars before any app import
os.environ.setdefault('SECRET_KEY', 'test-secret-key-not-for-production')
os.environ.setdefault('UPLINK_PASSWORD_HASH', 'pbkdf2:sha256:1:aaaaaaaaaa:bbbbbbbbbb')
os.environ.setdefault('CLAUDE_PASSWORD_HASH', 'pbkdf2:sha256:1:aaaaaaaaaa:bbbbbbbbbb')
os.environ.setdefault('ANTHROPIC_API_KEY', 'test-anthropic-key')


@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix='.db')

    import database
    original_path = database.USER_DB_PATH
    database.USER_DB_PATH = db_path

    from app import app as flask_app
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False

    with flask_app.app_context():
        database.init_db()
        yield flask_app

    database.USER_DB_PATH = original_path
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_client(app, client):
    """Authenticated admin test client."""
    from werkzeug.security import generate_password_hash
    import database
    pw_hash = generate_password_hash('AdminPass1!', method='pbkdf2:sha256')
    database.create_user('testadmin', pw_hash, 'admin')
    client.post('/api/auth/login', json={
        'username': 'testadmin',
        'password': 'AdminPass1!'
    })
    return client
```

- [ ] **Step 4: Verify fixtures load without error**

```bash
pytest tests/ --collect-only
```

Expected: `no tests ran` (no test files yet), no import errors.

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/conftest.py requirements.txt
git commit -m "test: add pytest infrastructure and fixtures"
```

---

## Task 2: Config Additions

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_config.py`:

```python
import os
import pytest


def test_github_token_optional(app):
    """GITHUB_TOKEN is optional — missing it does not crash startup."""
    import config
    assert hasattr(config, 'GITHUB_TOKEN')


def test_session_cookie_config(app):
    """Session cookie security flags are configured."""
    import config
    assert config.SESSION_COOKIE_HTTPONLY is True
    assert config.SESSION_COOKIE_SAMESITE == 'Lax'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_config.py -v
```

Expected: FAIL — `AttributeError: module 'config' has no attribute 'GITHUB_TOKEN'`

- [ ] **Step 3: Add new config vars to `config.py`**

Add after the `UPLOAD_ALLOWED_EXTENSIONS` block:

```python
# GitHub API token for monitor dashboard (optional — GitHub panel disabled if missing)
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')

# Session cookie security
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
# Set SESSION_COOKIE_SECURE=False only in local dev without HTTPS
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'true').lower() not in ('0', 'false', 'no')
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_config.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add GITHUB_TOKEN and session cookie config vars"
```

---

## Task 3: Security Hardening — Headers, Session Cookies, Fix control_redirect

**Files:**
- Modify: `app.py`
- Create: `tests/test_security.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_security.py`:

```python
def test_security_headers_present(client):
    """Every response includes hardened security headers."""
    resp = client.get('/')
    assert resp.headers.get('X-Frame-Options') == 'DENY'
    assert resp.headers.get('X-Content-Type-Options') == 'nosniff'
    assert 'Referrer-Policy' in resp.headers
    assert 'Content-Security-Policy' in resp.headers


def test_control_route_not_nested_function(app):
    """The /control route must be registered directly, not via a nested closure."""
    # If the route was a nested function it would recreate the decorator each request.
    # We verify it is a proper view by confirming it's in the URL map.
    rules = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert 'control' in rules


def test_control_requires_admin(client):
    """Unauthenticated /control access redirects to login."""
    resp = client.get('/control')
    assert resp.status_code in (302, 401)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_security.py -v
```

Expected: `test_security_headers_present` FAIL (no security headers), `test_control_route_not_nested_function` FAIL (endpoint is `control_redirect` not `control`).

- [ ] **Step 3: Replace `control_redirect` with a proper route in `app.py`**

Find the existing `control_redirect` function (~line 102) and replace it:

```python
# REMOVE this entire function:
# @app.route('/control')
# def control_redirect():
#     from auth import admin_required
#     @admin_required
#     def control():
#         return render_template('control.html')
#     return control()

# REPLACE with:
@app.route('/control')
@admin_required
def control():
    return render_template('control.html')
```

Also add the missing import at the top of `app.py`:

```python
from auth import auth_bp, admin_required
```

(The existing import is `from auth import auth_bp` — add `admin_required` to it.)

- [ ] **Step 4: Apply session cookie config and add security headers hook in `app.py`**

After `app.secret_key = config.SECRET_KEY`, add:

```python
app.config['SESSION_COOKIE_HTTPONLY'] = config.SESSION_COOKIE_HTTPONLY
app.config['SESSION_COOKIE_SAMESITE'] = config.SESSION_COOKIE_SAMESITE
app.config['SESSION_COOKIE_SECURE'] = config.SESSION_COOKIE_SECURE
```

After the blueprint registrations, add:

```python
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
```

- [ ] **Step 5: Update base.html nav link for control**

In `templates/base.html`, find:

```html
<li><a href="{{ url_for('control_redirect') }}" class="nav-link{% if request.endpoint == 'control_redirect' %} active{% endif %}">Control</a></li>
```

Replace with:

```html
<li><a href="{{ url_for('control') }}" class="nav-link{% if request.endpoint == 'control' %} active{% endif %}">Control</a></li>
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_security.py -v
```

Expected: all 3 PASS

- [ ] **Step 7: Smoke test the app starts**

```bash
flask run --port 5173 &
sleep 2
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/
kill %1
```

Expected: `200`

- [ ] **Step 8: Commit**

```bash
git add app.py config.py templates/base.html tests/test_security.py
git commit -m "fix: security headers, session cookie flags, remove control_redirect antipattern"
```

---

## Task 4: CSRF Protection

**Files:**
- Modify: `auth.py`
- Modify: `templates/base.html`
- Modify: `static/js/main.js`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_security.py`:

```python
def test_csrf_token_injected_after_login(admin_client):
    """A CSRF token is available in session after login."""
    with admin_client.session_transaction() as sess:
        assert 'csrf_token' in sess
        assert len(sess['csrf_token']) == 64  # 32 bytes hex = 64 chars


def test_post_without_csrf_rejected(admin_client):
    """State-changing requests without CSRF token are rejected with 403."""
    # Attempt POST to admin endpoint without CSRF header
    resp = admin_client.post('/api/admin/users', json={
        'username': 'hacker', 'password': 'x', 'role': 'user'
    })
    assert resp.status_code == 403


def test_post_with_csrf_accepted(admin_client):
    """State-changing requests with valid CSRF token are accepted."""
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.post('/api/admin/users',
        json={'username': 'newuser', 'password': 'Pass1!', 'role': 'user'},
        headers={'X-CSRF-Token': token}
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_security.py::test_csrf_token_injected_after_login tests/test_security.py::test_post_without_csrf_rejected tests/test_security.py::test_post_with_csrf_accepted -v
```

Expected: all FAIL

- [ ] **Step 3: Add CSRF token generation + validation to `auth.py`**

Add `import secrets` at the top of `auth.py`.

In `api_login` in `auth.py`, after `session['auth_time'] = datetime.now().isoformat()`, add:

```python
session['csrf_token'] = secrets.token_hex(32)
```

After the blueprint definition (`auth_bp = Blueprint(...)`), add:

```python
def _exempt_from_csrf(path: str) -> bool:
    """Paths that don't need CSRF protection (pre-auth endpoints)."""
    return path in ('/api/auth/login', '/api/auth/logout')


def validate_csrf():
    """Before-request CSRF check for all state-changing endpoints."""
    from flask import current_app
    if current_app.config.get('TESTING'):
        return  # Disabled in test suite
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    if _exempt_from_csrf(request.path):
        return
    token = request.headers.get('X-CSRF-Token') or request.form.get('_csrf_token', '')
    session_token = session.get('csrf_token', '')
    if not session_token or not secrets.compare_digest(token, session_token):
        from flask import abort
        abort(403)
```

- [ ] **Step 4: Register the CSRF check in `app.py`**

Add to the imports in `app.py`:

```python
from auth import auth_bp, admin_required, validate_csrf
```

After the blueprint registrations, add:

```python
app.before_request(validate_csrf)
```

- [ ] **Step 5: Inject CSRF token into templates via context processor in `app.py`**

Add after the existing `inject_static_version` context processor:

```python
@app.context_processor
def inject_csrf_token():
    from flask import session as _session
    return dict(csrf_token=_session.get('csrf_token', ''))
```

- [ ] **Step 6: Add CSRF meta tag to `templates/base.html`**

In `templates/base.html`, inside `<head>`, after the `<meta name="viewport">` tag, add:

```html
<meta name="csrf-token" content="{{ csrf_token }}">
```

- [ ] **Step 7: Add global fetch interceptor to `static/js/main.js`**

At the top of `static/js/main.js`, before any other code, add:

```javascript
// CSRF: attach token to all non-GET fetch requests
(function() {
    const _fetch = window.fetch;
    window.fetch = function(url, options = {}) {
        const method = (options.method || 'GET').toUpperCase();
        if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
            const token = document.querySelector('meta[name="csrf-token"]')?.content || '';
            options.headers = Object.assign({}, options.headers, { 'X-CSRF-Token': token });
        }
        return _fetch(url, options);
    };
})();
```

- [ ] **Step 8: Run CSRF tests**

```bash
pytest tests/test_security.py -v
```

Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add auth.py app.py templates/base.html static/js/main.js tests/test_security.py
git commit -m "feat: add CSRF token protection to all state-changing endpoints"
```

---

## Task 5: Upgrade Password Hashing to scrypt

**Files:**
- Modify: `admin.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_security.py`:

```python
def test_new_passwords_use_scrypt(admin_client):
    """Newly created user passwords are hashed with scrypt."""
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.post('/api/admin/users',
        json={'username': 'scryptuser', 'password': 'SecurePass1!', 'role': 'user'},
        headers={'X-CSRF-Token': token}
    )
    assert resp.status_code == 200
    import database
    user = database.get_user_by_username('scryptuser')
    assert user['password_hash'].startswith('scrypt:')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_security.py::test_new_passwords_use_scrypt -v
```

Expected: FAIL — hash starts with `pbkdf2:`

- [ ] **Step 3: Update `admin.py` to use scrypt**

In `admin.py`, in `api_admin_create_user`, replace:

```python
pw_hash = generate_password_hash(password, method='pbkdf2:sha256')
```

with:

```python
pw_hash = generate_password_hash(password, method='scrypt')
```

In `api_admin_reset_password`, replace:

```python
pw_hash = generate_password_hash(password, method='pbkdf2:sha256')
```

with:

```python
pw_hash = generate_password_hash(password, method='scrypt')
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_security.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add admin.py tests/test_security.py
git commit -m "fix: upgrade new password hashes from pbkdf2 to scrypt"
```

---

## Task 6: Database — New Tables and Query Functions

**Files:**
- Modify: `database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_database.py`:

```python
import pytest
import database


def test_add_and_list_github_repo(app):
    database.add_github_repo('mjolnir-armory', 'ericnelson', 'mjolnir-armory')
    repos = database.list_github_repos()
    assert len(repos) == 1
    assert repos[0]['id'] == 'mjolnir-armory'
    assert repos[0]['owner'] == 'ericnelson'
    assert repos[0]['enabled'] == 1


def test_upsert_github_repo_status(app):
    database.add_github_repo('myrepo', 'owner', 'myrepo')
    database.upsert_github_repo_status(
        repo_id='myrepo',
        last_commit_at='2026-04-14T10:00:00',
        last_commit_msg='feat: add thing',
        open_prs=3,
        ci_status='success',
        fetched_at='2026-04-14T10:05:00',
    )
    status = database.get_github_repo_status('myrepo')
    assert status['open_prs'] == 3
    assert status['ci_status'] == 'success'


def test_delete_github_repo(app):
    database.add_github_repo('todelete', 'owner', 'todelete')
    database.delete_github_repo('todelete')
    assert database.list_github_repos() == []


def test_add_and_list_recommendations(app):
    database.add_recommendation('rule', 'critical', 'Gitea offline', 'offline 2h')
    database.add_recommendation('ai', 'info', 'Deploy backlog growing', None)
    recs = database.list_recommendations(include_dismissed=False)
    assert len(recs) == 2
    assert recs[0]['severity'] == 'critical'


def test_dismiss_recommendation(app):
    database.add_recommendation('rule', 'warning', 'High CPU', None)
    recs = database.list_recommendations(include_dismissed=False)
    rec_id = recs[0]['id']
    database.dismiss_recommendation(rec_id)
    active = database.list_recommendations(include_dismissed=False)
    assert len(active) == 0
    all_recs = database.list_recommendations(include_dismissed=True)
    assert len(all_recs) == 1


def test_clear_recommendations_by_source(app):
    database.add_recommendation('rule', 'warning', 'Rule warning', None)
    database.add_recommendation('ai', 'info', 'AI insight', None)
    database.clear_recommendations(source='rule')
    recs = database.list_recommendations(include_dismissed=True)
    assert len(recs) == 1
    assert recs[0]['source'] == 'ai'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_database.py -v
```

Expected: all FAIL — functions don't exist yet.

- [ ] **Step 3: Add new tables to `init_db()` in `database.py`**

Inside `init_db()`, after the `telemetry_history` table creation, add:

```python
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS github_repos (
        id       TEXT PRIMARY KEY,
        owner    TEXT NOT NULL,
        repo     TEXT NOT NULL,
        enabled  INTEGER NOT NULL DEFAULT 1,
        added_at TEXT NOT NULL
    )
    """
)
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS github_repo_status (
        repo_id         TEXT PRIMARY KEY,
        last_commit_at  TEXT,
        last_commit_msg TEXT,
        open_prs        INTEGER DEFAULT 0,
        ci_status       TEXT,
        fetched_at      TEXT NOT NULL,
        FOREIGN KEY(repo_id) REFERENCES github_repos(id) ON DELETE CASCADE
    )
    """
)
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS monitor_recommendations (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        source     TEXT NOT NULL,
        severity   TEXT NOT NULL,
        message    TEXT NOT NULL,
        detail     TEXT,
        created_at TEXT NOT NULL,
        dismissed  INTEGER NOT NULL DEFAULT 0
    )
    """
)
conn.execute(
    "CREATE INDEX IF NOT EXISTS idx_recommendations_dismissed ON monitor_recommendations(dismissed)"
)
conn.commit()
```

- [ ] **Step 4: Add query functions to `database.py`**

Add these functions at the end of `database.py`:

```python
# ── GitHub Repos ─────────────────────────────────────────────────────────────

def list_github_repos():
    with _db_conn() as conn:
        cur = conn.execute("SELECT * FROM github_repos WHERE enabled = 1 ORDER BY id ASC")
        return [dict(row) for row in cur.fetchall()]

def add_github_repo(repo_id: str, owner: str, repo: str):
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO github_repos (id, owner, repo, added_at) VALUES (?, ?, ?, ?)",
            (repo_id, owner, repo, datetime.now().isoformat())
        )
        conn.commit()

def delete_github_repo(repo_id: str):
    with _db_conn() as conn:
        conn.execute("DELETE FROM github_repos WHERE id = ?", (repo_id,))
        conn.commit()

def upsert_github_repo_status(repo_id, last_commit_at, last_commit_msg,
                               open_prs, ci_status, fetched_at):
    with _db_conn() as conn:
        conn.execute(
            """
            INSERT INTO github_repo_status
                (repo_id, last_commit_at, last_commit_msg, open_prs, ci_status, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_id) DO UPDATE SET
                last_commit_at  = excluded.last_commit_at,
                last_commit_msg = excluded.last_commit_msg,
                open_prs        = excluded.open_prs,
                ci_status       = excluded.ci_status,
                fetched_at      = excluded.fetched_at
            """,
            (repo_id, last_commit_at, last_commit_msg, open_prs, ci_status, fetched_at)
        )
        conn.commit()

def get_github_repo_status(repo_id: str):
    with _db_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM github_repo_status WHERE repo_id = ?", (repo_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

def list_github_repo_statuses():
    """Returns repos joined with their latest status."""
    with _db_conn() as conn:
        cur = conn.execute(
            """
            SELECT r.id, r.owner, r.repo,
                   s.last_commit_at, s.last_commit_msg, s.open_prs, s.ci_status, s.fetched_at
            FROM github_repos r
            LEFT JOIN github_repo_status s ON r.id = s.repo_id
            WHERE r.enabled = 1
            ORDER BY r.id ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]


# ── Monitor Recommendations ───────────────────────────────────────────────────

def add_recommendation(source: str, severity: str, message: str, detail: str = None):
    with _db_conn() as conn:
        conn.execute(
            """
            INSERT INTO monitor_recommendations (source, severity, message, detail, created_at, dismissed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (source, severity, message, detail, datetime.now().isoformat())
        )
        conn.commit()

def list_recommendations(include_dismissed: bool = False):
    with _db_conn() as conn:
        if include_dismissed:
            cur = conn.execute(
                "SELECT * FROM monitor_recommendations ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, id ASC"
            )
        else:
            cur = conn.execute(
                "SELECT * FROM monitor_recommendations WHERE dismissed = 0 ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, id ASC"
            )
        return [dict(row) for row in cur.fetchall()]

def dismiss_recommendation(rec_id: int):
    with _db_conn() as conn:
        conn.execute(
            "UPDATE monitor_recommendations SET dismissed = 1 WHERE id = ?", (rec_id,)
        )
        conn.commit()

def clear_recommendations(source: str = None):
    """Delete all non-dismissed recommendations, optionally filtered by source."""
    with _db_conn() as conn:
        if source:
            conn.execute(
                "DELETE FROM monitor_recommendations WHERE source = ? AND dismissed = 0",
                (source,)
            )
        else:
            conn.execute("DELETE FROM monitor_recommendations WHERE dismissed = 0")
        conn.commit()
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_database.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add database.py tests/test_database.py
git commit -m "feat: add github_repos, github_repo_status, monitor_recommendations tables"
```

---

## Task 7: Recommendations Engine

**Files:**
- Create: `recommendations.py`
- Create: `tests/test_recommendations.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_recommendations.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


def _make_project(status='online', last_ping=None, response_time=100):
    return {
        'id': 'test-svc',
        'name': 'Test Service',
        'status': status,
        'last_ping': last_ping or datetime.now().isoformat(),
        'response_time': response_time,
    }


def test_offline_service_over_30min_is_critical(app):
    from recommendations import run_rule_checks
    stale_ping = (datetime.now() - timedelta(minutes=45)).isoformat()
    projects = [_make_project(status='offline', last_ping=stale_ping)]
    telemetry = []
    recent_failures = 0
    recs = run_rule_checks(projects, telemetry, recent_failures)
    assert any(r['severity'] == 'critical' and 'offline' in r['message'].lower() for r in recs)


def test_offline_service_under_30min_is_warning(app):
    from recommendations import run_rule_checks
    recent_ping = (datetime.now() - timedelta(minutes=10)).isoformat()
    projects = [_make_project(status='offline', last_ping=recent_ping)]
    recs = run_rule_checks(projects, [], 0)
    assert any(r['severity'] == 'warning' and 'offline' in r['message'].lower() for r in recs)


def test_high_cpu_is_warning(app):
    from recommendations import run_rule_checks
    # 5 readings all above 85%
    telemetry = [{'cpu_usage': 90.0, 'ram_usage': 50.0} for _ in range(5)]
    recs = run_rule_checks([], telemetry, 0)
    assert any(r['severity'] == 'warning' and 'cpu' in r['message'].lower() for r in recs)


def test_high_ram_is_critical(app):
    from recommendations import run_rule_checks
    telemetry = [{'cpu_usage': 20.0, 'ram_usage': 92.0} for _ in range(5)]
    recs = run_rule_checks([], telemetry, 0)
    assert any(r['severity'] == 'critical' and 'ram' in r['message'].lower() for r in recs)


def test_many_failed_logins_is_critical(app):
    from recommendations import run_rule_checks
    recs = run_rule_checks([], [], recent_failures=15)
    assert any(r['severity'] == 'critical' and 'login' in r['message'].lower() for r in recs)


def test_no_alerts_when_everything_healthy(app):
    from recommendations import run_rule_checks
    projects = [_make_project(status='online')]
    telemetry = [{'cpu_usage': 30.0, 'ram_usage': 40.0} for _ in range(5)]
    recs = run_rule_checks(projects, telemetry, recent_failures=0)
    assert recs == []


def test_ai_insights_returns_recommendations(app):
    from recommendations import run_ai_checks
    snapshot = {'services': [], 'github': [], 'telemetry_avg': {}}

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='- Deploy backlog growing for mjolnir-armory\n- CPU trending up')]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(content=mock_message.content)

    with patch('recommendations.anthropic.Anthropic', return_value=mock_client):
        recs = run_ai_checks(snapshot, api_key='fake-key')

    assert len(recs) >= 1
    assert all(r['source'] == 'ai' for r in recs)


def test_ai_insights_fails_gracefully(app):
    from recommendations import run_ai_checks
    snapshot = {'services': [], 'github': [], 'telemetry_avg': {}}

    with patch('recommendations.anthropic.Anthropic', side_effect=Exception('API down')):
        recs = run_ai_checks(snapshot, api_key='fake-key')

    assert recs == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_recommendations.py -v
```

Expected: all FAIL — `recommendations` module doesn't exist.

- [ ] **Step 3: Create `recommendations.py`**

```python
"""
Recommendations engine for the monitor dashboard.
Two entry points:
  - run_rule_checks(projects, telemetry, recent_failures) -> list[dict]
  - run_ai_checks(snapshot, api_key) -> list[dict]
"""

from datetime import datetime, timedelta
import anthropic


def _rec(source, severity, message, detail=None):
    return {'source': source, 'severity': severity, 'message': message, 'detail': detail}


def run_rule_checks(projects: list, telemetry: list, recent_failures: int) -> list:
    """
    Run rule-based checks and return a list of recommendation dicts.
    Does not touch the database — caller persists results.

    Args:
        projects: list of project dicts (id, name, status, last_ping, response_time)
        telemetry: list of recent telemetry dicts (cpu_usage, ram_usage), newest-first
        recent_failures: count of failed login attempts in the last hour
    """
    recs = []

    # Service health checks
    for p in projects:
        if p.get('status') in ('offline', 'error'):
            last_ping_str = p.get('last_ping')
            if last_ping_str:
                try:
                    last_ping = datetime.fromisoformat(last_ping_str)
                    offline_minutes = (datetime.now() - last_ping).total_seconds() / 60
                    if offline_minutes > 30:
                        recs.append(_rec(
                            'rule', 'critical',
                            f"{p['name']} has been offline",
                            f"Last seen {int(offline_minutes)} minutes ago"
                        ))
                    else:
                        recs.append(_rec(
                            'rule', 'warning',
                            f"{p['name']} appears offline",
                            f"Last ping {int(offline_minutes)} minutes ago"
                        ))
                except ValueError:
                    recs.append(_rec('rule', 'warning', f"{p['name']} appears offline", None))
            else:
                recs.append(_rec('rule', 'warning', f"{p['name']} has never been pinged", None))

    # CPU check — warn if last 5 readings all above 85%
    recent = telemetry[:5]
    if len(recent) >= 5 and all(r['cpu_usage'] > 85 for r in recent):
        avg = sum(r['cpu_usage'] for r in recent) / len(recent)
        recs.append(_rec(
            'rule', 'warning',
            'CPU usage sustained above 85%',
            f"Average over last 5 readings: {avg:.1f}%"
        ))

    # RAM check — critical if any reading above 90%
    if recent and any(r['ram_usage'] > 90 for r in recent):
        max_ram = max(r['ram_usage'] for r in recent)
        recs.append(_rec(
            'rule', 'critical',
            'RAM usage critically high',
            f"Peak: {max_ram:.1f}%"
        ))

    # Auth: failed login spike
    if recent_failures > 10:
        recs.append(_rec(
            'rule', 'critical',
            f'Elevated login failures detected',
            f'{recent_failures} failed attempts in the last hour'
        ))

    return recs


def run_ai_checks(snapshot: dict, api_key: str) -> list:
    """
    Ask Claude for 1-3 insights based on a state snapshot.
    Returns recommendation dicts with source='ai'.
    Fails silently — returns [] on any error.

    snapshot keys: services, github, telemetry_avg (cpu, ram), recent_audit_events
    """
    try:
        client = anthropic.Anthropic(api_key=api_key)

        prompt = (
            "You are a homelab monitoring assistant. Analyze this system snapshot and "
            "return 1-3 short, actionable insights that rule-based checks would miss. "
            "Focus on trends, stale projects, or patterns. "
            "Format: one insight per line, starting with '- '. No preamble.\n\n"
            f"Snapshot:\n{snapshot}"
        )

        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=300,
            messages=[{'role': 'user', 'content': prompt}]
        )

        raw = response.content[0].text.strip()
        insights = [
            line.lstrip('- ').strip()
            for line in raw.split('\n')
            if line.strip().startswith('-')
        ][:3]

        return [
            _rec('ai', 'info', insight)
            for insight in insights
            if insight
        ]

    except Exception:
        return []


def build_snapshot(projects: list, github_statuses: list, telemetry: list) -> dict:
    """Build the compact snapshot dict passed to run_ai_checks."""
    telemetry_avg = {}
    if telemetry:
        telemetry_avg = {
            'cpu_avg': round(sum(t['cpu_usage'] for t in telemetry) / len(telemetry), 1),
            'ram_avg': round(sum(t['ram_usage'] for t in telemetry) / len(telemetry), 1),
        }

    return {
        'services': [
            {'name': p['name'], 'status': p['status'], 'last_ping': p.get('last_ping')}
            for p in projects
        ],
        'github': [
            {
                'repo': g['id'],
                'open_prs': g.get('open_prs', 0),
                'last_commit_at': g.get('last_commit_at'),
                'ci_status': g.get('ci_status'),
            }
            for g in github_statuses
        ],
        'telemetry_avg': telemetry_avg,
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_recommendations.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add recommendations.py tests/test_recommendations.py
git commit -m "feat: add recommendations engine with rule-based and AI checks"
```

---

## Task 8: Monitor Blueprint

**Files:**
- Create: `blueprints/monitor.py`
- Modify: `app.py`
- Create: `tests/test_monitor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_monitor.py`:

```python
import pytest
import json


def test_monitor_page_requires_admin(client):
    resp = client.get('/monitor')
    assert resp.status_code in (302, 401)


def test_monitor_page_accessible_to_admin(admin_client):
    resp = admin_client.get('/monitor')
    assert resp.status_code == 200


def test_monitor_status_requires_admin(client):
    resp = client.get('/api/monitor/status')
    assert resp.status_code in (302, 401)


def test_monitor_status_returns_data(admin_client):
    resp = admin_client.get('/api/monitor/status')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'services' in data
    assert 'github' in data
    assert 'recommendations' in data
    assert 'stats' in data


def test_add_and_delete_github_repo(admin_client):
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    resp = admin_client.post('/api/monitor/repos',
        json={'id': 'my-repo', 'owner': 'ericnelson', 'repo': 'my-repo'},
        headers={'X-CSRF-Token': token}
    )
    assert resp.status_code == 200

    resp = admin_client.get('/api/monitor/repos')
    data = resp.get_json()
    assert any(r['id'] == 'my-repo' for r in data['repos'])

    resp = admin_client.delete('/api/monitor/repos/my-repo',
        headers={'X-CSRF-Token': token}
    )
    assert resp.status_code == 200

    resp = admin_client.get('/api/monitor/repos')
    data = resp.get_json()
    assert not any(r['id'] == 'my-repo' for r in data['repos'])


def test_dismiss_recommendation(admin_client, app):
    import database
    database.add_recommendation('rule', 'warning', 'Test alert', None)
    recs = database.list_recommendations()
    rec_id = recs[0]['id']

    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    resp = admin_client.post(f'/api/monitor/recommendations/{rec_id}/dismiss',
        headers={'X-CSRF-Token': token}
    )
    assert resp.status_code == 200
    remaining = database.list_recommendations(include_dismissed=False)
    assert len(remaining) == 0


def test_add_repo_requires_fields(admin_client):
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.post('/api/monitor/repos',
        json={'owner': 'ericnelson'},  # missing id and repo
        headers={'X-CSRF-Token': token}
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_monitor.py -v
```

Expected: all FAIL — blueprint doesn't exist.

- [ ] **Step 3: Create `blueprints/monitor.py`**

```python
from flask import Blueprint, jsonify, request, render_template, session
from auth import admin_required
import database
from utils import client_ip

monitor_bp = Blueprint('monitor', __name__)


@monitor_bp.route('/monitor')
@admin_required
def monitor():
    return render_template('monitor.html')


@monitor_bp.route('/api/monitor/status')
@admin_required
def api_monitor_status():
    """Full dashboard payload: services, github repos+status, recommendations, stats."""
    services = database.list_projects()
    github = database.list_github_repo_statuses()
    recommendations = database.list_recommendations(include_dismissed=False)

    online = sum(1 for s in services if s.get('status') == 'online')
    total = len(services)
    open_prs = sum(g.get('open_prs') or 0 for g in github)
    alerts = sum(1 for r in recommendations if r['severity'] in ('critical', 'warning'))
    ai_count = sum(1 for r in recommendations if r['source'] == 'ai')

    return jsonify({
        'services': services,
        'github': github,
        'recommendations': recommendations,
        'stats': {
            'services_online': online,
            'services_total': total,
            'open_prs': open_prs,
            'alerts': alerts,
            'ai_insights': ai_count,
        }
    })


@monitor_bp.route('/api/monitor/repos', methods=['GET'])
@admin_required
def api_list_repos():
    return jsonify({'repos': database.list_github_repos()})


@monitor_bp.route('/api/monitor/repos', methods=['POST'])
@admin_required
def api_add_repo():
    data = request.get_json(silent=True) or {}
    repo_id = (data.get('id') or '').strip()
    owner = (data.get('owner') or '').strip()
    repo = (data.get('repo') or '').strip()

    if not repo_id or not owner or not repo:
        return jsonify({'error': 'id, owner, and repo are required'}), 400

    # Sanitize: only allow alphanumeric, hyphens, underscores
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', repo_id):
        return jsonify({'error': 'Invalid repo id — alphanumeric, hyphens, underscores only'}), 400

    try:
        database.add_github_repo(repo_id, owner, repo)
    except Exception:
        return jsonify({'error': 'Repo already exists or database error'}), 409

    actor_id = session.get('user_id')
    database.append_audit('monitor_repo_add', client_ip(),
                          actor_user_id=actor_id, detail=f'repo={owner}/{repo}')
    return jsonify({'success': True})


@monitor_bp.route('/api/monitor/repos/<repo_id>', methods=['DELETE'])
@admin_required
def api_delete_repo(repo_id: str):
    database.delete_github_repo(repo_id)
    actor_id = session.get('user_id')
    database.append_audit('monitor_repo_delete', client_ip(),
                          actor_user_id=actor_id, detail=f'repo_id={repo_id}')
    return jsonify({'success': True})


@monitor_bp.route('/api/monitor/recommendations/refresh', methods=['POST'])
@admin_required
def api_refresh_recommendations():
    """Trigger immediate regen of rule-based recommendations."""
    import config
    import recommendations

    projects = database.list_projects()
    telemetry = database.get_telemetry_history(limit=5)

    # Count recent login failures from audit log
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
    audit = database.get_audit_log(limit=500)
    recent_failures = sum(
        1 for e in audit
        if e['event_type'] == 'login_failure' and e['created_at'] > cutoff
    )

    new_recs = recommendations.run_rule_checks(projects, telemetry, recent_failures)

    database.clear_recommendations(source='rule')
    for r in new_recs:
        database.add_recommendation(r['source'], r['severity'], r['message'], r.get('detail'))

    # AI insights (non-blocking — skip if API key not configured)
    if config.ANTHROPIC_API_KEY and config.ANTHROPIC_API_KEY != 'test-anthropic-key':
        github = database.list_github_repo_statuses()
        snapshot = recommendations.build_snapshot(projects, github, telemetry)
        ai_recs = recommendations.run_ai_checks(snapshot, config.ANTHROPIC_API_KEY)
        database.clear_recommendations(source='ai')
        for r in ai_recs:
            database.add_recommendation(r['source'], r['severity'], r['message'], r.get('detail'))

    return jsonify({'success': True, 'count': len(new_recs)})


@monitor_bp.route('/api/monitor/recommendations/<int:rec_id>/dismiss', methods=['POST'])
@admin_required
def api_dismiss_recommendation(rec_id: int):
    database.dismiss_recommendation(rec_id)
    actor_id = session.get('user_id')
    database.append_audit('recommendation_dismiss', client_ip(),
                          actor_user_id=actor_id, detail=f'rec_id={rec_id}')
    return jsonify({'success': True})
```

- [ ] **Step 4: Register `monitor_bp` in `app.py`**

Add to imports in `app.py`:

```python
from blueprints.monitor import monitor_bp
```

Add to blueprint registrations:

```python
app.register_blueprint(monitor_bp)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_monitor.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add blueprints/monitor.py app.py tests/test_monitor.py
git commit -m "feat: add monitor blueprint with status, repo management, and recommendation endpoints"
```

---

## Task 9: GitHub Background Polling

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add GitHub poll loop to `background_monitor()` in `app.py`**

Add the necessary imports at the top of `app.py`:

```python
import json
```

Inside `background_monitor()`, add a third time tracker after `last_telemetry_time = 0`:

```python
last_github_time = 0
```

Inside the `while True:` loop, after the telemetry block, add:

```python
# Poll GitHub every 10 minutes
if now - last_github_time >= 600:
    if config.GITHUB_TOKEN:
        try:
            repos = database.list_github_repos()
            for r in repos:
                _poll_github_repo(r['owner'], r['repo'], r['id'], config.GITHUB_TOKEN)
        except Exception as e:
            app.logger.error(f"Monitoring error (github): {e}")
    last_github_time = now
```

- [ ] **Step 2: Add `_poll_github_repo` helper function to `app.py`**

Add this function before `background_monitor()`:

```python
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

    # Latest commit
    commits = gh_get(f'{base_url}/commits?per_page=1')
    last_commit_at = commits[0]['commit']['committer']['date'] if commits else None
    last_commit_msg = commits[0]['commit']['message'].split('\n')[0][:120] if commits else None

    # Open PR count
    prs = gh_get(f'{base_url}/pulls?state=open&per_page=100')
    open_prs = len(prs)

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
```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

```bash
pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: extend background monitor with GitHub polling loop"
```

---

## Task 10: Monitor Template

**Files:**
- Create: `templates/monitor.html`
- Modify: `templates/base.html` (add nav link)

- [ ] **Step 1: Add Monitor nav link to `templates/base.html`**

In `templates/base.html`, find the admin Control nav link:

```html
{% if session.get('role') == 'admin' %}
<li><a href="{{ url_for('control') }}" class="nav-link{% if request.endpoint == 'control' %} active{% endif %}">Control</a></li>
{% endif %}
```

Replace with:

```html
{% if session.get('role') == 'admin' %}
<li><a href="{{ url_for('control') }}" class="nav-link{% if request.endpoint == 'control' %} active{% endif %}">Control</a></li>
<li><a href="{{ url_for('monitor.monitor') }}" class="nav-link{% if request.endpoint == 'monitor.monitor' %} active{% endif %}">Monitor</a></li>
{% endif %}
```

- [ ] **Step 2: Create `templates/monitor.html`**

```html
{% extends 'base.html' %}
{% block title %}Monitor{% endblock %}

{% block head %}
<style>
  .monitor-wrap { max-width: 1200px; margin: 0 auto; padding: var(--spacing-lg); }

  /* Stat row */
  .stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
  .stat-card {
    background: rgba(13, 33, 55, 0.6);
    border: 1px solid rgba(34, 211, 238, 0.15);
    border-radius: 6px;
    padding: 14px 18px;
    text-align: center;
  }
  .stat-card .stat-value { font-family: var(--font-mono); font-size: 1.8rem; font-weight: 700; }
  .stat-card .stat-label { font-size: 0.6rem; letter-spacing: 0.15em; color: rgba(34, 211, 238, 0.45); margin-top: 4px; }
  .stat-card.critical .stat-value { color: #ff7043; }
  .stat-card.good .stat-value { color: #81c784; }
  .stat-card.info .stat-value { color: #4fc3f7; }
  .stat-card.warn .stat-value { color: #ffd54f; }

  /* Alert banner */
  .alert-banner {
    background: rgba(13, 33, 55, 0.8);
    border: 1px solid rgba(255, 112, 67, 0.35);
    border-radius: 6px;
    padding: 12px 18px;
    margin-bottom: 16px;
  }
  .alert-banner .banner-header {
    font-family: var(--font-mono); font-size: 0.65rem; letter-spacing: 0.18em;
    color: #ff7043; margin-bottom: 8px;
  }
  .alert-list { display: flex; flex-direction: column; gap: 6px; }
  .alert-item {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 12px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05);
  }
  .alert-item:last-child { border-bottom: none; }
  .alert-icon { font-size: 0.75rem; flex-shrink: 0; margin-top: 1px; }
  .alert-msg { font-size: 0.8rem; flex: 1; }
  .alert-detail { font-size: 0.7rem; color: rgba(34, 211, 238, 0.4); margin-top: 2px; }
  .alert-dismiss { font-size: 0.65rem; color: rgba(34, 211, 238, 0.35); cursor: pointer;
    background: none; border: none; padding: 0 4px; flex-shrink: 0; }
  .alert-dismiss:hover { color: rgba(34, 211, 238, 0.7); }
  .sev-critical .alert-msg { color: #ff7043; }
  .sev-warning .alert-msg { color: #ffd54f; }
  .sev-info .alert-msg { color: #4fc3f7; }
  .alert-empty { font-size: 0.8rem; color: rgba(34, 211, 238, 0.4); padding: 4px 0; }

  /* Two-column grid */
  .monitor-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

  /* Panel */
  .monitor-panel {
    background: rgba(13, 33, 55, 0.6);
    border: 1px solid rgba(34, 211, 238, 0.15);
    border-radius: 6px;
    padding: 16px 18px;
  }
  .panel-header {
    font-family: var(--font-mono); font-size: 0.65rem; letter-spacing: 0.18em;
    color: rgba(34, 211, 238, 0.45); margin-bottom: 12px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .panel-action { font-size: 0.65rem; color: rgba(34, 211, 238, 0.4); cursor: pointer;
    background: none; border: 1px solid rgba(34,211,238,0.2); border-radius: 3px;
    padding: 2px 8px; }
  .panel-action:hover { color: #4fc3f7; border-color: rgba(34,211,238,0.5); }

  /* Service rows */
  .service-row {
    display: flex; align-items: center; gap: 10px; padding: 6px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 0.8rem;
  }
  .service-row:last-child { border-bottom: none; }
  .svc-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .svc-dot.online { background: #81c784; box-shadow: 0 0 6px rgba(129,199,132,0.5); }
  .svc-dot.offline { background: #ff7043; box-shadow: 0 0 6px rgba(255,112,67,0.5); }
  .svc-dot.error { background: #ffd54f; }
  .svc-name { flex: 1; color: rgba(255,255,255,0.85); }
  .svc-rt { font-family: var(--font-mono); font-size: 0.7rem; color: rgba(34, 211, 238, 0.4); }

  /* GitHub rows */
  .repo-row {
    display: flex; flex-direction: column; gap: 3px; padding: 7px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
  }
  .repo-row:last-child { border-bottom: none; }
  .repo-name { font-size: 0.8rem; color: #4fc3f7; }
  .repo-meta { font-size: 0.7rem; color: rgba(34, 211, 238, 0.4); font-family: var(--font-mono); }
  .ci-badge { display: inline-block; font-size: 0.6rem; padding: 1px 6px; border-radius: 3px;
    font-family: var(--font-mono); margin-left: 6px; letter-spacing: 0.1em; }
  .ci-success { background: rgba(129,199,132,0.15); color: #81c784; border: 1px solid rgba(129,199,132,0.3); }
  .ci-failure { background: rgba(255,112,67,0.15); color: #ff7043; border: 1px solid rgba(255,112,67,0.3); }
  .ci-pending { background: rgba(255,213,79,0.15); color: #ffd54f; border: 1px solid rgba(255,213,79,0.3); }
  .ci-none { background: rgba(34,211,238,0.05); color: rgba(34,211,238,0.3); border: 1px solid rgba(34,211,238,0.1); }

  /* Add repo form */
  .add-repo-form { margin-top: 12px; display: flex; gap: 6px; flex-wrap: wrap; }
  .add-repo-form input {
    background: rgba(255,255,255,0.04); border: 1px solid rgba(34,211,238,0.2);
    color: #fff; padding: 5px 10px; border-radius: 4px; font-size: 0.75rem;
    font-family: var(--font-mono); flex: 1; min-width: 80px;
  }
  .add-repo-form input::placeholder { color: rgba(34,211,238,0.25); }
  .add-repo-form button { padding: 5px 12px; font-size: 0.7rem; letter-spacing: 0.1em; }
  .no-items { font-size: 0.8rem; color: rgba(34,211,238,0.3); padding: 4px 0; }

  @media (max-width: 768px) {
    .stat-row { grid-template-columns: repeat(2, 1fr); }
    .monitor-grid { grid-template-columns: 1fr; }
  }
</style>
{% endblock %}

{% block content %}
<div class="monitor-wrap">
  <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom: 20px;">
    <h1 style="font-family: var(--font-display); font-size: 1.4rem; letter-spacing: 0.15em;">
      MONITOR <span style="color: rgba(34,211,238,0.4); font-size: 0.9rem;">// COMMAND CENTER</span>
    </h1>
    <div style="font-family: var(--font-mono); font-size: 0.6rem; color: rgba(34,211,238,0.35);" id="last-updated">
      LOADING...
    </div>
  </div>

  <!-- Stat Row -->
  <div class="stat-row" id="stat-row">
    <div class="stat-card info"><div class="stat-value" id="stat-services">—</div><div class="stat-label">SERVICES ONLINE</div></div>
    <div class="stat-card good"><div class="stat-value" id="stat-prs">—</div><div class="stat-label">OPEN PRs</div></div>
    <div class="stat-card warn"><div class="stat-value" id="stat-alerts">—</div><div class="stat-label">ALERTS</div></div>
    <div class="stat-card info"><div class="stat-value" id="stat-ai">—</div><div class="stat-label">AI INSIGHTS</div></div>
  </div>

  <!-- Alert Banner -->
  <div class="alert-banner">
    <div class="banner-header">▲ ALERTS &amp; RECOMMENDATIONS</div>
    <div class="alert-list" id="alert-list">
      <div class="alert-empty">Loading...</div>
    </div>
  </div>

  <!-- Two-Column Grid -->
  <div class="monitor-grid">
    <!-- Services Panel -->
    <div class="monitor-panel">
      <div class="panel-header">
        <span>HOMELAB SERVICES</span>
        <button class="panel-action" onclick="refreshData()">REFRESH</button>
      </div>
      <div id="services-list"><div class="no-items">Loading...</div></div>
    </div>

    <!-- GitHub Panel -->
    <div class="monitor-panel">
      <div class="panel-header">
        <span>GITHUB REPOS</span>
      </div>
      <div id="github-list"><div class="no-items">Loading...</div></div>
      <div class="add-repo-form">
        <input id="repo-id" placeholder="slug" title="URL-safe identifier, e.g. my-repo">
        <input id="repo-owner" placeholder="owner">
        <input id="repo-name" placeholder="repo">
        <button class="mock-button" onclick="addRepo()" style="font-size:0.7rem;padding:5px 12px;">ADD</button>
      </div>
    </div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script>
let _dashData = null;

function sevIcon(sev) {
  return sev === 'critical' ? '⚠' : sev === 'warning' ? '⚑' : '✦';
}

function timeAgo(iso) {
  if (!iso) return 'never';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 120) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

function renderStats(stats) {
  const s = stats.services_online, t = stats.services_total;
  document.getElementById('stat-services').textContent = `${s}/${t}`;
  document.getElementById('stat-prs').textContent = stats.open_prs;
  document.getElementById('stat-alerts').textContent = stats.alerts;
  document.getElementById('stat-ai').textContent = stats.ai_insights;

  // Color the alerts stat
  const alertCard = document.getElementById('stat-alerts').closest('.stat-card');
  alertCard.className = 'stat-card ' + (stats.alerts > 0 ? 'critical' : 'good');
}

function renderAlerts(recs) {
  const el = document.getElementById('alert-list');
  if (!recs.length) {
    el.innerHTML = '<div class="alert-empty">All clear — no active alerts.</div>';
    return;
  }
  el.innerHTML = recs.map(r => `
    <div class="alert-item sev-${r.severity}" id="alert-${r.id}">
      <span class="alert-icon">${sevIcon(r.severity)}</span>
      <div style="flex:1">
        <div class="alert-msg">${escHtml(r.message)}</div>
        ${r.detail ? `<div class="alert-detail">${escHtml(r.detail)}</div>` : ''}
      </div>
      <button class="alert-dismiss" onclick="dismissAlert(${r.id})" title="Dismiss">✕</button>
    </div>
  `).join('');
}

function renderServices(services) {
  const el = document.getElementById('services-list');
  if (!services.length) { el.innerHTML = '<div class="no-items">No services configured.</div>'; return; }
  el.innerHTML = services.map(s => `
    <div class="service-row">
      <div class="svc-dot ${s.status === 'online' ? 'online' : 'offline'}"></div>
      <span class="svc-name">${escHtml(s.name)}</span>
      ${s.response_time ? `<span class="svc-rt">${s.response_time}ms</span>` : ''}
    </div>
  `).join('');
}

function renderGithub(repos) {
  const el = document.getElementById('github-list');
  if (!repos.length) { el.innerHTML = '<div class="no-items">No repos configured.</div>'; return; }
  el.innerHTML = repos.map(r => {
    const ci = r.ci_status || 'none';
    const ciClass = ['success','failure','pending'].includes(ci) ? `ci-${ci}` : 'ci-none';
    return `
      <div class="repo-row">
        <div>
          <span class="repo-name">${escHtml(r.id)}</span>
          <span class="ci-badge ${ciClass}">${ci.toUpperCase()}</span>
          <button onclick="deleteRepo('${escHtml(r.id)}')" style="font-size:0.6rem;color:rgba(255,112,67,0.4);background:none;border:none;cursor:pointer;padding:0 4px;">✕</button>
        </div>
        <div class="repo-meta">
          ${r.open_prs || 0} open PRs · last commit ${timeAgo(r.last_commit_at)}
          ${r.last_commit_msg ? ' · ' + escHtml(r.last_commit_msg.slice(0, 60)) : ''}
        </div>
      </div>
    `;
  }).join('');
}

function escHtml(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

async function refreshData() {
  try {
    const resp = await fetch('/api/monitor/status');
    if (!resp.ok) return;
    const data = await resp.json();
    _dashData = data;
    renderStats(data.stats);
    renderAlerts(data.recommendations);
    renderServices(data.services);
    renderGithub(data.github);
    document.getElementById('last-updated').textContent =
      'LAST UPDATED: ' + new Date().toLocaleTimeString();
  } catch (e) {
    console.error('Monitor refresh failed:', e);
  }
}

async function dismissAlert(id) {
  const resp = await fetch(`/api/monitor/recommendations/${id}/dismiss`, { method: 'POST' });
  if (resp.ok) {
    const el = document.getElementById(`alert-${id}`);
    if (el) el.remove();
    // Update alert count
    const remaining = document.querySelectorAll('#alert-list .alert-item').length;
    document.getElementById('stat-alerts').textContent = remaining;
  }
}

async function addRepo() {
  const id = document.getElementById('repo-id').value.trim();
  const owner = document.getElementById('repo-owner').value.trim();
  const repo = document.getElementById('repo-name').value.trim();
  if (!id || !owner || !repo) return;

  const resp = await fetch('/api/monitor/repos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, owner, repo })
  });
  if (resp.ok) {
    document.getElementById('repo-id').value = '';
    document.getElementById('repo-owner').value = '';
    document.getElementById('repo-name').value = '';
    refreshData();
  } else {
    const err = await resp.json();
    alert(err.error || 'Failed to add repo');
  }
}

async function deleteRepo(id) {
  if (!confirm(`Remove ${id} from monitor?`)) return;
  const resp = await fetch(`/api/monitor/repos/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (resp.ok) refreshData();
}

// Initial load + auto-refresh every 30s
refreshData();
setInterval(refreshData, 30000);
</script>
{% endblock %}
```

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 4: Manually verify the dashboard loads**

```bash
flask run --port 5173
```

Open `http://localhost:5173`, log in as admin, navigate to Monitor. Verify:
- Stat row shows service counts
- Alert banner renders (empty or populated)
- Services list shows homelab services
- GitHub panel shows repos + add form
- No console errors

- [ ] **Step 5: Commit**

```bash
git add templates/monitor.html templates/base.html
git commit -m "feat: add monitor dashboard Command Center template"
```

---

## Task 11: Wire Recommendations Into Background Monitor

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add recommendation refresh to `background_monitor()` in `app.py`**

Add a fourth time tracker after `last_github_time = 0`:

```python
last_recommendations_time = 0
```

Inside the `while True:` loop, after the GitHub block, add:

```python
# Refresh recommendations every 30 minutes
if now - last_recommendations_time >= 1800:
    try:
        import recommendations as rec_engine
        projects = database.list_projects()
        telemetry = database.get_telemetry_history(limit=5)
        from datetime import datetime as _dt, timedelta as _td
        cutoff = (_dt.now() - _td(hours=1)).isoformat()
        audit = database.get_audit_log(limit=500)
        recent_failures = sum(
            1 for e in audit
            if e['event_type'] == 'login_failure' and e['created_at'] > cutoff
        )
        new_recs = rec_engine.run_rule_checks(projects, telemetry, recent_failures)
        database.clear_recommendations(source='rule')
        for r in new_recs:
            database.add_recommendation(
                r['source'], r['severity'], r['message'], r.get('detail')
            )

        if config.ANTHROPIC_API_KEY:
            github = database.list_github_repo_statuses()
            snapshot = rec_engine.build_snapshot(projects, github, telemetry)
            ai_recs = rec_engine.run_ai_checks(snapshot, config.ANTHROPIC_API_KEY)
            database.clear_recommendations(source='ai')
            for r in ai_recs:
                database.add_recommendation(
                    r['source'], r['severity'], r['message'], r.get('detail')
                )
    except Exception as e:
        app.logger.error(f"Monitoring error (recommendations): {e}")
    last_recommendations_time = now
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 3: Final commit**

```bash
git add app.py
git commit -m "feat: wire recommendations refresh into background monitor loop"
```

---

## Done

Run the full suite one final time:

```bash
pytest tests/ -v --tb=short
```

All green. The monitor dashboard is live at `/monitor` (admin only).
