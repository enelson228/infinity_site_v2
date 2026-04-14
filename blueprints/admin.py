from flask import Blueprint, jsonify, request, session
import database
from auth import admin_required
from werkzeug.security import generate_password_hash

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/api/admin/users', methods=['GET'])
@admin_required
def api_admin_list_users():
    users = database.list_users()
    return jsonify({'users': users})

@admin_bp.route('/api/admin/users', methods=['POST'])
@admin_required
def api_admin_create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    role = (data.get('role') or 'user').strip().lower()
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if role not in ('user', 'admin'):
        return jsonify({'error': 'Invalid role'}), 400
    pw_hash = generate_password_hash(password, method='scrypt')
    try:
        database.create_user(username, pw_hash, role)
    except Exception: # In a real app, catch sqlite3.IntegrityError specifically
        return jsonify({'error': 'Username already exists or database error'}), 409
    
    actor_id = session.get('user_id')
    from utils import client_ip
    database.append_audit('user_create', client_ip(), actor_user_id=actor_id, detail=f'username={username} role={role}')
    return jsonify({'success': True})

@admin_bp.route('/api/admin/users/<int:user_id>/password', methods=['PUT'])
@admin_required
def api_admin_reset_password(user_id: int):
    data = request.get_json(silent=True) or {}
    password = data.get('password') or ''
    if not password:
        return jsonify({'error': 'Password required'}), 400
    pw_hash = generate_password_hash(password, method='scrypt')
    if not database.update_user_password(user_id, pw_hash):
        return jsonify({'error': 'User not found'}), 404
    
    actor_id = session.get('user_id')
    from utils import client_ip
    database.append_audit('password_reset', client_ip(), actor_user_id=actor_id, target_user_id=user_id)
    return jsonify({'success': True})

@admin_bp.route('/api/admin/users/<int:user_id>/disable', methods=['PUT'])
@admin_required
def api_admin_disable_user(user_id: int):
    actor_id = session.get('user_id')
    if actor_id and int(actor_id) == user_id:
        return jsonify({'error': 'Cannot disable your own account'}), 400
    if not database.set_user_disabled(user_id, True):
        return jsonify({'error': 'User not found'}), 404
    
    from utils import client_ip
    database.append_audit('user_disable', client_ip(), actor_user_id=actor_id, target_user_id=user_id)
    return jsonify({'success': True})

@admin_bp.route('/api/admin/users/<int:user_id>/enable', methods=['PUT'])
@admin_required
def api_admin_enable_user(user_id: int):
    if not database.set_user_disabled(user_id, False):
        return jsonify({'error': 'User not found'}), 404
    
    actor_id = session.get('user_id')
    from utils import client_ip
    database.append_audit('user_enable', client_ip(), actor_user_id=actor_id, target_user_id=user_id)
    return jsonify({'success': True})

@admin_bp.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def api_admin_delete_user(user_id: int):
    actor_id = session.get('user_id')
    if actor_id and int(actor_id) == user_id:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    if not database.delete_user(user_id):
        return jsonify({'error': 'User not found'}), 404
    
    from utils import client_ip
    database.append_audit('user_delete', client_ip(), actor_user_id=actor_id, target_user_id=user_id)
    return jsonify({'success': True})

@admin_bp.route('/api/admin/memory/<int:user_id>', methods=['GET'])
@admin_required
def api_admin_list_memory(user_id: int):
    return jsonify({'memories': database.list_memories(user_id)})

@admin_bp.route('/api/admin/memory/<int:user_id>', methods=['POST'])
@admin_required
def api_admin_add_memory(user_id: int):
    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'Content required'}), 400
    database.add_memory(user_id, content)
    
    actor_id = session.get('user_id')
    from utils import client_ip
    database.append_audit('memory_add', client_ip(), actor_user_id=actor_id, target_user_id=user_id)
    return jsonify({'success': True})

@admin_bp.route('/api/admin/memory/<int:memory_id>', methods=['DELETE'])
@admin_required
def api_admin_delete_memory(memory_id: int):
    target_user_id = database.delete_memory(memory_id)
    if target_user_id is None:
        return jsonify({'error': 'Memory not found'}), 404
    
    actor_id = session.get('user_id')
    from utils import client_ip
    database.append_audit('memory_delete', client_ip(), actor_user_id=actor_id, target_user_id=target_user_id)
    return jsonify({'success': True})

@admin_bp.route('/api/admin/audit', methods=['GET'])
@admin_required
def api_admin_audit():
    events = database.get_audit_log()
    return jsonify({'events': events})
