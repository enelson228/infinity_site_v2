import base64
import json
import logging
import os
import re
from pathlib import Path
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
_FORGE_VIDEOS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'static', 'forge_videos'
)

_RUNPOD_BASE = 'https://api.runpod.ai/v2'

_MODEL_REGISTRY = {
    'juggernaut-xl': {
        'endpoint_attr': 'FORGE_ENDPOINT_ID',
        'worker_type': 'forge',
        'default_steps': 28,
        'default_guidance': 7.0,
        'max_steps': 60,
        'max_size': 1536,
    },
    'cyberrealistic-pony': {
        'endpoint_attr': 'CYBERREALISTIC_PONY_ENDPOINT_ID',
        'worker_type': 'forge',
        'default_steps': 30,
        'default_guidance': 5.0,
        'max_steps': 60,
        'max_size': 1536,
    },
    'sdxl': {
        'endpoint_attr': 'SDXL_ENDPOINT_ID',
        'worker_type': 'sdxl',
        'default_steps': 75,
        'default_guidance': 11.5,
        'max_steps': 150,
        'max_size': 4096,
    },
}

_WORKER_DEFAULT_MODEL = {
    'forge': 'juggernaut-xl',
    'sdxl': 'sdxl',
}
_VIDEO_DEFAULTS = {
    'width': 480,
    'height': 832,
    'length': 81,
    'steps': 10,
    'cfg': 2.0,
}


def _runpod_headers():
    return {
        'Authorization': f'Bearer {config.RUNPOD_API_KEY}',
        'Content-Type': 'application/json',
    }


def _extract_b64_image(output):
    """Extract the first image from supported RunPod output shapes."""
    if isinstance(output, list) and output:
        return output[0].get('image') or output[0].get('images', [None])[0]
    if isinstance(output, dict):
        if 'images' in output and isinstance(output['images'], list) and output['images']:
            return output['images'][0]
        return output.get('image') or (output.get('images') or [None])[0]
    return None


def _extract_video_url(output):
    """Extract the first video URL from supported RunPod output shapes."""
    if isinstance(output, str):
        value = output.strip()
        if value.startswith(('http://', 'https://')):
            return value
        if value.startswith('data:') and ';base64,' not in value:
            return value
        return None
    if isinstance(output, list):
        for item in output:
            video_url = _extract_video_url(item)
            if video_url:
                return video_url
        return None
    if isinstance(output, dict):
        if isinstance(output.get('videos'), list):
            for item in output['videos']:
                video_url = _extract_video_url(item)
                if video_url:
                    return video_url
        for key in ('video_url', 'video', 'url'):
            value = output.get(key)
            if isinstance(value, str):
                video_url = _extract_video_url(value)
                if video_url:
                    return video_url
            if isinstance(value, dict):
                nested = _extract_video_url(value)
                if nested:
                    return nested
    return None


def _extract_b64_video(output):
    """Extract a base64-encoded video payload from supported RunPod output shapes."""
    if isinstance(output, str):
        value = output.strip()
        if value.startswith(('http://', 'https://')):
            return None
        if value.startswith('data:'):
            if ';base64,' in value:
                return value.split(',', 1)[1]
            return None
        return value
    if isinstance(output, list):
        for item in output:
            payload = _extract_b64_video(item)
            if payload:
                return payload
        return None
    if isinstance(output, dict):
        if isinstance(output.get('videos'), list):
            for item in output['videos']:
                payload = _extract_b64_video(item)
                if payload:
                    return payload
        for key in ('video_base64', 'video_b64', 'video', 'data', 'base64'):
            value = output.get(key)
            if isinstance(value, str):
                payload = _extract_b64_video(value)
                if payload:
                    return payload
            if isinstance(value, dict):
                nested = _extract_b64_video(value)
                if nested:
                    return nested
    return None


