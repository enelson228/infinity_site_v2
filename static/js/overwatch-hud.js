/* ============================================
   OVERWATCH HUD — DOM Readouts
   Coords · UTC clock · alert ticker · counts
   ============================================ */

window.OW_HUD = (function () {
    'use strict';

    let viewer = null;

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
                _showFlightDetail(picked.id);
                picked.id.label.show = true;
            } else {
                _clearFlightDetail();
                const aircraftMap = OW_Render.getAircraftMap();
                for (const rec of aircraftMap.values()) {
                    rec.entity.label.show = false;
                }
            }
        }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

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
        set('stat-traffic',   window.OW.trafficCount   || 0);
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
    function _showFlightDetail(entity) {
        const panel = document.getElementById('flight-detail');
        if (!panel) return;

        const map = OW_Render.getAircraftMap();
        const key = entity.id.replace('aircraft_', '');
        const rec = map.get(key);
        if (!rec) return;

        const f = rec.flight;
        panel.innerHTML = [
            _fr('CALLSIGN', f.callsign),
            _fr('ICAO24',   f.icao24.toUpperCase()),
            _fr('ALT',      `${Math.round(f.alt_m)} m`),
            _fr('SPEED',    `${Math.round(f.velocity * 1.944)} kt`),
            _fr('HEADING',  `${Math.round(f.heading)}°`),
            _fr('V/RATE',   `${f.vertRate > 0 ? '+' : ''}${Math.round(f.vertRate)} m/s`),
            _fr('COUNTRY',  f.country || '--'),
        ].join('');
    }

    function _clearFlightDetail() {
        const panel = document.getElementById('flight-detail');
        if (panel) panel.innerHTML = '<div class="ow-no-selection">HOVER AIRCRAFT<br>TO INSPECT</div>';
    }

    function _fr(key, val) {
        return `<div class="ow-flight-row"><span class="fkey">${key}</span><span class="fval">${_escHtml(String(val))}</span></div>`;
    }

    function _escHtml(s) {
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    return { init, updateCoords, updateCounts, addAlert };
})();
