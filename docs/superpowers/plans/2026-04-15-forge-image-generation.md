# Forge Image Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/forge` page that submits prompts to a RunPod SDXL serverless endpoint, polls for completion, saves generated images, and displays a deletable gallery.

**Architecture:** New `blueprints/forge.py` blueprint with four routes (page, generate, status, delete). RunPod async flow: POST to `/run` → return job_id → frontend polls `/status/<job_id>` every 2s → on COMPLETED save PNG to `static/forge_outputs/` and metadata to SQLite. Protected by existing `@login_required`.

**Tech Stack:** Flask, SQLite (existing `database.py` patterns), `urllib.request` (no new deps), Jinja2, vanilla JS fetch + setInterval polling.

---

### Task 1: Config — add RunPod env vars

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Add the two new optional config vars**

Open `config.py` and add after the `GITHUB_TOKEN` line:

```python
# RunPod serverless image generation (optional — Forge disabled if missing)
RUNPOD_API_KEY = os.environ.get('RUNPOD_API_KEY', '')
SD_ENDPOINT_ID = os.environ.get('SD_ENDPOINT_ID', '')
```

- [ ] **Step 2: Verify the app still starts**

```bash
cd /Users/ericnelson/Projects/infinity_site_v2
doppler run --project mjolinr_server --config prd -- python -c "import config; print('RUNPOD_API_KEY set:', bool(config.RUNPOD_API_KEY))"
```

Expected output: `RUNPOD_API_KEY set: True`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat: add RUNPOD_API_KEY and SD_ENDPOINT_ID config vars"
```

---

### Task 2: Database — forge_images table and CRUD

**Files:**
- Modify: `database.py`
- Create: `tests/test_forge_db.py`

- [ ] **Step 1: Write failing tests for all DB functions**

Create `tests/test_forge_db.py`:

```python
import pytest
from datetime import datetime


def test_add_and_list_forge_images(app):
    import database
    with app.app_context():
        img_id = database.add_forge_image('job-001', 'a red dragon', 'job-001.png', datetime.now().isoformat())
        assert isinstance(img_id, int)

        images = database.list_forge_images()
        assert len(images) == 1
        assert images[0]['job_id'] == 'job-001'
        assert images[0]['prompt'] == 'a red dragon'
        assert images[0]['filename'] == 'job-001.png'


def test_list_forge_images_newest_first(app):
    import database
    with app.app_context():
        database.add_forge_image('job-001', 'prompt one', 'job-001.png', '2026-01-01T00:00:00')
        database.add_forge_image('job-002', 'prompt two', 'job-002.png', '2026-01-02T00:00:00')

        images = database.list_forge_images()
        assert images[0]['job_id'] == 'job-002'
        assert images[1]['job_id'] == 'job-001'


def test_get_forge_image(app):
    import database
    with app.app_context():
        img_id = database.add_forge_image('job-003', 'a cat', 'job-003.png', datetime.now().isoformat())
        row = database.get_forge_image(img_id)
        assert row is not None
        assert row['job_id'] == 'job-003'


def test_get_forge_image_not_found(app):
    import database
    with app.app_context():
        assert database.get_forge_image(99999) is None


def test_get_forge_image_by_job_id(app):
    import database
    with app.app_context():
        database.add_forge_image('job-004', 'a ship', 'job-004.png', datetime.now().isoformat())
        row = database.get_forge_image_by_job_id('job-004')
        assert row is not None
        assert row['prompt'] == 'a ship'


def test_get_forge_image_by_job_id_not_found(app):
    import database
    with app.app_context():
        assert database.get_forge_image_by_job_id('nonexistent') is None


def test_delete_forge_image(app):
    import database
    with app.app_context():
        img_id = database.add_forge_image('job-005', 'a mountain', 'job-005.png', datetime.now().isoformat())
        database.delete_forge_image(img_id)
        assert database.get_forge_image(img_id) is None


