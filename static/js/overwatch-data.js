/* ============================================
   OVERWATCH Data — API Fetching Module
   OpenSky flights · Celestrak TLEs · Overpass roads
   ============================================ */

window.OW_Data = (function () {
    'use strict';

    // ────────────────────────────────────────
    // OpenSky Network — Live Flight Data
    // ────────────────────────────────────────
    async function fetchFlights() {
        const { lat, lon } = window.OW.center;
        const r = window.OW.bbox;
        const lamin = lat - r, lomin = lon - r;
        const lamax = lat + r, lomax = lon + r;
        const { user, pass } = window.OW.openskyCreds;

        const url = `https://opensky-network.org/api/states/all` +
            `?lamin=${lamin}&lomin=${lomin}&lamax=${lamax}&lomax=${lomax}`;

        const headers = {};
        if (user && pass) {
            headers['Authorization'] = 'Basic ' + btoa(`${user}:${pass}`);
        }

        try {
            const resp = await fetch(url, { headers, cache: 'no-store' });
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
                    onGround: !!s[8],
                    country:  s[2] || '',
                    squawk:   s[14] || '',
                }))
                .filter(f => f.lat != null && f.lon != null && !f.onGround);

            OW_Render.updateAircraft(flights);
            window.OW.aircraftCount = flights.length;
            OW_HUD.updateCounts();
        } catch (e) {
            console.warn('[OW] OpenSky fetch failed:', e.message);
            // Don't clear entities on transient failure
        }
    }

    function startFlightPolling(intervalMs) {
        fetchFlights(); // immediate call
        setInterval(fetchFlights, intervalMs);
    }

    // ────────────────────────────────────────
    // Celestrak — Satellite TLEs (via Flask proxy)
    // ────────────────────────────────────────
    async function fetchTLEs(group) {
        try {
            const resp = await fetch(`/api/tle?group=${encodeURIComponent(group)}`,
                { cache: 'no-store' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const text = await resp.text();
            if (text.startsWith('#')) throw new Error(text.trim());
            return parseTLEs(text);
        } catch (e) {
            console.warn(`[OW] TLE fetch failed (${group}):`, e.message);
            return [];
        }
    }

    /**
     * Parse 3-line TLE format:
     *   NAME
     *   1 NNNNN...
     *   2 NNNNN...
     */
    function parseTLEs(text) {
        const lines = text
            .split('\n')
            .map(l => l.trim())
            .filter(l => l.length > 0 && !l.startsWith('#'));

        const sats = [];
        for (let i = 0; i < lines.length - 2; i++) {
            const name = lines[i];
            const tle1 = lines[i + 1];
            const tle2 = lines[i + 2];
            if (tle1.startsWith('1 ') && tle2.startsWith('2 ')) {
                sats.push({
                    name: name.replace(/^0 /, '').trim(),
                    tle1,
                    tle2,
                });
                i += 2;
            }
        }
        return sats;
    }

    async function fetchSatellites() {
        OW_HUD.addAlert('ACQUIRING TLE DATA FROM CELESTRAK...', 'info');

        const [stations, starlink, gps] = await Promise.all([
            fetchTLEs('stations'),
            fetchTLEs('starlink'),
            fetchTLEs('gps-ops'),
        ]);

        // Limit Starlink to 40 to keep entity count manageable
        const all = [
            ...stations.map(s => ({ ...s, group: 'station' })),
            ...starlink.slice(0, 40).map(s => ({ ...s, group: 'starlink' })),
            ...gps.map(s => ({ ...s, group: 'gps' })),
        ];

        OW_Render.initSatellites(all);
        window.OW.satelliteCount = all.length;
        OW_HUD.updateCounts();
        OW_HUD.addAlert(
            `TRACKING ${all.length} ORBITAL OBJECTS ` +
            `(ISS: ${stations.length} | SL: ${Math.min(40, starlink.length)} | GPS: ${gps.length})`,
            'info'
        );

        // Refresh every 6 minutes
        setTimeout(fetchSatellites, 6 * 60 * 1000);
    }

    // ────────────────────────────────────────
    // Overpass API — OSM Road Network
    // ────────────────────────────────────────
    async function fetchRoads() {
        const { lat, lon } = window.OW.center;
        const r = window.OW.bbox;

        const query = [
            '[out:json][timeout:30];',
            '(',
            '  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified)$"]',
            `    (${lat - r},${lon - r},${lat + r},${lon + r});`,
            ');',
            'out body;',
            '>;',
            'out skel qt;',
        ].join('\n');

        try {
            OW_HUD.addAlert('FETCHING ROAD NETWORK FROM OVERPASS API...', 'info');
            const resp = await fetch('https://overpass-api.de/api/interpreter', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: 'data=' + encodeURIComponent(query),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            const graph = parseOverpass(data);
            OW_HUD.addAlert(
                `ROAD NETWORK LOADED — ${graph.edges.length} SEGMENTS ACROSS ${graph.nodes.size} NODES`,
                'info'
            );
            OW_Render.initTraffic(graph);
        } catch (e) {
            console.warn('[OW] Overpass failed, using procedural mode:', e.message);
            OW_HUD.addAlert('ROAD NETWORK UNAVAILABLE — ENGAGING PROCEDURAL TRAFFIC GRID', 'warn');
            OW_Render.initTrafficProcedural();
        }
    }

    function parseOverpass(data) {
        const nodes = new Map();
        const ways = [];

        for (const el of data.elements) {
            if (el.type === 'node') {
                nodes.set(el.id, { lat: el.lat, lon: el.lon });
            } else if (el.type === 'way' && el.nodes) {
                ways.push({
                    nodeIds: el.nodes,
                    highway: el.tags && el.tags.highway || 'unclassified',
                });
            }
        }

        // Build bidirectional edge list
        const edges = [];
        for (const way of ways) {
            for (let i = 0; i < way.nodeIds.length - 1; i++) {
                const a = nodes.get(way.nodeIds[i]);
                const b = nodes.get(way.nodeIds[i + 1]);
                if (a && b) {
                    edges.push({ from: a, to: b, highway: way.highway });
                    edges.push({ from: b, to: a, highway: way.highway });
                }
            }
        }

        return { nodes, edges };
    }

    // ── Public API ──
    return {
        fetchFlights,
        startFlightPolling,
        fetchTLEs,
        parseTLEs,
        fetchSatellites,
        fetchRoads,
    };
})();
