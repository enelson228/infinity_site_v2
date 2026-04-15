import json
import pytest
from unittest.mock import patch, MagicMock


# ── Page route ────────────────────────────────────────────────────────────────

def test_forge_page_requires_login(client):
    resp = client.get('/forge')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_forge_page_renders_when_logged_in(admin_client):
    resp = admin_client.get('/forge')
    assert resp.status_code == 200
    assert b'FORGE' in resp.data


# ── Generate endpoint ─────────────────────────────────────────────────────────

def test_generate_requires_login(client):
    # API routes return 401 (not 302) for unauthenticated JSON requests
    resp = client.post('/api/forge/generate', json={'prompt': 'a dragon'})
    assert resp.status_code == 401


def test_generate_rejects_empty_prompt(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'test-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.post('/api/forge/generate',
                             json={'prompt': ''},
                             headers={'X-CSRF-Token': token})
    assert resp.status_code == 400
    assert b'prompt' in resp.data.lower()


def test_generate_rejects_prompt_too_long(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'test-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.post('/api/forge/generate',
                             json={'prompt': 'x' * 501},
                             headers={'X-CSRF-Token': token})
    assert resp.status_code == 400


def test_generate_returns_job_id(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'test-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'id': 'job-abc123', 'status': 'IN_QUEUE'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.post('/api/forge/generate',
                                 json={'prompt': 'a red dragon'},
                                 headers={'X-CSRF-Token': token})

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['job_id'] == 'job-abc123'


def test_generate_returns_502_on_runpod_error(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'test-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    with patch('urllib.request.urlopen', side_effect=Exception('connection refused')):
        resp = admin_client.post('/api/forge/generate',
                                 json={'prompt': 'a dragon'},
                                 headers={'X-CSRF-Token': token})

    assert resp.status_code == 502


def test_generate_disabled_without_config(admin_client):
    import config
    config.RUNPOD_API_KEY = ''
    config.SD_ENDPOINT_ID = ''
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.post('/api/forge/generate',
                             json={'prompt': 'a dragon'},
                             headers={'X-CSRF-Token': token})
    assert resp.status_code == 503
