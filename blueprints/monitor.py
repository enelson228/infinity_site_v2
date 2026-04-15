from flask import Blueprint, jsonify, request, render_template, session
from auth import admin_required
import database
import recommendations
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
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', repo_id):
        return jsonify({'error': 'Invalid repo id'}), 400
    if not database.delete_github_repo(repo_id):
        return jsonify({'error': 'Repo not found'}), 404
    actor_id = session.get('user_id')
    database.append_audit('monitor_repo_delete', client_ip(),
                          actor_user_id=actor_id, detail=f'repo_id={repo_id}')
    return jsonify({'success': True})


@monitor_bp.route('/api/monitor/recommendations/refresh', methods=['POST'])
@admin_required
def api_refresh_recommendations():
    """Trigger immediate regen of rule-based recommendations."""
    result = recommendations.refresh_recommendations()
    return jsonify({'success': True, 'count': result['rule_count']})


@monitor_bp.route('/api/monitor/recommendations/<int:rec_id>/dismiss', methods=['POST'])
@admin_required
def api_dismiss_recommendation(rec_id: int):
    if not database.dismiss_recommendation(rec_id):
        return jsonify({'error': 'Recommendation not found'}), 404
    actor_id = session.get('user_id')
    database.append_audit('recommendation_dismiss', client_ip(),
                          actor_user_id=actor_id, detail=f'rec_id={rec_id}')
    return jsonify({'success': True})
