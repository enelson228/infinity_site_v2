import base64
import json
import logging
import os
import re
import urllib.error
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


_ENDPOINT_PROFILES = {
    'sdxl': {
        'value': 'sdxl',
        'label': 'SDXL 2.1.1 Serverless',
        'model': 'sdxl-2.1.1',
        'model_label': 'SDXL 2.1.1',
        'defaults': {
            'steps': 30,
            'width': 1024,
            'height': 1024,
            'guidance': 7.5,
        },
        'presets': [
            {'value': '1x1-balanced', 'label': '1:1 Balanced - 30stp / CFG 7.5 / 1024x1024', 'steps': 30, 'guidance': 7.5, 'width': 1024, 'height': 1024},
            {'value': '1x1-detail', 'label': '1:1 Detail - 40stp / CFG 8.0 / 1024x1024', 'steps': 40, 'guidance': 8.0, 'width': 1024, 'height': 1024},
            {'value': '4x3-balanced', 'label': '4:3 Balanced - 30stp / CFG 7.5 / 1152x896', 'steps': 30, 'guidance': 7.5, 'width': 1152, 'height': 896},
            {'value': '16x9-cinematic', 'label': '16:9 Cinematic - 35stp / CFG 7.5 / 1344x768', 'steps': 35, 'guidance': 7.5, 'width': 1344, 'height': 768},
            {'value': '3x4-portrait', 'label': '3:4 Portrait - 35stp / CFG 8.0 / 896x1152', 'steps': 35, 'guidance': 8.0, 'width': 896, 'height': 1152},
            {'value': '9x16-portrait', 'label': '9:16 Portrait - 35stp / CFG 8.0 / 768x1344', 'steps': 35, 'guidance': 8.0, 'width': 768, 'height': 1344},
        ],
    },
    'forge': {
        'value': 'forge',
        'label': 'Forge Juggernaut XL',
        'model': 'juggernaut-xl',
        'model_label': 'Juggernaut XL',
        'defaults': {
            'steps': 28,
            'width': 1024,
            'height': 1024,
            'guidance': 7.0,
        },
        'presets': [
            {'value': '1x1-balanced', 'label': '1:1 Balanced - 20stp / CFG 5.0 / 1024x1024', 'steps': 20, 'guidance': 5.0, 'width': 1024, 'height': 1024},
            {'value': '1x1-sweetspot', 'label': '1:1 Sweet Spot - 28stp / CFG 7.0 / 1024x1024', 'steps': 28, 'guidance': 7.0, 'width': 1024, 'height': 1024},
            {'value': '1x1-detail', 'label': '1:1 Detail - 35stp / CFG 7.5 / 1024x1024', 'steps': 35, 'guidance': 7.5, 'width': 1024, 'height': 1024},
            {'value': '4x3-balanced', 'label': '4:3 Balanced - 24stp / CFG 6.0 / 1152x896', 'steps': 24, 'guidance': 6.0, 'width': 1152, 'height': 896},
            {'value': '16x9-cinematic', 'label': '16:9 Cinematic - 28stp / CFG 7.0 / 1344x768', 'steps': 28, 'guidance': 7.0, 'width': 1344, 'height': 768},
            {'value': '3x4-portrait', 'label': '3:4 Portrait - 28stp / CFG 7.0 / 896x1152', 'steps': 28, 'guidance': 7.0, 'width': 896, 'height': 1152},
            {'value': '9x16-portrait', 'label': '9:16 Portrait - 28stp / CFG 7.0 / 768x1344', 'steps': 28, 'guidance': 7.0, 'width': 768, 'height': 1344},
        ],
    },
    'wan': {
        'value': 'wan',
        'label': 'Wan2.2 Video Serverless',
        'model': 'wan2.2',
        'model_label': 'Wan 2.2',
        'defaults': {
            'steps': 10,
            'width': 480,
            'height': 832,
            'guidance': 2.0,
        },
        'presets': [
            {'value': 'portrait', 'label': 'Portrait - 10stp / CFG 2.0 / 480x832', 'steps': 10, 'guidance': 2.0, 'width': 480, 'height': 832},
            {'value': 'landscape', 'label': 'Landscape - 10stp / CFG 2.0 / 832x480', 'steps': 10, 'guidance': 2.0, 'width': 832, 'height': 480},
        ],
    },
}


def _runpod_headers():
    return {
        'Authorization': f'Bearer {config.RUNPOD_API_KEY}',
        'Content-Type': 'application/json',
    }


