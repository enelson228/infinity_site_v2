const API_BASE = window.STORYTELL_API_BASE || 'http://localhost:8000';
let currentProjectId = null;
let currentProjectDetail = null;
let autoSyncTimer = null;

const TEXT_STAGE_ORDER = ['story_bible', 'characters', 'scenes', 'script', 'shotlist', 'prompts'];
const STAGE_LABELS = {
  story_bible: 'Story bible',
  characters: 'Characters',
  scenes: 'Scenes',
  script: 'Script',
  shotlist: 'Shotlist',
  prompts: 'Prompts',
};

const $ = (id) => document.getElementById(id);
function show(data) { $('output').textContent = JSON.stringify(data, null, 2); }

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function activeStage(detail, stageType) {
  return detail.stages
    .filter((stage) => stage.stage_type === stageType && stage.is_active === 1)
    .sort((a, b) => b.version - a.version)[0];
}

function stagePreview(stage) {
  const content = stage?.content || {};
  if (!stage || !Object.keys(content).length) return 'Not generated yet.';
  if (content.logline) return content.logline;
  if (Array.isArray(content.characters)) return content.characters.map((c) => c.name).filter(Boolean).slice(0, 4).join(', ');
  if (Array.isArray(content.scenes)) return `${content.scenes.length} scenes: ${content.scenes[0]?.title || content.scenes[0]?.summary || 'scene plan'}`;
  if (Array.isArray(content.script_scenes)) return `${content.script_scenes.length} scripted scenes with dialogue/action beats.`;
  if (Array.isArray(content.shots)) return `${content.shots.length} shots ready for prompt generation.`;
  if (Array.isArray(content.prompts)) return `${content.prompts.length} image/video prompts. First: ${content.prompts[0]?.image_prompt || 'prompt ready'}`;
  return JSON.stringify(content).slice(0, 180);
}

function renderPipelineSummary(detail) {
  const target = $('pipelineSummary');
  if (!target) return;
  if (!detail) {
    target.className = 'pipeline-summary empty';
    target.textContent = 'Create a project, then generate the text pipeline to review stage summaries here.';
    return;
  }

  target.className = 'pipeline-summary';
  target.innerHTML = TEXT_STAGE_ORDER.map((stageType) => {
    const stage = activeStage(detail, stageType);
    const status = stage?.status || 'not_started';
    return `
      <article class="stage-card stage-${escapeHtml(status)}">
        <div class="stage-card__header">
          <h3>${escapeHtml(STAGE_LABELS[stageType])}</h3>
          <span>${escapeHtml(status.replaceAll('_', ' '))}${stage ? ` · v${stage.version}` : ''}</span>
        </div>
        <p>${escapeHtml(stagePreview(stage))}</p>
      </article>
    `;
  }).join('');
}

function activePrompts(detail) {
  return activeStage(detail, 'prompts')?.content?.prompts || [];
}

function fillPromptFields(prompt) {
  if (!prompt) return;
  $('imagePrompt').value = prompt.image_prompt || '';
  $('width').value = prompt.recommended_width || 1024;
  $('height').value = prompt.recommended_height || 576;
  $('videoPrompt').value = prompt.video_prompt || '';
  $('videoDuration').value = prompt.duration_seconds || 5;
}

function selectedGeneratedPrompt() {
  const rawValue = $('promptSelect')?.value;
  if (rawValue === undefined || rawValue === '') return null;
  const selectedIndex = Number(rawValue);
  if (!Number.isInteger(selectedIndex)) return null;
  return activePrompts(currentProjectDetail)[selectedIndex] || null;
}