def test_delete_forge_image_nonexistent(app):
    import database
    with app.app_context():
        # Should not raise
        database.delete_forge_image(99999)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/ericnelson/Projects/infinity_site_v2
doppler run --project mjolinr_server --config prd -- python -m pytest tests/test_forge_db.py -v
```

Expected: All FAIL with `AttributeError: module 'database' has no attribute 'add_forge_image'`

- [ ] **Step 3: Add the `forge_images` table to `init_db()` in `database.py`**

Add this block inside `init_db()`, after the `monitor_recommendations` table creation and before `conn.commit()`:

```python
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS forge_images (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id     TEXT NOT NULL UNIQUE,
                prompt     TEXT NOT NULL,
                filename   TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
```

- [ ] **Step 4: Add the five CRUD functions to `database.py`**

Add these after the `clear_recommendations` function at the bottom of the file:

```python
# ── Forge Images ──────────────────────────────────────────────────────────────

def add_forge_image(job_id: str, prompt: str, filename: str, created_at: str) -> int:
    with _db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO forge_images (job_id, prompt, filename, created_at) VALUES (?, ?, ?, ?)",
            (job_id, prompt, filename, created_at),
        )
        conn.commit()
        return cur.lastrowid

def list_forge_images():
    with _db_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM forge_images ORDER BY id DESC"
        )
        return [dict(row) for row in cur.fetchall()]

