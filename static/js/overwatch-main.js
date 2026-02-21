/* ============================================
   OVERWATCH Main — Config + CesiumJS Init
   ============================================

   SETUP STEPS:
   1. Get a free Cesium Ion token at https://cesium.com/ion/signup
      → My Tokens → copy Default Token → paste below
   2. (Optional) Set OPENSKY_USER / OPENSKY_PASS for more API credits
      https://opensky-network.org — free registration
   3. (Optional) Replace CCTV_STREAMS urls with real .m3u8 HLS streams
      Tips: Windy.com traffic cams, NYC DOT 511ny.org/cameras
            Open cam page → DevTools (F12) → Network tab → filter ".m3u8"
   ============================================ */

// ── Configuration ──────────────────────────────────────────────────────────

const CESIUM_ION_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI3NmJiMzA2ZC0xZTY0LTRmY2ItOTc0OS01ZWM2MTFkZTc2MmIiLCJpZCI6MzkyNjYyLCJpYXQiOjE3NzE2NTQ2NDV9.22GxjzoKKKVKKl_CeCH7eJBW07RIOkCb2KhM0SWRcUA';
//    ↑ Required for: world terrain, OSM 3D buildings, high-res imagery
//      Without a valid token the globe still works with basic imagery.

const CENTER = { lat: 40.7128, lon: -74.006, alt: 8000 };
//             ↑ New York City — default; overridden by localStorage on load

const BBOX = 0.3;
//           ↑ Degrees radius for flight/road queries (~33 km at NYC lat)

const OPENSKY_USER = '';
const OPENSKY_PASS = '';
//                   ↑ Optional — leave empty for anonymous (400 credits/day)

const CCTV_STREAMS = [
    {
        label: 'CAM-01 / BROADWAY',
        url:   '',   // ← paste .m3u8 URL here
    },
    {
        label: 'CAM-02 / HARBOR',
        url:   '',   // ← paste .m3u8 URL here
    },
    {
        label: 'CAM-03 / MIDTOWN',
        url:   '',   // ← paste .m3u8 URL here
    },
];

// Flight polling interval (minimum 10 s per OpenSky ToS; anonymous = 10 s)
const FLIGHT_POLL_MS = 15000;

// ── Preset city list ────────────────────────────────────────────────────────
const PRESET_CITIES = [
    { key: 'NYC', label: 'NEW YORK',    lat: 40.7128, lon:  -74.0060, alt: 8000 },
    { key: 'LAX', label: 'LOS ANGELES', lat: 34.0522, lon: -118.2437, alt: 8000 },
    { key: 'LHR', label: 'LONDON',      lat: 51.5074, lon:   -0.1278, alt: 9000 },
    { key: 'TYO', label: 'TOKYO',       lat: 35.6762, lon:  139.6503, alt: 8000 },
    { key: 'SYD', label: 'SYDNEY',      lat:-33.8688, lon:  151.2093, alt: 8000 },
    { key: 'CDG', label: 'PARIS',       lat: 48.8566, lon:    2.3522, alt: 8000 },
    { key: 'DXB', label: 'DUBAI',       lat: 25.2048, lon:   55.2708, alt: 8000 },
    { key: 'SIN', label: 'SINGAPORE',   lat:  1.3521, lon:  103.8198, alt: 8000 },
    { key: 'CUSTOM', label: 'CUSTOM',   lat: null,    lon: null,      alt: 8000 },
];

// ── Shared state namespace ──────────────────────────────────────────────────
window.OW = {
    viewer:         null,
    center:         { ...CENTER },
    bbox:           BBOX,
    openskyCreds:   { user: OPENSKY_USER, pass: OPENSKY_PASS },
    filterMode:     'normal',
    satMode:        false,
    aircraftCount:  0,
    satelliteCount: 0,
    trafficCount:   0,
};

// ── Imagery provider instances ──────────────────────────────────────────────
let _cartoProvider = null;
let _esriProvider  = null;