def _decode_video_base64(payload):
    if not payload:
        return None
    if payload.startswith('data:'):
        payload = payload.split(',', 1)[1]
    compact = ''.join(payload.split())
    return base64.b64decode(compact + '=' * (-len(compact) % 4))


def _get_endpoint(endpoint_attr):
    return getattr(config, endpoint_attr, '') if endpoint_attr else ''


def _request_int(name):
    value = request.args.get(name)
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _request_float(name):
    value = request.args.get(name)
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _forge_static_url_to_base64(image_url):
    if not image_url or not image_url.startswith('/static/forge_outputs/'):
        return None

    filename = image_url.rsplit('/', 1)[-1]
    if not filename:
        return None

    file_path = Path(_FORGE_OUTPUTS) / filename
    try:
        resolved = file_path.resolve(strict=True)
        outputs_root = Path(_FORGE_OUTPUTS).resolve()
        resolved.relative_to(outputs_root)
    except (FileNotFoundError, ValueError):
        return None

    return base64.b64encode(resolved.read_bytes()).decode('ascii')


def _available_models():
    return {
        model: bool(_get_endpoint(meta['endpoint_attr']))
        for model, meta in _MODEL_REGISTRY.items()
    }


def _resolve_model(worker_type, requested_model):
    model = (requested_model or '').strip().lower() or _WORKER_DEFAULT_MODEL.get(worker_type, 'sdxl')
    meta = _MODEL_REGISTRY.get(model)
    if meta and meta['worker_type'] == worker_type and _get_endpoint(meta['endpoint_attr']):
        return model, meta

    fallback_model = _WORKER_DEFAULT_MODEL.get(worker_type)
    fallback_meta = _MODEL_REGISTRY.get(fallback_model)
    if fallback_meta and _get_endpoint(fallback_meta['endpoint_attr']):
        return fallback_model, fallback_meta

    for candidate_model, candidate_meta in _MODEL_REGISTRY.items():
        if candidate_meta['worker_type'] == worker_type and _get_endpoint(candidate_meta['endpoint_attr']):
            return candidate_model, candidate_meta

    return None, None


@forge_bp.route('/forge')
@login_required
def forge():
    images = database.list_forge_images()
    videos = database.list_forge_videos()
    media_items = database.list_forge_media()

    available_models = _available_models()
    has_sdxl = available_models.get('sdxl', False)
    has_forge = any(
        available_models.get(model, False)
        for model, meta in _MODEL_REGISTRY.items()
        if meta['worker_type'] == 'forge'
    )
    has_wan = bool(config.WAN_VIDEO_ENDPOINT_ID)
    endpoint_configured = bool(config.RUNPOD_API_KEY) and (any(available_models.values()) or has_wan)

    return render_template(
        'forge.html',
        images=images,
        videos=videos,
        media_items=media_items,
        endpoint_configured=endpoint_configured,
        has_sdxl=has_sdxl,
        has_forge=has_forge,
        has_wan=has_wan,
        available_models=available_models,
        storytell_api_base=getattr(config, 'STORYTELL_API_BASE', '/storytell-api'),
    )


@forge_bp.route('/forge/video')
@login_required
def forge_video():
    videos = database.list_forge_videos()
    endpoint_configured = bool(config.RUNPOD_API_KEY and config.WAN_VIDEO_ENDPOINT_ID)
    return render_template(
        'forge_video.html',
        videos=videos,
        endpoint_configured=endpoint_configured,
    )


