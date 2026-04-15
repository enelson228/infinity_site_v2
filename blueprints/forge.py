import base64
import json
import os
import urllib.request
from datetime import datetime
from flask import Blueprint, jsonify, render_template, request
import config
import database
from auth import login_required

forge_bp = Blueprint('forge', __name__)

_FORGE_OUTPUTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'static', 'forge_outputs'
)

_RUNPOD_BASE = 'https://api.runpod.ai/v2'


def _runpod_headers():
    return {
        'Authorization': f'Bearer {config.RUNPOD_API_KEY}',
        'Content-Type': 'application/json',
    }


@forge_bp.route('/forge')
@login_required
def forge():
    images = database.list_forge_images()
    endpoint_configured = bool(config.RUNPOD_API_KEY and config.SD_ENDPOINT_ID)
    return render_template('forge.html', images=images, endpoint_configured=endpoint_configured)


@forge_bp.route('/api/forge/generate', methods=['POST'])
@login_required
def api_forge_generate():
    if not config.RUNPOD_API_KEY or not config.SD_ENDPOINT_ID:
        return jsonify({'error': 'Image generation endpoint not configured'}), 503

    data = request.get_json(silent=True) or {}
    prompt = (data.get('prompt') or '').strip()
    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400
    if len(prompt) > 500:
        return jsonify({'error': 'Prompt must be 500 characters or fewer'}), 400

    negative_prompt = (data.get('negative_prompt') or '').strip()

    payload = json.dumps({
        'input': {
            'prompt': prompt,
            'negative_prompt': negative_prompt,
            'num_inference_steps': 20,
            'width': 1024,
            'height': 1024,
        }
    }).encode()

    url = f'{_RUNPOD_BASE}/{config.SD_ENDPOINT_ID}/run'
    req = urllib.request.Request(url, data=payload, headers=_runpod_headers(), method='POST')

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
        return jsonify({'job_id': result['id']})
    except Exception as e:
        return jsonify({'error': f'RunPod error: {e}'}), 502
