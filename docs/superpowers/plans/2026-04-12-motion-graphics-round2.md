# Motion Graphics Round 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 CSS/JS motion effects to the Infinity homelab site: UNSC boot sequence, target-lock nav, metric scramble count-up, comms static overlay, and holographic icon float.

**Architecture:** All new animations live in `static/css/motion.css` (loaded globally via `base.html`). Boot sequence logic is isolated in `static/js/boot.js` (home-page only). Telemetry scramble is added to `static/js/telemetry.js` via IntersectionObserver. Nav target-lock corners are injected by `static/js/main.js`. No existing animation code is removed.

**Tech Stack:** Vanilla CSS (keyframes, clip-path, mix-blend-mode), Vanilla JS (IntersectionObserver, setTimeout, setInterval, sessionStorage), Flask/Jinja2 templates.

---

## Task 1: Create `motion.css` and load it globally

**Files:**
- Create: `static/css/motion.css`
- Modify: `templates/base.html`

- [ ] **Step 1: Create `static/css/motion.css` with a file header only**

```css
/**
 * INFINITY — Motion Graphics Round 2
 * All animation keyframes and supporting classes.
 * Loaded after style.css via base.html.
 */
```

- [ ] **Step 2: Add the `<link>` to `templates/base.html` after the existing style.css link**

Find this line in `templates/base.html:14`:
```html
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
```

Replace with:
```html
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/motion.css') }}">
```

- [ ] **Step 3: Verify in preview — open http://localhost:5001 and check browser devtools Network tab shows `motion.css` loaded with 200 status**

- [ ] **Step 4: Commit**

```bash
git add static/css/motion.css templates/base.html
git commit -m "feat: add motion.css and load globally"
```

---

## Task 2: Comms Static Overlay (CSS + HTML)

This is pure CSS + a single div — no JS required. Do it first so the hero has its atmospheric layer from the start.

**Files:**
- Modify: `static/css/motion.css`
- Modify: `templates/home.html`

- [ ] **Step 1: Add `.hero-static` CSS to `static/css/motion.css`**

Append to `static/css/motion.css`:

```css
/* ============================================================
   Concept 4 — Comms Static Overlay
   ============================================================ */

@keyframes staticShift {
    0%   { background-position: 0px 0px; }
    12%  { background-position: 30px 12px; }
    25%  { background-position: -18px 40px; }
    37%  { background-position: 45px -20px; }
    50%  { background-position: -30px 25px; }
    62%  { background-position: 20px -35px; }
    75%  { background-position: -42px 18px; }
    87%  { background-position: 15px 50px; }
    100% { background-position: 0px 0px; }
}

@keyframes scanSweep {
    0%   { top: -2px; opacity: 0; }
    3%   { opacity: 0.12; }
    97%  { opacity: 0.08; }
    100% { top: 100%; opacity: 0; }
}

.hero-static {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 1;
    /* Layer A: animated noise grain */
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E");
    background-size: 200px 200px;
    animation: staticShift 0.8s steps(1) infinite;
    opacity: 0.05;
    mix-blend-mode: screen;
}

.hero-static::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    height: 1px;
    background: rgba(246, 166, 35, 0.5);
    animation: scanSweep 5s linear infinite;
}
```

- [ ] **Step 2: Add `.hero-static` div to `templates/home.html` inside `.hero-grid`**

Find in `templates/home.html:9-15`:
```html
    <div class="hero-grid">
        <div class="hero-grid-ripple">
            <div class="grid-ripple"></div>
            <div class="grid-ripple"></div>
            <div class="grid-crosshair"></div>
        </div>
    </div>
```

Replace with:
```html
    <div class="hero-grid">
        <div class="hero-static"></div>
        <div class="hero-grid-ripple">
            <div class="grid-ripple"></div>
            <div class="grid-ripple"></div>
            <div class="grid-crosshair"></div>
        </div>
    </div>
```

- [ ] **Step 3: Verify in preview — restart server, navigate to http://localhost:5001, look at the hero grid area. A slow amber scanline should sweep top-to-bottom every 5 seconds. The background should have a very subtle grain texture.**

To restart:
```bash
# Stop and restart preview server via Claude Preview MCP
# Or run: doppler run -- /path/to/venv/bin/python3 app.py
```

- [ ] **Step 4: Commit**

```bash
git add static/css/motion.css templates/home.html
git commit -m "feat: add comms static overlay to hero section"
```

---

## Task 3: Holographic Icon Float (CSS only)

