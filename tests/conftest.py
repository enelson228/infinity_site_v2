import os
import tempfile
import pytest

# Set required env vars before any app import.
# Use direct assignment for empty/missing vars — setdefault won't override empty strings.
_test_defaults = {
    'SECRET_KEY': 'test-secret-key-not-for-production',
    'UPLINK_PASSWORD_HASH': 'pbkdf2:sha256:1:aaaaaaaaaa:bbbbbbbbbb',
    'CLAUDE_PASSWORD_HASH': 'pbkdf2:sha256:1:aaaaaaaaaa:bbbbbbbbbb',
    'ANTHROPIC_API_KEY': 'test-anthropic-key',
}
for _k, _v in _test_defaults.items():
    if not os.environ.get(_k):
        os.environ[_k] = _v


@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix='.db')

    import database
    original_path = database.USER_DB_PATH
    database.USER_DB_PATH = db_path

    from app import app as flask_app
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False

    with flask_app.app_context():
        database.init_db()
        yield flask_app

    database.USER_DB_PATH = original_path
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def reset_runpod_config():
    """Restore RunPod config vars after each test to prevent order-dependent failures."""
    import config
    original_key = config.RUNPOD_API_KEY
    original_endpoint = config.SD_ENDPOINT_ID
    original_sdxl_endpoint = config.SDXL_ENDPOINT_ID
    original_forge_endpoint = config.FORGE_ENDPOINT_ID
    original_cyberrealistic_pony_endpoint = config.CYBERREALISTIC_PONY_ENDPOINT_ID
    original_wan_video_endpoint = config.WAN_VIDEO_ENDPOINT_ID
    yield
    config.RUNPOD_API_KEY = original_key
    config.SD_ENDPOINT_ID = original_endpoint
    config.SDXL_ENDPOINT_ID = original_sdxl_endpoint
    config.FORGE_ENDPOINT_ID = original_forge_endpoint
    config.CYBERREALISTIC_PONY_ENDPOINT_ID = original_cyberrealistic_pony_endpoint
    config.WAN_VIDEO_ENDPOINT_ID = original_wan_video_endpoint


@pytest.fixture
def admin_client(app, client):
    """Authenticated admin test client."""
    from werkzeug.security import generate_password_hash
    import database
    pw_hash = generate_password_hash('AdminPass1!', method='pbkdf2:sha256')
    database.create_user('testadmin', pw_hash, 'admin')
    client.post('/api/auth/login', json={
        'username': 'testadmin',
        'password': 'AdminPass1!'
    })
    return client
