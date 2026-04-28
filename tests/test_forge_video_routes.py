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
                'size': '1280*720',
                'duration': 5,
                'num_inference_steps': 30,
                'guidance': 5,
                'flow_shift': 5,
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
        'size': '1280*720',
        'num_inference_steps': 30,
        'guidance': 5.0,
        'duration': 5,
        'flow_shift': 5,
        'enable_prompt_optimization': False,
        'enable_safety_checker': True,
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
                'advanced_input': {
                    'high_noise_loras': [{'path': 'https://hf/high.safetensors', 'scale': 1.0}],
                },
            },
            headers={'X-CSRF-Token': token},
        )

    assert resp.status_code == 200
    payload = json.loads(urlopen.call_args.args[0].data.decode())
    assert payload['input']['high_noise_loras'][0]['path'] == 'https://hf/high.safetensors'


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
