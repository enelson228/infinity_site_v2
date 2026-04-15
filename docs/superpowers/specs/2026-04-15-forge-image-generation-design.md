# Forge — Image Generation Feature Design

**Date:** 2026-04-15  
**Status:** Approved  
**Feature:** `/forge` — RunPod SDXL serverless image generation with persistent gallery

---

## Overview

Add a dedicated image generation page at `/forge` to the infinity_site_v2 homelab dashboard. Users submit a text prompt, a RunPod SDXL serverless worker generates the image asynchronously, the result is saved to disk and SQLite, and displayed in a deletable gallery.

---

## Architecture

### New Files
- `blueprints/forge.py` — blueprint with all routes and RunPod integration logic
- `templates/forge.html` — page template extending `base.html`
- `static/forge_outputs/` — directory for saved PNG files (created at startup if missing)

### Modified Files
- `app.py` — register `forge_bp`, ensure `static/forge_outputs/` exists at startup
- `config.py` — add `RUNPOD_API_KEY` (optional) and `SD_ENDPOINT_ID` (optional)
- `database.py` — add `forge_images` table and CRUD functions

### Authentication
`@login_required` on all forge routes — same session cookie auth as the terminal. No separate password.

---

## Configuration

Two new environment variables read from Doppler (already present as `RUNPOD_API_KEY` and `SD_ENDPOINT_ID`):

```python
RUNPOD_API_KEY = os.environ.get('RUNPOD_API_KEY', '')
SD_ENDPOINT_ID = os.environ.get('SD_ENDPOINT_ID', '')
```

Both are optional at config load time. If either is missing, the Generate button is disabled and a notice is shown on the page. The app still starts without them.

---

## Database

New table `forge_images` in SQLite:

```sql
CREATE TABLE IF NOT EXISTS forge_images (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id    TEXT NOT NULL,
    prompt    TEXT NOT NULL,
    filename  TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### Database Functions (added to `database.py`)
- `add_forge_image(job_id, prompt, filename, created_at)` → row id
- `list_forge_images()` → list of dicts, newest first
- `get_forge_image(image_id)` → single dict or None (by primary key)
- `get_forge_image_by_job_id(job_id)` → single dict or None (for idempotency check)
- `delete_forge_image(image_id)` → removes DB record

---

## API Routes (`blueprints/forge.py`)

### `GET /forge`
- Auth: `@login_required`
- Renders `forge.html` with `images = database.list_forge_images()` passed to template
- If `config.SD_ENDPOINT_ID` or `config.RUNPOD_API_KEY` is falsy, passes `endpoint_configured=False`

### `POST /api/forge/generate`
- Auth: `@login_required`
- Body: `{"prompt": "...", "negative_prompt": "..."}` (negative_prompt optional)
- Validates prompt is non-empty, max 500 chars
- POSTs to `https://api.runpod.ai/v2/{SD_ENDPOINT_ID}/run` with:
  ```json
  {
    "input": {
      "prompt": "<prompt>",
      "negative_prompt": "<negative_prompt>",
      "num_inference_steps": 20,
      "width": 1024,
      "height": 1024
    }
  }
  ```
  Authorization header: `Bearer {RUNPOD_API_KEY}`
- Returns `{"job_id": "..."}` on success
- Returns `{"error": "..."}` with appropriate HTTP status on failure

### `GET /api/forge/status/<job_id>`
- Auth: `@login_required`
- GETs `https://api.runpod.ai/v2/{SD_ENDPOINT_ID}/status/{job_id}`
- Possible RunPod statuses: `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`
- If `COMPLETED`:
  - Checks DB for existing record with this `job_id` — if found, returns existing image URL (idempotent, no duplicate writes)
  - If not found: extracts base64 image from `output.image` (falls back to `output.images[0]`), decodes and saves PNG to `static/forge_outputs/{job_id}.png`, calls `database.add_forge_image(job_id, prompt, filename, created_at)`
  - Returns `{"status": "COMPLETED", "image_url": "/static/forge_outputs/{job_id}.png", "image_id": <id>}`
- If terminal status (`FAILED`, `CANCELLED`, `TIMED_OUT`):
  - Returns `{"status": "FAILED", "error": "..."}`
- If in-progress (`IN_QUEUE`, `IN_PROGRESS`):
  - Returns `{"status": "<status>"}` — frontend keeps polling

**Problem:** The prompt is needed at save time but not available from the RunPod status response. The frontend must include `prompt` in the status poll request as a query param: `GET /api/forge/status/<job_id>?prompt=<prompt>`.

### `DELETE /api/forge/images/<image_id>`
- Auth: `@login_required`
- Fetches row from DB, deletes file from `static/forge_outputs/`, deletes DB record
- Returns `{"success": true}` — 404 if not found
- File deletion failure is logged but does not block DB deletion

---

## Frontend (`templates/forge.html`)

Extends `base.html`. INFINITY dark aesthetic, same fonts and color variables.

### Generation Panel
- Heading: "FORGE — IMAGE SYNTHESIS"
- Textarea for prompt (required, max 500 chars)
- Collapsible/optional textarea for negative prompt
- "GENERATE" button
- Status line: hidden by default, shows "QUEUED...", "GENERATING...", "SAVING..." during active job
- Error line: shown inline if generation fails, re-enables button

### Gallery
- Rendered server-side from `images` passed to template at page load
- CSS grid, 3 columns on desktop, responsive
- Each card: image thumbnail, prompt text (truncated), timestamp, delete button
- New images prepended to the grid via JS when a generation completes
- Delete: `fetch` DELETE → remove card from DOM on success

### Polling Logic (JS)
```
submit → POST /api/forge/generate → get job_id
  → setInterval(poll, 2000)
    → GET /api/forge/status/<job_id>?prompt=<prompt>
    → if COMPLETED: prepend image card, clear interval, re-enable button
    → if FAILED: show error, clear interval, re-enable button
    → if IN_QUEUE / IN_PROGRESS: update status text, keep polling
```

No client-side timeout — the user can wait as long as needed (cold starts can take 60–90s).

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Endpoint not configured | Generate button disabled, notice shown |
| RunPod API unreachable | `/api/forge/generate` returns 502, error shown inline |
| Job FAILED/TIMED_OUT | Status endpoint returns FAILED, error shown inline |
| Image decode failure | Logged server-side, COMPLETED returns error instead of image |
| File write failure | Logged, image not persisted but result still returned to client |
| Missing image on delete | 404 returned, card removal skipped |

---

## RunPod Setup (out of band)

Before deploying this feature, the user must:
1. Deploy the official **RunPod SDXL serverless worker** template from the RunPod console
2. Copy the new endpoint ID into Doppler as `SD_ENDPOINT_ID`

The existing `RUNPOD_API_KEY` in Doppler is already set and will be used as-is.

---

## Out of Scope

- Image download button (can be added later; browser right-click saves already works)
- Prompt history / search
- Generation parameters exposed in the UI (steps, guidance scale, seed) — hardcoded defaults for now
- User-scoped galleries (all images shared across all logged-in users)
