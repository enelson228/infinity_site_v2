def test_security_headers_present(client):
    """Every response includes hardened security headers."""
    resp = client.get('/')
    assert resp.headers.get('X-Frame-Options') == 'DENY'
    assert resp.headers.get('X-Content-Type-Options') == 'nosniff'
    assert 'Referrer-Policy' in resp.headers
    assert 'Content-Security-Policy' in resp.headers


def test_control_route_not_nested_function(app):
    """The /control route must be registered directly, not via a nested closure."""
    rules = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert 'control' in rules


def test_control_requires_admin(client):
    """Unauthenticated /control access redirects to login."""
    resp = client.get('/control')
    assert resp.status_code in (302, 401)


def test_csrf_token_injected_after_login(admin_client):
    """A CSRF token is available in session after login."""
    with admin_client.session_transaction() as sess:
        assert 'csrf_token' in sess
        assert len(sess['csrf_token']) == 64  # 32 bytes hex = 64 chars


def test_post_without_csrf_rejected(admin_client):
    """State-changing requests without CSRF token are rejected with 403."""
    resp = admin_client.post('/api/admin/users', json={
        'username': 'hacker', 'password': 'x', 'role': 'user'
    })
    assert resp.status_code == 403


def test_post_with_csrf_accepted(admin_client):
    """State-changing requests with valid CSRF token are accepted."""
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.post('/api/admin/users',
        json={'username': 'newuser', 'password': 'Pass1!', 'role': 'user'},
        headers={'X-CSRF-Token': token}
    )
    assert resp.status_code == 200
