import time
import psutil
from flask import Blueprint, render_template, jsonify
import config
import database
from auth import login_required

telemetry_bp = Blueprint('telemetry', __name__)

def telemetry_auth_required(f):
    if config.TELEMETRY_PUBLIC:
        return f
    return login_required(f)

@telemetry_bp.route('/telemetry')
@telemetry_auth_required
def telemetry():
    return render_template('telemetry.html')

@telemetry_bp.route('/api/telemetry')
@telemetry_auth_required
def api_telemetry():
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_freq = psutil.cpu_freq()
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    net = psutil.net_io_counters()
    uptime_seconds = int(time.time() - psutil.boot_time())
    load_avg = psutil.getloadavg()

    # Get history for charts
    history = database.get_telemetry_history(24)

    return jsonify({
        'cpu': {
            'percent': round(cpu_percent, 1),
            'cores_logical': psutil.cpu_count(logical=True),
            'cores_physical': psutil.cpu_count(logical=False),
            'freq_current': round(cpu_freq.current, 0) if cpu_freq else None,
            'freq_max': round(cpu_freq.max, 0) if cpu_freq else None,
        },
        'ram': {
            'total': ram.total,
            'used': ram.used,
            'available': ram.available,
            'percent': round(ram.percent, 1),
        },
        'disk': {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': round(disk.percent, 1),
        },
        'network': {
            'bytes_sent': net.bytes_sent,
            'bytes_recv': net.bytes_recv,
            'packets_sent': net.packets_sent,
            'packets_recv': net.packets_recv,
        },
        'uptime_seconds': uptime_seconds,
        'load_avg': {
            'one': round(load_avg[0], 2),
            'five': round(load_avg[1], 2),
            'fifteen': round(load_avg[2], 2),
        },
        'timestamp': time.time(),
        'history': history
    })

@telemetry_bp.route('/api/telemetry/audit')
@telemetry_auth_required
def api_telemetry_audit():
    # Public-ish audit feed (system events only, no IPs or sensitive details)
    events = database.get_audit_log(limit=50)
    # Sanitize for telemetry view
    sanitized = []
    for e in events:
        sanitized.append({
            'created_at': e['created_at'],
            'event_type': e['event_type'],
            'detail': e['detail'] if 'username' in (e['detail'] or '') else '' # Hide specific details unless safe
        })
    return jsonify({'events': sanitized})