def get_forge_image(image_id: int):
    with _db_conn() as conn:
        cur = conn.execute("SELECT * FROM forge_images WHERE id = ?", (image_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def get_forge_image_by_job_id(job_id: str):
    with _db_conn() as conn:
        cur = conn.execute("SELECT * FROM forge_images WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def delete_forge_image(image_id: int):
    with _db_conn() as conn:
        conn.execute("DELETE FROM forge_images WHERE id = ?", (image_id,))
        conn.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
doppler run --project mjolinr_server --config prd -- python -m pytest tests/test_forge_db.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add database.py tests/test_forge_db.py
git commit -m "feat: add forge_images table and CRUD functions"
```

---

### Task 3: Blueprint — page route and generate endpoint

**Files:**
- Create: `blueprints/forge.py`
- Create: `tests/test_forge_routes.py`

- [ ] **Step 1: Write failing tests for the page route and generate endpoint**

Create `tests/test_forge_routes.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock


# ── Page route ────────────────────────────────────────────────────────────────

def test_forge_page_requires_login(client):
    resp = client.get('/forge')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_forge_page_renders_when_logged_in(admin_client):
    resp = admin_client.get('/forge')
    assert resp.status_code == 200
    assert b'FORGE' in resp.data


# ── Generate endpoint ─────────────────────────────────────────────────────────

def test_generate_requires_login(client):
    # API routes return 401 (not 302) for unauthenticated JSON requests
    resp = client.post('/api/forge/generate', json={'prompt': 'a dragon'})
    assert resp.status_code == 401


def test_generate_rejects_empty_prompt(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'test-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.post('/api/forge/generate',
                             json={'prompt': ''},
                             headers={'X-CSRF-Token': token})
    assert resp.status_code == 400
    assert b'prompt' in resp.data.lower()


def test_generate_rejects_prompt_too_long(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'test-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.post('/api/forge/generate',
                             json={'prompt': 'x' * 501},
                             headers={'X-CSRF-Token': token})
    assert resp.status_code == 400


def test_generate_returns_job_id(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'test-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'id': 'job-abc123', 'status': 'IN_QUEUE'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.post('/api/forge/generate',
                                 json={'prompt': 'a red dragon'},
                                 headers={'X-CSRF-Token': token})

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['job_id'] == 'job-abc123'


def test_generate_returns_502_on_runpod_error(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'test-endpoint'
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']

    with patch('urllib.request.urlopen', side_effect=Exception('connection refused')):
        resp = admin_client.post('/api/forge/generate',
                                 json={'prompt': 'a dragon'},
                                 headers={'X-CSRF-Token': token})

    assert resp.status_code == 502


def test_generate_disabled_without_config(admin_client):
    import config
    config.RUNPOD_API_KEY = ''
    config.SD_ENDPOINT_ID = ''
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.post('/api/forge/generate',
                             json={'prompt': 'a dragon'},
                             headers={'X-CSRF-Token': token})
    assert resp.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
doppler run --project mjolinr_server --config prd -- python -m pytest tests/test_forge_routes.py -v
```

Expected: All FAIL with import errors or 404s (blueprint not registered yet)

- [ ] **Step 3: Create `blueprints/forge.py` with page route and generate endpoint**

```python
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
```

- [ ] **Step 4: Register the blueprint temporarily in `app.py` to unblock the tests**

In `app.py`, add after the other blueprint imports:

```python
from blueprints.forge import forge_bp
```

And add after the other `app.register_blueprint` calls:

```python
app.register_blueprint(forge_bp)
```

Also add this line after the other `os.makedirs` calls:

```python
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'forge_outputs'), exist_ok=True)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
doppler run --project mjolinr_server --config prd -- python -m pytest tests/test_forge_routes.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add blueprints/forge.py tests/test_forge_routes.py app.py
git commit -m "feat: add forge blueprint with page route and generate endpoint"
```

---

### Task 4: Blueprint — status and delete endpoints

**Files:**
- Modify: `blueprints/forge.py`
- Modify: `tests/test_forge_routes.py`

- [ ] **Step 1: Add failing tests for status and delete endpoints**

Append to `tests/test_forge_routes.py`:

```python
# ── Status endpoint ───────────────────────────────────────────────────────────

def test_status_requires_login(client):
    resp = client.get('/api/forge/status/job-123?prompt=test')
    assert resp.status_code == 401


def test_status_returns_in_queue(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'test-endpoint'

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'status': 'IN_QUEUE'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.get('/api/forge/status/job-123?prompt=a+dragon')

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['status'] == 'IN_QUEUE'


def test_status_saves_image_on_completed(admin_client, tmp_path, monkeypatch):
    import blueprints.forge as forge_module
    monkeypatch.setattr(forge_module, '_FORGE_OUTPUTS', str(tmp_path))
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'test-endpoint'

    # 1x1 red PNG in base64
    tiny_png_b64 = (
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8'
        'z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=='
    )
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        'status': 'COMPLETED',
        'output': [{'image': tiny_png_b64, 'seed': 42}],
    }).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.get('/api/forge/status/job-save-test?prompt=a+cat')

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['status'] == 'COMPLETED'
    assert 'image_url' in data
    assert 'image_id' in data

    # Verify file was written
    saved_file = tmp_path / 'job-save-test.png'
    assert saved_file.exists()


def test_status_idempotent_on_repeated_completed_poll(admin_client, tmp_path, monkeypatch):
    """Polling after COMPLETED should return existing record without duplicate writes."""
    import blueprints.forge as forge_module
    monkeypatch.setattr(forge_module, '_FORGE_OUTPUTS', str(tmp_path))
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'test-endpoint'

    tiny_png_b64 = (
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8'
        'z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=='
    )
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        'status': 'COMPLETED',
        'output': [{'image': tiny_png_b64, 'seed': 1}],
    }).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        admin_client.get('/api/forge/status/job-idem?prompt=test')

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp2 = admin_client.get('/api/forge/status/job-idem?prompt=test')

    import database
    images = database.list_forge_images()
    idem_images = [i for i in images if i['job_id'] == 'job-idem']
    assert len(idem_images) == 1  # No duplicate

    data = json.loads(resp2.data)
    assert data['status'] == 'COMPLETED'


