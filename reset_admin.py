import os
import sqlite3
from werkzeug.security import generate_password_hash
from datetime import datetime

# Set dummy env vars so we can import database/config without errors
os.environ.setdefault('SECRET_KEY', 'reset-only')
os.environ.setdefault('UPLINK_PASSWORD_HASH', 'reset-only')
os.environ.setdefault('CLAUDE_PASSWORD_HASH', 'reset-only')
os.environ.setdefault('ANTHROPIC_API_KEY', 'reset-only')

import database

def reset_admin(username, password):
    print(f"Resetting password for user: {username}...")
    pw_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    with database._db_conn() as conn:
        # Check if user exists
        cur = conn.execute("SELECT id FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        
        if row:
            conn.execute(
                "UPDATE users SET password_hash = ?, disabled = 0, role = 'admin' WHERE username = ?",
                (pw_hash, username)
            )
            print(f"User {username} updated successfully.")
        else:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, created_at, disabled)
                VALUES (?, ?, ?, ?, 0)
                """,
                (username, pw_hash, 'admin', datetime.now().isoformat())
            )
            print(f"User {username} created successfully.")
        conn.commit()

if __name__ == "__main__":
    # You can change 'admin123' to whatever password you want to use
    reset_admin('john117', 'admin123')
    print("\nPassword set to: admin123")
    print("You can now log in at http://localhost:5173/login")
