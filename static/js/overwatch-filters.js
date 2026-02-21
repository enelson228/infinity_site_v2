/* ============================================
   OVERWATCH Filters — GLSL PostProcessStages
   FLIR Thermal · Night Vision · CRT
   Keyboard: 1=FLIR  2=NV  3=CRT  Esc=Normal
   ============================================ */

window.OW_Filters = (function () {
    'use strict';

    let viewer   = null;
    const stages = {};
    const t0     = Date.now();

    // ── time helper (seconds since page load) ──
    const elapsedSec = () => (Date.now() - t0) / 1000;

    /* ─────────────────────────────────────────
       FLIR THERMAL
       Luminance → 7-stop thermal colormap
       ───────────────────────────────────────── */
    const FLIR_FRAG = `
        uniform sampler2D colorTexture;
        in  vec2 v_textureCoordinates;

        vec3 thermal(float t) {
            // black → blue → cyan → green → yellow → red → white
            vec3 stops[7];
            stops[0] = vec3(0.00, 0.00, 0.00);
            stops[1] = vec3(0.00, 0.00, 0.55);
            stops[2] = vec3(0.00, 0.55, 0.75);
            stops[3] = vec3(0.00, 0.75, 0.00);
            stops[4] = vec3(1.00, 0.90, 0.00);
            stops[5] = vec3(1.00, 0.00, 0.00);
            stops[6] = vec3(1.00, 1.00, 1.00);
            float seg = t * 6.0;
            int   i   = int(clamp(floor(seg), 0.0, 5.0));
            float f   = fract(seg);
            vec3 a, b;
            if      (i == 0) { a = stops[0]; b = stops[1]; }
            else if (i == 1) { a = stops[1]; b = stops[2]; }
            else if (i == 2) { a = stops[2]; b = stops[3]; }
            else if (i == 3) { a = stops[3]; b = stops[4]; }
            else if (i == 4) { a = stops[4]; b = stops[5]; }
            else             { a = stops[5]; b = stops[6]; }
            return mix(a, b, f);
        }

        void main() {
            vec4  color = texture(colorTexture, v_textureCoordinates);
            float lum   = dot(color.rgb, vec3(0.299, 0.587, 0.114));
            // Gamma-boost faint areas so cold sky isn't pitch black
            lum = clamp(pow(max(lum, 0.0), 0.75) * 1.1, 0.0, 1.0);
            out_FragColor = vec4(thermal(lum), color.a);
        }
    `;

    /* ─────────────────────────────────────────
       NIGHT VISION
       Green phosphor · noise · scanlines · vignette
       ───────────────────────────────────────── */
    const NV_FRAG = `
        uniform sampler2D colorTexture;
        uniform float u_time;
        in  vec2 v_textureCoordinates;

        float hash(vec2 p) {
            p  = fract(p * vec2(234.34, 435.345));
            p += dot(p, p + 34.23);
            return fract(p.x * p.y);
        }

        void main() {
            vec2 uv    = v_textureCoordinates;
            vec4 color = texture(colorTexture, uv);

            float lum = dot(color.rgb, vec3(0.299, 0.587, 0.114));

            // Phosphor green
            vec3 nv = vec3(0.0, clamp(lum * 1.6 + color.g * 0.3, 0.0, 1.0), 0.0);

            // Grain noise
            float noise = hash(uv * 1.3 + fract(vec2(u_time * 0.017, u_time * 0.023)));
            nv += vec3(0.0, noise * 0.045, 0.0);

            // Horizontal scanlines
            float scan = sin(uv.y * 650.0 * 3.14159);
            nv *= 0.91 + 0.09 * scan;

            // Radial vignette
            vec2  c   = uv - 0.5;
            float vig = 1.0 - dot(c, c) * 2.2;
            nv *= clamp(vig, 0.0, 1.0);

            out_FragColor = vec4(nv, color.a);
        }
    `;

    /* ─────────────────────────────────────────
       CRT
       Barrel distort · scanlines · chromatic aberration
       flicker · vignette · amber tint
       ───────────────────────────────────────── */
    const CRT_FRAG = `
        uniform sampler2D colorTexture;
        uniform float u_time;
        in  vec2 v_textureCoordinates;

        vec2 barrel(vec2 uv) {
            vec2 cc = uv - 0.5;
            float r2 = dot(cc, cc);
            return uv + cc * r2 * 0.14;
        }

        void main() {
            vec2 uv = barrel(v_textureCoordinates);

            // Clip outside barrel
            if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
                out_FragColor = vec4(0.0, 0.0, 0.0, 1.0);
                return;
            }

            // Chromatic aberration — R/G/B sampled at slight offsets
            float ab   = 0.0025;
            float r    = texture(colorTexture, uv + vec2( ab,  0.0)).r;
            float g    = texture(colorTexture, uv                  ).g;
            float b    = texture(colorTexture, uv + vec2(-ab,  0.0)).b;
            vec3 color = vec3(r, g, b);

            // Scanlines
            float scan = sin(uv.y * 780.0 * 3.14159);
            color *= 0.87 + 0.13 * scan;

            // Subtle flicker
            color *= 0.97 + 0.03 * sin(u_time * 8.1 + 1.3);

            // Vignette
            vec2  c   = uv - 0.5;
            float vig = 1.0 - dot(c, c) * 1.6;
            color *= clamp(vig, 0.0, 1.0);

            // Warm amber tint
            color.r *= 1.06;
            color.g *= 0.97;
            color.b *= 0.88;

            out_FragColor = vec4(clamp(color, 0.0, 1.0), 1.0);
        }
    `;

    // ── Status bar labels ──
    const MODE_LABELS = {
        flir:        '// FLIR ACTIVE',
        nightvision: '// N-VIS ACTIVE',
        crt:         '// CRT ACTIVE',
        normal:      '// NORMAL',
    };

    function init(v) {
        viewer = v;

        try {
            stages.flir = viewer.scene.postProcessStages.add(
                new Cesium.PostProcessStage({
                    name: 'ow_flir',
                    fragmentShader: FLIR_FRAG,
                })
            );
            stages.flir.enabled = false; // force off — constructor flag not always respected

            stages.nightvision = viewer.scene.postProcessStages.add(
                new Cesium.PostProcessStage({
                    name: 'ow_nv',
                    fragmentShader: NV_FRAG,
                    uniforms: { u_time: elapsedSec },
                })
            );
            stages.nightvision.enabled = false;

            stages.crt = viewer.scene.postProcessStages.add(
                new Cesium.PostProcessStage({
                    name: 'ow_crt',
                    fragmentShader: CRT_FRAG,
                    uniforms: { u_time: elapsedSec },
                })
            );
            stages.crt.enabled = false;

        } catch (e) {
            console.warn('[OW] PostProcessStage init failed:', e.message);
            // Filters will simply not work — graceful degradation
        }

        // Guarantee clean normal state on startup
        setFilter('normal');

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            switch (e.key) {
                case '1':      setFilter('flir');        break;
                case '2':      setFilter('nightvision'); break;
                case '3':      setFilter('crt');         break;
                case 'Escape': setFilter('normal');      break;
            }
        });

        // Click handlers for filter buttons
        document.querySelectorAll('.ow-filter-btn').forEach(btn => {
            btn.addEventListener('click', () => setFilter(btn.dataset.filter));
        });
    }

    function setFilter(name) {
        if (name === 'sat') return; // SAT imagery mode is handled in overwatch-main.js

        // Disable all stages
        for (const stage of Object.values(stages)) {
            try { stage.enabled = false; } catch (_) {}
        }

        // Enable the requested stage
        if (name !== 'normal' && stages[name]) {
            try { stages[name].enabled = true; } catch (_) {}
        }

        window.OW.filterMode = name;

        // Update button active state
        document.querySelectorAll('.ow-filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.filter === name);
        });

        // Update status bar
        const sbFilter = document.getElementById('sb-filter');
        if (sbFilter) {
            const satSuffix = window.OW && window.OW.satMode ? ' + SAT' : '';
            sbFilter.textContent = (MODE_LABELS[name] || '// NORMAL') + satSuffix;
        }

        OW_HUD.addAlert(`VISUAL MODE → ${name.toUpperCase()}`, 'info');
    }

    return { init, setFilter };
})();
