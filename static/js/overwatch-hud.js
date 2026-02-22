/* ============================================
   OVERWATCH HUD — DOM Readouts
   Coords · UTC clock · alert ticker · counts
   ============================================ */

window.OW_HUD = (function () {
    'use strict';

    let viewer = null;
    let tooltipEl = null;
    let trackedAircraftId = null;
    let activePanelId = null;

    // ── Rotating ambient alert messages ──
    const AMBIENT_ALERTS = [
        'RADAR SWEEP COMPLETE — SECTOR NOMINAL',
        'GPS CONSTELLATION LOCK CONFIRMED — 24 VEHICLES ACTIVE',
        'THREAT ASSESSMENT: MINIMAL — ALL VECTORS CLEAR',
        'UNSC DATALINK STABLE — UPLINK AT 99.4%',
        'ORBITAL MECHANICS NOMINAL — PROPAGATION ACTIVE',
        'FLIGHT CORRIDOR MONITORING ENABLED',
        'SENSOR FUSION PIPELINE: OPERATIONAL',
        'STARLINK MEGACONSTELLATION — LOW-LATENCY COVERAGE',
        'ISS ORBITAL VELOCITY: ~7.66 km/s',
        'GEOFENCE PERIMETER INTACT — NO INTRUSIONS',
        'OPEN FLIGHT DATA COURTESY OF OPENSKY NETWORK',
        'TLE DATA COURTESY OF CELESTRAK — LAST REFRESH < 6 MIN',
    ];
    let ambientIdx = 0;

    function init(v) {
        viewer = v;
        tooltipEl = document.getElementById('flight-tooltip');
        if (!tooltipEl) {
            tooltipEl = document.createElement('div');
            tooltipEl.id = 'flight-tooltip';
            tooltipEl.className = 'ow-flight-tooltip hidden';
            document.body.appendChild(tooltipEl);
        }

        // UTC clock
        _updateClock();
        setInterval(_updateClock, 1000);

        // Single MOUSE_MOVE handler — coords + aircraft hover (two handlers on same
        // event type would overwrite each other in Cesium's ScreenSpaceEventHandler)
        const handler = new Cesium.ScreenSpaceEventHandler(viewer.canvas);
        handler.setInputAction(evt => {
            // ── Coordinate readout ──
            const ellipsoid = viewer.scene.globe.ellipsoid;
            const cart3     = viewer.camera.pickEllipsoid(evt.endPosition, ellipsoid);
            if (cart3) {
                const carto = Cesium.Cartographic.fromCartesian(cart3);
                updateCoords(
                    Cesium.Math.toDegrees(carto.latitude),
                    Cesium.Math.toDegrees(carto.longitude),
                    carto.height
                );
            }

            // ── Aircraft hover — label + detail panel ──
            const picked = viewer.scene.pick(evt.endPosition);
            if (Cesium.defined(picked) && picked.id && picked.id.id &&
                picked.id.id.startsWith('aircraft_')) {
                _showFlightTooltip(picked.id, evt.endPosition);
                picked.id.label.show = true;
            } else {
                _hideFlightTooltip();
                const aircraftMap = OW_Render.getAircraftMap();
                for (const rec of aircraftMap.values()) {
                    rec.entity.label.show = false;
                }
            }
        }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

        handler.setInputAction(evt => {
            const picked = viewer.scene.pick(evt.position);
            if (Cesium.defined(picked) && picked.id && picked.id.id &&
                picked.id.id.startsWith('aircraft_')) {
                _trackAircraft(picked.id);
                _setActivePanel(picked.id);
            } else {
                _trackAircraft(null);
                _setActivePanel(null);
            }
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

        // Ambient alert ticker — every 14 s
        setInterval(() => {
            addAlert(AMBIENT_ALERTS[ambientIdx % AMBIENT_ALERTS.length], 'info');
            ambientIdx++;
        }, 14000);

        // Hide the Cesium loading overlay once the globe renders a frame
        const loadingEl = document.getElementById('cesium-loading');
        if (loadingEl) {
            const removeOnce = viewer.scene.postRender.addEventListener(() => {
                loadingEl.classList.add('hidden');
                setTimeout(() => loadingEl.remove(), 700);
                removeOnce();
            });
        }
    }

    // ── UTC Clock ──
    function _updateClock() {
        const now = new Date();
        const pad = n => String(n).padStart(2, '0');
        const el  = document.getElementById('sb-clock');
        if (el) el.textContent =
            `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())} UTC`;
    }

    // ── Coordinate readout ──
    function updateCoords(lat, lon, alt) {
        const coordEl = document.getElementById('sb-coords');
        const altEl   = document.getElementById('sb-alt');

        if (coordEl) {
            const latStr = `${Math.abs(lat).toFixed(4)}°${lat >= 0 ? 'N' : 'S'}`;
            const lonStr = `${Math.abs(lon).toFixed(4)}°${lon >= 0 ? 'E' : 'W'}`;
            coordEl.textContent = `${latStr}  ${lonStr}`;
        }
        if (altEl) {
            altEl.textContent = alt > 1 ? `${Math.round(alt)}m` : '0m';
        }
    }

    // ── Entity count badges ──
    function updateCounts() {
        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        set('stat-aircraft',  window.OW.aircraftCount  || 0);
        set('stat-satellites', window.OW.satelliteCount || 0);
        set('sb-aircraft',    window.OW.aircraftCount  || 0);
    }

    // ── Alert log ──
    function addAlert(msg, type) {
        type = type || 'info';
        const logEl = document.getElementById('alert-log');
        if (!logEl) return;

        const now = new Date();
        const pad = n => String(n).padStart(2, '0');
        const ts  = `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}Z`;

        const entry = document.createElement('div');
        entry.className = `ow-alert-entry alert-${type}`;
        entry.innerHTML =
            `<span class="ow-alert-time">[${ts}]</span>` +
            `<span class="ow-alert-msg"> ${_escHtml(msg)}</span>`;

        logEl.insertBefore(entry, logEl.firstChild); // newest on top

        // Cap at 60 entries
        while (logEl.children.length > 60) {
            logEl.removeChild(logEl.lastChild);
        }
    }

    // ── Flight detail panel ──
    function _showFlightTooltip(entity, screenPos) {
        if (!tooltipEl) return;
        const map = OW_Render.getAircraftMap();
        const key = entity.id.replace('aircraft_', '');
        const rec = map.get(key);
        if (!rec) return _hideFlightTooltip();

        const f = rec.flight;
        const latStr = f.lat != null ? `${f.lat.toFixed(4)}°` : '--';
        const lonStr = f.lon != null ? `${f.lon.toFixed(4)}°` : '--';
        const callsign = (f.callsign || '').toUpperCase();
        const squawk = (f.squawk || '').toUpperCase();
        tooltipEl.innerHTML = [
            _fr('CALLSIGN', callsign || f.icao24.toUpperCase()),
            _fr('ICAO24',   f.icao24.toUpperCase()),
            _fr('COUNTRY',  (f.country || '--').toUpperCase()),
            _fr('LAT',      latStr),
            _fr('LON',      lonStr),
            _fr('ALT',      `${Math.round(f.alt_m)} m`),
            _fr('SPEED',    `${Math.round(f.velocity * 1.944)} KT`),
            _fr('HEADING',  `${Math.round(f.heading)}°`),
            _fr('V/RATE',   `${f.vertRate > 0 ? '+' : ''}${Math.round(f.vertRate)} M/S`),
            _fr('SQUAWK',   squawk || '--'),
            _fr('ON GND',   f.onGround ? 'YES' : 'NO'),
        ].join('');

        tooltipEl.classList.remove('hidden');

        const pad = 12;
        const offset = 14;
        let x = screenPos.x + offset;
        let y = screenPos.y + offset;
        const w = tooltipEl.offsetWidth;
        const h = tooltipEl.offsetHeight;
        const maxX = window.innerWidth - w - pad;
        const maxY = window.innerHeight - h - pad;
        x = Math.max(pad, Math.min(x, maxX));
        y = Math.max(pad, Math.min(y, maxY));
        tooltipEl.style.transform = `translate(${x}px, ${y}px)`;
    }

    function _hideFlightTooltip() {
        if (!tooltipEl) return;
        tooltipEl.classList.add('hidden');
        tooltipEl.style.transform = 'translate(-9999px, -9999px)';
    }

    function _trackAircraft(entity) {
        if (!entity) {
            trackedAircraftId = null;
            if (window.OW_Render && typeof OW_Render.setTrackedAircraft === 'function') {
                OW_Render.setTrackedAircraft(null);
            }
            return;
        }

        trackedAircraftId = entity.id;
        const icao = entity.id.replace('aircraft_', '');
        if (window.OW_Render && typeof OW_Render.setTrackedAircraft === 'function') {
            OW_Render.setTrackedAircraft(icao);
        }
        addAlert(`TRACK: ${entity.name || entity.id}`, 'info');
    }

    function _setActivePanel(entity) {
        const panel = document.getElementById('flight-detail');
        if (!panel) return;

        if (!entity) {
            activePanelId = null;
            panel.innerHTML = '<div class="ow-no-selection">CLICK AIRCRAFT<br>TO LOCK DETAILS</div>';
            return;
        }

        activePanelId = entity.id;
        const map = OW_Render.getAircraftMap();
        const key = entity.id.replace('aircraft_', '');
        const rec = map.get(key);
        if (!rec) return;

        const f = rec.flight;
        const latStr = f.lat != null ? `${f.lat.toFixed(4)}°` : '--';
        const lonStr = f.lon != null ? `${f.lon.toFixed(4)}°` : '--';
        const callsign = (f.callsign || '').toUpperCase();
        const squawk = (f.squawk || '').toUpperCase();
        panel.innerHTML = [
            _fr('CALLSIGN', callsign || f.icao24.toUpperCase()),
            _fr('ICAO24',   f.icao24.toUpperCase()),
            _fr('COUNTRY',  (f.country || '--').toUpperCase()),
            _fr('LAT',      latStr),
            _fr('LON',      lonStr),
            _fr('ALT',      `${Math.round(f.alt_m)} m`),
            _fr('SPEED',    `${Math.round(f.velocity * 1.944)} KT`),
            _fr('HEADING',  `${Math.round(f.heading)}°`),
            _fr('V/RATE',   `${f.vertRate > 0 ? '+' : ''}${Math.round(f.vertRate)} M/S`),
            _fr('SQUAWK',   squawk || '--'),
            _fr('ON GND',   f.onGround ? 'YES' : 'NO'),
        ].join('');
    }

    function refreshActivePanel() {
        if (!activePanelId) return;
        const ent = viewer.entities.getById(activePanelId);
        if (ent) _setActivePanel(ent);
    }

    function _fr(key, val) {
        return `<div class="ow-flight-row"><span class="fkey">${key}</span><span class="fval">${_escHtml(String(val))}</span></div>`;
    }

    function _escHtml(s) {
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    return { init, updateCoords, updateCounts, addAlert, refreshActivePanel };
})();
