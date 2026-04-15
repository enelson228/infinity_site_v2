"""
Recommendations engine for the monitor dashboard.
Two entry points:
  - run_rule_checks(projects, telemetry, recent_failures) -> list[dict]
  - run_ai_checks(snapshot, api_key) -> list[dict]
"""

from datetime import datetime, timedelta, timezone
import json
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
                    # Strip tz info if present — DB stores naive local timestamps
                    if last_ping.tzinfo is not None:
                        last_ping = last_ping.replace(tzinfo=None)
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
                except (ValueError, TypeError):
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

    # RAM check — critical if any reading above 90% (checks all telemetry, not just recent 5)
    if telemetry and any(r['ram_usage'] > 90 for r in telemetry):
        max_ram = max(r['ram_usage'] for r in telemetry)
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

    snapshot keys: services, github, telemetry_avg (cpu_avg, ram_avg)
    """
    try:
        client = anthropic.Anthropic(api_key=api_key)

        prompt = (
            "You are a homelab monitoring assistant. Analyze this system snapshot and "
            "return 1-3 short, actionable insights that rule-based checks would miss. "
            "Focus on trends, stale projects, or patterns. "
            "Format: one insight per line, starting with '- '. No preamble.\n\n"
            f"Snapshot:\n{json.dumps(snapshot)}"
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


def refresh_recommendations() -> dict:
    """
    Run the full recommendation refresh cycle: rule checks + optional AI checks.
    Reads state from the database and writes results back.
    Returns {'rule_count': N, 'ai_count': N}.
    """
    import database
    import config
    from datetime import datetime as _dt, timedelta as _td

    projects = database.list_projects()
    telemetry = database.get_telemetry_history(limit=5)

    cutoff = (_dt.now() - _td(hours=1)).isoformat()
    audit = database.get_audit_log(limit=500)
    recent_failures = sum(
        1 for e in audit
        if e['event_type'] == 'login_failure' and e['created_at'] > cutoff
    )

    new_recs = run_rule_checks(projects, telemetry, recent_failures)
    database.clear_recommendations(source='rule')
    for r in new_recs:
        database.add_recommendation(r['source'], r['severity'], r['message'], r.get('detail'))

    ai_count = 0
    if config.ANTHROPIC_API_KEY and config.ANTHROPIC_API_KEY != 'test-anthropic-key':
        github = database.list_github_repo_statuses()
        snapshot = build_snapshot(projects, github, telemetry)
        ai_recs = run_ai_checks(snapshot, config.ANTHROPIC_API_KEY)
        database.clear_recommendations(source='ai')
        for r in ai_recs:
            database.add_recommendation(r['source'], r['severity'], r['message'], r.get('detail'))
        ai_count = len(ai_recs)

    return {'rule_count': len(new_recs), 'ai_count': ai_count}