@forge_bp.route('/api/forge/generate', methods=['POST'])
@login_required
def api_forge_generate():
    if not config.RUNPOD_API_KEY:
        return jsonify({'error': 'RunPod API Key not configured'}), 503

    if not any(_available_models().values()):
        logger.error("No RunPod endpoints configured in config.py or environment")
        return jsonify({'error': 'Image generation endpoint not configured'}), 503

    data = request.get_json(silent=True) or {}
    prompt = (data.get('prompt') or '').strip()
    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400
    if len(prompt) > 500:
        return jsonify({'error': 'Prompt must be 500 characters or fewer'}), 400

    negative_prompt = (data.get('negative_prompt') or '').strip()
    worker_type = data.get('worker_type', 'sdxl')
    model, model_meta = _resolve_model(worker_type, data.get('model'))
    if not model or not model_meta:
        return jsonify({'error': f'Endpoint for {worker_type} not configured'}), 503

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

    default_steps = model_meta['default_steps']
    default_width = 1024
    default_height = 1024
    default_guidance = model_meta['default_guidance']

    max_steps = model_meta['max_steps']
    max_size = model_meta['max_size']

    steps        = _clamp(data.get('steps'),          1,   max_steps, default_steps)
    width        = _clamp(data.get('width'),           256, max_size,  default_width)
    height       = _clamp(data.get('height'),          256, max_size,  default_height)
    guidance     = _clamp_f(data.get('guidance_scale'), 1.0, 15.0 if worker_type == 'forge' else 30.0, default_guidance)
    seed_raw     = data.get('seed')
    seed         = _clamp(seed_raw, 0, 2**32 - 1, -1) if seed_raw not in (None, '', -1, '-1') else -1

    gen_input = {
        'prompt': prompt,
        'negative_prompt': negative_prompt,
        'num_inference_steps': steps,
        'width': width,
        'height': height,
        'guidance_scale': guidance,
        'model': model,
    }
    if seed >= 0:
        gen_input['seed'] = seed

    payload = json.dumps({'input': gen_input}).encode()

    endpoint_id = _get_endpoint(model_meta['endpoint_attr'])

    url = f'{_RUNPOD_BASE}/{endpoint_id}/run'
    req = urllib.request.Request(url, data=payload, headers=_runpod_headers(), method='POST')

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
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


