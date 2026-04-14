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
