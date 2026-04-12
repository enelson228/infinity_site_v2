/**
 * INFINITY — UNSC Boot Sequence
 * Plays once per browser session on the home page.
 * Skipped if sessionStorage key 'booted' is already set.
 */
(function bootSequence() {
    // Only run on home page (hero section present)
    if (!document.querySelector('.hero')) return;

    // Skip on subsequent visits within same session
    if (sessionStorage.getItem('booted')) return;
    sessionStorage.setItem('booted', '1');

    // Lines to display: [text, unused, isReady (green), tag (amber)]
    const lines = [
        ['MJOLNIR OS v4.1  ·  INITIALIZING...', false, false],
        ['AUTH  ..........  ', false, false, '[OK]'],
        ['NET UPLINK  .....  ', false, false, '[LOCKED]'],
        ['OPERATOR  .......  ', false, false, '[INFINITY]'],
        ['CLEARANCE  ......  ', false, false, '[LEVEL 5]'],
        ['SYSTEM READY ▋', false, true],
    ];

    // Build overlay
    const overlay = document.createElement('div');
    overlay.id = 'boot-overlay';

    const divider = document.createElement('div');
    divider.className = 'boot-divider';
    overlay.appendChild(divider);

    const container = document.createElement('div');
    container.className = 'boot-lines';
    overlay.appendChild(container);

    const divider2 = document.createElement('div');
    divider2.className = 'boot-divider';
    overlay.appendChild(divider2);

    document.body.appendChild(overlay);

    // Prevent page scroll during boot
    document.body.style.overflow = 'hidden';

    // Stagger line reveals
    const delays = [200, 600, 1000, 1400, 1800, 2200];

    lines.forEach(([text, , isReady, tag], i) => {
        const span = document.createElement('span');
        span.className = 'boot-line' + (isReady ? ' ready' : '');

        if (tag) {
            span.textContent = text;
            const tagSpan = document.createElement('span');
            tagSpan.className = 'boot-tag';
            tagSpan.textContent = tag;
            span.appendChild(tagSpan);
        } else {
            span.textContent = text;
        }

        container.appendChild(span);

        setTimeout(() => {
            span.classList.add('visible');
        }, delays[i]);
    });

    // Fade out and remove
    setTimeout(() => {
        overlay.classList.add('fading');
    }, 2600);

    setTimeout(() => {
        overlay.remove();
        document.body.style.overflow = '';
    }, 3200);
}());
