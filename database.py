import sqlite3
import os
import time
from datetime import datetime
from contextlib import contextmanager
import config

USER_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'users.db')
os.makedirs(os.path.dirname(USER_DB_PATH), exist_ok=True)

def _db_conn():
    conn = sqlite3.connect(USER_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                size INTEGER NOT NULL,
                uploaded TEXT NOT NULL,
                uploader TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rate_limits (
                bucket TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                url TEXT,
                icon TEXT,
                category TEXT,
                status TEXT DEFAULT 'online',
                sort_order INTEGER DEFAULT 0,
                last_ping TEXT,
                response_time INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cpu_usage REAL NOT NULL,
                ram_usage REAL NOT NULL,
                timestamp REAL NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_bucket_ts ON rate_limits(bucket, timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_history_ts ON telemetry_history(timestamp)")
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

        # Schema migrations for existing installs
        cur = conn.execute("PRAGMA table_info(users)")
        cols = {row["name"] for row in cur.fetchall()}
        if "disabled" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
            conn.commit()

        cur = conn.execute("PRAGMA table_info(projects)")
        cols = {row["name"] for row in cur.fetchall()}
        if "last_ping" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN last_ping TEXT")
            conn.execute("ALTER TABLE projects ADD COLUMN response_time INTEGER")
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

def get_user_by_username(username: str):
    with _db_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()

def get_user_by_id(user_id: int):
    with _db_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()

def list_memories(user_id: int):
    with _db_conn() as conn:
        cur = conn.execute(
            "SELECT id, content, created_at FROM memories WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        )
        return [dict(row) for row in cur.fetchall()]

def append_audit(event_type: str, ip: str, actor_user_id=None, target_user_id=None, detail: str = ''):
    with _db_conn() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (event_type, actor_user_id, target_user_id, ip, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_type, actor_user_id, target_user_id, ip, detail, datetime.now().isoformat()),
        )
        conn.commit()

def list_users():
    with _db_conn() as conn:
        cur = conn.execute(
            "SELECT id, username, role, created_at, disabled FROM users ORDER BY id ASC"
        )
        return [dict(row) for row in cur.fetchall()]

def create_user(username, pw_hash, role):
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at, disabled) VALUES (?, ?, ?, ?, 0)",
            (username, pw_hash, role, datetime.now().isoformat()),
        )
        conn.commit()

def update_user_password(user_id, pw_hash):
    with _db_conn() as conn:
        cur = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
        conn.commit()
        return cur.rowcount > 0

def set_user_disabled(user_id, disabled: bool):
    with _db_conn() as conn:
        cur = conn.execute("UPDATE users SET disabled = ? WHERE id = ?", (1 if disabled else 0, user_id))
        conn.commit()
        return cur.rowcount > 0

def delete_user(user_id):
    with _db_conn() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return cur.rowcount > 0

def add_memory(user_id, content):
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO memories (user_id, content, created_at) VALUES (?, ?, ?)",
            (user_id, content, datetime.now().isoformat()),
        )
        conn.commit()

def delete_memory(memory_id):
    with _db_conn() as conn:
        cur = conn.execute("SELECT user_id FROM memories WHERE id = ?", (memory_id,))
        row = cur.fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        return row['user_id']

def get_audit_log(limit=200):
    with _db_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, event_type, actor_user_id, target_user_id, ip, detail, created_at
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """, (limit,)
        )
        return [dict(r) for r in cur.fetchall()]

def list_files():
    with _db_conn() as conn:
        cur = conn.execute("SELECT * FROM files ORDER BY uploaded DESC")
        return [dict(row) for row in cur.fetchall()]

def add_file(file_id, name, stored_name, size, uploaded, uploader):
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO files (id, name, stored_name, size, uploaded, uploader) VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, name, stored_name, size, uploaded, uploader)
        )
        conn.commit()

def get_file(file_id):
    with _db_conn() as conn:
        cur = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        return cur.fetchone()

def delete_file(file_id):
    with _db_conn() as conn:
        cur = conn.execute("SELECT stored_name FROM files WHERE id = ?", (file_id,))
        row = cur.fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()
        return row['stored_name']

def check_rate_limit(bucket: str, window_seconds: int, max_attempts: int) -> bool:
    now = time.time()
    cutoff = now - window_seconds
    with _db_conn() as conn:
        # Cleanup old entries occasionally
        conn.execute("DELETE FROM rate_limits WHERE timestamp < ?", (cutoff - window_seconds,))
        
        # Count attempts
        cur = conn.execute(
            "SELECT COUNT(*) as count FROM rate_limits WHERE bucket = ? AND timestamp > ?",
            (bucket, cutoff)
        )
        count = cur.fetchone()['count']
        
        if count >= max_attempts:
            return True
            
        # Record attempt
        conn.execute("INSERT INTO rate_limits (bucket, timestamp) VALUES (?, ?)", (bucket, now))
        conn.commit()
        return False

def list_projects():
    with _db_conn() as conn:
        cur = conn.execute("SELECT * FROM projects ORDER BY sort_order ASC, name ASC")
        return [dict(row) for row in cur.fetchall()]

def add_project(pid, name, description, url, icon, category, status='online', sort_order=0):
    with _db_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO projects (id, name, description, url, icon, category, status, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (pid, name, description, url, icon, category, status, sort_order)
        )
        conn.commit()

def update_project_status(pid, status, response_time):
    with _db_conn() as conn:
        conn.execute(
            "UPDATE projects SET status = ?, last_ping = ?, response_time = ? WHERE id = ?",
            (status, datetime.now().isoformat(), response_time, pid)
        )
        conn.commit()

def add_telemetry_history(cpu, ram):
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO telemetry_history (cpu_usage, ram_usage, timestamp) VALUES (?, ?, ?)",
            (cpu, ram, time.time())
        )
        conn.commit()

def get_telemetry_history(limit=24):
    with _db_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM telemetry_history ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        return [dict(row) for row in cur.fetchall()]


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
