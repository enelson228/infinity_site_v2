import os


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

# Flask configuration (required)
SECRET_KEY = _required_env('SECRET_KEY')

# Upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size

# Session configuration
SESSION_LIFETIME_HOURS = 24

# Shared password hash for Uplink Cache (required)
UPLINK_PASSWORD_HASH = _required_env('UPLINK_PASSWORD_HASH')

# INFINITY Terminal password hash (required, separate from Uplink Cache)
CLAUDE_PASSWORD_HASH = _required_env('CLAUDE_PASSWORD_HASH')

# Anthropic API key (required)
ANTHROPIC_API_KEY = _required_env('ANTHROPIC_API_KEY')

# Rate limiting (non-secret)
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = int(os.environ.get('LOGIN_RATE_LIMIT_MAX_ATTEMPTS', '10'))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get('LOGIN_RATE_LIMIT_WINDOW_SECONDS', '600'))

# Telemetry access (non-secret)
TELEMETRY_PUBLIC = os.environ.get('TELEMETRY_PUBLIC', 'false').lower() in ('1', 'true', 'yes')

# Optional file extension allowlist (comma-separated, lowercased)
UPLOAD_ALLOWED_EXTENSIONS = {
    ext.strip().lower().lstrip('.')
    for ext in os.environ.get('UPLOAD_ALLOWED_EXTENSIONS', '').split(',')
    if ext.strip()
}
