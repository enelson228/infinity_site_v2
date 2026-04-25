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

CESIUM_ION_TOKEN = os.environ.get('CESIUM_ION_TOKEN', '')

# Trusted reverse proxy count for accurate client IP (set to 1 if behind Nginx/Caddy)
TRUSTED_PROXIES = int(os.environ.get('TRUSTED_PROXIES', '1'))

# Rate limiting (non-secret)
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = int(os.environ.get('LOGIN_RATE_LIMIT_MAX_ATTEMPTS', '10'))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get('LOGIN_RATE_LIMIT_WINDOW_SECONDS', '600'))

# Telemetry access (non-secret)
TELEMETRY_PUBLIC = os.environ.get('TELEMETRY_PUBLIC', 'false').lower() in ('1', 'true', 'yes')

_DEFAULT_EXTENSIONS = 'pdf,txt,png,jpg,jpeg,gif,webp,zip,tar,gz,mp4,mp3,doc,docx,csv,json,md'
UPLOAD_ALLOWED_EXTENSIONS = {
    ext.strip().lower().lstrip('.')
    for ext in os.environ.get('UPLOAD_ALLOWED_EXTENSIONS', _DEFAULT_EXTENSIONS).split(',')
    if ext.strip()
}

# GitHub API token for monitor dashboard (optional — GitHub panel disabled if missing)
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')

# RunPod serverless image generation
RUNPOD_API_KEY = os.environ.get('RUNPOD_API_KEY', '')
SD_ENDPOINT_ID = os.environ.get('SD_ENDPOINT_ID', '')
# Specific endpoint overrides. FORGE_ENDPOINT_ID is the Juggernaut XL endpoint.
SDXL_ENDPOINT_ID = os.environ.get('SDXL_ENDPOINT_ID', SD_ENDPOINT_ID)
FORGE_ENDPOINT_ID = os.environ.get('FORGE_ENDPOINT_ID', '')


# AI model for monitor recommendations (optional override)
AI_MODEL = os.environ.get('AI_MODEL', 'claude-haiku-4-5-20251001')

# Session cookie security
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
# Set SESSION_COOKIE_SECURE=False only in local dev without HTTPS
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'true').lower() not in ('0', 'false', 'no')