**Files:**
- Modify: `static/css/motion.css`

- [ ] **Step 1: Append icon float keyframes and rules to `static/css/motion.css`**

```css
/* ============================================================
   Concept 5 — Holographic Icon Float
   ============================================================ */

@keyframes iconFloat {
    0%, 100% {
        transform: translateY(0px);
        filter: drop-shadow(0 2px 4px rgba(34, 211, 238, 0.2));
    }
    50% {
        transform: translateY(-6px);
        filter: drop-shadow(0 8px 16px rgba(34, 211, 238, 0.5));
    }
}

.project-icon {
    animation: iconFloat 3s ease-in-out infinite;
}

/* Stagger delays per card position */
.project-card:nth-child(1) .project-icon { animation-delay: 0s; }
.project-card:nth-child(2) .project-icon { animation-delay: 0.5s; }
.project-card:nth-child(3) .project-icon { animation-delay: 1s; }
.project-card:nth-child(4) .project-icon { animation-delay: 1.5s; }
.project-card:nth-child(5) .project-icon { animation-delay: 2s; }
.project-card:nth-child(6) .project-icon { animation-delay: 2.5s; }

/* Hover: freeze float at elevated position with brighter glow */
.project-card:hover .project-icon {
    animation-play-state: paused;
    transform: translateY(-6px);
    filter: drop-shadow(0 8px 16px rgba(34, 211, 238, 0.7));
    transition: filter 0.2s ease;
}
```

- [ ] **Step 2: Verify in preview — navigate to http://localhost:5001/projects. Project card icons should gently bob up and down at staggered rates. Hovering a card should freeze the icon at the top of its float with a brighter cyan glow.**

- [ ] **Step 3: Commit**

```bash
git add static/css/motion.css
git commit -m "feat: add holographic icon float to project cards"
```

---

## Task 4: Target Lock Navigation (CSS + JS)

**Files:**
- Modify: `static/css/motion.css`
- Modify: `static/js/main.js`

- [ ] **Step 1: Append target-lock CSS to `static/css/motion.css`**

```css
/* ============================================================
   Concept 2 — Target Lock Navigation
   ============================================================ */

/* Corner spans injected by JS into each .nav-link */
.corner-tl,
.corner-br {
    position: absolute;
    width: 8px;
    height: 8px;
    pointer-events: none;
    clip-path: inset(50% 50% 50% 50%);
    transition: clip-path 0.15s ease-in;
}

.corner-tl {
    top: -3px;
    left: -3px;
    border-top: 1.5px solid var(--reach-amber, #f6a623);
    border-left: 1.5px solid var(--reach-amber, #f6a623);
}

.corner-br {
    bottom: -3px;
    right: -3px;
    border-bottom: 1.5px solid var(--reach-amber, #f6a623);
    border-right: 1.5px solid var(--reach-amber, #f6a623);
}

/* Targeted state: draw corners in */
.nav-link.targeted .corner-tl,
.nav-link.targeted .corner-br {
    clip-path: inset(0 0 0 0);
    transition: clip-path 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Active link: corners always visible at low opacity */
.nav-link.active .corner-tl,
.nav-link.active .corner-br {
    clip-path: inset(0 0 0 0);
    opacity: 0.35;
    transition: none;
}
```

- [ ] **Step 2: Add corner span injection and hover handlers to `static/js/main.js`**

Add the following block at the end of `static/js/main.js` (after the existing nav close-on-outside-click handler):

```js
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
```

- [ ] **Step 3: Verify in preview — hover each nav link (Home, Projects, Telemetry, Uplink). Corner brackets should snap in on hover and retract cleanly on mouseout. The active page link should show faint permanent corners.**

- [ ] **Step 4: Commit**

```bash
git add static/css/motion.css static/js/main.js
git commit -m "feat: add target-lock corner brackets to nav links"
```

---

## Task 5: Metric Scramble Count-Up (CSS + JS)

**Files:**
- Modify: `static/css/motion.css`
- Modify: `templates/telemetry.html`
- Modify: `static/js/telemetry.js`

- [ ] **Step 1: Append scramble CSS to `static/css/motion.css`**

```css
/* ============================================================
   Concept 3 — Metric Scramble Count-Up
   ============================================================ */

/* Scramble phase: amber flash */
.scrambling {
    color: var(--reach-amber, #f6a623) !important;
    text-shadow: 0 0 8px rgba(246, 166, 35, 0.6) !important;
    transition: none !important;
}
```

