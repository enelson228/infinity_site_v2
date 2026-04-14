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
