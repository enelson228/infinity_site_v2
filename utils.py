from flask import request
import config
import database

def client_ip() -> str:
    """Return the real client IP, respecting TRUSTED_PROXIES reverse-proxy hops."""
    if config.TRUSTED_PROXIES > 0:
        forwarded = request.headers.get('X-Forwarded-For', '')
        if forwarded:
            parts = [p.strip() for p in forwarded.split(',')]
            idx = max(0, len(parts) - config.TRUSTED_PROXIES)
            return parts[idx]
    return request.remote_addr or 'unknown'

def is_rate_limited(bucket: str) -> bool:
    """
    Check if a bucket is rate limited using the SQLite database.
    This works across multiple worker processes.
    """
    return database.check_rate_limit(
        bucket,
        config.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        config.LOGIN_RATE_LIMIT_MAX_ATTEMPTS
    )

def is_allowed_upload(filename: str) -> bool:
    if not config.UPLOAD_ALLOWED_EXTENSIONS:
        return True
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in config.UPLOAD_ALLOWED_EXTENSIONS