- [ ] **Step 2: Add `data-scramble` attributes to metric big-value elements in `templates/telemetry.html`**

The telemetry JS updates `#cpu-percent`, `#ram-percent`, `#disk-percent` dynamically. These elements need `data-scramble` set by JS after the API response, not in the HTML. Instead, mark the container elements so the scramble JS can identify them once values arrive.

Add `data-scramble-target` attribute to the three big-value spans. Find these lines in `templates/telemetry.html`:

Line 43: `<span class="metric-big-value" id="cpu-percent">—</span>`
Line 74: `<span class="metric-big-value" id="ram-percent">—</span>`

Search for `id="disk-percent"` (around line 110):
`<span class="metric-big-value" id="disk-percent">—</span>`

Replace each with the `data-scramble-target` attribute added:
```html
<span class="metric-big-value" id="cpu-percent" data-scramble-target>—</span>
```
```html
<span class="metric-big-value" id="ram-percent" data-scramble-target>—</span>
```
```html
<span class="metric-big-value" id="disk-percent" data-scramble-target>—</span>
```

- [ ] **Step 3: Add `scrambleValue` helper function to `static/js/telemetry.js`** (add before the first existing function)

Add this function near the top of `static/js/telemetry.js` (before the first function definition):

```js
/**
 * Scramble count-up animation for metric values.
 * @param {HTMLElement} el - Element to animate
 * @param {string} finalValue - The real value to display (e.g. "94.7")
 */
function scrambleValue(el, finalValue) {
    // Only play once per page load
    if (el.dataset.scrambled) {
        el.textContent = finalValue;
        return;
    }
    el.dataset.scrambled = 'true';

    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#@$%';
    const len = String(finalValue).length;
    const numericVal = parseFloat(finalValue);
    const duration = (isNaN(numericVal) || numericVal < 100) ? 400 : 600;

    el.classList.add('scrambling');

    const interval = setInterval(() => {
        el.textContent = Array.from({ length: len }, () =>
            chars[Math.floor(Math.random() * chars.length)]
        ).join('');
    }, 40);

    setTimeout(() => {
        clearInterval(interval);
        el.classList.remove('scrambling');
        el.textContent = finalValue;
    }, duration);
}
```

- [ ] **Step 5: Wire `scrambleValue` into the telemetry update function**

In `static/js/telemetry.js`, make these three specific replacements:

Line 48 — change:
```js
    document.getElementById('cpu-percent').textContent = cpu.percent;
```
To:
```js
    scrambleValue(document.getElementById('cpu-percent'), String(cpu.percent));
```

Line 65 — change:
```js
    document.getElementById('ram-percent').textContent = ram.percent;
```
To:
```js
    scrambleValue(document.getElementById('ram-percent'), String(ram.percent));
```

Line 73 — change:
```js
    document.getElementById('disk-percent').textContent = disk.percent;
```
To:
```js
    scrambleValue(document.getElementById('disk-percent'), String(disk.percent));
```

- [ ] **Step 6: Verify in preview — navigate to http://localhost:5001/telemetry. On first load the CPU, RAM, and Disk big-value numbers should flash amber with random characters for ~400ms then snap to their real values in cyan. Subsequent 5-second refreshes should show the real values directly (no re-scramble).**

- [ ] **Step 7: Commit**

```bash
git add static/css/motion.css templates/telemetry.html static/js/telemetry.js
git commit -m "feat: add metric scramble count-up to telemetry values"
```

---

## Task 6: UNSC Boot Sequence (JS + CSS + HTML)

**Files:**
- Create: `static/js/boot.js`
- Modify: `static/css/motion.css`
- Modify: `templates/home.html`

- [ ] **Step 1: Append boot sequence CSS to `static/css/motion.css`**

```css
/* ============================================================
   Concept 1 — UNSC Boot Sequence
   ============================================================ */

#boot-overlay {
    position: fixed;
    inset: 0;
    z-index: 9999;
    background: #0d1117;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    opacity: 1;
    transition: opacity 500ms ease;
}

#boot-overlay.fading {
    opacity: 0;
}

.boot-lines {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    line-height: 2;
    text-align: left;
    min-width: 320px;
}

.boot-line {
    display: block;
    color: var(--reach-cyan, #22d3ee);
    opacity: 0;
    transform: translateX(-8px);
    transition: opacity 0.2s ease, transform 0.2s ease;
}

.boot-line.visible {
    opacity: 1;
    transform: translateX(0);
}

.boot-tag {
    color: var(--reach-amber, #f6a623);
}

.boot-line.ready {
    color: #4ade80;
}

.boot-divider {
    width: 320px;
    height: 1px;
    background: rgba(246, 166, 35, 0.2);
    margin: 16px 0;
}
```