function _buildCartoProvider() {
    return new Cesium.UrlTemplateImageryProvider({
        url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        subdomains: ['a', 'b', 'c', 'd'],
        maximumLevel: 19,
        credit: new Cesium.Credit('© CARTO © OpenStreetMap contributors', false),
    });
}

function _buildEsriProvider() {
    return new Cesium.UrlTemplateImageryProvider({
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        maximumLevel: 19,
        credit: new Cesium.Credit('© Esri, DigitalGlobe, GeoEye', false),
    });
}

// ── Main Async Init ─────────────────────────────────────────────────────────
(async function initOverwatch() {
    // Token — warn in console if placeholder still set
    if (CESIUM_ION_TOKEN === 'PASTE_TOKEN_HERE') {
        console.warn(
            '[OW] No Cesium Ion token set.\n' +
            '     Sign up free at https://cesium.com/ion/signup\n' +
            '     then paste your token in overwatch-main.js → CESIUM_ION_TOKEN'
        );
    }
    Cesium.Ion.defaultAccessToken = CESIUM_ION_TOKEN;

    // ── Cesium Viewer ──
    const viewer = new Cesium.Viewer('cesium-container', {
        terrain: Cesium.Terrain.fromWorldTerrain({
            requestWaterMask:     false,
            requestVertexNormals: false,
        }),
        animation:                            false,
        baseLayerPicker:                      false,
        fullscreenButton:                     false,
        geocoder:                             false,
        homeButton:                           false,
        infoBox:                              false,
        sceneModePicker:                      false,
        selectionIndicator:                   false,
        timeline:                             false,
        navigationHelpButton:                 false,
        navigationInstructionsInitiallyVisible: false,
        orderIndependentTranslucency:         true,
        requestRenderMode:                    false, // keep rendering for animations
    });

    window.OW.viewer = viewer;

    // ── Imagery: CartoDB dark (default) ──
    _cartoProvider = _buildCartoProvider();
    viewer.imageryLayers.removeAll();
    viewer.imageryLayers.addImageryProvider(_cartoProvider);

    // ── Scene appearance ──
    viewer.scene.backgroundColor =
        new Cesium.Color(0.05, 0.065, 0.09, 1.0); // near-black slate
    viewer.scene.globe.enableLighting        = false; // disable sun lighting — dark map looks better unlit
    viewer.scene.globe.showGroundAtmosphere  = false;
    viewer.scene.skyAtmosphere.show          = false;
    viewer.scene.skyBox.show                 = false;
    viewer.scene.sun.show                    = false;
    viewer.scene.moon.show                   = false;

    // Dark base color shown while tiles load
    viewer.scene.globe.baseColor =
        Cesium.Color.fromCssColorString('#0d1117');

    // ── OSM 3D Buildings (requires valid Ion token) ──
    try {
        const osmBuildings = await Cesium.createOsmBuildingsAsync();
        // Subtle tint to match slate palette
        osmBuildings.style = new Cesium.Cesium3DTileStyle({
            // Slightly lighter than the dark base so buildings read clearly
            color: 'color("#2a3350", 0.9)',
        });
        viewer.scene.primitives.add(osmBuildings);
    } catch (e) {
        console.info('[OW] OSM buildings unavailable (needs valid Ion token):', e.message);
    }

    // ── Wire modules ──
    OW_Filters.init(viewer);
    OW_HUD.init(viewer);
    OW_Render.init(viewer);
    OW_Geo.init(viewer);

    // ── Location + SAT mode (reads localStorage, must run before flyTo) ──
    _initLocationSwitcher(viewer);
    _initSatMode(viewer);

    // ── Fly to center city (uses window.OW.center, possibly restored) ──
    viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(
            window.OW.center.lon, window.OW.center.lat, window.OW.center.alt
        ),
        orientation: {
            heading: Cesium.Math.toRadians(0),
            pitch:   Cesium.Math.toRadians(-45),
            roll:    0,
        },
        duration: 2.5,
    });

    // ── CCTV streams ──
    _initCCTV(CCTV_STREAMS);

    // Apply configured labels to CCTV panels
    CCTV_STREAMS.forEach((cam, i) => {
        const el = document.getElementById(`cctv-label-${i}`);
        if (el) el.textContent = cam.label;
    });

    // ── Start data feeds (stagger to avoid thundering herd) ──
    OW_Data.startFlightPolling(FLIGHT_POLL_MS);

    setTimeout(() => OW_Data.fetchSatellites(), 500);

    setTimeout(() => OW_Data.fetchRoads(), 1500);

    // ── Boot alerts ──
    OW_HUD.addAlert('OVERWATCH ONLINE — ALL SENSOR SYSTEMS NOMINAL', 'info');
    OW_HUD.addAlert(
        `TRACKING AREA: ${window.OW.center.lat.toFixed(4)}° ${window.OW.center.lon.toFixed(4)}° ±${BBOX}°`,
        'info'
    );
    if (CESIUM_ION_TOKEN === 'PASTE_TOKEN_HERE') {
        OW_HUD.addAlert('WARNING: NO CESIUM ION TOKEN — LIMITED TERRAIN/IMAGERY', 'warn');
    }

})().catch(err => {
    console.error('[OW] Fatal init error:', err);
    OW_HUD.addAlert(`INIT FAILURE: ${err.message}`, 'error');
});