function renderPromptSelector(detail) {
  const select = $('promptSelect');
  if (!select) return;
  const prompts = detail ? activePrompts(detail) : [];
  if (!prompts.length) {
    select.disabled = true;
    select.innerHTML = '<option value="">Generate the text pipeline to load prompts</option>';
    return;
  }

  const previousValue = select.value;
  select.disabled = false;
  select.innerHTML = [
    '<option value="">Select a generated shot prompt</option>',
    ...prompts.map((prompt, index) => {
      const label = `${prompt.shot_id || `shot-${index + 1}`} · ${prompt.image_prompt || 'image prompt'}`.slice(0, 120);
      return `<option value="${index}">${escapeHtml(label)}</option>`;
    }),
  ].join('');

  if (previousValue && prompts[Number(previousValue)]) {
    select.value = previousValue;
  }
}

function imageAssets(detail) {
  return (detail?.assets || []).filter((asset) => asset.asset_type === 'image' && asset.storage_key);
}

function selectedKeyframeAsset() {
  const rawValue = $('keyframeAssetSelect')?.value;
  if (rawValue === undefined || rawValue === '') return null;
  const selectedIndex = Number(rawValue);
  if (!Number.isInteger(selectedIndex)) return null;
  return imageAssets(currentProjectDetail)[selectedIndex] || null;
}

function renderKeyframeAssetSelector(detail) {
  const select = $('keyframeAssetSelect');
  if (!select) return;
  const assets = imageAssets(detail);
  if (!assets.length) {
    select.disabled = true;
    select.innerHTML = '<option value="">Complete an image job to load keyframes</option>';
    return;
  }

  const previousValue = select.value;
  select.disabled = false;
  select.innerHTML = [
    '<option value="">Select a generated keyframe asset</option>',
    ...assets.map((asset, index) => {
      const labelParts = [asset.shot_id, asset.storage_key].filter(Boolean);
      const label = (labelParts.join(' · ') || `image asset ${index + 1}`).slice(0, 120);
      return `<option value="${index}">${escapeHtml(label)}</option>`;
    }),
  ].join('');

  if (previousValue && assets[Number(previousValue)]) {
    select.value = previousValue;
  }
}

function shortId(id) {
  return id ? String(id).slice(0, 8) : 'n/a';
}

function renderJobsAndAssets(detail) {
  const jobsTarget = $('jobsList');
  const assetsTarget = $('assetsList');
  if (!jobsTarget || !assetsTarget) return;

  const jobs = detail?.jobs || [];
  if (!jobs.length) {
    jobsTarget.className = 'list empty';
    jobsTarget.textContent = 'No jobs yet. Generate text, images, or video to populate this list.';
  } else {
    jobsTarget.className = 'list';
    jobsTarget.innerHTML = jobs.slice(0, 8).map((job) => `
      <article class="list-item status-${escapeHtml(job.status)}">
        <div class="list-item__header">
          <strong>${escapeHtml(job.job_type)}</strong>
          <span>${escapeHtml(job.status)}</span>
        </div>
        <p>${escapeHtml(job.provider)} · ${escapeHtml(shortId(job.id))}${job.runpod_job_id ? ` · RunPod ${escapeHtml(shortId(job.runpod_job_id))}` : ''}</p>
      </article>
    `).join('');
  }

  const assets = detail?.assets || [];
  if (!assets.length) {
    assetsTarget.className = 'list empty';
    assetsTarget.textContent = 'No assets yet. Completed worker callbacks will create image/video assets here.';
  } else {
    assetsTarget.className = 'list';
    assetsTarget.innerHTML = assets.slice(0, 8).map((asset) => `
      <article class="list-item">
        <div class="list-item__header">
          <strong>${escapeHtml(asset.asset_type)}</strong>
          <span>${escapeHtml(asset.shot_id || 'manual')}</span>
        </div>
        <p title="${escapeHtml(asset.storage_key)}">${escapeHtml(asset.storage_key)}</p>
        ${asset.url ? `<p><a href="${escapeHtml(asset.url)}" target="_blank" rel="noopener">Open preview</a></p>` : ''}
      </article>
    `).join('');
  }
}

function assetLabel(asset, index) {
  return [asset.asset_type, asset.shot_id || 'manual', shortId(asset.id) || `asset-${index + 1}`].filter(Boolean).join(' · ');
}