def test_status_failed_job(admin_client):
    import config
    config.RUNPOD_API_KEY = 'test-key'
    config.SD_ENDPOINT_ID = 'test-endpoint'

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({'status': 'FAILED', 'error': 'OOM'}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch('urllib.request.urlopen', return_value=mock_response):
        resp = admin_client.get('/api/forge/status/job-fail?prompt=test')

    data = json.loads(resp.data)
    assert data['status'] == 'FAILED'


# ── Delete endpoint ───────────────────────────────────────────────────────────

def test_delete_requires_login(client):
    resp = client.delete('/api/forge/images/1')
    assert resp.status_code == 401


def test_delete_image(admin_client, tmp_path, monkeypatch):
    import blueprints.forge as forge_module
    monkeypatch.setattr(forge_module, '_FORGE_OUTPUTS', str(tmp_path))

    import database
    fake_file = tmp_path / 'job-del.png'
    fake_file.write_bytes(b'fake')
    img_id = database.add_forge_image('job-del', 'a test', 'job-del.png', datetime.now().isoformat())

    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.delete(f'/api/forge/images/{img_id}',
                               headers={'X-CSRF-Token': token})
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    assert not fake_file.exists()
    assert database.get_forge_image(img_id) is None


def test_delete_image_not_found(admin_client):
    with admin_client.session_transaction() as sess:
        token = sess['csrf_token']
    resp = admin_client.delete('/api/forge/images/99999',
                               headers={'X-CSRF-Token': token})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
doppler run --project mjolinr_server --config prd -- python -m pytest tests/test_forge_routes.py::test_status_returns_in_queue tests/test_forge_routes.py::test_delete_image -v
```

Expected: Both FAIL (routes don't exist yet)

- [ ] **Step 3: Add the status and delete routes to `blueprints/forge.py`**

Append to `blueprints/forge.py`:

```python
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

        filename = f'{job_id}.png'
        filepath = os.path.join(_FORGE_OUTPUTS, filename)

        try:
            image_bytes = base64.b64decode(b64_image)
            os.makedirs(_FORGE_OUTPUTS, exist_ok=True)
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f'Forge: failed to save image {job_id}: {e}')
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
        import logging
        logging.getLogger(__name__).error(f'Forge: could not delete file {filepath}: {e}')

    database.delete_forge_image(image_id)
    return jsonify({'success': True})
```

- [ ] **Step 4: Run all forge tests**

```bash
doppler run --project mjolinr_server --config prd -- python -m pytest tests/test_forge_routes.py tests/test_forge_db.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add blueprints/forge.py tests/test_forge_routes.py
git commit -m "feat: add forge status polling and delete endpoints"
```

---

### Task 5: Template — forge.html

**Files:**
- Create: `templates/forge.html`

- [ ] **Step 1: Create `templates/forge.html`**

```html
{% extends "base.html" %}

{% block title %}Forge{% endblock %}

