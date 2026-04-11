# Motion Graphics Round 2 — Infinity Site v2

**Date:** 2026-04-11
**Status:** Approved

## Overview

Five additive motion graphics enhancements building on the Round 1 animations (bracket scan-lock, sonar rings, grid ripple, glitch text, 3D card tilt). All changes are pure CSS/JS — no libraries, no breaking changes. Round 2 introduces a new `motion.css` file to keep `style.css` from growing beyond 2700 lines.

---

## Architecture

### New Files
| File | Purpose |
|------|---------|
| `static/css/motion.css` | All 5 animation keyframes and supporting classes |
| `static/js/boot.js` | Boot sequence logic (home page only) |

### Modified Files
| File | Changes |
|------|---------|
| `templates/base.html` | Add `<link>` for `motion.css` in `<head>` |
| `templates/home.html` | Boot overlay `<div>`, static overlay `<div>` inside `.hero-grid` |
| `templates/telemetry.html` | Add `data-scramble` attribute to metric value elements |
| `static/js/main.js` | Target-lock nav hover handler (~15 lines) |
| `static/js/telemetry.js` | IntersectionObserver for scramble count-up |
| `static/css/motion.css` | All motion keyframes including float — no changes needed to `style.css` |

---

## Concept 1 — UNSC Boot Sequence

**Location:** Home page, first visit per session
**Files:** `static/js/boot.js`, `templates/home.html`

### Behavior
A full-screen overlay covers the page on first visit. Six terminal lines print sequentially via `setTimeout` stagger:

```
MJOLNIR OS v4.1  ·  INITIALIZING...
AUTH  ..........  [OK]
NET UPLINK  .....  [LOCKED]
OPERATOR  .......  [INFINITY]
CLEARANCE  ......  [LEVEL 5]
SYSTEM READY ▋
```

After the final line, a 400ms pause, then the overlay fades to opacity 0 over 500ms and is removed from the DOM. `sessionStorage.setItem('booted', '1')` prevents replay within the same browser session. The script only runs on the home route (checked via `document.querySelector('.hero')`).

### Overlay Spec
- `position: fixed; inset: 0; z-index: 9999; background: #0d1117`
- Font: `JetBrains Mono`, 0.8rem, `--reach-cyan`
- Lines stagger at 400ms intervals
- OK/LOCKED/LEVEL 5 tags in `--reach-amber`
- Final "SYSTEM READY" line in `#4ade80` (green)
- Fade-out: CSS `transition: opacity 500ms ease`

### Timing
| Event | Delay |
|-------|-------|
| Line 1 | 200ms |
| Line 2 | 600ms |
| Line 3 | 1000ms |
| Line 4 | 1400ms |
| Line 5 | 1800ms |
| Line 6 | 2200ms |
| Fade start | 2600ms |
| DOM removal | 3200ms |

---

## Concept 2 — Target Lock Navigation

**Location:** Global nav bar
**Files:** `static/js/main.js`, `static/css/motion.css`

### Behavior
`mouseover` on a `.nav-link` adds `.targeted` class. `mouseout` removes it. CSS animates four corner points drawing in via `clip-path`. Active nav links (`.nav-link.active`) keep corners permanently at reduced opacity.

### CSS Spec
`.nav-link` gets `position: relative`. A `<span class="nav-corners">` is injected inside each link by JS (or via CSS pseudo approach using `::before`/`::after` on the link).

Since `::before`/`::after` are already used by the nav for other purposes, use two injected `<span>` elements per link (`.corner-tl` and `.corner-br`) with absolute positioning.

```
.corner-tl: top:-3px left:-3px  — border-top + border-left, 8×8px, 1.5px --reach-amber
.corner-br: bottom:-3px right:-3px — border-bottom + border-right, 8×8px, 1.5px --reach-amber
```

On `.targeted .corner-tl` / `.targeted .corner-br`:
- `clip-path`: `inset(50% 50% 50% 50%)` → `inset(0 0 0 0)` over 0.2s cubic-bezier(0.4,0,0.2,1)

On `.nav-link.active .corner-tl` / `.nav-link.active .corner-br`:
- Always visible at `opacity: 0.35`, no animation

On `mouseout`:
- `clip-path` snaps back to `inset(50% 50% 50% 50%)` over 0.15s

