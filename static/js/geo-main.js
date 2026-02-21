/* ============================================
   GEO — 2D Tactical Street Map (Leaflet)
   New York Metro Area
   ============================================ */
'use strict';

// ── Config ─────────────────────────────────────────────────────────────────
const GEO_CENTER   = [40.7128, -74.006]; // NYC lat/lon
const GEO_ZOOM     = 11;
const GEO_BBOX     = 0.45;               // degrees radius for queries
const POLL_MS      = 15000;              // OpenSky refresh interval

// CCTV camera positions — update lat/lon to match your actual camera locations
// URL is optional (just for the detail panel link, not for streaming here)
const GEO_CAMERAS = [
    { label: 'CAM-01 / BROADWAY',  lat: 40.7580, lon: -73.9855, url: '' },
    { label: 'CAM-02 / HARBOR',    lat: 40.6892, lon: -74.0445, url: '' },
    { label: 'CAM-03 / MIDTOWN',   lat: 40.7549, lon: -73.9840, url: '' },
];

// Geofence zones shown on the map (adjust as desired)
const GEO_ZONES = [
    {
        label: 'JFK APPROACH',
        color: '#f6a623',
        coords: [[40.56, -73.85], [40.56, -73.65], [40.70, -73.65], [40.70, -73.85]],
    },
    {
        label: 'LAGUARDIA APPROACH',
        color: '#22d3ee',
        coords: [[40.75, -73.92], [40.75, -73.82], [40.82, -73.82], [40.82, -73.92]],
    },
    {
        label: 'HUDSON CORRIDOR',
        color: '#4ade80',
        coords: [[40.64, -74.08], [40.64, -74.01], [40.88, -74.01], [40.88, -74.08]],
    },
];

// ── Tile layers ─────────────────────────────────────────────────────────────
const TILE_LAYERS = {
    osm: {
        url:   'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        opts:  { attribution: '© OpenStreetMap contributors', maxZoom: 19 },
    },
    dark: {
        url:   'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        opts:  { attribution: '© CARTO © OpenStreetMap contributors', maxZoom: 19, subdomains: 'abcd' },
    },
    satellite: {
        url:   'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        opts:  { attribution: '© Esri', maxZoom: 18 },
    },
    topo: {
        url:   'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
        opts:  { attribution: '© OpenTopoMap contributors', maxZoom: 17 },
    },
};

// ── State ───────────────────────────────────────────────────────────────────
let map          = null;
let tileLayer    = null;
let aircraftLayer = null;  // MarkerClusterGroup
let satLayer     = null;   // LayerGroup
let cameraLayer  = null;   // LayerGroup
let zonesLayer   = null;   // LayerGroup
let satEntities  = [];     // [{ name, tle1, tle2, marker, trackLine }]
let refreshTimer = null;
let countdown    = POLL_MS / 1000;

const layerVisible = { aircraft: true, satellites: true, cameras: true, zones: true };

// ── Init ────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initMap();
    initLayers();
    initUI();
    addZones();
    addCameras();

    fetchFlights();
    fetchSatellites();

    refreshTimer = setInterval(() => {
        fetchFlights();
        countdown = POLL_MS / 1000;
    }, POLL_MS);

    // Countdown ticker
    setInterval(() => {
        countdown = Math.max(0, countdown - 1);
        const el = document.getElementById('g-refresh');
        if (el) el.textContent = countdown + 's';
    }, 1000);

    // UTC clock
    setInterval(updateClock, 1000);
    updateClock();
});

