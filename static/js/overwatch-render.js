/* ============================================
   OVERWATCH Render — CesiumJS Entity Management
   Aircraft · Satellites · Traffic agents · Frustums
   ============================================ */

window.OW_Render = (function () {
    'use strict';

    let viewer = null;

    // Entity stores
    const aircraftMap   = new Map(); // icao24 → { entity, posProperty, flight, history }
    const aircraftTrackMap = new Map(); // icao24 → track entity
    let trackedAircraftIcao = null;
    const satEntities   = [];
    let satPropTimer  = null;
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
                rec.history.push([f.lon, f.lat, Math.max(f.alt_m, 10)]);
                if (rec.history.length > 120) rec.history.shift();
                if (trackedAircraftIcao === f.icao24) {
                    _updateAircraftTrack(f.icao24, rec);
                }
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
                        show: false,
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

                aircraftMap.set(f.icao24, {
                    entity,
                    posProperty,
                    flight: f,
                    history: [[f.lon, f.lat, Math.max(f.alt_m, 10)]],
                });
            }
        }

        // Remove entities for aircraft no longer in bbox
        for (const [icao, rec] of aircraftMap) {
            if (!seen.has(icao)) {
                if (trackedAircraftIcao === icao) {
                    trackedAircraftIcao = null;
                    const trackEnt = aircraftTrackMap.get(icao);
                    if (trackEnt) viewer.entities.remove(trackEnt);
                    aircraftTrackMap.delete(icao);
                }
                viewer.entities.remove(rec.entity);
                aircraftMap.delete(icao);
            }
        }

        window.OW.aircraftCount = aircraftMap.size;
    }

    // Allow HUD to inspect the aircraft map
    function getAircraftMap() { return aircraftMap; }

    function setTrackedAircraft(icao24) {
        if (trackedAircraftIcao && trackedAircraftIcao !== icao24) {
            const prev = aircraftTrackMap.get(trackedAircraftIcao);
            if (prev) viewer.entities.remove(prev);
            aircraftTrackMap.delete(trackedAircraftIcao);
        }

        trackedAircraftIcao = icao24 || null;
        if (!trackedAircraftIcao) return;

        const rec = aircraftMap.get(trackedAircraftIcao);
        if (!rec) return;
        _updateAircraftTrack(trackedAircraftIcao, rec);
    }

    function _updateAircraftTrack(icao24, rec) {
        if (!rec.history || rec.history.length < 1) return;
        let coords = rec.history;
        if (coords.length < 2 && rec.flight) {
            const [lon, lat, alt] = coords[0];
            const heading = (rec.flight.heading || 0) * Math.PI / 180;
            const speed = rec.flight.velocity || 0; // m/s
            const dist = Math.min(Math.max(speed * 60, 500), 5000); // 0.5–5 km
            const dLat = dist / 111320;
            const dLon = dist / (111320 * Math.cos(lat * Math.PI / 180) || 1);
            const lat2 = lat + dLat * Math.cos(heading);
            const lon2 = lon + dLon * Math.sin(heading);
            coords = [[lon, lat, alt], [lon2, lat2, alt]];
        }

        const positions = Cesium.Cartesian3.fromDegreesArrayHeights(
            coords.flat()
        );

        let trackEnt = aircraftTrackMap.get(icao24);
        if (!trackEnt) {
            trackEnt = viewer.entities.add({
                polyline: {
                    positions,
                    width: 2,
                    material: new Cesium.PolylineGlowMaterialProperty({
                        glowPower: 0.15,
                        color: Cesium.Color.fromCssColorString('#f6a623').withAlpha(0.6),
                    }),
                },
            });
            aircraftTrackMap.set(icao24, trackEnt);
        } else {
            trackEnt.polyline.positions = positions;
        }
    }

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

        // Kick ground tracks after satellites are available (handles slow/failed initial fetches)
        if (window.OW_Geo && typeof OW_Geo.onSatellitesReady === 'function') {
            OW_Geo.onSatellitesReady(satEntities);
        }
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
            if (window.OW_HUD && typeof OW_HUD.refreshActivePanel === 'function') {
                OW_HUD.refreshActivePanel();
            }
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

    // ── Public API ──
    return {
        init,
        updateAircraft,
        getAircraftMap,
        setTrackedAircraft,
        getSatEntities: () => satEntities,
        initSatellites,
    };
})();
