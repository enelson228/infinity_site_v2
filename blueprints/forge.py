import base64
import json
import logging
import os
import urllib.request
from datetime import datetime
from flask import Blueprint, jsonify, render_template, request
import config
import database
from auth import login_required

logger = logging.getLogger(__name__)

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


_TERMINAL_STATUSES = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT'}


@forge_bp.route('/api/forge/status/<job_id>')
@login_required
def api_forge_status(job_id):
    if not config.RUNPOD_API_KEY or not config.SD_ENDPOINT_ID:
        return jsonify({'error': 'Endpoint not configured'}), 503

    prompt = request.args.get('prompt', '')

    url = f'{_RUNPOD_BASE}/{config.SD_ENDPOINT_ID}/status/{job_id}'
    req = urllib.request.Request(url, headers=_runpod_headers())

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
    except Exception as e:
        return jsonify({'error': f'RunPod error: {e}'}), 502

    status = result.get('status', 'UNKNOWN')

    if status == 'COMPLETED':
        # Idempotency: return existing record if already saved
        existing = database.get_forge_image_by_job_id(job_id)
        if existing:
            return jsonify({
                'status': 'COMPLETED',
                'image_url': f'/static/forge_outputs/{existing["filename"]}',
                'image_id': existing['id'],
            })

        # Extract base64 image — handle list-of-objects or dict output formats
        output = result.get('output')
        b64_image = None
        if isinstance(output, list) and output:
            b64_image = output[0].get('image') or output[0].get('images', [None])[0]
        elif isinstance(output, dict):
            b64_image = output.get('image') or (output.get('images') or [None])[0]

        if not b64_image:
            return jsonify({'error': 'No image in response', 'status': 'FAILED'}), 502

        # Strip data URL prefix if worker returns "data:image/png;base64,<data>"
        if isinstance(b64_image, str) and b64_image.startswith('data:'):
            b64_image = b64_image.split(',', 1)[1]

        filename = f'{job_id}.png'
        filepath = os.path.join(_FORGE_OUTPUTS, filename)

        try:
            # Fix missing padding (some workers omit trailing '=' characters)
            image_bytes = base64.b64decode(b64_image + '=' * (-len(b64_image) % 4))
            os.makedirs(_FORGE_OUTPUTS, exist_ok=True)
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
        except Exception as e:
            logger.error(f'Forge: failed to save image {job_id}: {e}')
            return jsonify({'error': 'Failed to save image', 'status': 'FAILED'}), 500

        img_id = database.add_forge_image(job_id, prompt, filename, datetime.now().isoformat())
        return jsonify({
            'status': 'COMPLETED',
            'image_url': f'/static/forge_outputs/{filename}',
            'image_id': img_id,
        })

    if status in _TERMINAL_STATUSES:
        return jsonify({'status': 'FAILED', 'error': result.get('error', status)})

    return jsonify({'status': status})


@forge_bp.route('/api/forge/images/<int:image_id>', methods=['DELETE'])
@login_required
def api_forge_delete(image_id):
    row = database.get_forge_image(image_id)
    if not row:
        return jsonify({'error': 'Not found'}), 404

    filepath = os.path.join(_FORGE_OUTPUTS, row['filename'])
    try:
        os.remove(filepath)
    except OSError as e:
        logger.error(f'Forge: could not delete file {filepath}: {e}')

    database.delete_forge_image(image_id)
    return jsonify({'success': True})