def _extract_b64_image(output):
    """
    Robustly extract the first base64 image string from various RunPod output shapes.
    Prioritizes common image keys and validates that the string looks like base64.
    """
    if not output:
        return None
        
    def is_likely_b64(s):
        if not isinstance(s, str) or len(s) < 40:
            return False
        # Base64 for images is typically very long and has no spaces.
        # It may have a data:image/... prefix.
        if ' ' in s.strip():
            return False
        return True

    # 1. If it's a dict, check common direct keys FIRST
    if isinstance(output, dict):
        for key in ['image', 'images', 'output', 'results', 'img_base64', 'b64']:
            val = output.get(key)
            if val:
                # If the value is a list, check its items
                if isinstance(val, list):
                    for item in val:
                        res = _extract_b64_image(item)
                        if res: return res
                # If the value is a string, check if it's likely b64
                elif is_likely_b64(val):
                    return val
                # Otherwise recurse
                elif isinstance(val, dict):
                    res = _extract_b64_image(val)
                    if res: return res
        
        # Fallback: search all values if no common keys matched
        for val in output.values():
            if isinstance(val, (str, list, dict)):
                res = _extract_b64_image(val)
                if res: return res

    # 2. If it's a list, try extracting from each item
    if isinstance(output, list):
        for item in output:
            res = _extract_b64_image(item)
            if res: return res

    # 3. If it's a string, check if it's likely b64
    if is_likely_b64(output):
        return output
                    
    return None


def _available_endpoint_profiles():
    profiles = {}
    if config.SDXL_ENDPOINT_ID:
        profiles['sdxl'] = _ENDPOINT_PROFILES['sdxl']
    if config.FORGE_ENDPOINT_ID:
        profiles['forge'] = _ENDPOINT_PROFILES['forge']
    if config.WAN_VIDEO_ID:
        profiles['wan'] = _ENDPOINT_PROFILES['wan']
    return profiles


def _normalize_worker_type(worker_type):
    return worker_type if worker_type in _available_endpoint_profiles() else 'sdxl'


def _profile_for_worker(worker_type):
    profiles = _available_endpoint_profiles()
    normalized = worker_type if worker_type in profiles else next(iter(profiles), None)
    return profiles.get(normalized), normalized


@forge_bp.route('/forge')
@login_required
def forge():
    images = database.list_forge_images()
    has_sdxl = bool(config.SDXL_ENDPOINT_ID)
    has_forge = bool(config.FORGE_ENDPOINT_ID)
    endpoint_profiles = _available_endpoint_profiles()
    default_worker_type = 'sdxl' if has_sdxl else ('forge' if has_forge else next(iter(endpoint_profiles), 'sdxl'))
    endpoint_configured = bool(config.RUNPOD_API_KEY) and bool(endpoint_profiles)

    return render_template('forge.html',
                           images=images,
                           endpoint_configured=endpoint_configured,
                           has_sdxl=has_sdxl,
                           has_forge=has_forge,
                           endpoint_profiles=endpoint_profiles,
                           default_worker_type=default_worker_type)


