import os
import tempfile
import pytest

# Set required env vars before any app import
os.environ.setdefault('SECRET_KEY', 'test-secret-key-not-for-production')
os.environ.setdefault('UPLINK_PASSWORD_HASH', 'pbkdf2:sha256:1:aaaaaaaaaa:bbbbbbbbbb')
os.environ.setdefault('CLAUDE_PASSWORD_HASH', 'pbkdf2:sha256:1:aaaaaaaaaa:bbbbbbbbbb')
os.environ.setdefault('ANTHROPIC_API_KEY', 'test-anthropic-key')


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
