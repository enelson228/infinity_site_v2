# Monitor Dashboard Design

**Date:** 2026-04-14
**Project:** infinity_site_v2
**Status:** Approved

---

## Overview

A secure, admin-only monitoring dashboard at `/monitor` that provides a unified view of homelab service health, GitHub repository status, and intelligent recommendations. Built as a Flask blueprint following the existing project patterns, with targeted security hardening applied across the codebase as part of the build.

---

## Architecture

### New files
- `blueprints/monitor.py` — routes for `/monitor` and `/api/monitor/*`
- `templates/monitor.html` — dashboard template (Command Center layout)
- `recommendations.py` — rules engine + AI insights module

### Modified files
- `database.py` — two new tables: `github_repos`, `github_repo_status`, `monitor_recommendations`
- `app.py` — register `monitor_bp`; extend `background_monitor()` with GitHub poll loop; fix `control_redirect`; add security headers hook; set secure session cookie config
- `config.py` — add `GITHUB_TOKEN`, `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE` env vars
- `auth.py` / `admin.py` — add CSRF token generation, injection, and validation

### Access control
All `/monitor` routes and `/api/monitor/*` endpoints are gated with the existing `@admin_required` decorator. No new auth system.

---

## Layout — Command Center

```
┌─────────────────────────────────────────────┐
│  [8/9 SERVICES]  [3 OPEN PRs]  [2 ALERTS]  [1 AI] │  ← stat row
├─────────────────────────────────────────────┤
│  ▲ ALERTS & RECOMMENDATIONS                  │  ← prominent alert banner
│  ⚠ Gitea offline 2h  ⚑ stale PR  ✦ AI insight │
├──────────────────────┬──────────────────────┤
│  SERVICES            │  GITHUB REPOS        │
│  ● Nextcloud online  │  mjolnir-armory ✓ CI │
│  ● Plex online       │  infinity_site_v2    │
│  ● Gitea offline     │  ...                 │
└──────────────────────┴──────────────────────┘
```

Stat row at top. Alerts banner is the most prominent element — impossible to miss. Services and GitHub repos side-by-side below. Fits the UNSC aesthetic of the existing site.

---

## Data Model

Three new tables added to `database.py`:

```sql
-- GitHub repo configurations (admin-managed)
CREATE TABLE github_repos (
    id       TEXT PRIMARY KEY,          -- slug, e.g. "mjolnir-armory"
    owner    TEXT NOT NULL,             -- GitHub username/org
    repo     TEXT NOT NULL,             -- repo name
    enabled  INTEGER NOT NULL DEFAULT 1,
    added_at TEXT NOT NULL
);

-- Cached GitHub fetch results (written by background monitor)
CREATE TABLE github_repo_status (
    repo_id         TEXT PRIMARY KEY,
    last_commit_at  TEXT,
    last_commit_msg TEXT,
    open_prs        INTEGER DEFAULT 0,
    ci_status       TEXT,              -- 'success' | 'failure' | 'pending' | 'none'
    fetched_at      TEXT NOT NULL,
    FOREIGN KEY(repo_id) REFERENCES github_repos(id) ON DELETE CASCADE
);

-- Cached recommendations (written by recommendations engine)
CREATE TABLE monitor_recommendations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT NOT NULL,          -- 'rule' | 'ai'
    severity   TEXT NOT NULL,          -- 'critical' | 'warning' | 'info'
    message    TEXT NOT NULL,
    detail     TEXT,
    created_at TEXT NOT NULL,
    dismissed  INTEGER NOT NULL DEFAULT 0
);
```

GitHub token stored in `config.py` via env var `GITHUB_TOKEN`. Never stored in the database.

---

## GitHub Integration

- Background monitor gains a third poll loop: runs every 10 minutes
- Fetches from GitHub REST API using `urllib` only (no new dependencies)
- Endpoints used: `/repos/{owner}/{repo}`, `/repos/{owner}/{repo}/pulls?state=open`, `/repos/{owner}/{repo}/commits`, `/repos/{owner}/{repo}/actions/runs?per_page=1`
- Results written to `github_repo_status` table (upsert by `repo_id`)
- If `GITHUB_TOKEN` is not set at startup, GitHub panel renders a config warning — no runtime errors
- Repos are managed via `/api/monitor/repos` (GET/POST/DELETE), admin-only

---

## Recommendations Engine

`recommendations.py` exposes two functions called by the background monitor every 30 minutes and on-demand via `POST /api/monitor/recommendations/refresh`.

### Rule-based checks (always run, no API cost)

| Condition | Severity |
|-----------|----------|
| Service offline > 30 min | `critical` |
| Service offline < 30 min | `warning` |
| CPU > 85% sustained (last 5 readings) | `warning` |
| RAM > 90% | `critical` |
| GitHub repo: no commit in > 30 days | `info` |
| GitHub repo: open PR > 14 days old | `warning` |
| Auth: > 10 failed logins in last hour | `critical` |
| Auth: new admin account created | `info` |

### AI insights (Claude API)

- Runs every 30 minutes alongside rule-based checks
- Input: compact JSON snapshot of current state (service statuses, GitHub repo ages, recent audit events, telemetry 1h averages)
- Output: 1–3 short actionable insights, things rule-based checks miss
- Written to `monitor_recommendations` with `source='ai'`
- Fails gracefully — rule-based checks always run regardless of API availability

### Dismissal

`POST /api/monitor/recommendations/<id>/dismiss` sets `dismissed=1`. Dismissed recommendations are hidden from the dashboard until the next regeneration cycle clears and rewrites all findings.

---

## API Endpoints

All endpoints require admin session.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/monitor` | Dashboard page |
| GET | `/api/monitor/status` | Full dashboard data (services, repos, recommendations) |
| GET | `/api/monitor/repos` | List configured GitHub repos |
| POST | `/api/monitor/repos` | Add a GitHub repo |
| DELETE | `/api/monitor/repos/<id>` | Remove a GitHub repo |
| POST | `/api/monitor/recommendations/refresh` | Trigger immediate regen |
| POST | `/api/monitor/recommendations/<id>/dismiss` | Dismiss a recommendation |

---

## Security Hardening

Applied to existing codebase as part of this build.

### `app.py`
- Remove `control_redirect` nested-decorator antipattern — replace with direct `@admin_required` on the route function
- Add `@app.after_request` hook injecting security headers on every response:
  - `Content-Security-Policy: default-src 'self'` (tightened as needed for inline scripts)
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
- Set `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'`

### CSRF Protection
- Per-session CSRF token generated with `secrets.token_hex(32)` on first login, stored in session
- Injected into all templates via `app.context_processor`
- Validated on all state-changing endpoints (POST/PUT/DELETE) in a `before_request` hook
- No new dependencies — uses Python stdlib `secrets`

### Password hashing
- Upgrade `generate_password_hash` from `pbkdf2:sha256` to `scrypt` for all new password sets
- Existing hashes remain valid (Werkzeug `check_password_hash` is algorithm-agnostic)

### `blueprints/monitor.py`
- All routes gated with `@admin_required`
- GitHub token validated at startup — missing token shows config warning, not a runtime error
- API responses never echo raw user input unescaped

### `config.py`
- New env vars: `GITHUB_TOKEN`, `SESSION_COOKIE_SECURE` (default `True`), `SESSION_COOKIE_HTTPONLY` (default `True`), `SESSION_COOKIE_SAMESITE` (default `'Lax'`)

---

## Out of Scope

- Email/webhook alerting (future milestone)
- Multi-user dashboard views / per-user dismissals
- Historical recommendation trends
- GitHub webhooks (polling is sufficient for homelab scale)