{% block content %}
<div class="container" style="padding-top: var(--spacing-xl); padding-bottom: var(--spacing-xl);">

  <!-- Header -->
  <div style="margin-bottom: var(--spacing-xl);">
    <h1 style="font-family: var(--font-display); font-size: 1.8rem; letter-spacing: 0.15em; color: var(--reach-cyan); text-shadow: 0 0 12px rgba(34,211,238,0.4); margin: 0 0 4px 0;">FORGE</h1>
    <p style="font-family: var(--font-mono); font-size: 0.65rem; color: rgba(34,211,238,0.4); letter-spacing: 0.2em; margin: 0;">// IMAGE SYNTHESIS — RUNPOD SDXL SERVERLESS</p>
  </div>

  <!-- Generation Panel -->
  <div class="terminal-panel" style="margin-bottom: var(--spacing-xl); padding: var(--spacing-lg);">

    {% if not endpoint_configured %}
    <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--reach-orange); letter-spacing: 0.1em; padding: var(--spacing-md); border: 1px solid rgba(234,88,12,0.3); background: rgba(234,88,12,0.05);">
      ⚠ ENDPOINT NOT CONFIGURED — Set RUNPOD_API_KEY and SD_ENDPOINT_ID in Doppler.
    </div>
    {% endif %}

    <div style="margin-bottom: var(--spacing-md);">
      <label style="font-family: var(--font-mono); font-size: 0.65rem; color: rgba(34,211,238,0.6); letter-spacing: 0.15em; display: block; margin-bottom: 6px;">PROMPT</label>
      <textarea
        id="forge-prompt"
        rows="3"
        maxlength="500"
        placeholder="Describe the image..."
        {% if not endpoint_configured %}disabled{% endif %}
        style="width: 100%; background: rgba(0,0,0,0.4); border: 1px solid rgba(34,211,238,0.2); color: var(--text-primary); font-family: var(--font-mono); font-size: 0.8rem; padding: 10px 12px; resize: vertical; outline: none; box-sizing: border-box;"
      ></textarea>
      <div style="font-family: var(--font-mono); font-size: 0.6rem; color: rgba(34,211,238,0.3); text-align: right; margin-top: 3px;"><span id="prompt-count">0</span>/500</div>
    </div>

    <details style="margin-bottom: var(--spacing-md);">
      <summary style="font-family: var(--font-mono); font-size: 0.65rem; color: rgba(34,211,238,0.4); letter-spacing: 0.1em; cursor: pointer; user-select: none;">NEGATIVE PROMPT (optional)</summary>
      <textarea
        id="forge-negative"
        rows="2"
        maxlength="500"
        placeholder="Things to exclude from the image..."
        {% if not endpoint_configured %}disabled{% endif %}
        style="width: 100%; margin-top: 8px; background: rgba(0,0,0,0.4); border: 1px solid rgba(34,211,238,0.15); color: var(--text-primary); font-family: var(--font-mono); font-size: 0.8rem; padding: 10px 12px; resize: vertical; outline: none; box-sizing: border-box;"
      ></textarea>
    </details>

    <div style="display: flex; align-items: center; gap: var(--spacing-md);">
      <button
        id="forge-generate-btn"
        {% if not endpoint_configured %}disabled{% endif %}
        style="font-family: var(--font-display); font-size: 0.8rem; letter-spacing: 0.15em; padding: 10px 28px; background: transparent; border: 1px solid var(--reach-cyan); color: var(--reach-cyan); cursor: pointer; transition: all 0.2s;"
        onmouseover="if(!this.disabled)this.style.background='rgba(34,211,238,0.1)'"
        onmouseout="this.style.background='transparent'"
      >GENERATE</button>
      <span id="forge-status" style="font-family: var(--font-mono); font-size: 0.7rem; color: var(--reach-amber); letter-spacing: 0.1em; display: none;"></span>
    </div>

    <div id="forge-error" style="display: none; margin-top: var(--spacing-sm); font-family: var(--font-mono); font-size: 0.7rem; color: var(--reach-orange); letter-spacing: 0.05em;"></div>
  </div>

  <!-- Gallery -->
  <div style="margin-bottom: var(--spacing-md);">
    <h2 style="font-family: var(--font-display); font-size: 1rem; letter-spacing: 0.15em; color: rgba(34,211,238,0.7); margin: 0 0 var(--spacing-md) 0;">GENERATED IMAGES</h2>
  </div>

  <div id="forge-gallery" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--spacing-md);">
    {% for img in images %}
    <div class="forge-card" data-id="{{ img.id }}" style="background: rgba(0,0,0,0.4); border: 1px solid rgba(34,211,238,0.15); overflow: hidden;">
      <img src="/static/forge_outputs/{{ img.filename }}" alt="Generated image" loading="lazy"
           style="width: 100%; display: block; aspect-ratio: 1; object-fit: cover;">
      <div style="padding: 10px 12px;">
        <p style="font-family: var(--font-mono); font-size: 0.65rem; color: rgba(34,211,238,0.5); margin: 0 0 6px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{{ img.prompt }}">{{ img.prompt }}</p>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-family: var(--font-mono); font-size: 0.55rem; color: rgba(34,211,238,0.3);">{{ img.created_at[:16] }}</span>
          <button
            onclick="forgeDelete({{ img.id }}, this)"
            style="font-family: var(--font-mono); font-size: 0.6rem; letter-spacing: 0.1em; padding: 3px 10px; background: transparent; border: 1px solid rgba(234,88,12,0.4); color: var(--reach-orange); cursor: pointer;"
            onmouseover="this.style.background='rgba(234,88,12,0.1)'"
            onmouseout="this.style.background='transparent'"
          >DELETE</button>
        </div>
      </div>
    </div>
    {% else %}
    <p id="forge-empty" style="font-family: var(--font-mono); font-size: 0.7rem; color: rgba(34,211,238,0.3); letter-spacing: 0.1em; grid-column: 1 / -1;">NO IMAGES GENERATED YET.</p>
    {% endfor %}
  </div>