@forge_bp.route('/api/forge/generate', methods=['POST'])
@login_required
def api_forge_generate():
    if not config.RUNPOD_API_KEY:
        return jsonify({'error': 'RunPod API Key not configured'}), 503
    
    if not _available_endpoint_profiles():
        logger.error("No RunPod endpoints configured in config.py or environment")
        return jsonify({'error': 'Image generation endpoint not configured'}), 503

    data = request.get_json(silent=True) or {}
    prompt = (data.get('prompt') or '').strip()
    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400
    if len(prompt) > 500:
        return jsonify({'error': 'Prompt must be 500 characters or fewer'}), 400

    negative_prompt = (data.get('negative_prompt') or '').strip()
    worker_type = _normalize_worker_type(data.get('worker_type', 'sdxl'))
    profile, worker_type = _profile_for_worker(worker_type)
    if not profile:
        logger.error("No RunPod endpoints configured in config.py or environment")
        return jsonify({'error': 'Image generation endpoint not configured'}), 503
    model = profile['model']

    def _clamp(val, lo, hi, default):
        try:
            return max(lo, min(hi, int(val)))
        except (TypeError, ValueError):
            return default

    def _clamp_f(val, lo, hi, default):
        try:
            return max(lo, min(hi, float(val)))
        except (TypeError, ValueError):
            return default

    defaults = profile['defaults']
    default_steps = defaults['steps']
    default_width = defaults['width']
    default_height = defaults['height']
    default_guidance = defaults['guidance']

    max_steps = 60 if worker_type == 'forge' else 150
    max_size = 1536 if worker_type == 'forge' else 4096
    max_guidance = 15.0 if worker_type == 'forge' else 30.0

    steps        = _clamp(data.get('steps'),          1,   max_steps, default_steps)
    width        = _clamp(data.get('width'),           256, max_size,  default_width)
    height       = _clamp(data.get('height'),          256, max_size,  default_height)
    guidance     = _clamp_f(data.get('guidance_scale'), 1.0, max_guidance, default_guidance)
    seed_raw     = data.get('seed')
    seed         = _clamp(seed_raw, 0, 2**32 - 1, -1) if seed_raw not in (None, '', -1, '-1') else -1

    if worker_type == 'wan':
        image_base64 = data.get('image_base64')
        if not image_base64:
            return jsonify({'error': 'Image is required for Wan2.2 Video Generation'}), 400
        
        # Strip data URL prefix if present (e.g. "data:image/jpeg;base64,")
        if isinstance(image_base64, str) and ',' in image_base64:
            image_base64 = image_base64.split(',', 1)[1]
        
        gen_input = {
            'prompt': prompt,
            'image_base64': image_base64,
            'width': width,
            'height': height,
            'steps': steps,
            'cfg': guidance,
        }
    else:
        gen_input = {
            'prompt': prompt,
            'negative_prompt': negative_prompt,
            'num_inference_steps': steps,
            'width': width,
            'height': height,
            'guidance_scale': guidance,
        }
        # Only include 'model' if it's not the default sdxl, as some workers reject it
        if worker_type != 'sdxl':
            gen_input['model'] = model
        
    if seed >= 0:
        gen_input['seed'] = seed

    payload = json.dumps({'input': gen_input}).encode()

    # Determine endpoint ID
    if worker_type == 'wan':
        endpoint_id = config.WAN_VIDEO_ID
    else:
        endpoint_id = config.FORGE_ENDPOINT_ID if worker_type == 'forge' else config.SDXL_ENDPOINT_ID
    
    if not endpoint_id:
        return jsonify({'error': f'Endpoint for {worker_type} not configured'}), 503

    url = f'{_RUNPOD_BASE}/{endpoint_id}/run'
    req = urllib.request.Request(url, data=payload, headers=_runpod_headers(), method='POST')

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
        
        logger.info(f"RunPod Generate response for {worker_type}: {result}")
        job_id = result.get('id')
        if not job_id:
            logger.error("RunPod Generate missing job ID for endpoint %s: %s", endpoint_id, result)
            return jsonify({
                'error': (
                    'RunPod did not return a job ID. '
                    'Check that FORGE_ENDPOINT_ID points to an async queue-based endpoint.'
                ),
                'runpod_status': result.get('status'),
            }), 502

        # Store endpoint_id in return so client can pass it back for status checks
        return jsonify({
            'job_id': job_id,
            'endpoint_id': endpoint_id,
            'status': result.get('status', 'IN_QUEUE'),
            'worker_type': worker_type,
            'model': model,
        })
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            detail = e.read().decode()
        except Exception:
            detail = str(e)
        logger.error("RunPod Generate HTTP error: %s", detail)
        return jsonify({'error': f'RunPod error: {detail or e}'}), 502
    except Exception as e:
        logger.error(f"RunPod Generate error: {e}")
        return jsonify({'error': f'RunPod error: {e}'}), 502


_TERMINAL_STATUSES = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT'}


@forge_bp.route('/api/forge/status/<job_id>')
@login_required
def api_forge_status(job_id):
    if not re.match(r'^[a-zA-Z0-9_-]+$', job_id):
        return jsonify({'error': 'Invalid job ID'}), 400
    
    # Client should pass endpoint_id as a query param. If it does not,
    # prefer the explicit worker-specific endpoints before the legacy default.
    worker_type = _normalize_worker_type(request.args.get('worker_type', 'sdxl'))
    endpoint_id = request.args.get('endpoint_id')
    if not endpoint_id:
        if worker_type == 'wan':
            endpoint_id = config.WAN_VIDEO_ID
        elif worker_type == 'forge':
            endpoint_id = config.FORGE_ENDPOINT_ID or config.SDXL_ENDPOINT_ID or config.SD_ENDPOINT_ID
        else:
            endpoint_id = config.SDXL_ENDPOINT_ID or config.FORGE_ENDPOINT_ID or config.SD_ENDPOINT_ID
    if not endpoint_id:
        return jsonify({'error': 'Endpoint ID missing for status check'}), 400

    if not config.RUNPOD_API_KEY:
        return jsonify({'error': 'Endpoint not configured'}), 503

    prompt = request.args.get('prompt', '')
    profile, worker_type = _profile_for_worker(worker_type)
    model = (profile or _ENDPOINT_PROFILES['sdxl'])['model']

    url = f'{_RUNPOD_BASE}/{endpoint_id}/status/{job_id}'
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
        b64_image = _extract_b64_image(output)

        # Fallback: if 'output' yielded nothing, try searching the entire result object
        if not b64_image:
            b64_image = _extract_b64_image(result)

        if not b64_image:
            logger.error(f"Forge: No image found in RunPod output. Keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
            return jsonify({'error': 'No image found in response', 'status': 'FAILED'}), 502


        # Strip data URL prefix if worker returns "data:image/png;base64,<data>"
        if isinstance(b64_image, str) and b64_image.startswith('data:'):
            b64_image = b64_image.split(',', 1)[1]

        extension = '.mp4' if worker_type == 'wan' else '.png'
        filename = f'{job_id}{extension}'
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

        img_id = database.add_forge_image(job_id, prompt, filename, datetime.now().isoformat(), model, worker_type)
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
