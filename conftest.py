"""Root conftest.py - runs before any test collection."""
import os
import sys

# Set environment variables at MODULE LOAD TIME, not in a hook
# This must happen BEFORE pytest-flask or any other plugins run
_test_env_vars = {
    'SECRET_KEY': 'test-secret-key-not-for-production',
    'UPLINK_PASSWORD_HASH': 'pbkdf2:sha256:1:aaaaaaaaaa:bbbbbbbbbb',
    'CLAUDE_PASSWORD_HASH': 'pbkdf2:sha256:1:aaaaaaaaaa:bbbbbbbbbb',
    'ANTHROPIC_API_KEY': 'test-anthropic-key',
    'SESSION_COOKIE_SECURE': 'false',
}
for key, value in _test_env_vars.items():
    os.environ.setdefault(key, value)

def pytest_configure(config):
    """Run before pytest starts collecting tests (for logging/debugging)."""
    pass
