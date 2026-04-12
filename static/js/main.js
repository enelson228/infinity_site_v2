/**
 * INFINITY - Main JavaScript
 * Shared utilities and navigation
 */

// Navigation scroll effect
const nav = document.getElementById('nav');
const navToggle = document.getElementById('nav-toggle');
const navLinks = document.getElementById('nav-links');

// Check if on home page by looking for hero section
const isHomePage = document.querySelector('.hero') !== null;

// Add scrolled class on scroll (always on non-home pages)
window.addEventListener('scroll', () => {
    if (window.scrollY > 50 || !isHomePage) {
        nav.classList.add('scrolled');
    } else if (isHomePage) {
        nav.classList.remove('scrolled');
    }
});

// Ensure nav is styled on load (non-home pages)
if (!isHomePage) {
    nav.classList.add('scrolled');
}

// Mobile nav toggle
navToggle?.addEventListener('click', () => {
    navToggle.classList.toggle('active');
    navLinks.classList.toggle('open');
});

// Close mobile nav when clicking a link
navLinks?.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => {
        navToggle.classList.remove('active');
        navLinks.classList.remove('open');
    });
});

// Close mobile nav when clicking outside
document.addEventListener('click', (e) => {
    if (!nav.contains(e.target) && navLinks.classList.contains('open')) {
        navToggle.classList.remove('active');
        navLinks.classList.remove('open');
    }
});

/**
 * Format file size for display
 * @param {number} bytes - File size in bytes
 * @returns {string} Formatted file size
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Format date for display
 * @param {string} isoString - ISO date string
 * @returns {string} Formatted date
 */
function formatDate(isoString) {
    const date = new Date(isoString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

/**
 * Get file icon based on extension
 * @param {string} filename - File name
 * @returns {string} SVG icon HTML
 */
function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const icons = {
        pdf: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
        doc: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
        docx: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
        zip: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
        jpg: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
        jpeg: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
        png: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
        gif: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
    };
    return icons[ext] || '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
}

// Export utilities for other scripts
window.INFINITY = {
    formatFileSize,
    formatDate,
    getFileIcon
};

// Target Lock Navigation — inject corner spans and wire hover
(function initTargetLock() {
    document.querySelectorAll('.nav-link').forEach(link => {
        // Ensure relative positioning for absolute children
        link.style.position = 'relative';

        // Inject corner spans
        const tl = document.createElement('span');
        tl.className = 'corner-tl';
        const br = document.createElement('span');
        br.className = 'corner-br';
        link.appendChild(tl);
        link.appendChild(br);

        // Draw in on hover
        link.addEventListener('mouseenter', () => {
            link.classList.add('targeted');
        });

        // Retract on mouse leave
        link.addEventListener('mouseleave', () => {
            link.classList.remove('targeted');
        });
    });
}());
