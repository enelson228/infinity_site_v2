import os
from flask import Blueprint, send_from_directory

coms_uplink_bp = Blueprint('coms_uplink', __name__)

_STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'static', 'tools', 'coms-uplink'
)

@coms_uplink_bp.route('/coms-uplink')
def coms_uplink():
    return send_from_directory(_STATIC_DIR, 'index.html')