function initMap() {
    map = L.map('geo-map', {
        center: GEO_CENTER,
        zoom:   GEO_ZOOM,
        zoomControl: true,
        attributionControl: true,
    });

    // Default: OSM street map
    const t = TILE_LAYERS.osm;
    tileLayer = L.tileLayer(t.url, t.opts).addTo(map);

    // Cursor coordinates
    map.on('mousemove', (e) => {
        const el = document.getElementById('g-cursor');
        if (el) {
            const lat = e.latlng.lat.toFixed(4);
            const lon = e.latlng.lng.toFixed(4);
            el.textContent = `${Math.abs(lat)}°${lat >= 0 ? 'N' : 'S'}  ${Math.abs(lon)}°${lon >= 0 ? 'E' : 'W'}`;
        }
    });

    // Zoom level
    map.on('zoomend', () => {
        const el = document.getElementById('g-zoom');
        if (el) el.textContent = map.getZoom();
    });
    document.getElementById('g-zoom').textContent = GEO_ZOOM;

    // Close detail panel on map click
    map.on('click', () => {
        document.getElementById('geo-detail').style.display = 'none';
    });
}

function initLayers() {
    aircraftLayer = L.markerClusterGroup({
        maxClusterRadius: 40,
        disableClusteringAtZoom: 12,
        spiderfyOnMaxZoom: true,
    });
    satLayer    = L.layerGroup();
    cameraLayer = L.layerGroup();
    zonesLayer  = L.layerGroup();

    map.addLayer(aircraftLayer);
    map.addLayer(satLayer);
    map.addLayer(cameraLayer);
    map.addLayer(zonesLayer);
}

// ── UI wiring ───────────────────────────────────────────────────────────────
function initUI() {
    // Layer toggles
    document.querySelectorAll('.geo-toggle-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const key = btn.dataset.layer;
            layerVisible[key] = !layerVisible[key];
            btn.classList.toggle('active', layerVisible[key]);

            const layerMap = {
                aircraft:   aircraftLayer,
                satellites: satLayer,
                cameras:    cameraLayer,
                zones:      zonesLayer,
            };
            const lyr = layerMap[key];
            if (!lyr) return;
            if (layerVisible[key]) map.addLayer(lyr);
            else                   map.removeLayer(lyr);
        });
    });

    // Map style switcher
    document.getElementById('geo-style-select').addEventListener('change', (e) => {
        const t = TILE_LAYERS[e.target.value];
        if (!t) return;
        map.removeLayer(tileLayer);
        tileLayer = L.tileLayer(t.url, t.opts).addTo(map);
        tileLayer.bringToBack();
    });

    // Detail panel close
    document.getElementById('geo-detail-close').addEventListener('click', () => {
        document.getElementById('geo-detail').style.display = 'none';
    });
}

// ── Aircraft markers ─────────────────────────────────────────────────────────
const aircraftMarkers = new Map(); // icao24 → marker

