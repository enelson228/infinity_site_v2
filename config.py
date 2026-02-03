import os
from werkzeug.security import generate_password_hash

# Flask configuration
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')

# Upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size

# Session configuration
SESSION_LIFETIME_HOURS = 24

# Shared password for Uplink Cache (change this!)
# Default password: "noble6" - generate new hash with:
# python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password', method='pbkdf2:sha256'))"
UPLINK_PASSWORD_HASH = generate_password_hash('noble6', method='pbkdf2:sha256')
