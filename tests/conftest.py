import os
import sys
import tempfile
import pytest

# CRITICAL: Set required env vars BEFORE any app imports
# Load from .env.test if it exists, otherwise use defaults
_env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env.test')
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip()
                # Always set, even if already in environ (overwrite empty values)
                os.environ[key] = value
else:
    # Fallback defaults if .env.test doesn't exist
    _defaults = {
        'SECRET_KEY': 'test-secret-key-not-for-production',
        'UPLINK_PASSWORD_HASH': 'pbkdf2:sha256:1:aaaaaaaaaa:bbbbbbbbbb',
        'CLAUDE_PASSWORD_HASH': 'pbkdf2:sha256:1:aaaaaaaaaa:bbbbbbbbbb',
        'ANTHROPIC_API_KEY': 'test-anthropic-key',
        'SESSION_COOKIE_SECURE': 'false',
    }
    for key, value in _defaults.items():
        # Always set, even if already in environ (overwrite empty values)
        os.environ[key] = value


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