function renderMediaGallery(detail) {
  const target = $('mediaGallery');
  if (!target) return;
  const assets = (detail?.assets || []).filter((asset) => ['image', 'video'].includes(asset.asset_type));
  if (!assets.length) {
    target.className = 'media-gallery empty';
    target.textContent = 'Generated images and videos will appear here with previews.';
    return;
  }

  target.className = 'media-gallery';
  target.innerHTML = assets.slice(0, 12).map((asset, index) => {
    const url = asset.url || '';
    const safeUrl = escapeHtml(url);
    const title = escapeHtml(assetLabel(asset, index));
    const storage = escapeHtml(asset.storage_key);
    const preview = asset.asset_type === 'image'
      ? (url ? `<img src="${safeUrl}" alt="${title}" loading="lazy" />` : '<div class="media-missing">No preview URL yet. Click Sync latest RunPod job.</div>')
      : (url ? `<video src="${safeUrl}" controls preload="metadata"></video>` : '<div class="media-missing">No preview URL yet. Click Sync latest RunPod job.</div>');
    const useButton = asset.asset_type === 'image'
      ? `<button type="button" class="use-keyframe" data-storage-key="${storage}">Use as video keyframe</button>`
      : '';
    return `
      <article class="media-card media-${escapeHtml(asset.asset_type)}">
        <div class="media-preview">${preview}</div>
        <div class="media-card__body">
          <strong>${title}</strong>
          <p title="${storage}">${storage}</p>
          <div class="media-actions">
            ${url ? `<a href="${safeUrl}" target="_blank" rel="noopener">Open full preview</a>` : ''}
            ${useButton}
          </div>
        </div>
      </article>
    `;
  }).join('');
}

function renderExportHistory(exports) {
  const target = $('exportsList');
  if (!target) return;
  if (!exports?.length) {
    target.className = 'list empty';
    target.textContent = 'No exports yet. Create an editor export package to populate this list.';
    return;
  }
  target.className = 'list';
  target.innerHTML = exports.slice(0, 8).map((item) => `
    <article class="list-item status-completed">
      <div class="list-item__header">
        <strong>${escapeHtml(item.export_id)}</strong>
        <span>${escapeHtml(item.files.length)} files</span>
      </div>
      <p title="${escapeHtml(item.export_path)}">${escapeHtml(item.asset_count)} assets · ${escapeHtml(item.shot_count)} shots · ${escapeHtml(item.export_path)}</p>
    </article>
  `).join('');
}

function enableProjectControls(enabled) {
  $('mockStory').disabled = !enabled;
  $('sendRunpod').disabled = !enabled;
  $('regenerateImage').disabled = !enabled;
  $('sendVideo').disabled = !enabled;
  $('generateTextPipeline').disabled = !enabled;
  $('refreshProject').disabled = !enabled;
  $('cancelLatestJob').disabled = !enabled;
  $('createExport').disabled = !enabled;
  $('syncLatestJob').disabled = !enabled;
  $('toggleAutoSync').disabled = !enabled;
  $('mockCompleteImage').disabled = true;
  $('mockCompleteVideo').disabled = true;
}

async function refreshProjectList(selectedProjectId = currentProjectId) {
  const select = $('projectSelect');
  if (!select) return [];
  const projects = await get('/api/projects');
  if (!projects.length) {
    select.disabled = true;
    $('loadProject').disabled = true;
    select.innerHTML = '<option value="">No projects yet</option>';
    return projects;
  }
  select.disabled = false;
  select.innerHTML = [
    '<option value="">Select an existing project</option>',
    ...projects.map((project) => `<option value="${escapeHtml(project.id)}">${escapeHtml(project.title || project.idea)} · ${escapeHtml(shortId(project.id))}</option>`),
  ].join('');
  if (selectedProjectId && projects.some((project) => project.id === selectedProjectId)) {
    select.value = selectedProjectId;
  }
  $('loadProject').disabled = !select.value;
  return projects;
}