@forge_bp.route('/api/forge/videos/generate', methods=['POST'])
@login_required
def api_forge_video_generate():
    if not config.RUNPOD_API_KEY:
        return jsonify({'error': 'RunPod API Key not configured'}), 503
    if not config.WAN_VIDEO_ENDPOINT_ID:
        return jsonify({'error': 'WAN video endpoint not configured'}), 503

    data = request.get_json(silent=True) or {}
    prompt = (data.get('prompt') or '').strip()
    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400
    if len(prompt) > 500:
        return jsonify({'error': 'Prompt must be 500 characters or fewer'}), 400

    negative_prompt = (data.get('negative_prompt') or '').strip()
    image_base64 = (data.get('image_base64') or '').strip()
    image_url = (data.get('image_url') or '').strip()
    if not image_base64:
        local_image_base64 = _forge_static_url_to_base64(image_url)
        if local_image_base64:
            image_base64 = local_image_base64
            image_url = ''

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

    # Handle 'size' param (e.g. "1280*720") from forge_video.html
    width, height = None, None
    size = data.get('size')
    if isinstance(size, str) and '*' in size:
        try:
            w_str, h_str = size.split('*', 1)
            width = int(w_str)
            height = int(h_str)
        except (ValueError, TypeError):
            pass

    width = _clamp(width if width is not None else data.get('width'), 256, 1280, _VIDEO_DEFAULTS['width'])
    height = _clamp(height if height is not None else data.get('height'), 256, 1280, _VIDEO_DEFAULTS['height'])
    length = _clamp(data.get('length') or data.get('duration'), 1, 161, _VIDEO_DEFAULTS['length'])
    steps = _clamp(data.get('steps') or data.get('num_inference_steps'), 1, 50, _VIDEO_DEFAULTS['steps'])
    cfg = _clamp_f(data.get('cfg') or data.get('guidance') or data.get('guidance_scale'), 0.1, 20.0, _VIDEO_DEFAULTS['cfg'])
    context_overlap = _clamp(data.get('context_overlap') or data.get('flow_shift'), 1, 64, 48)
    seed_raw = data.get('seed')
    seed = _clamp(seed_raw, 0, 2**32 - 1, -1) if seed_raw not in (None, '', -1, '-1') else -1

    gen_input = {
        'prompt': prompt,
        'negative_prompt': negative_prompt,
        'width': width,
        'height': height,
        'length': length,
        'steps': steps,
        'cfg': cfg,
        'context_overlap': context_overlap,
    }
    if image_base64:
        gen_input['image_base64'] = image_base64
    if image_url:
        gen_input['image_url'] = image_url
    if seed >= 0:
        gen_input['seed'] = seed

    lora_pairs = data.get('lora_pairs')
    if lora_pairs not in (None, '', []):
        if not isinstance(lora_pairs, list):
            return jsonify({'error': 'LoRA pairs must be a JSON array'}), 400
        gen_input['lora_pairs'] = lora_pairs

    advanced_input = data.get('advanced_input')
    if advanced_input not in (None, '', {}):
        if not isinstance(advanced_input, dict):
            return jsonify({'error': 'Advanced input must be a JSON object'}), 400
        gen_input.update(advanced_input)

    payload = json.dumps({'input': gen_input}).encode()
    url = f'{_RUNPOD_BASE}/{config.WAN_VIDEO_ENDPOINT_ID}/run'
    req = urllib.request.Request(url, data=payload, headers=_runpod_headers(), method='POST')

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode())
        job_id = result.get('id')
        if not job_id:
            logger.error("RunPod WAN Generate missing job ID: %s", result)
            return jsonify({
                'error': (
                    'RunPod did not return a job ID. '
                    'Check that WAN_VIDEO_ENDPOINT_ID points to an async queue-based endpoint.'
                ),
                'runpod_status': result.get('status'),
            }), 502
        return jsonify({
            'job_id': job_id,
            'endpoint_id': config.WAN_VIDEO_ENDPOINT_ID,
            'status': result.get('status', 'IN_QUEUE'),
        })
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            detail = e.read().decode()
        except Exception:
            detail = str(e)
        logger.error("RunPod WAN Generate HTTP error: %s", detail)
        return jsonify({'error': f'RunPod error: {detail or e}'}), 502
    except Exception as e:
        logger.error("RunPod WAN Generate error: %s", e)
        return jsonify({'error': f'RunPod error: {e}'}), 502


_TERMINAL_STATUSES = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT'}


@forge_bp.route('/api/forge/status/<job_id>')
@login_required
def api_forge_status(job_id):
    if not re.match(r'^[a-zA-Z0-9_-]+$', job_id):
        return jsonify({'error': 'Invalid job ID'}), 400
    
    # Client should pass endpoint_id as a query param. If it does not,
    # prefer the explicit worker-specific endpoints before the legacy default.
    worker_type = request.args.get('worker_type', 'sdxl')
    requested_model = request.args.get('model')
    model, model_meta = _resolve_model(worker_type, requested_model)
    endpoint_id = request.args.get('endpoint_id')
    if not endpoint_id and model_meta and (request.args.get('worker_type') or requested_model):
        endpoint_id = _get_endpoint(model_meta['endpoint_attr'])
    if not endpoint_id:
        endpoint_id = (
            config.CYBERREALISTIC_PONY_ENDPOINT_ID
            or config.FORGE_ENDPOINT_ID
            or config.SDXL_ENDPOINT_ID
            or config.SD_ENDPOINT_ID
        )
    if not endpoint_id:
        return jsonify({'error': 'Endpoint ID missing for status check'}), 400

    if not config.RUNPOD_API_KEY:
        return jsonify({'error': 'Endpoint not configured'}), 503

    prompt = request.args.get('prompt', '')
    negative_prompt = request.args.get('negative_prompt', '')
    steps = _request_int('steps')
    guidance_scale = _request_float('guidance_scale')
    width = _request_int('width')
    height = _request_int('height')
    seed = _request_int('seed')

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
                'model': existing.get('model') or model,
                'worker_type': existing.get('worker_type') or worker_type,
            })

        # Extract base64 image — handle list-of-objects or dict output formats
        output = result.get('output')
        b64_image = _extract_b64_image(output)

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

        img_id = database.add_forge_image(
            job_id,
            prompt,
            filename,
            datetime.now().isoformat(),
            model,
            worker_type,
            negative_prompt,
            steps,
            guidance_scale,
            width,
            height,
            seed,
        )
        return jsonify({
            'status': 'COMPLETED',
            'image_url': f'/static/forge_outputs/{filename}',
            'image_id': img_id,
            'model': model,
            'worker_type': worker_type,
        })

    if status in _TERMINAL_STATUSES:
        return jsonify({'status': 'FAILED', 'error': result.get('error', status)})

    return jsonify({'status': status})