</div>
{% endblock %}

{% block scripts %}
<script>
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

// Prompt character counter
const promptEl = document.getElementById('forge-prompt');
const countEl = document.getElementById('prompt-count');
if (promptEl) {
  promptEl.addEventListener('input', () => {
    countEl.textContent = promptEl.value.length;
  });
}

// Generate
document.getElementById('forge-generate-btn')?.addEventListener('click', async () => {
  const prompt = promptEl.value.trim();
  const negative = document.getElementById('forge-negative')?.value.trim() || '';
  if (!prompt) { showError('Prompt is required.'); return; }

  setGenerating(true);
  showError('');
  showStatus('SUBMITTING...');

  try {
    const resp = await fetch('/api/forge/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ prompt, negative_prompt: negative }),
    });
    const data = await resp.json();
    if (!resp.ok) { showError(data.error || 'Generation failed.'); setGenerating(false); return; }
    pollStatus(data.job_id, prompt);
  } catch (e) {
    showError('Network error. Try again.');
    setGenerating(false);
  }
});

function pollStatus(jobId, prompt) {
  showStatus('QUEUED...');
  const interval = setInterval(async () => {
    try {
      const resp = await fetch(`/api/forge/status/${jobId}?prompt=${encodeURIComponent(prompt)}`);
      const data = await resp.json();

      if (data.status === 'COMPLETED') {
        clearInterval(interval);
        showStatus('');
        setGenerating(false);
        prependImageCard(data.image_id, data.image_url, prompt);
      } else if (data.status === 'FAILED') {
        clearInterval(interval);
        showError(data.error || 'Generation failed.');
        showStatus('');
        setGenerating(false);
      } else if (data.status === 'IN_PROGRESS') {
        showStatus('GENERATING...');
      } else {
        showStatus('QUEUED...');
      }
    } catch (e) {
      // transient network error — keep polling
    }
  }, 2000);
}

function prependImageCard(imageId, imageUrl, prompt) {
  const gallery = document.getElementById('forge-gallery');
  const empty = document.getElementById('forge-empty');
  if (empty) empty.remove();

  const now = new Date().toISOString().slice(0, 16);
  const card = document.createElement('div');
  card.className = 'forge-card';
  card.dataset.id = imageId;
  card.style.cssText = 'background:rgba(0,0,0,0.4);border:1px solid rgba(34,211,238,0.15);overflow:hidden;';
  card.innerHTML = `
    <img src="${imageUrl}" alt="Generated image" style="width:100%;display:block;aspect-ratio:1;object-fit:cover;">
    <div style="padding:10px 12px;">
      <p style="font-family:var(--font-mono);font-size:0.65rem;color:rgba(34,211,238,0.5);margin:0 0 6px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${escapeHtml(prompt)}">${escapeHtml(prompt)}</p>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="font-family:var(--font-mono);font-size:0.55rem;color:rgba(34,211,238,0.3);">${now}</span>
        <button onclick="forgeDelete(${imageId},this)" style="font-family:var(--font-mono);font-size:0.6rem;letter-spacing:0.1em;padding:3px 10px;background:transparent;border:1px solid rgba(234,88,12,0.4);color:var(--reach-orange);cursor:pointer;" onmouseover="this.style.background='rgba(234,88,12,0.1)'" onmouseout="this.style.background='transparent'">DELETE</button>
      </div>
    </div>`;
  gallery.prepend(card);
}

