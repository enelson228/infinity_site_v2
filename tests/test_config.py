import os
import pytest


def test_github_token_optional(app):
    """GITHUB_TOKEN is optional — missing it does not crash startup."""
    import config
    assert hasattr(config, 'GITHUB_TOKEN')


def test_session_cookie_config(app):
    """Session cookie security flags are configured."""
    import config
    assert config.SESSION_COOKIE_HTTPONLY is True
    assert config.SESSION_COOKIE_SAMESITE == 'Lax'