async function get(path) {
  const res = await fetch(`${API_BASE}${path}`);
  const data = await res.json();
  if (!res.ok) throw new Error(JSON.stringify(data));
  return data;
}

async function post(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(JSON.stringify(data));
  return data;
}

async function patch(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(JSON.stringify(data));
  return data;
}

function latestActiveImageJob(detail) {
  return (detail?.jobs || []).find((job) => job.job_type === 'image.generate' && ['queued', 'running'].includes(job.status));
}

function latestActiveVideoJob(detail) {
  return (detail?.jobs || []).find((job) => job.job_type === 'video.i2v' && ['queued', 'running'].includes(job.status));
}

function latestActiveRunpodJob(detail) {
  return (detail?.jobs || []).find((job) => job.runpod_job_id && ['queued', 'running'].includes(job.status));
}

async function syncLatestRunpodJob() {
  await refreshProject();
  const job = latestActiveRunpodJob(currentProjectDetail);
  if (!job) throw new Error('No queued or running RunPod job found');
  const synced = await post(`/api/jobs/${job.id}/sync`, {});
  await refreshProject();
  return synced;
}

function stopAutoSync() {
  if (autoSyncTimer) clearInterval(autoSyncTimer);
  autoSyncTimer = null;
  if ($('toggleAutoSync')) $('toggleAutoSync').textContent = 'Enable auto-sync';
}

function startAutoSync() {
  stopAutoSync();
  autoSyncTimer = setInterval(async () => {
    try {
      if (!currentProjectId) return stopAutoSync();
      const job = latestActiveRunpodJob(currentProjectDetail);
      if (!job) return stopAutoSync();
      const synced = await post(`/api/jobs/${job.id}/sync`, {});
      await refreshProject();
      show({ auto_synced: synced, project: currentProjectDetail });
    } catch (err) {
      show({ auto_sync_error: String(err) });
      stopAutoSync();
    }
  }, 6000);
  $('toggleAutoSync').textContent = 'Disable auto-sync';
}

$('createProject').addEventListener('click', async () => {
  try {
    const project = await post('/api/projects', {
      idea: $('idea').value,
      genre: $('genre').value,
      tone: $('tone').value,
      target_minutes: Number($('minutes').value),
    });
    currentProjectId = project.id;
    enableProjectControls(true);
    await refreshProjectList(project.id);
    await refreshProject();
    show({ project, detail: currentProjectDetail });
  } catch (err) { show({ error: String(err) }); }
});

$('loadProject').addEventListener('click', async () => {
  try {
    const projectId = $('projectSelect').value;
    if (!projectId) throw new Error('Select a project to load');
    currentProjectId = projectId;
    enableProjectControls(true);
    await refreshProject();
    show({ loaded_project: currentProjectDetail });
  } catch (err) { show({ error: String(err) }); }
});

$('projectSelect').addEventListener('change', () => {
  $('loadProject').disabled = !$('projectSelect').value;
});

$('mockStory').addEventListener('click', async () => {
  try { const detail = await post(`/api/projects/${currentProjectId}/generate/mock-story`, {}); currentProjectDetail = detail; renderPipelineSummary(detail); renderPromptSelector(detail); renderKeyframeAssetSelector(detail); renderJobsAndAssets(detail); renderExportHistory([]); show(detail); }
  catch (err) { show({ error: String(err) }); }
});

async function submitImageJob({ randomizeSeed = false } = {}) {
  const selectedPrompt = selectedGeneratedPrompt();
  if (randomizeSeed) $('seed').value = Math.floor(Math.random() * 2147483647);
  const result = await post('/api/runpod/image', {
    project_id: currentProjectId,
    shot_id: selectedPrompt?.shot_id,
    prompt: $('imagePrompt').value,
    negative_prompt: selectedPrompt?.negative_prompt,
    width: Number($('width').value),
    height: Number($('height').value),
    seed: Number($('seed').value),
    num_outputs: 1,
  });
  await refreshProject();
  startAutoSync();
  return result;
}

