import json
from unittest.mock import MagicMock, patch


def test_forge_video_page_requires_login(client):
    resp = client.get('/forge/video')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_forge_video_page_renders_when_logged_in(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.WAN_VIDEO_ENDPOINT_ID = 'wan-endpoint'
    resp = admin_client.get('/forge/video')
    assert resp.status_code == 200
    assert b'FORGE VIDEO' in resp.data


def test_video_generate_routes_to_wan_endpoint(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.WAN_VIDEO_ENDPOINT_ID = 'wan-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'id': 'job-video', 'status': 'IN_QUEUE'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response) as urlopen:
        resp = admin_client.post(
            '/api/forge/videos/generate',
            json={
                'prompt': 'orbit around a mountain observatory',
                'negative_prompt': 'text, watermark',
                'image_base64': 'ZmFrZS1pbWFnZQ==',
                'width': 480,
                'height': 832,
                'length': 81,
                'steps': 10,
                'cfg': 2.0,
                'context_overlap': 48,
                'seed': 123,
            },
            headers={'X-CSRF-Token': token},
        )

    assert resp.status_code == 200
    req = urlopen.call_args.args[0]
    assert req.full_url == 'https://api.runpod.ai/v2/wan-endpoint/run'
    payload = json.loads(req.data.decode())
    assert payload['input'] == {
        'prompt': 'orbit around a mountain observatory',
        'negative_prompt': 'text, watermark',
        'image_base64': 'ZmFrZS1pbWFnZQ==',
        'width': 480,
        'height': 832,
        'length': 81,
        'steps': 10,
        'cfg': 2.0,
        'context_overlap': 48,
        'seed': 123,
    }


def test_video_generate_merges_advanced_input(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.WAN_VIDEO_ENDPOINT_ID = 'wan-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'id': 'job-video', 'status': 'IN_QUEUE'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response) as urlopen:
        resp = admin_client.post(
            '/api/forge/videos/generate',
            json={
                'prompt': 'orbit around a mountain observatory',
                'image_url': 'https://example.com/ref.png',
                'advanced_input': {
                    'extra_param': 7,
                },
            },
            headers={'X-CSRF-Token': token},
        )

    assert resp.status_code == 200
    payload = json.loads(urlopen.call_args.args[0].data.decode())
    assert payload['input']['image_url'] == 'https://example.com/ref.png'
    assert payload['input']['extra_param'] == 7


def test_video_generate_converts_local_forge_image_url_to_base64(admin_client, tmp_path, monkeypatch):
    import blueprints.forge as forge_module
    import config

    monkeypatch.setattr(forge_module, '_FORGE_OUTPUTS', str(tmp_path))
    config.RUNPOD_API_KEY = 'test-key'
    config.WAN_VIDEO_ENDPOINT_ID = 'wan-endpoint'

    image_bytes = b'fake-png-bytes'
    (tmp_path / 'job-ref.png').write_bytes(image_bytes)

    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'id': 'job-video', 'status': 'IN_QUEUE'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response) as urlopen:
        resp = admin_client.post(
            '/api/forge/videos/generate',
            json={
                'prompt': 'animate this',
                'image_url': '/static/forge_outputs/job-ref.png',
            },
            headers={'X-CSRF-Token': token},
        )

    assert resp.status_code == 200
    payload = json.loads(urlopen.call_args.args[0].data.decode())
    assert payload['input']['image_base64'] == 'ZmFrZS1wbmctYnl0ZXM='
    assert 'image_url' not in payload['input']


def test_video_generate_accepts_lora_pairs(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.WAN_VIDEO_ENDPOINT_ID = 'wan-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'id': 'job-video', 'status': 'IN_QUEUE'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response) as urlopen:
        resp = admin_client.post(
            '/api/forge/videos/generate',
            json={
                'prompt': 'orbit around a mountain observatory',
                'image_url': 'https://example.com/ref.png',
                'lora_pairs': [{'high': 'high.safetensors', 'low': 'low.safetensors', 'high_weight': 1.0, 'low_weight': 1.0}],
            },
            headers={'X-CSRF-Token': token},
        )

    assert resp.status_code == 200
    payload = json.loads(urlopen.call_args.args[0].data.decode())
    assert payload['input']['lora_pairs'][0]['high'] == 'high.safetensors'


def test_video_status_saves_completed_video(admin_client, tmp_path, monkeypatch):
    import blueprints.forge as forge_module
    monkeypatch.setattr(forge_module, '_FORGE_VIDEOS', str(tmp_path))
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.WAN_VIDEO_ENDPOINT_ID = 'wan-endpoint'

    status_response = MagicMock()
    status_response.read.return_value = json.dumps({
        'status': 'COMPLETED',
        'output': {'video_url': 'https://video.runpod.ai/example/output.mp4'},
    }).encode()
    status_response.__enter__ = lambda s: s
    status_response.__exit__ = MagicMock(return_value=False)

    download_response = MagicMock()
    download_response.read.return_value = b'fake-mp4-data'
    download_response.__enter__ = lambda s: s
    download_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', side_effect=[status_response, download_response]):
        resp = admin_client.get('/api/forge/videos/status/job-video-save?prompt=a+test')

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['status'] == 'COMPLETED'
    assert (tmp_path / 'job-video-save.mp4').exists()


def test_video_status_saves_completed_base64_video(admin_client, tmp_path, monkeypatch):
    import blueprints.forge as forge_module
    monkeypatch.setattr(forge_module, '_FORGE_VIDEOS', str(tmp_path))
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.WAN_VIDEO_ENDPOINT_ID = 'wan-endpoint'

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        'status': 'COMPLETED',
        'output': {'video': 'ZmFrZS1tcDQtZGF0YQ=='},
    }).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.get('/api/forge/videos/status/job-video-b64?prompt=a+test')

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['status'] == 'COMPLETED'
    assert (tmp_path / 'job-video-b64.mp4').read_bytes() == b'fake-mp4-data'


def test_video_status_failed_job(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.WAN_VIDEO_ENDPOINT_ID = 'wan-endpoint'

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'status': 'FAILED', 'error': 'OOM'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.get('/api/forge/videos/status/job-video-fail?prompt=test')

    data = json.loads(resp.data)
    assert data['status'] == 'FAILED'


def test_video_delete_route(admin_client, tmp_path, monkeypatch):
    import blueprints.forge as forge_module
    monkeypatch.setattr(forge_module, '_FORGE_VIDEOS', str(tmp_path))
    import database
    from datetime import datetime

    fake_file = tmp_path / 'job-video-del.mp4'
    fake_file.write_bytes(b'fake')
    video_id = database.add_forge_video('job-video-del', 'a test', 'job-video-del.mp4', datetime.now().isoformat())

    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.delete(f'/api/forge/videos/{video_id}', headers={'X-CSRF-Token': token})
    assert resp.status_code == 200
    assert database.get_forge_video(video_id) is None
    assert not fake_file.exists()