@forge_bp.route('/api/forge/videos/status/<job_id>')
@login_required
def api_forge_video_status(job_id):
    if not re.match(r'^[a-zA-Z0-9_-]+$', job_id):
        return jsonify({'error': 'Invalid job ID'}), 400

    endpoint_id = request.args.get('endpoint_id') or config.WAN_VIDEO_ENDPOINT_ID
    if not endpoint_id:
        return jsonify({'error': 'Endpoint ID missing for status check'}), 400
    if not config.RUNPOD_API_KEY:
        return jsonify({'error': 'Endpoint not configured'}), 503

    prompt = request.args.get('prompt', '')
    url = f'{_RUNPOD_BASE}/{endpoint_id}/status/{job_id}'
    req = urllib.request.Request(url, headers=_runpod_headers())

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode())
    except Exception as e:
        return jsonify({'error': f'RunPod error: {e}'}), 502

    status = result.get('status', 'UNKNOWN')

    if status == 'COMPLETED':
        existing = database.get_forge_video_by_job_id(job_id)
        if existing:
            return jsonify({
                'status': 'COMPLETED',
                'video_url': f'/static/forge_videos/{existing["filename"]}',
                'video_id': existing['id'],
            })

        output = result.get('output')
        video_url = _extract_video_url(output)
        b64_video = _extract_b64_video(output)
        if not video_url and not b64_video:
            return jsonify({'error': 'No video in response', 'status': 'FAILED'}), 502

        filename = f'{job_id}.mp4'
        filepath = os.path.join(_FORGE_VIDEOS, filename)

        try:
            os.makedirs(_FORGE_VIDEOS, exist_ok=True)
            if b64_video:
                video_bytes = _decode_video_base64(b64_video)
            else:
                download_req = urllib.request.Request(video_url, headers={'User-Agent': 'InfinityForgeVideo/1.0'})
                with urllib.request.urlopen(download_req, timeout=120) as resp:
                    video_bytes = resp.read()
            if not video_bytes:
                raise ValueError('empty video payload')
            with open(filepath, 'wb') as f:
                f.write(video_bytes)
        except Exception as e:
            logger.error('Forge Video: failed to save video %s: %s', job_id, e)
            return jsonify({'error': 'Failed to save video', 'status': 'FAILED'}), 500

        video_id = database.add_forge_video(job_id, prompt, filename, datetime.now().isoformat())
        return jsonify({
            'status': 'COMPLETED',
            'video_url': f'/static/forge_videos/{filename}',
            'video_id': video_id,
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


@forge_bp.route('/api/forge/videos/<int:video_id>', methods=['DELETE'])
@login_required
def api_forge_video_delete(video_id):
    row = database.get_forge_video(video_id)
    if not row:
        return jsonify({'error': 'Not found'}), 404

    filepath = os.path.join(_FORGE_VIDEOS, row['filename'])
    try:
        os.remove(filepath)
    except OSError as e:
        logger.error('Forge Video: could not delete file %s: %s', filepath, e)

    database.delete_forge_video(video_id)
    return jsonify({'success': True})