$('sendRunpod').addEventListener('click', async () => {
  try {
    const result = await submitImageJob();
    show(result);
  } catch (err) { show({ error: String(err) }); }
});

$('regenerateImage').addEventListener('click', async () => {
  try {
    const result = await submitImageJob({ randomizeSeed: true });
    show({ regenerated_with_new_seed: Number($('seed').value), job: result });
  } catch (err) { show({ error: String(err) }); }
});

$('mockCompleteImage').addEventListener('click', async () => {
  try {
    await refreshProject();
    const job = latestActiveImageJob(currentProjectDetail);
    if (!job) throw new Error('No queued or running image job found');
    const prefix = job.input?.output?.prefix || `projects/${currentProjectId}/mock/${job.id}/`;
    const shotId = job.input?.shot_id || selectedGeneratedPrompt()?.shot_id || null;
    const completed = await patch(`/api/jobs/${job.id}`, {
      status: 'completed',
      output: {
        assets: [{
          type: 'image',
          shot_id: shotId,
          storage_key: `${prefix}image_001.png`,
          metadata: {
            shot_id: shotId,
            seed: job.input?.inputs?.seed,
            width: job.input?.inputs?.width,
            height: job.input?.inputs?.height,
            mock: true,
          },
        }],
      },
      runtime_ms: 1200,
    });
    await refreshProject();
    show({ completed, project: currentProjectDetail });
  } catch (err) { show({ error: String(err) }); }
});

$('sendVideo').addEventListener('click', async () => {
  try {
    const selectedPrompt = selectedGeneratedPrompt();
    const selectedAsset = selectedKeyframeAsset();
    const result = await post('/api/runpod/video', {
      project_id: currentProjectId,
      shot_id: selectedAsset?.shot_id || selectedPrompt?.shot_id || 'manual-shot',
      image_storage_key: selectedAsset?.storage_key || $('keyframeKey').value,
      prompt: $('videoPrompt').value,
      negative_prompt: selectedPrompt?.negative_prompt,
      duration_seconds: Number($('videoDuration').value),
      fps: Number($('videoFps').value),
      width: 1280,
      height: 720,
      seed: Number($('videoSeed').value),
      quality_tier: 'production',
    });
    await refreshProject();
    startAutoSync();
    show(result);
  } catch (err) { show({ error: String(err) }); }
});

$('mockCompleteVideo').addEventListener('click', async () => {
  try {
    await refreshProject();
    const job = latestActiveVideoJob(currentProjectDetail);
    if (!job) throw new Error('No queued or running video job found');
    const prefix = job.input?.output?.prefix || `projects/${currentProjectId}/mock/${job.id}/`;
    const shotId = job.input?.shot_id || selectedGeneratedPrompt()?.shot_id || 'manual-shot';
    const completed = await patch(`/api/jobs/${job.id}`, {
      status: 'completed',
      output: {
        assets: [{
          type: 'video',
          shot_id: shotId,
          storage_key: `${prefix}video_001.mp4`,
          metadata: {
            shot_id: shotId,
            source_image_storage_key: job.input?.inputs?.image_storage_key,
            seed: job.input?.inputs?.seed,
            duration_seconds: job.input?.inputs?.duration_seconds,
            fps: job.input?.inputs?.fps,
            mock: true,
          },
        }],
      },
      runtime_ms: 2400,
    });
    await refreshProject();
    show({ completed, project: currentProjectDetail });
  } catch (err) { show({ error: String(err) }); }
});

$('keyframeAssetSelect').addEventListener('change', () => {
  try {
    const selectedAsset = selectedKeyframeAsset();
    if (!selectedAsset) return;
    $('keyframeKey').value = selectedAsset.storage_key;
    show({ selected_keyframe_asset: selectedAsset });
  } catch (err) { show({ error: String(err) }); }
});

