import os
import pytest


def test_github_token_optional():
    """GITHUB_TOKEN is optional — missing it does not crash startup."""
    import config
    assert hasattr(config, 'GITHUB_TOKEN')
    # GITHUB_TOKEN should default to empty string if not set
    assert isinstance(config.GITHUB_TOKEN, str)


def test_session_cookie_config():
    """Session cookie security flags are configured."""
    import config
    assert config.SESSION_COOKIE_HTTPONLY is True
    assert config.SESSION_COOKIE_SAMESITE == 'Lax'
    # Verify SESSION_COOKIE_SECURE is a boolean
    assert isinstance(config.SESSION_COOKIE_SECURE, bool)