// ── Location Switcher ───────────────────────────────────────────────────────
function _initLocationSwitcher(viewer) {
    // Restore saved location
    try {
        const saved = localStorage.getItem('ow_location');
        if (saved) {
            const city = JSON.parse(saved);
            if (city && typeof city.lat === 'number' && typeof city.lon === 'number') {
                window.OW.center = { lat: city.lat, lon: city.lon, alt: city.alt || 8000 };
                _updateLocDisplay(city.label || 'CUSTOM', city.lat, city.lon);
                // Sync the select element
                const sel = document.getElementById('loc-select');
                if (sel && city.key) {
                    sel.value = city.key;
                    if (city.key === 'CUSTOM') {
                        const custom = document.getElementById('loc-custom');
                        if (custom) custom.style.display = 'flex';
                    }
                }
            }
        }
    } catch (_) {}

    // Select change → show/hide custom inputs
    const locSelect = document.getElementById('loc-select');
    if (locSelect) {
        locSelect.addEventListener('change', () => {
            const customDiv = document.getElementById('loc-custom');
            if (customDiv) {
                customDiv.style.display = locSelect.value === 'CUSTOM' ? 'flex' : 'none';
            }
        });
    }

    // Set Location button
    const setBtn = document.getElementById('loc-set-btn');
    if (setBtn) {
        setBtn.addEventListener('click', () => {
            const sel = document.getElementById('loc-select');
            if (!sel) return;
            const key = sel.value;

            let city;
            if (key === 'CUSTOM') {
                const latInput = document.getElementById('loc-lat');
                const lonInput = document.getElementById('loc-lon');
                const lat = parseFloat(latInput?.value);
                const lon = parseFloat(lonInput?.value);

                if (isNaN(lat) || isNaN(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
                    OW_HUD.addAlert('INVALID COORDINATES — LAT ±90 / LON ±180', 'error');
                    return;
                }
                city = { key: 'CUSTOM', label: 'CUSTOM', lat, lon, alt: 8000 };
            } else {
                city = PRESET_CITIES.find(c => c.key === key);
                if (!city) return;
            }

            window.OW.center = { lat: city.lat, lon: city.lon, alt: city.alt };

            viewer.camera.flyTo({
                destination: Cesium.Cartesian3.fromDegrees(city.lon, city.lat, city.alt),
                orientation: {
                    heading: Cesium.Math.toRadians(0),
                    pitch:   Cesium.Math.toRadians(-45),
                    roll:    0,
                },
                duration: 2.0,
            });

            localStorage.setItem('ow_location', JSON.stringify(city));
            _updateLocDisplay(city.label, city.lat, city.lon);
            OW_HUD.addAlert(`LOCATION → ${city.label} (${city.lat.toFixed(4)}°, ${city.lon.toFixed(4)}°)`, 'info');
            OW_Data.fetchRoads();
        });
    }
}

function _updateLocDisplay(label, lat, lon) {
    const el = document.getElementById('loc-display');
    if (el) {
        el.textContent = `${label} — ${lat.toFixed(4)}° / ${lon.toFixed(4)}°`;
    }
}

// ── SAT Imagery Mode ────────────────────────────────────────────────────────
function _initSatMode(viewer) {
    // Restore saved state
    try {
        if (localStorage.getItem('ow_satmode') === 'true') {
            _applySatMode(viewer, true);
        }
    } catch (_) {}

    // Button click
    const satBtn = document.querySelector('[data-filter="sat"]');
    if (satBtn) {
        satBtn.addEventListener('click', () => _applySatMode(viewer, !window.OW.satMode));
    }

    // Keyboard shortcut: '4'
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.key === '4') _applySatMode(viewer, !window.OW.satMode);
    });
}

