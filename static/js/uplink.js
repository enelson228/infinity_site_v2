/**
 * INFINITY - Uplink Cache JavaScript
 */
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const browseTrigger = document.getElementById('browse-trigger');
const uploadProgress = document.getElementById('upload-progress');
const progressFill = document.getElementById('progress-fill');
const progressText = document.getElementById('progress-text');
const fileList = document.getElementById('file-list');
const emptyState = document.getElementById('empty-state');
const logoutBtn = document.getElementById('logout-btn');
const lightbox = document.getElementById('uplink-lightbox');
const lightboxImg = document.getElementById('lightbox-img');
const lightboxFilename = document.getElementById('lightbox-filename');

const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || '';
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp']);

function isImage(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    return IMAGE_EXTENSIONS.has(ext);
}

function openPreview(fileId, filename) {
    lightboxImg.src = `/api/files/${fileId}/preview`;
    lightboxFilename.textContent = filename;
    lightbox.style.display = 'block';
    document.body.style.overflow = 'hidden';
}

function closePreview() {
    lightbox.style.display = 'none';
    lightboxImg.src = '';
    document.body.style.overflow = '';
}

/**
 * Load and display files
 */
async function loadFiles() {
    try {
        const response = await fetch('/api/files');
        const data = await response.json();

        if (data.files && data.files.length > 0) {
            emptyState.style.display = 'none';
            renderFiles(data.files);
        } else {
            emptyState.style.display = 'block';
            const fileItems = fileList.querySelectorAll('.file-item');
            fileItems.forEach(item => item.remove());
        }
    } catch (error) {
        console.error('Failed to load files:', error);
    }
}

/**
 * Render file list
 */
function renderFiles(files) {
    const existingItems = fileList.querySelectorAll('.file-item');
    existingItems.forEach(item => item.remove());

    files.sort((a, b) => new Date(b.uploaded) - new Date(a.uploaded));

    files.forEach((file, index) => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item vault-file-item';
        fileItem.style.animationDelay = `${index * 0.1}s`;

        const isImg = isImage(file.name);
        const fileInfoData = isImg ? `data-id="${file.id}" data-name="${file.name}" style="cursor: pointer;"` : '';
        const iconSvg = isImg
            ? `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                <circle cx="12" cy="12" r="3"></circle>
               </svg>`
            : `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="12" y1="8" x2="12" y2="16"></line>
                <line x1="8" y1="12" x2="16" y2="12"></line>
               </svg>`;

        fileItem.innerHTML = `
            <div class="file-info" ${fileInfoData}>
                <div class="file-icon vault-icon" style="border: 1px solid rgba(34, 211, 238, 0.3); background: rgba(34, 211, 238, 0.05); color: var(--reach-cyan);">
                    ${iconSvg}
                </div>
                <div class="file-details">
                    <div class="file-name scramble-text" data-text="${file.name}"></div>
                    <div class="file-meta" style="color: rgba(34, 211, 238, 0.6); font-family: var(--font-mono);">
                        <span style="border-right: 1px solid rgba(34, 211, 238, 0.2); padding-right: 8px;">${INFINITY.formatFileSize(file.size)}</span>
                        <span style="padding-left: 8px;">${INFINITY.formatDate(file.uploaded)}</span>
                    </div>
                </div>
            </div>
            <div class="file-actions">
                <button class="file-btn download vault-btn" data-id="${file.id}" title="Decrypt & Download" style="color: var(--reach-cyan); border-color: rgba(34, 211, 238, 0.3);">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    DECRYPT
                </button>
                <button class="file-btn delete vault-btn-danger" data-id="${file.id}" title="Purge Record" style="color: var(--reach-orange); border-color: rgba(232, 93, 4, 0.3);">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                    PURGE
                </button>
            </div>
        `;
        fileList.appendChild(fileItem);
    });

    attachFileActions();
    triggerScrambleAnimation();
}

/**
 * Scramble text animation for a cyber/decrypt effect
 */
function triggerScrambleAnimation() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&*';
    document.querySelectorAll('.scramble-text').forEach(el => {
        const targetText = el.getAttribute('data-text');
        let iterations = 0;

        const interval = setInterval(() => {
            el.textContent = targetText.split('').map((char, index) => {
                if (index < iterations) return char;
                return chars[Math.floor(Math.random() * chars.length)];
            }).join('');

            iterations += 1;
            if (iterations > targetText.length) {
                clearInterval(interval);
                el.textContent = targetText;
            }
        }, 30);
    });
}

/**
 * Attach event listeners to file action buttons
 */
function attachFileActions() {
    document.querySelectorAll('.file-btn.download').forEach(btn => {
        btn.addEventListener('click', () => downloadFile(btn.dataset.id));
    });

    document.querySelectorAll('.file-btn.delete').forEach(btn => {
        btn.addEventListener('click', () => deleteFile(btn.dataset.id));
    });

    document.querySelectorAll('.file-info[data-id]').forEach(info => {
        info.addEventListener('click', (e) => {
            e.preventDefault();
            openPreview(info.dataset.id, info.dataset.name);
        });
    });
}

/**
 * Download a file
 */
function downloadFile(fileId) {
    window.location.href = `/api/files/${fileId}/download`;
}

/**
 * Delete a file
 */
async function deleteFile(fileId) {
    if (!confirm('Are you sure you want to delete this file?')) return;
    try {
        const response = await fetch(`/api/files/${fileId}`, { method: 'DELETE', headers: { 'X-CSRF-Token': CSRF_TOKEN } });
        if (response.ok) loadFiles();
        else alert('Failed to delete file');
    } catch (error) {
        console.error('Delete error:', error);
        alert('Failed to delete file');
    }
}

/**
 * Upload files
 */
async function uploadFiles(files) {
    if (files.length === 0) return;

    uploadProgress.classList.add('visible');
    let completed = 0;

    for (const file of files) {
        progressText.textContent = `Uploading ${file.name}...`;
        progressFill.style.width = '0%';

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/files/upload', {
                method: 'POST',
                headers: { 'X-CSRF-Token': CSRF_TOKEN },
                body: formData
            });

            if (!response.ok) throw new Error('Upload failed');

            completed++;
            progressFill.style.width = `${(completed / files.length) * 100}%`;
        } catch (error) {
            console.error('Upload error:', error);
            progressText.textContent = `Failed to upload ${file.name}`;
            await new Promise(resolve => setTimeout(resolve, 2000));
        }
    }

    progressText.textContent = 'Upload complete!';
    progressFill.style.width = '100%';

    setTimeout(() => {
        uploadProgress.classList.remove('visible');
        progressFill.style.width = '0%';
    }, 1500);

    loadFiles();
}

/**
 * Handle logout
 */
async function logout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
        window.location.href = '/uplink/login';
    } catch (error) {
        window.location.href = '/uplink/login';
    }
}

// Lightbox: ESC key and click-outside to close
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && lightbox.style.display === 'block') closePreview();
});

lightbox.addEventListener('click', (e) => {
    if (e.target === lightbox) closePreview();
});

// Browse trigger
browseTrigger.addEventListener('click', () => fileInput.click());

// File input change
fileInput.addEventListener('change', (e) => {
    uploadFiles(Array.from(e.target.files));
    fileInput.value = '';
});

// Drag and drop events
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    uploadFiles(Array.from(e.dataTransfer.files));
});

document.addEventListener('dragover', (e) => e.preventDefault());
document.addEventListener('drop', (e) => e.preventDefault());

// Logout button
logoutBtn.addEventListener('click', logout);

// Initialize
document.addEventListener('DOMContentLoaded', loadFiles);
