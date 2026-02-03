import os
import json
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify, session,
    redirect, url_for, send_from_directory
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

# Ensure upload folder exists
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

# Simple file metadata storage (JSON file instead of SQLite for simplicity)
METADATA_FILE = os.path.join(app.instance_path, 'files_metadata.json')
os.makedirs(app.instance_path, exist_ok=True)


def load_metadata():
    """Load file metadata from JSON file."""
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r') as f:
            return json.load(f)
    return {'files': []}


def save_metadata(data):
    """Save file metadata to JSON file."""
    with open(METADATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def auth_required(f):
    """Decorator to require authentication for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('uplink_login'))

        # Check session expiry
        auth_time = session.get('auth_time')
        if auth_time:
            auth_datetime = datetime.fromisoformat(auth_time)
            if datetime.now() - auth_datetime > timedelta(hours=config.SESSION_LIFETIME_HOURS):
                session.clear()
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'error': 'Session expired'}), 401
                return redirect(url_for('uplink_login'))

        return f(*args, **kwargs)
    return decorated_function


# Page Routes
@app.route('/')
def home():
    return render_template('home.html')


@app.route('/projects')
def projects():
    return render_template('projects.html')


@app.route('/uplink')
@auth_required
def uplink():
    return render_template('uplink.html')


@app.route('/uplink/login')
def uplink_login():
    if session.get('authenticated'):
        return redirect(url_for('uplink'))
    return render_template('uplink_login.html')


# API Routes
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()
    password = data.get('password', '')

    if check_password_hash(config.UPLINK_PASSWORD_HASH, password):
        session['authenticated'] = True
        session['auth_time'] = datetime.now().isoformat()
        return jsonify({'success': True})

    return jsonify({'error': 'Invalid password'}), 401


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/api/projects')
def api_projects():
    projects_file = os.path.join(os.path.dirname(__file__), 'projects.json')
    with open(projects_file, 'r') as f:
        data = json.load(f)
    return jsonify(data)


@app.route('/api/files')
@auth_required
def api_files():
    metadata = load_metadata()
    return jsonify(metadata)


@app.route('/api/files/upload', methods=['POST'])
@auth_required
def api_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Generate unique ID and secure filename
    file_id = str(uuid.uuid4())
    original_filename = secure_filename(file.filename)
    stored_filename = f"{file_id}_{original_filename}"

    # Save file
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
    file.save(filepath)

    # Get file size
    file_size = os.path.getsize(filepath)

    # Save metadata
    metadata = load_metadata()
    file_entry = {
        'id': file_id,
        'name': original_filename,
        'stored_name': stored_filename,
        'size': file_size,
        'uploaded': datetime.now().isoformat(),
        'uploader': session.get('uploader_name', 'Anonymous')
    }
    metadata['files'].append(file_entry)
    save_metadata(metadata)

    return jsonify({'success': True, 'file': file_entry})


@app.route('/api/files/<file_id>/download')
@auth_required
def api_download(file_id):
    metadata = load_metadata()
    file_entry = next((f for f in metadata['files'] if f['id'] == file_id), None)

    if not file_entry:
        return jsonify({'error': 'File not found'}), 404

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        file_entry['stored_name'],
        download_name=file_entry['name'],
        as_attachment=True
    )


@app.route('/api/files/<file_id>', methods=['DELETE'])
@auth_required
def api_delete(file_id):
    metadata = load_metadata()
    file_entry = next((f for f in metadata['files'] if f['id'] == file_id), None)

    if not file_entry:
        return jsonify({'error': 'File not found'}), 404

    # Delete physical file
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file_entry['stored_name'])
    if os.path.exists(filepath):
        os.remove(filepath)

    # Remove from metadata
    metadata['files'] = [f for f in metadata['files'] if f['id'] != file_id]
    save_metadata(metadata)

    return jsonify({'success': True})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
