import json
import pytest
from unittest.mock import patch, MagicMock


# ── Page route ────────────────────────────────────────────────────────────────

def test_forge_page_requires_login(client):
    resp = client.get('/forge')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_forge_page_renders_when_logged_in(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'
    config.CYBERREALISTIC_PONY_ENDPOINT_ID = 'cyber-endpoint'
    config.WAN_VIDEO_ENDPOINT_ID = 'wan-endpoint'
    resp = admin_client.get('/forge')
    assert resp.status_code == 200
    assert b'FORGE' in resp.data
    assert b'CyberRealistic Pony' in resp.data
    assert b'WAN 2.2 Animate' in resp.data


# ── Generate endpoint ─────────────────────────────────────────────────────────

def test_generate_requires_login(client):
    # Mutating API routes are blocked by CSRF before auth if no session exists.
    resp = client.post('/api/forge/generate', json={'prompt': 'a dragon'})
    assert resp.status_code == 403


def test_generate_rejects_empty_prompt(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SDXL_ENDPOINT_ID = 'test-endpoint'
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
    config.SDXL_ENDPOINT_ID = 'test-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.post('/api/forge/generate',
                             json={'prompt': 'x' * 501},
                             headers={'X-CSRF-Token': token})
    assert resp.status_code == 400


def test_generate_returns_job_id(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SDXL_ENDPOINT_ID = 'test-endpoint'
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
    assert data['status'] == 'IN_QUEUE'


def test_generate_routes_juggernaut_payload_to_forge_endpoint(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SDXL_ENDPOINT_ID = 'sdxl-endpoint'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'id': 'job-juggernaut', 'status': 'IN_QUEUE'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response) as urlopen:
        resp = admin_client.post(
            '/api/forge/generate',
            json={
                'prompt': 'a cinematic orbital foundry',
                'negative_prompt': 'blurry',
                'worker_type': 'forge',
                'steps': 28,
                'width': 1024,
                'height': 1024,
                'guidance_scale': 7,
                'seed': 123,
            },
            headers={'X-CSRF-Token': token},
        )

    assert resp.status_code == 200
    req = urlopen.call_args.args[0]
    assert req.full_url == 'https://api.runpod.ai/v2/forge-endpoint/run'
    payload = json.loads(req.data.decode())
    assert payload['input'] == {
        'prompt': 'a cinematic orbital foundry',
        'negative_prompt': 'blurry',
        'num_inference_steps': 28,
        'width': 1024,
        'height': 1024,
        'guidance_scale': 7.0,
        'model': 'juggernaut-xl',
        'seed': 123,
    }


def test_generate_routes_cyberrealistic_pony_to_dedicated_endpoint(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'
    config.CYBERREALISTIC_PONY_ENDPOINT_ID = 'cyber-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'id': 'job-cyber', 'status': 'IN_QUEUE'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response) as urlopen:
        resp = admin_client.post(
            '/api/forge/generate',
            json={
                'prompt': 'cinematic portrait',
                'negative_prompt': 'blurry',
                'worker_type': 'forge',
                'model': 'cyberrealistic-pony',
                'steps': 36,
                'width': 896,
                'height': 1152,
                'guidance_scale': 5.5,
            },
            headers={'X-CSRF-Token': token},
        )

    assert resp.status_code == 200
    req = urlopen.call_args.args[0]
    assert req.full_url == 'https://api.runpod.ai/v2/cyber-endpoint/run'
    payload = json.loads(req.data.decode())
    assert payload['input'] == {
        'prompt': 'cinematic portrait',
        'negative_prompt': 'blurry',
        'num_inference_steps': 36,
        'width': 896,
        'height': 1152,
        'guidance_scale': 5.5,
        'model': 'cyberrealistic-pony',
    }


def test_generate_clamps_juggernaut_cost_heavy_values(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'id': 'job-clamp', 'status': 'IN_QUEUE'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response) as urlopen:
        resp = admin_client.post(
            '/api/forge/generate',
            json={
                'prompt': 'a large render',
                'worker_type': 'forge',
                'steps': 150,
                'width': 4096,
                'height': 4096,
                'guidance_scale': 30,
            },
            headers={'X-CSRF-Token': token},
        )

    assert resp.status_code == 200
    payload = json.loads(urlopen.call_args.args[0].data.decode())
    assert payload['input']['num_inference_steps'] == 60
    assert payload['input']['width'] == 1536
    assert payload['input']['height'] == 1536
    assert payload['input']['guidance_scale'] == 15.0


def test_generate_falls_back_to_juggernaut_when_requested_forge_model_is_unconfigured(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'
    config.CYBERREALISTIC_PONY_ENDPOINT_ID = ''
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'id': 'job-fallback', 'status': 'IN_QUEUE'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response) as urlopen:
        resp = admin_client.post(
            '/api/forge/generate',
            json={'prompt': 'fallback test', 'worker_type': 'forge', 'model': 'cyberrealistic-pony'},
            headers={'X-CSRF-Token': token},
        )

    assert resp.status_code == 200
    req = urlopen.call_args.args[0]
    assert req.full_url == 'https://api.runpod.ai/v2/forge-endpoint/run'
    payload = json.loads(req.data.decode())
    assert payload['input']['model'] == 'juggernaut-xl'


def test_generate_returns_502_when_runpod_omits_job_id(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'status': 'COMPLETED', 'output': {'images': ['abc']}}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.post('/api/forge/generate',
                                 json={'prompt': 'a red dragon', 'worker_type': 'forge'},
                                 headers={'X-CSRF-Token': token})

    assert resp.status_code == 502
    data = json.loads(resp.data)
    assert 'job ID' in data['error']


def test_generate_returns_502_on_runpod_error(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SDXL_ENDPOINT_ID = 'test-endpoint'
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
    config.SDXL_ENDPOINT_ID = ''
    config.FORGE_ENDPOINT_ID = ''
    config.CYBERREALISTIC_PONY_ENDPOINT_ID = ''
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.post('/api/forge/generate',
                             json={'prompt': 'a dragon'},
                             headers={'X-CSRF-Token': token})
    assert resp.status_code == 503


# ── Status endpoint ───────────────────────────────────────────────────────────

def test_status_requires_login(client):
    resp = client.get('/api/forge/status/job-123?prompt=test')
    assert resp.status_code == 401


def test_status_returns_in_queue(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'status': 'IN_QUEUE'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.get('/api/forge/status/job-123?prompt=a+dragon')

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['status'] == 'IN_QUEUE'


def test_status_returns_running(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'status': 'RUNNING'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.get('/api/forge/status/job-123?prompt=a+dragon')

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['status'] == 'RUNNING'


def test_status_saves_image_on_completed(admin_client, tmp_path, monkeypatch):
    import blueprints.forge as forge_module
    monkeypatch.setattr(forge_module, '_FORGE_OUTPUTS', str(tmp_path))
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'

    # 1x1 red PNG in base64
    tiny_png_b64 = (
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8'
        'z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=='
    )
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        'status': 'COMPLETED',
        'output': [{'image': tiny_png_b64, 'seed': 42}],
    }).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.get('/api/forge/status/job-save-test?prompt=a+cat')

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['status'] == 'COMPLETED'
    assert 'image_url' in data
    assert 'image_id' in data

    # Verify file was written
    saved_file = tmp_path / 'job-save-test.png'
    assert saved_file.exists()


def test_status_saves_image_from_output_images_dict(admin_client, tmp_path, monkeypatch):
    import blueprints.forge as forge_module
    monkeypatch.setattr(forge_module, '_FORGE_OUTPUTS', str(tmp_path))
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'

    tiny_png_b64 = (
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8'
        'z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=='
    )
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        'status': 'COMPLETED',
        'output': {'images': [tiny_png_b64], 'seed': 42},
    }).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.get('/api/forge/status/job-save-dict?prompt=a+cat')

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['status'] == 'COMPLETED'
    assert (tmp_path / 'job-save-dict.png').exists()


def test_status_idempotent_on_repeated_completed_poll(admin_client, tmp_path, monkeypatch):
    """Polling after COMPLETED should return existing record without duplicate writes."""
    import blueprints.forge as forge_module
    monkeypatch.setattr(forge_module, '_FORGE_OUTPUTS', str(tmp_path))
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'

    tiny_png_b64 = (
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8'
        'z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=='
    )
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        'status': 'COMPLETED',
        'output': [{'image': tiny_png_b64, 'seed': 1}],
    }).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        admin_client.get('/api/forge/status/job-idem?prompt=test')

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp2 = admin_client.get('/api/forge/status/job-idem?prompt=test')

    import database
    images = database.list_forge_images()
    idem_images = [i for i in images if i['job_id'] == 'job-idem']
    assert len(idem_images) == 1  # No duplicate

    data = json.loads(resp2.data)
    assert data['status'] == 'COMPLETED'


