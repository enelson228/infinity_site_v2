/**
 * INFINITY - Projects Page JavaScript
 */

const projectsGrid = document.getElementById('projects-grid');
const projectsListBody = document.getElementById('projects-list-body');
const viewToggleBtns = document.querySelectorAll('.view-toggle-btn');
const refreshBtn = document.getElementById('refresh-status-btn');

// Icon SVGs for projects
const projectIcons = {
    server: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>',
    film: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="17" x2="22" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/></svg>',
    shield: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
    home: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
    box: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>',
    activity: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    cloud: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>',
    database: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
    globe: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
    anchor: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="5" r="3"/><line x1="12" y1="8" x2="12" y2="22"/><path d="M5 15H2a10 10 0 0 0 20 0h-3"/></svg>',
};

/**
 * Get icon SVG by name
 */
function getProjectIcon(iconName) {
    return projectIcons[iconName] || projectIcons.server;
}

/**
 * Create project card HTML
 */
function createProjectCard(project) {
    const clickAction = project.detail_url
        ? `window.location.href='${project.detail_url}'`
        : `window.open('${project.url}', '_blank')`;
    
    const latency = project.response_time ? `<span class="latency-badge">${project.response_time}ms</span>` : '';
    const heartbeat = `<span class="heartbeat ${project.status}"></span>`;

    return `
        <article class="project-card" onclick="${clickAction}">
            <div class="project-header">
                <div class="project-icon">${getProjectIcon(project.icon)}</div>
                <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
                    <span class="project-status ${project.status}">${heartbeat} ${project.status.toUpperCase()}</span>
                    ${latency}
                </div>
            </div>
            <h3 class="project-name">${project.name}</h3>
            <p class="project-description">${project.description}</p>
            <div class="project-meta">
                <span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <polyline points="12 6 12 12 16 14"/>
                    </svg>
                    ${project.last_ping ? 'PINGED: ' + project.last_ping.split('T')[1].split('.')[0] : 'NEVER'}
                </span>
            </div>
        </article>
    `;
}

/**
 * Create project list row HTML
 */
function createProjectRow(project) {
    const href = project.detail_url || project.url;
    const target = project.detail_url ? '_self' : '_blank';
    const clickAction = project.detail_url
        ? `window.location.href='${project.detail_url}'`
        : `window.open('${project.url}', '_blank')`;
    
    const heartbeat = `<span class="heartbeat ${project.status}"></span>`;

    return `
        <div class="list-row" onclick="${clickAction}">
            <div class="list-name">
                <div class="list-name-icon">${getProjectIcon(project.icon)}</div>
                <div class="list-name-text">
                    <h4>${project.name}</h4>
                    <p>${project.description}</p>
                </div>
            </div>
            <span class="list-status project-status ${project.status}">${heartbeat} ${project.status.toUpperCase()}</span>
            <span class="list-updated">${project.response_time ? project.response_time + 'ms' : '---'}</span>
            <div class="list-action">
                <a href="${href}" target="${target}" onclick="event.stopPropagation()">OPEN →</a>
            </div>
        </div>
    `;
}

/**
 * Load and render projects
 */
async function loadProjects() {
    const sweep = document.getElementById('tactical-scanner-sweep');
    if (refreshBtn) refreshBtn.classList.add('loading');
    
    try {
        // Trigger scanning effect
        if (sweep) {
            sweep.classList.remove('scanning');
            // Trigger reflow
            void sweep.offsetWidth;
            sweep.classList.add('scanning');
        }
        
        const response = await fetch('/api/projects');
        const data = await response.json();

        // Artificial delay for the scan effect
        await new Promise(r => setTimeout(r, 600));

        if (data.categories && data.categories.length > 0) {
            // Render grouped by category
            let gridHtml = '';
            let listHtml = '';

            data.categories.forEach((cat, cIdx) => {
                // Category Header in Grid
                gridHtml += `<h2 class="category-title" style="animation-delay: ${cIdx * 0.1}s">${cat.name.toUpperCase()}</h2>`;
                gridHtml += `<div class="category-grid">`;
                
                // Add staggering to cards
                cat.projects.forEach((p, pIdx) => {
                    const cardHtml = createProjectCard(p);
                    // Inject animation delay into the article tag
                    const delayedCard = cardHtml.replace('<article class="project-card"', `<article class="project-card tactical-fade-in" style="animation-delay: ${(cIdx * 0.1) + (pIdx * 0.05)}s"`);
                    gridHtml += delayedCard;
                });
                gridHtml += `</div>`;

                // Category Header in List
                listHtml += `<div class="list-category-row">${cat.name.toUpperCase()}</div>`;
                cat.projects.forEach((p, pIdx) => {
                     const rowHtml = createProjectRow(p);
                     const delayedRow = rowHtml.replace('<div class="list-row"', `<div class="list-row tactical-fade-in" style="animation-delay: ${(cIdx * 0.1) + (pIdx * 0.05)}s"`);
                     listHtml += delayedRow;
                });
            });

            projectsGrid.innerHTML = gridHtml;
            projectsListBody.innerHTML = listHtml;
        } else {
            // Fallback to original linear list
            projectsGrid.innerHTML = `<div class="category-grid">${data.projects.map(createProjectCard).join('')}</div>`;
            projectsListBody.innerHTML = data.projects.map(createProjectRow).join('');
        }

    } catch (error) {
        console.error('Failed to load projects:', error);
        projectsGrid.innerHTML = '<div class="radar-empty-state"><div class="radar-text" style="color: var(--reach-orange)">SCAN FAILED</div></div>';
    } finally {
        if (refreshBtn) refreshBtn.classList.remove('loading');
        setTimeout(() => {
            if (sweep) sweep.classList.remove('scanning');
        }, 1500);
    }
}

/**
 * Toggle between grid and list view
 */
function setView(view) {
    viewToggleBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === view);
    });

    document.getElementById('projects-grid').classList.toggle('active', view === 'grid');
    document.getElementById('projects-list').classList.toggle('active', view === 'list');

    // Store preference
    localStorage.setItem('projectsView', view);
}

// Event listeners for view toggle
viewToggleBtns.forEach(btn => {
    btn.addEventListener('click', () => setView(btn.dataset.view));
});

refreshBtn?.addEventListener('click', loadProjects);

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Restore view preference
    const savedView = localStorage.getItem('projectsView') || 'grid';
    setView(savedView);

    // Load projects
    loadProjects();
    
    // Auto refresh every 60s
    setInterval(loadProjects, 60000);
});