- [ ] **Step 2: Create `static/js/boot.js`**

```js
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

    // Lines to display: [text, isTag (amber), isReady (green)]
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
```

- [ ] **Step 3: Load `boot.js` on the home page via `templates/home.html` `{% block scripts %}`**

In `templates/home.html`, the existing `{% block scripts %}` block starts at line 117. Add the boot.js script tag before the inline script:

```html
{% block scripts %}
<script src="{{ url_for('static', filename='js/boot.js') }}"></script>
<script>
    // Fetch project count for status panel
    fetch('/api/projects')
        .then(res => res.json())
        .then(data => {
            const onlineCount = data.projects.filter(p => p.status === 'online').length;
            document.getElementById('active-services').textContent = onlineCount;
        })
        .catch(() => {
            document.getElementById('active-services').textContent = '0';
        });
</script>
{% endblock %}
```

- [ ] **Step 4: Verify boot sequence in preview**

1. Open http://localhost:5001 in a fresh tab (or clear sessionStorage: DevTools → Application → Session Storage → clear)
2. The dark overlay should appear, lines should print in one by one over ~2.2 seconds
3. After the final line, overlay fades out over 0.5s and the home page is visible
4. Reload the page — boot should NOT replay (sessionStorage key present)
5. To test replay: DevTools → Application → Session Storage → delete `booted` key → refresh

- [ ] **Step 5: Commit**

```bash
git add static/css/motion.css static/js/boot.js templates/home.html
git commit -m "feat: add UNSC boot sequence on first home page visit"
```

---

## Task 7: Final Verification Pass

- [ ] **Step 1: Restart preview server to pick up all template changes**

Stop and restart the `infinity-site-v2` preview server.

- [ ] **Step 2: Home page — boot sequence**

Clear sessionStorage (`booted` key), navigate to http://localhost:5001. Confirm:
- Boot overlay appears, 6 lines print sequentially with ~400ms stagger
- Tagged values `[OK]`, `[LOCKED]`, `[INFINITY]`, `[LEVEL 5]` appear in amber
- Final `SYSTEM READY ▋` line appears in green
- Overlay fades out after ~2.6s, home page fully visible
- Reload: boot does NOT replay

- [ ] **Step 3: Home page — comms static + hero animations**

On http://localhost:5001 scroll to the hero section:
- Subtle noise grain texture visible over hero grid (very faint — 5% opacity)
- A 1px amber scanline sweeps top-to-bottom over ~5 seconds, loops continuously

- [ ] **Step 4: Nav bar — target lock**

Hover each nav link: Home, Projects, Telemetry, Uplink:
- Corner brackets draw in on hover (0.2s clip-path animation)
- Brackets retract cleanly on mouseout (0.15s)
- Active page link shows permanent faint corners at 35% opacity

- [ ] **Step 5: Telemetry — scramble count-up**

Navigate to http://localhost:5001/telemetry:
- CPU, RAM, Disk big values flash amber random characters for ~400ms then snap to real values in cyan
- Wait 5 seconds (next refresh cycle): values update directly without scramble (played only once)

- [ ] **Step 6: Projects — icon float**

Navigate to http://localhost:5001/projects:
- Each project card icon gently bobs up and down on staggered sine-wave cycles
- Hovering a card: icon freezes at elevated position with bright cyan drop-shadow
- Mouseout: float resumes

- [ ] **Step 7: Commit final verification**

```bash
git add -A
git status  # confirm nothing unexpected
git commit -m "chore: verified all 5 motion graphics round 2 effects"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| New `motion.css` file | Task 1 |
| `motion.css` loaded via `base.html` | Task 1 |
| Comms static overlay CSS + `hero-static` div | Task 2 |
| Holographic icon float CSS | Task 3 |
| Target lock nav CSS | Task 4 |
| Target lock nav JS corner injection | Task 4 |
| Metric scramble CSS `.scrambling` class | Task 5 |
| `data-scramble-target` on telemetry elements | Task 5 |
| `scrambleValue` function in telemetry.js | Task 5 |
| Boot overlay CSS | Task 6 |
| `boot.js` boot sequence logic | Task 6 |
| `boot.js` loaded on home page | Task 6 |
| sessionStorage replay prevention | Task 6 |
| Full verification checklist | Task 7 |