$('mediaGallery')?.addEventListener('click', (event) => {
  const button = event.target.closest('.use-keyframe');
  if (!button) return;
  const storageKey = button.dataset.storageKey;
  $('keyframeKey').value = storageKey;
  const assets = imageAssets(currentProjectDetail);
  const index = assets.findIndex((asset) => asset.storage_key === storageKey);
  if (index >= 0) $('keyframeAssetSelect').value = String(index);
  show({ selected_keyframe_storage_key: storageKey });
});

$('promptSelect').addEventListener('change', () => {
  try {
    const prompts = activePrompts(currentProjectDetail);
    const selectedPrompt = prompts[Number($('promptSelect').value)];
    if (!selectedPrompt) return;
    fillPromptFields(selectedPrompt);
    show({ selected_prompt: selectedPrompt });
  } catch (err) { show({ error: String(err) }); }
});

$('generateTextPipeline').addEventListener('click', async () => {
  try {
    const stages = await post(`/api/projects/${currentProjectId}/generate/text`, {});
    await refreshProject();
    show({ generated_stages: stages, project: currentProjectDetail });
  } catch (err) { show({ error: String(err) }); }
});

$('refreshProject').addEventListener('click', async () => {
  try { await refreshProject(); show(currentProjectDetail); }
  catch (err) { show({ error: String(err) }); }
});

$('syncLatestJob').addEventListener('click', async () => {
  try {
    const synced = await syncLatestRunpodJob();
    show({ synced, project: currentProjectDetail });
  } catch (err) { show({ error: String(err) }); }
});

$('toggleAutoSync').addEventListener('click', async () => {
  try {
    if (autoSyncTimer) return stopAutoSync();
    await refreshProject();
    if (!latestActiveRunpodJob(currentProjectDetail)) throw new Error('No queued or running RunPod job found');
    startAutoSync();
    show({ auto_sync: 'enabled' });
  } catch (err) { show({ error: String(err) }); }
});

$('createExport').addEventListener('click', async () => {
  try {
    const result = await post(`/api/projects/${currentProjectId}/export`, {});
    await refreshProject();
    show({ export: result, project: currentProjectDetail });
  } catch (err) { show({ error: String(err) }); }
});

$('approveActivePrompts').addEventListener('click', async () => {
  try {
    await refreshProject();
    const prompts = activeStage(currentProjectDetail, 'prompts');
    if (!prompts) throw new Error('No active prompts stage found');
    const approved = await post(`/api/projects/${currentProjectId}/stages/${prompts.id}/approve`, {});
    await refreshProject();
    show({ approved, project: currentProjectDetail });
  } catch (err) { show({ error: String(err) }); }
});

$('cancelLatestJob').addEventListener('click', async () => {
  try {
    await refreshProject();
    const job = currentProjectDetail.jobs.find((j) => ['queued', 'running'].includes(j.status));
    if (!job) throw new Error('No queued or running job found');
    const cancelled = await post(`/api/jobs/${job.id}/cancel`, {});
    await refreshProject();
    show({ cancelled, project: currentProjectDetail });
  } catch (err) { show({ error: String(err) }); }
});

async function refreshProject() {
  const data = await get(`/api/projects/${currentProjectId}`);
  const exportList = await get(`/api/projects/${currentProjectId}/exports`);
  currentProjectDetail = data;
  $('approveActivePrompts').disabled = !data.stages.some((s) => s.stage_type === 'prompts' && s.is_active === 1 && s.status === 'needs_review');
  $('cancelLatestJob').disabled = !data.jobs.some((j) => ['queued', 'running'].includes(j.status));
  $('syncLatestJob').disabled = !latestActiveRunpodJob(data);
  $('toggleAutoSync').disabled = !latestActiveRunpodJob(data);
  $('mockCompleteImage').disabled = !latestActiveImageJob(data);
  $('mockCompleteVideo').disabled = !latestActiveVideoJob(data);
  renderPipelineSummary(data);
  renderPromptSelector(data);
  renderKeyframeAssetSelector(data);
  renderJobsAndAssets(data);
  renderMediaGallery(data);
  renderExportHistory(exportList);
  return data;
}

refreshProjectList().catch((err) => show({ error: String(err) }));