def test_status_failed_job(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'status': 'FAILED', 'error': 'OOM'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.get('/api/forge/status/job-fail?prompt=test')

    data = json.loads(resp.data)
    assert data['status'] == 'FAILED'


def test_status_prefers_forge_endpoint_without_query_param(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'legacy-endpoint'
    config.SDXL_ENDPOINT_ID = 'sdxl-endpoint'
    config.CYBERREALISTIC_PONY_ENDPOINT_ID = 'cyber-endpoint'
    config.FORGE_ENDPOINT_ID = 'forge-endpoint'

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'status': 'FAILED', 'error': 'OOM'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response) as urlopen:
        resp = admin_client.get('/api/forge/status/job-fail?prompt=test')

    data = json.loads(resp.data)
    assert data['status'] == 'FAILED'
    req = urlopen.call_args.args[0]
    assert req.full_url == 'https://api.runpod.ai/v2/cyber-endpoint/status/job-fail'


# ── Delete endpoint ───────────────────────────────────────────────────────────

def test_delete_requires_login(client):
    resp = client.delete('/api/forge/images/1')
    assert resp.status_code == 403


def test_delete_image(admin_client, tmp_path, monkeypatch):
    import blueprints.forge as forge_module
    monkeypatch.setattr(forge_module, '_FORGE_OUTPUTS', str(tmp_path))

    import database
    from datetime import datetime
    fake_file = tmp_path / 'job-del.png'
    fake_file.write_bytes(b'fake')
    img_id = database.add_forge_image('job-del', 'a test', 'job-del.png', datetime.now().isoformat())

    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.delete(f'/api/forge/images/{img_id}',
                               headers={'X-CSRF-Token': token})
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    assert not fake_file.exists()
    assert database.get_forge_image(img_id) is None


def test_delete_image_not_found(admin_client):
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.delete('/api/forge/images/99999',
                               headers={'X-CSRF-Token': token})
    assert resp.status_code == 404