---

## Concept 3 — Metric Scramble Count-Up

**Location:** Telemetry page, metric value elements
**Files:** `static/js/telemetry.js`, `static/css/motion.css`

### Behavior
`IntersectionObserver` (threshold: 0.3) watches all `[data-scramble]` elements. On first intersection:

1. **Scramble phase** (amber, `--reach-amber`): `setInterval` at 40ms replaces text with random alphanumeric characters matching the character length of the real value string. Duration determined by parsing the numeric portion: `parseFloat(data-scramble value) < 100` → 400ms, otherwise 600ms.
2. **Settle phase**: `clearInterval`, snap to real value, switch color to `--reach-cyan`.

Real value stored in `data-scramble` attribute: `<span data-scramble="94.7%">94.7%</span>`. Played once per page load via `data-scrambled="true"` flag set on the element after first play.

### Scramble Character Set
`ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#@$%`

---

## Concept 4 — Comms Static Overlay

**Location:** Home page, hero section
**Files:** `static/css/motion.css`, `templates/home.html`

### Behavior
A `<div class="hero-static">` added inside `.hero-grid` (sibling to `.hero-grid-ripple`). Two animation layers:

**Layer A — Noise grain:** `background-image` with inline SVG `feTurbulence` filter. `background-size: 200px 200px`. `background-position` cycles through 8 offset positions via `@keyframes staticShift` (0.1s steps, infinite). Opacity: 0.05. `mix-blend-mode: screen`.

**Layer B — Scanline (`::after`):** 1px tall, full width, amber at 12% opacity. `@keyframes scanSweep`: `top: -1px` → `top: 100%` over 5s linear, infinite. Restarts immediately (no pause between cycles).

Both layers: `position: absolute; inset: 0; pointer-events: none`.

### CSS
```css
.hero-static {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 1;
}
```
`.hero-grid` must have `position: relative` (already true from existing styles).

---

## Concept 5 — Holographic Icon Float

**Location:** Projects page, `.project-icon` inside cards
**Files:** `static/css/motion.css`

### Behavior
`.project-icon` gets a continuous sine-wave float animation. On `.project-card:hover .project-icon`, the animation pauses and the icon snaps to the elevated position with a brighter glow.

### Keyframes
```css
@keyframes iconFloat {
  0%, 100% {
    transform: translateY(0px);
    box-shadow: 0 4px 12px rgba(34,211,238,0.15);
    filter: drop-shadow(0 2px 4px rgba(34,211,238,0.2));
  }
  50% {
    transform: translateY(-6px);
    box-shadow: 0 12px 24px rgba(34,211,238,0.4);
    filter: drop-shadow(0 6px 12px rgba(34,211,238,0.4));
  }
}
```

**Stagger** via explicit per-child rules (CSS `calc()` with `n` doesn't work without `@property`):
```css
.project-card:nth-child(1) .project-icon { animation-delay: 0s; }
.project-card:nth-child(2) .project-icon { animation-delay: 0.5s; }
.project-card:nth-child(3) .project-icon { animation-delay: 1s; }
.project-card:nth-child(4) .project-icon { animation-delay: 1.5s; }
.project-card:nth-child(5) .project-icon { animation-delay: 2s; }
.project-card:nth-child(6) .project-icon { animation-delay: 2.5s; }
```

**Hover state:**
```css
.project-card:hover .project-icon {
  animation-play-state: paused;
  transform: translateY(-6px);
  box-shadow: 0 16px 32px rgba(34,211,238,0.6);
  filter: drop-shadow(0 8px 16px rgba(34,211,238,0.6));
  transition: box-shadow 0.2s ease, filter 0.2s ease;
}
```

---

## Verification Checklist

1. Home page (fresh session): boot sequence plays, fades, doesn't replay on refresh
2. Home page (reload): boot skipped, site loads normally
3. Nav bar: hover each link — corners draw in, retract on mouseout; active link corners stay at low opacity
4. Telemetry page: scroll metric cards into view — values scramble then resolve
5. Home page hero: subtle noise grain + slow scanline visible over hero grid
6. Projects page: icons floating; hover a card — float pauses, icon locks up with bright glow
7. Mobile: confirm no tilt/hover side-effects on touch (boot sequence still fires, others gracefully no-op)