async function fetchFlights() {
    const [lat, lon] = GEO_CENTER;
    const r = GEO_BBOX;
    const url = `https://opensky-network.org/api/states/all` +
        `?lamin=${lat - r}&lomin=${lon - r}&lamax=${lat + r}&lomax=${lon + r}`;

    try {
        const resp = await fetch(url, { cache: 'no-store' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        const flights = (data.states || [])
            .map(s => ({
                icao24:   s[0],
                callsign: (s[1] || '').trim() || s[0].toUpperCase(),
                lon:      s[5],
                lat:      s[6],
                alt_m:    s[13] != null ? s[13] : (s[7] || 0),
                heading:  s[10] || 0,
                velocity: s[9]  || 0,
                vertRate: s[11] || 0,
                country:  s[2]  || '--',
            }))
            .filter(f => f.lat != null && f.lon != null && !s8(data.states, f.icao24));

        updateAircraftMarkers(flights);
        const el = document.getElementById('g-aircraft-count');
        if (el) el.textContent = flights.length;
        setTicker(`OPENSKY UPDATED — ${flights.length} AIRCRAFT IN SECTOR`);

    } catch (e) {
        console.warn('[GEO] OpenSky failed:', e.message);
        setTicker('OPENSKY FETCH FAILED — RETRYING IN ' + POLL_MS / 1000 + 's');
    }
}

// Helper: check onGround flag from raw state array
function s8(states, icao24) {
    const s = (states || []).find(x => x[0] === icao24);
    return s ? !!s[8] : false;
}

function updateAircraftMarkers(flights) {
    const seen = new Set();

    for (const f of flights) {
        seen.add(f.icao24);

        // Rotate aircraft SVG icon by heading
        const icon = L.divIcon({
            className: '',
            html: `<div class="geo-aircraft-icon" style="transform:rotate(${f.heading}deg)">
                     <svg width="18" height="18" viewBox="0 0 24 24" fill="#f6a623">
                       <path d="M12 2L8 10H4l4 4-1 6 5-3 5 3-1-6 4-4h-4z"/>
                     </svg>
                   </div>`,
            iconSize:   [18, 18],
            iconAnchor: [9, 9],
        });

        if (aircraftMarkers.has(f.icao24)) {
            const m = aircraftMarkers.get(f.icao24);
            m.setLatLng([f.lat, f.lon]);
            m.setIcon(icon);
            m._geoFlight = f;
        } else {
            const m = L.marker([f.lat, f.lon], { icon });
            m._geoFlight = f;
            m.on('click', (e) => {
                L.DomEvent.stopPropagation(e);
                showFlightDetail(m._geoFlight);
            });
            aircraftLayer.addLayer(m);
            aircraftMarkers.set(f.icao24, m);
        }
    }

    // Remove departed
    for (const [icao, m] of aircraftMarkers) {
        if (!seen.has(icao)) {
            aircraftLayer.removeLayer(m);
            aircraftMarkers.delete(icao);
        }
    }
}

function showFlightDetail(f) {
    document.getElementById('geo-detail-title').textContent = `// ${f.callsign}`;
    document.getElementById('geo-detail-body').innerHTML = [
        dr('ICAO24',   f.icao24.toUpperCase()),
        dr('CALLSIGN', f.callsign),
        dr('ALTITUDE', `${Math.round(f.alt_m)} m / ${Math.round(f.alt_m * 3.281)} ft`),
        dr('SPEED',    `${Math.round(f.velocity * 1.944)} kt`),
        dr('HEADING',  `${Math.round(f.heading)}°`),
        dr('V/RATE',   `${f.vertRate > 0 ? '+' : ''}${Math.round(f.vertRate)} m/s`),
        dr('COUNTRY',  f.country),
        dr('POSITION', `${f.lat.toFixed(4)}°, ${f.lon.toFixed(4)}°`),
    ].join('');
    document.getElementById('geo-detail').style.display = 'block';
}

// ── Satellites ───────────────────────────────────────────────────────────────
async function fetchSatellites() {
    try {
        const [r1, r2] = await Promise.all([
            fetch('/api/tle?group=stations'),
            fetch('/api/tle?group=visual'),
        ]);
        const [t1, t2] = await Promise.all([r1.text(), r2.text()]);
        const tles = [...parseTLEs(t1, 'station'), ...parseTLEs(t2, 'visual').slice(0, 20)];
        renderSatellites(tles);

        const el = document.getElementById('g-sat-count');
        if (el) el.textContent = tles.length;
        setTicker(`TLE DATA LOADED — TRACKING ${tles.length} ORBITAL OBJECTS`);

        // Refresh ground tracks every 30 s
        setInterval(() => updateSatPositions(), 30000);
    } catch (e) {
        console.warn('[GEO] TLE fetch failed:', e.message);
    }
}

function parseTLEs(text, group) {
    const lines = text.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#'));
    const sats  = [];
    for (let i = 0; i < lines.length - 2; i++) {
        if (lines[i + 1].startsWith('1 ') && lines[i + 2].startsWith('2 ')) {
            sats.push({ name: lines[i].replace(/^0 /, '').trim(), tle1: lines[i + 1], tle2: lines[i + 2], group });
            i += 2;
        }
    }
    return sats;
}

function renderSatellites(tles) {
    satLayer.clearLayers();
    satEntities = [];

    for (const sat of tles) {
        const isISS  = /ISS|ZARYA/i.test(sat.name);
        const color  = sat.group === 'station' ? '#22d3ee' : '#f6a623';
        const size   = isISS ? 10 : 6;

        const pos = propagateSat(sat, new Date());
        if (!pos) continue;

        const icon = L.divIcon({
            className: '',
            html: `<div style="width:${size}px;height:${size}px;border-radius:50%;
                               background:${color};box-shadow:0 0 6px ${color};
                               border:1px solid rgba(255,255,255,0.4)"></div>`,
            iconSize:   [size, size],
            iconAnchor: [size / 2, size / 2],
        });

        const marker = L.marker([pos.lat, pos.lon], { icon });
        marker._satData = sat;

        // Ground track — compute positions over ±45 min
        const trackCoords = computeGroundTrack(sat, new Date(), 45);
        const trackLine   = L.polyline(trackCoords, {
            color,
            weight:    1,
            opacity:   0.4,
            dashArray: '4 4',
        });

        if (isISS) {
            marker.bindTooltip(sat.name, {
                permanent: true,
                className: 'geo-zone-label',
                offset:    [8, 0],
            });
        }

        marker.on('click', (e) => {
            L.DomEvent.stopPropagation(e);
            showSatDetail(sat, pos);
        });

        satLayer.addLayer(trackLine);
        satLayer.addLayer(marker);
        satEntities.push({ sat, marker, trackLine });
    }
}

function updateSatPositions() {
    const now = new Date();
    for (const rec of satEntities) {
        const pos = propagateSat(rec.sat, now);
        if (!pos) continue;
        rec.marker.setLatLng([pos.lat, pos.lon]);
        const track = computeGroundTrack(rec.sat, now, 45);
        rec.trackLine.setLatLngs(track);
    }
}

function propagateSat(sat, date) {
    try {
        const satrec = satellite.twoline2satrec(sat.tle1, sat.tle2);
        const pv     = satellite.propagate(satrec, date);
        if (!pv || !pv.position) return null;
        const gmst   = satellite.gstime(date);
        const geo    = satellite.eciToGeodetic(pv.position, gmst);
        return {
            lat:   satellite.degreesLat(geo.latitude),
            lon:   satellite.degreesLong(geo.longitude),
            altKm: Math.round(geo.height),
        };
    } catch (_) { return null; }
}

function computeGroundTrack(sat, centerDate, minuteRadius) {
    const coords  = [];
    const satrec  = satellite.twoline2satrec(sat.tle1, sat.tle2);
    const stepMin = 2;

    for (let m = -minuteRadius; m <= minuteRadius; m += stepMin) {
        const d    = new Date(centerDate.getTime() + m * 60000);
        const pv   = satellite.propagate(satrec, d);
        if (!pv || !pv.position) continue;
        const gmst = satellite.gstime(d);
        const geo  = satellite.eciToGeodetic(pv.position, gmst);
        coords.push([satellite.degreesLat(geo.latitude), satellite.degreesLong(geo.longitude)]);
    }
    return coords;
}

function showSatDetail(sat, pos) {
    document.getElementById('geo-detail-title').textContent = `// ${sat.name}`;
    document.getElementById('geo-detail-body').innerHTML = [
        dr('NAME',    sat.name),
        dr('GROUP',   sat.group.toUpperCase()),
        dr('ALT',     `${pos.altKm} km`),
        dr('LAT',     `${pos.lat.toFixed(4)}°`),
        dr('LON',     `${pos.lon.toFixed(4)}°`),
        dr('TLE1',    `<span style="font-size:0.5rem;word-break:break-all">${sat.tle1}</span>`),
        dr('TLE2',    `<span style="font-size:0.5rem;word-break:break-all">${sat.tle2}</span>`),
    ].join('');
    document.getElementById('geo-detail').style.display = 'block';
}

// ── Cameras ──────────────────────────────────────────────────────────────────
function addCameras() {
    for (const cam of GEO_CAMERAS) {
        const icon = L.divIcon({
            className: '',
            html: `<div style="position:relative;width:14px;height:14px">
                     <div style="width:10px;height:10px;border:2px solid #4ade80;
                                 border-radius:50%;position:absolute;top:2px;left:2px;
                                 background:rgba(74,222,128,0.15)"></div>
                     <div style="width:18px;height:18px;border:1px solid rgba(74,222,128,0.3);
                                 border-radius:50%;position:absolute;top:-2px;left:-2px;
                                 animation:cam-pulse 2s ease-in-out infinite"></div>
                   </div>`,
            iconSize:   [14, 14],
            iconAnchor: [7, 7],
        });

        const m = L.marker([cam.lat, cam.lon], { icon });
        m.bindTooltip(cam.label, { className: 'geo-zone-label', direction: 'right' });
        m.on('click', (e) => {
            L.DomEvent.stopPropagation(e);
            showCamDetail(cam);
        });
        cameraLayer.addLayer(m);
    }

    const el = document.getElementById('g-cam-count');
    if (el) el.textContent = GEO_CAMERAS.length;
}

function showCamDetail(cam) {
    document.getElementById('geo-detail-title').textContent = `// ${cam.label}`;
    document.getElementById('geo-detail-body').innerHTML = [
        dr('LABEL',   cam.label),
        dr('LAT',     `${cam.lat.toFixed(4)}°`),
        dr('LON',     `${cam.lon.toFixed(4)}°`),
        dr('STREAM',  cam.url ? '<span style="color:#4ade80">CONFIGURED</span>' : '<span style="color:#ef4444">NO URL SET</span>'),
        dr('STATUS',  cam.url ? '<span style="color:#4ade80">ONLINE</span>' : '<span style="color:#94a3b8">STANDBY</span>'),
    ].join('');
    document.getElementById('geo-detail').style.display = 'block';
}

// ── Geofence Zones ───────────────────────────────────────────────────────────
function addZones() {
    for (const zone of GEO_ZONES) {
        const poly = L.polygon(zone.coords, {
            color:       zone.color,
            weight:      1.5,
            opacity:     0.7,
            fillColor:   zone.color,
            fillOpacity: 0.05,
            dashArray:   '6 4',
        });

        const center = poly.getBounds().getCenter();
        const label  = L.marker(center, {
            icon: L.divIcon({
                className: 'geo-zone-label',
                html: zone.label,
                iconAnchor: [0, 0],
            }),
            interactive: false,
        });

        zonesLayer.addLayer(poly);
        zonesLayer.addLayer(label);
    }
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function dr(key, val) {
    return `<div class="geo-detail-row">
        <span class="geo-detail-key">${key}</span>
        <span class="geo-detail-val">${val}</span>
    </div>`;
}

function updateClock() {
    const now = new Date();
    const p   = n => String(n).padStart(2, '0');
    const el  = document.getElementById('g-clock');
    if (el) el.textContent = `${p(now.getUTCHours())}:${p(now.getUTCMinutes())}:${p(now.getUTCSeconds())} UTC`;
}

const TICKERS = [
    'GEOSPATIAL SYSTEMS ONLINE',
    'THREAT ASSESSMENT: MINIMAL',
    'GPS CONSTELLATION NOMINAL — 24 SVs ACTIVE',
    'UNSC DATALINK STABLE',
    'OVERWATCH SENSOR FUSION ACTIVE',
];
let tickerIdx = 0;
function setTicker(msg) {
    const el = document.getElementById('g-ticker');
    if (el) el.textContent = msg;
}
setInterval(() => {
    setTicker(TICKERS[tickerIdx % TICKERS.length]);
    tickerIdx++;
}, 10000);
