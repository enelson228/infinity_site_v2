import logging
import os
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, session, send_from_directory
from werkzeug.utils import secure_filename
import config
import database
from auth import login_required
from utils import is_allowed_upload

logger = logging.getLogger(__name__)

uplink_bp = Blueprint('uplink', __name__)

@uplink_bp.route('/uplink')
@login_required
def uplink():
    return render_template('uplink.html')

@uplink_bp.route('/api/files')
@login_required
def api_files():
    files = database.list_files()
    return jsonify({'files': files})

@uplink_bp.route('/api/files/upload', methods=['POST'])
@login_required
def api_upload():
    logger.info('Upload attempt: files=%s csrf_header=%s session_has_csrf=%s',
                list(request.files.keys()),
                bool(request.headers.get('X-CSRF-Token')),
                bool(session.get('csrf_token')))
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not is_allowed_upload(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    file_id = str(uuid.uuid4())
    original_filename = secure_filename(file.filename)
    stored_filename = f"{file_id}_{original_filename}"

    filepath = os.path.join(config.UPLOAD_FOLDER, stored_filename)
    file.save(filepath)
    file_size = os.path.getsize(filepath)

    file_entry = {
        'id': file_id,
        'name': original_filename,
        'stored_name': stored_filename,
        'size': file_size,
        'uploaded': datetime.now().isoformat(),
        'uploader': session.get('username', 'Anonymous')
    }
    
    database.add_file(
        file_id=file_entry['id'],
        name=file_entry['name'],
        stored_name=file_entry['stored_name'],
        size=file_entry['size'],
        uploaded=file_entry['uploaded'],
        uploader=file_entry['uploader']
    )

    return jsonify({'success': True, 'file': file_entry})

@uplink_bp.route('/api/files/<file_id>/download')
@login_required
def api_download(file_id):
    file_entry = database.get_file(file_id)

    if not file_entry:
        return jsonify({'error': 'File not found'}), 404

    return send_from_directory(
        config.UPLOAD_FOLDER,
        file_entry['stored_name'],
        download_name=file_entry['name'],
        as_attachment=True
    )

@uplink_bp.route('/api/files/<file_id>/preview')
@login_required
def api_preview(file_id):
    file_entry = database.get_file(file_id)
    if not file_entry:
        return jsonify({'error': 'File not found'}), 404

    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    filename = file_entry['name'].lower()
    file_ext = filename.rsplit('.', 1)[-1] if '.' in filename else ''
    if file_ext not in allowed_extensions:
        return jsonify({'error': 'File is not an image'}), 400

    return send_from_directory(
        config.UPLOAD_FOLDER,
        file_entry['stored_name'],
        download_name=file_entry['name'],
        as_attachment=False
    )

@uplink_bp.route('/api/files/<file_id>', methods=['DELETE'])
@login_required
def api_delete(file_id):
    stored_name = database.delete_file(file_id)
    if not stored_name:
        return jsonify({'error': 'File not found'}), 404

    filepath = os.path.join(config.UPLOAD_FOLDER, stored_name)
    if os.path.exists(filepath):
        os.remove(filepath)

    return jsonify({'success': True})
