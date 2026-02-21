/* ============================================
   OVERWATCH Render — CesiumJS Entity Management
   Aircraft · Satellites · Traffic agents · Frustums
   ============================================ */

window.OW_Render = (function () {
    'use strict';

    let viewer = null;

    // Entity stores
    const aircraftMap   = new Map(); // icao24 → { entity, posProperty }
    const satEntities   = [];
    const trafficAgents = [];

    let satPropTimer  = null;
    let trafficTimer  = null;
    let currentSatData = [];

    function init(v) {
        viewer = v;
    }

    // ═══════════════════════════════════════════
    // AIRCRAFT
    // ═══════════════════════════════════════════

    function updateAircraft(flights) {
        const seen = new Set();

        for (const f of flights) {
            seen.add(f.icao24);
            const now = Cesium.JulianDate.now();
            const pos = Cesium.Cartesian3.fromDegrees(f.lon, f.lat, Math.max(f.alt_m, 10));

            if (aircraftMap.has(f.icao24)) {
                // Update existing entity
                const rec = aircraftMap.get(f.icao24);
                rec.posProperty.addSample(now, pos);
                rec.flight = f;
            } else {
                // Create new entity with sampled positions (enables path trail)
                const posProperty = new Cesium.SampledPositionProperty();
                posProperty.forwardExtrapolationType  = Cesium.ExtrapolationType.HOLD;
                posProperty.backwardExtrapolationType = Cesium.ExtrapolationType.HOLD;
                posProperty.addSample(now, pos);

                const amber = Cesium.Color.fromCssColorString('#f6a623');

                const entity = viewer.entities.add({
                    id:       `aircraft_${f.icao24}`,
                    name:     f.callsign,
                    position: posProperty,

                    point: {
                        pixelSize: 7,
                        color: amber,
                        outlineColor: Cesium.Color.WHITE.withAlpha(0.6),
                        outlineWidth: 1,
                        heightReference: Cesium.HeightReference.NONE,
                        disableDepthTestDistance: Number.POSITIVE_INFINITY,
                    },

                    label: {
                        text: f.callsign,
                        font: '11px "JetBrains Mono", monospace',
                        fillColor: amber,
                        outlineColor: Cesium.Color.BLACK,
                        outlineWidth: 2,
                        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                        pixelOffset: new Cesium.Cartesian2(0, -12),
                        show: false,
                        disableDepthTestDistance: Number.POSITIVE_INFINITY,
                        scaleByDistance: new Cesium.NearFarScalar(1e4, 1.0, 8e6, 0.4),
                    },

                    path: {
                        show: true,
                        leadTime:  0,
                        trailTime: 90,
                        width: 1.5,
                        material: new Cesium.PolylineGlowMaterialProperty({
                            glowPower: 0.12,
                            color: amber.withAlpha(0.45),
                        }),
                        resolution: 1,
                    },
                });

                aircraftMap.set(f.icao24, { entity, posProperty, flight: f });
            }
        }

        // Remove entities for aircraft no longer in bbox
        for (const [icao, rec] of aircraftMap) {
            if (!seen.has(icao)) {
                viewer.entities.remove(rec.entity);
                aircraftMap.delete(icao);
            }
        }

        window.OW.aircraftCount = aircraftMap.size;
    }

    // Allow HUD to inspect the aircraft map
    function getAircraftMap() { return aircraftMap; }

    // ═══════════════════════════════════════════
    // SATELLITES
    // ═══════════════════════════════════════════

    function initSatellites(satData) {
        // Clean up previous satellite entities
        for (const e of satEntities) { viewer.entities.remove(e); }
        satEntities.length = 0;
        if (satPropTimer) { clearInterval(satPropTimer); satPropTimer = null; }

        currentSatData = satData;

        for (const sat of satData) {
            const isISS     = /ISS|ZARYA/i.test(sat.name);
            const isStation = sat.group === 'station';

            let color;
            if (isStation)          color = Cesium.Color.fromCssColorString('#22d3ee'); // cyan
            else if (sat.group === 'gps')     color = Cesium.Color.fromCssColorString('#4ade80'); // green
            else                    color = Cesium.Color.fromCssColorString('#f6a623'); // amber (Starlink)

            // SampledPositionProperty — propagation fills this every second
            const posProp = new Cesium.SampledPositionProperty(Cesium.ReferenceFrame.FIXED);
            posProp.forwardExtrapolationType  = Cesium.ExtrapolationType.HOLD;
            posProp.backwardExtrapolationType = Cesium.ExtrapolationType.HOLD;
            posProp.interpolationDegree = 5;
            posProp.setInterpolationOptions({
                interpolationDegree: 5,
                interpolationAlgorithm: Cesium.LagrangePolynomialApproximation,
            });

            const entity = viewer.entities.add({
                id:       `sat_${sat.name.replace(/\s+/g, '_')}`,
                name:     sat.name,
                position: posProp,

                point: {
                    pixelSize: isISS ? 10 : 4,
                    color,
                    outlineColor: color.withAlpha(0.4),
                    outlineWidth: isISS ? 3 : 1,
                    heightReference: Cesium.HeightReference.NONE,
                    disableDepthTestDistance: Number.POSITIVE_INFINITY,
                },

                label: {
                    text: sat.name,
                    font: `${isISS ? 12 : 10}px "JetBrains Mono", monospace`,
                    fillColor: color,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 2,
                    style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                    verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                    pixelOffset: new Cesium.Cartesian2(0, -10),
                    show: isISS,
                    disableDepthTestDistance: Number.POSITIVE_INFINITY,
                },

                path: {
                    show: sat.group !== 'starlink', // skip paths for mass Starlink (perf)
                    leadTime:  1800,
                    trailTime: 1800,
                    width: 1,
                    material: color.withAlpha(0.25),
                    resolution: 60,
                },

                // Custom properties for bookkeeping
                _ow_posProp:  posProp,
                _ow_satData:  sat,
                _ow_altKm:    0,
            });

            satEntities.push(entity);
        }

        // Propagate immediately, then every second
        propagateSatellites();
        satPropTimer = setInterval(propagateSatellites, 1000);

        updateSatList();
    }

    function propagateSatellites() {
        const now  = new Date();
        const jd   = Cesium.JulianDate.fromDate(now);
        const gmst = satellite.gstime(now);

        for (const entity of satEntities) {
            const sat = entity._ow_satData;
            if (!sat) continue;

            try {
                const satrec = satellite.twoline2satrec(sat.tle1, sat.tle2);
                const pv     = satellite.propagate(satrec, now);
                if (!pv || !pv.position) continue;

                const geo = satellite.eciToGeodetic(pv.position, gmst);
                const lon = satellite.degreesLong(geo.longitude);
                const lat = satellite.degreesLat(geo.latitude);
                const alt = geo.height * 1000; // km → m

                if (isNaN(lon) || isNaN(lat) || alt < 0) continue;

                const cartesian = Cesium.Cartesian3.fromDegrees(lon, lat, alt);
                entity._ow_posProp.addSample(jd, cartesian);
                entity._ow_altKm = Math.round(geo.height);
            } catch (_) {
                // Decayed or invalid TLE — skip silently
            }
        }

        // Update sidebar list every 5 s
        if (Math.floor(Date.now() / 1000) % 5 === 0) {
            updateSatList();
        }
    }

    function updateSatList() {
        const listEl = document.getElementById('sat-list');
        if (!listEl || !satEntities.length) return;

        const groupOrder = { station: 0, gps: 1, starlink: 2 };
        const sorted = [...satEntities].sort((a, b) =>
            (groupOrder[a._ow_satData.group] || 9) - (groupOrder[b._ow_satData.group] || 9)
        );

        listEl.innerHTML = sorted.slice(0, 22).map(e => {
            const groupTag = { station: 'ISS', gps: 'GPS', starlink: 'SL' }[e._ow_satData.group] || '??';
            return `
            <div class="ow-sat-row" data-satid="${e.id}">
                <span class="ow-sat-name" title="${e._ow_satData.name}">${e._ow_satData.name}</span>
                <span class="ow-sat-alt">
                    <span class="ow-sat-group">${groupTag}</span>${e._ow_altKm || '?'}km
                </span>
            </div>`;
        }).join('');

        // Click row → track satellite
        listEl.querySelectorAll('.ow-sat-row').forEach(row => {
            row.addEventListener('click', () => {
                const ent = viewer.entities.getById(row.dataset.satid);
                if (ent) {
                    viewer.trackedEntity = ent;
                    OW_HUD.addAlert(`TRACKING: ${ent.name}`, 'info');
                }
            });
        });
    }

    // ═══════════════════════════════════════════
    // TRAFFIC AGENTS
    // ═══════════════════════════════════════════

    const AGENT_COUNT = 120;

    const VEHICLE_TYPES = [
        { color: '#e2e8f0', size: 4, weight: 65 }, // civilian white
        { color: '#f6a623', size: 4, weight: 20 }, // amber taxi
        { color: '#ef4444', size: 5, weight: 8  }, // red emergency
        { color: '#3b82f6', size: 5, weight: 7  }, // blue enforcement
    ];

    function pickVehicleType() {
        let r = Math.random() * 100, w = 0;
        for (const t of VEHICLE_TYPES) { w += t.weight; if (r < w) return t; }
        return VEHICLE_TYPES[0];
    }

    function initTraffic(graph) {
        if (!graph || graph.edges.length < 10) {
            initTrafficProcedural();
            return;
        }
        _spawnAgents(graph.edges);
    }

    function initTrafficProcedural() {
        const { lat, lon } = window.OW.center;
        const step  = 0.004; // ~400 m city block
        const span  = 10;
        const edges = [];

        for (let i = -span; i < span; i++) {
            for (let j = -span; j < span; j++) {
                const la0 = lat + i * step,       lo0 = lon + j * step;
                const la1 = lat + (i + 1) * step, lo1 = lon + (j + 1) * step;

                // Horizontal
                edges.push({ from: { lat: la0, lon: lo0 }, to: { lat: la0, lon: lo1 } });
                edges.push({ from: { lat: la0, lon: lo1 }, to: { lat: la0, lon: lo0 } });
                // Vertical
                edges.push({ from: { lat: la0, lon: lo0 }, to: { lat: la1, lon: lo0 } });
                edges.push({ from: { lat: la1, lon: lo0 }, to: { lat: la0, lon: lo0 } });
            }
        }
        _spawnAgents(edges);
    }

    function _spawnAgents(edges) {
        // Clean up any existing traffic
        for (const a of trafficAgents) {
            if (a.entity) viewer.entities.remove(a.entity);
        }
        trafficAgents.length = 0;
        if (trafficTimer) { clearInterval(trafficTimer); trafficTimer = null; }

        for (let i = 0; i < AGENT_COUNT; i++) {
            const type  = pickVehicleType();
            const edge  = edges[Math.floor(Math.random() * edges.length)];
            const prog  = Math.random();
            const speed = 0.0006 + Math.random() * 0.0014; // progress-units/tick

            const startPos = lerpEdge(edge, prog);
            const entity   = viewer.entities.add({
                position: Cesium.Cartesian3.fromDegrees(startPos.lon, startPos.lat, 1),
                point: {
                    pixelSize: type.size,
                    color: Cesium.Color.fromCssColorString(type.color),
                    heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
                    disableDepthTestDistance: 5000,
                },
            });

            trafficAgents.push({ edge, progress: prog, speed, edges, entity });
        }

        window.OW.trafficCount = AGENT_COUNT;
        OW_HUD.updateCounts();

        trafficTimer = setInterval(_tickTraffic, 100);
    }

    function _tickTraffic() {
        for (const agent of trafficAgents) {
            agent.progress += agent.speed;
            if (agent.progress >= 1.0) {
                // Pick a new random edge (simple simulation — no routing needed)
                agent.edge     = agent.edges[Math.floor(Math.random() * agent.edges.length)];
                agent.progress = 0;
            }
            const p = lerpEdge(agent.edge, agent.progress);
            if (agent.entity) {
                agent.entity.position =
                    Cesium.Cartesian3.fromDegrees(p.lon, p.lat, 1);
            }
        }
    }

    function lerpEdge(edge, t) {
        return {
            lat: edge.from.lat + (edge.to.lat - edge.from.lat) * t,
            lon: edge.from.lon + (edge.to.lon - edge.from.lon) * t,
        };
    }

    // ── Public API ──
    return {
        init,
        updateAircraft,
        getAircraftMap,
        getSatEntities: () => satEntities,
        initSatellites,
        initTraffic,
        initTrafficProcedural,
    };
})();