function _applySatMode(viewer, enabled) {
    window.OW.satMode = enabled;
    viewer.imageryLayers.removeAll();

    if (enabled) {
        if (!_esriProvider) _esriProvider = _buildEsriProvider();
        viewer.imageryLayers.addImageryProvider(_esriProvider);
    } else {
        if (!_cartoProvider) _cartoProvider = _buildCartoProvider();
        viewer.imageryLayers.addImageryProvider(_cartoProvider);
    }

    document.querySelector('[data-filter="sat"]')?.classList.toggle('active', enabled);

    try { localStorage.setItem('ow_satmode', String(enabled)); } catch (_) {}

    // Re-trigger setFilter so the status bar suffix updates
    OW_Filters.setFilter(window.OW.filterMode || 'normal');

    OW_HUD.addAlert(`IMAGERY → ${enabled ? 'SATELLITE (ESRI)' : 'DARK (CARTO)'}`, 'info');
}

// ── CCTV HLS Stream Init ────────────────────────────────────────────────────
function _initCCTV(streams) {
    let activeCount = 0;

    streams.forEach((cam, i) => {
        const video = document.getElementById(`video-${i}`);
        const nosig = document.getElementById(`nosig-${i}`);
        if (!video || !nosig) return;

        if (!cam.url) {
            // No URL configured — show NO SIGNAL (default state is already shown)
            return;
        }

        function showSignal() {
            nosig.classList.add('hidden');
            video.style.display = 'block';
            activeCount++;
            document.getElementById('stat-cctv').textContent = activeCount;

            // Update the CCTV sys indicator dot to green
            const dot = document.getElementById('dot-cctv');
            if (dot) {
                dot.classList.remove('dot-red', 'dot-amber');
                dot.classList.add('dot-green');
            }
        }

        function showNoSignal() {
            nosig.classList.remove('hidden');
            video.style.display = 'none';
        }

        if (typeof Hls !== 'undefined' && Hls.isSupported()) {
            const hls = new Hls({
                enableWorker:    true,
                lowLatencyMode:  true,
                backBufferLength: 30,
                maxBufferLength: 15,
            });

            hls.on(Hls.Events.MANIFEST_PARSED, () => {
                video.play().catch(() => {});
                showSignal();
            });

            hls.on(Hls.Events.ERROR, (_evt, data) => {
                if (data.fatal) { showNoSignal(); hls.destroy(); }
            });

            hls.loadSource(cam.url);
            hls.attachMedia(video);

        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
            // Native HLS (Safari / iOS)
            video.src = cam.url;
            video.addEventListener('loadedmetadata', () => {
                video.play().catch(() => {});
                showSignal();
            });
            video.addEventListener('error', showNoSignal);

        } else {
            showNoSignal();
        }
    });
}