async function forgeDelete(imageId, btn) {
  btn.disabled = true;
  try {
    const resp = await fetch(`/api/forge/images/${imageId}`, {
      method: 'DELETE',
      headers: { 'X-CSRF-Token': csrfToken },
    });
    if (resp.ok) {
      const card = document.querySelector(`.forge-card[data-id="${imageId}"]`);
      if (card) card.remove();
      if (!document.querySelector('.forge-card')) {
        const gallery = document.getElementById('forge-gallery');
        gallery.innerHTML = '<p id="forge-empty" style="font-family:var(--font-mono);font-size:0.7rem;color:rgba(34,211,238,0.3);letter-spacing:0.1em;grid-column:1/-1;">NO IMAGES GENERATED YET.</p>';
      }
    }
  } catch (e) {
    btn.disabled = false;
  }
}

function setGenerating(on) {
  const btn = document.getElementById('forge-generate-btn');
  if (btn) btn.disabled = on;
}

function showStatus(msg) {
  const el = document.getElementById('forge-status');
  if (!el) return;
  el.textContent = msg;
  el.style.display = msg ? 'inline' : 'none';
}

function showError(msg) {
  const el = document.getElementById('forge-error');
  if (!el) return;
  el.textContent = msg;
  el.style.display = msg ? 'block' : 'none';
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
</script>
{% endblock %}
```

- [ ] **Step 2: Verify the page loads in the browser**

With the dev server running, navigate to `http://localhost:5173/forge` (you'll be redirected to login first). Verify:
- Page renders with "FORGE // IMAGE SYNTHESIS" header
- Prompt textarea and GENERATE button are visible
- If endpoint is configured, button is active; if not, a warning shows

- [ ] **Step 3: Commit**

```bash
git add templates/forge.html
git commit -m "feat: add forge.html template with generation panel and gallery"
```

---

### Task 6: Nav link + full test run

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Add Forge to the nav**

In `templates/base.html`, add the Forge link inside the `<ul class="nav-links">` block, after the Uplink Cache link and before the `{% if session.get('role') == 'admin' %}` block:

```html
<li><a href="{{ url_for('forge.forge') }}" class="nav-link{% if request.endpoint == 'forge.forge' %} active{% endif %}">Forge</a></li>
```

- [ ] **Step 2: Run the full test suite**

```bash
doppler run --project mjolinr_server --config prd -- python -m pytest tests/ -v
```

Expected: All PASS, no regressions

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: add Forge nav link to base template"
```

---

### Task 7: Smoke test in browser

- [ ] **Step 1: Verify nav link appears on all pages**

Navigate to `http://localhost:5173/` — confirm "Forge" appears in the nav bar.

- [ ] **Step 2: Verify login protection**

Open an incognito window and navigate to `http://localhost:5173/forge` — should redirect to login.

- [ ] **Step 3: Verify gallery is empty on first load**

After logging in, navigate to `/forge` — should show "NO IMAGES GENERATED YET."

- [ ] **Step 4: Verify the endpoint-not-configured banner (if SD_ENDPOINT_ID is empty)**

Temporarily unset `SD_ENDPOINT_ID` in Doppler or set it to empty and restart the server. The warning banner should appear and the GENERATE button should be disabled. Restore the value when done.
