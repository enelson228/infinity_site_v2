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
