/* ============================================
   OVERWATCH Geo — Geofence Zones + Satellite Ground Tracks
   Ported from /geo (Leaflet) → CesiumJS 3D globe
   ============================================ */

window.OW_Geo = (function () {
    'use strict';

    // ── Geofence Zone Config (ported verbatim from geo-main.js) ──
    const GEO_ZONES = [
        { label: 'JFK APPROACH',       color: '#f6a623',
          coords: [[40.56,-73.85],[40.56,-73.65],[40.70,-73.65],[40.70,-73.85]] },
        { label: 'LAGUARDIA APPROACH', color: '#22d3ee',
          coords: [[40.75,-73.92],[40.75,-73.82],[40.82,-73.82],[40.82,-73.92]] },
        { label: 'HUDSON CORRIDOR',    color: '#4ade80',
          coords: [[40.64,-74.08],[40.64,-74.01],[40.88,-74.01],[40.88,-74.08]] },
    ];

    let viewer = null;
    const groundTrackEntities = new Map(); // sat name → entity
    let _trackTimer = null;

    // ── Public init ────────────────────────────────────────────────────────────
    function init(v) {
        viewer = v;
        _drawZones();
        _initGroundTracks();
    }

    // ── Zones ──────────────────────────────────────────────────────────────────
    function _drawZones() {
        for (const zone of GEO_ZONES) {
            const color = Cesium.Color.fromCssColorString(zone.color);

            // 1. Polygon fill (clamp to ground, very low alpha)
            viewer.entities.add({
                polygon: {
                    hierarchy: new Cesium.PolygonHierarchy(
                        Cesium.Cartesian3.fromDegreesArray(_flatLonLat(zone.coords))
                    ),
                    material: color.withAlpha(0.06),
                    outline: false,
                    classificationType: Cesium.ClassificationType.TERRAIN,
                },
            });

            // 2. Dashed polyline outline (close the polygon by repeating first coord)
            const closedCoords = [...zone.coords, zone.coords[0]];
            viewer.entities.add({
                polyline: {
                    positions: Cesium.Cartesian3.fromDegreesArray(_flatLonLat(closedCoords)),
                    clampToGround: true,
                    width: 1.5,
                    material: new Cesium.PolylineDashMaterialProperty({
                        color: color.withAlpha(0.75),
                        dashLength: 16,
                        dashPattern: 0xFF00,
                    }),
                },
            });

            // 3. Label at centroid
            const lats = zone.coords.map(c => c[0]);
            const lons = zone.coords.map(c => c[1]);
            const centLat = lats.reduce((a, b) => a + b, 0) / lats.length;
            const centLon = lons.reduce((a, b) => a + b, 0) / lons.length;

            viewer.entities.add({
                position: Cesium.Cartesian3.fromDegrees(centLon, centLat, 0),
                label: {
                    text: zone.label,
                    font: '10px "JetBrains Mono", monospace',
                    fillColor: color,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 2,
                    style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                    heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
                    disableDepthTestDistance: Number.POSITIVE_INFINITY,
                    pixelOffset: new Cesium.Cartesian2(0, 0),
                },
            });
        }
    }

    // ── Ground Tracks ──────────────────────────────────────────────────────────

    let _retryCount = 0;

    function _initGroundTracks() {
        const entities = OW_Render.getSatEntities();
        if (entities && entities.length > 0) {
            _startGroundTracks(entities);
        } else if (_retryCount < 10) {
            _retryCount++;
            setTimeout(_initGroundTracks, 2000);
        }
    }

    function _startGroundTracks(satEntities) {
        _clearGroundTracks();
        _buildGroundTracks(satEntities);
        if (_trackTimer) { clearInterval(_trackTimer); }
        _trackTimer = setInterval(_refreshGroundTracks, 30000);

        const count = groundTrackEntities.size;
        if (count > 0) {
            OW_HUD.addAlert(`GROUND TRACKS LOADED — ${count} ORBITS`, 'info');
        } else {
            console.warn('[OW] Ground track build produced 0 tracks.');
        }
    }

    function _clearGroundTracks() {
        for (const [, rec] of groundTrackEntities) {
            viewer.entities.remove(rec.entity);
        }
        groundTrackEntities.clear();
    }

    function _buildGroundTracks(satEntities) {
        for (const entity of satEntities) {
            const sat = entity._ow_satData;
            if (!sat || sat.group === 'starlink') continue;

            const track = _computeGroundTrack(sat, new Date(), 45);
            if (track.length < 2) continue;

            const color = Cesium.Color.fromCssColorString(
                sat.group === 'station' ? '#22d3ee' :
                sat.group === 'gps'     ? '#4ade80' : '#f6a623'
            );

            const trackEntity = viewer.entities.add({
                polyline: {
                    positions: Cesium.Cartesian3.fromDegreesArray(_flatLonLat(track)),
                    clampToGround: true,
                    width: 1,
                    material: new Cesium.PolylineDashMaterialProperty({
                        color: color.withAlpha(0.35),
                        dashLength: 8,
                        dashPattern: 0xFF00,
                    }),
                },
            });

            groundTrackEntities.set(sat.name, { entity: trackEntity, sat });
        }
    }

    function _refreshGroundTracks() {
        const now = new Date();
        for (const [, rec] of groundTrackEntities) {
            const track = _computeGroundTrack(rec.sat, now, 45);
            if (track.length < 2) continue;
            rec.entity.polyline.positions =
                Cesium.Cartesian3.fromDegreesArray(_flatLonLat(track));
        }
    }

    // ── SGP4 ground track computation (identical to geo-main.js) ──────────────
    function _computeGroundTrack(sat, centerDate, minuteRadius) {
        const coords  = [];
        const satrec  = satellite.twoline2satrec(sat.tle1, sat.tle2);
        const stepMin = 2;

        for (let m = -minuteRadius; m <= minuteRadius; m += stepMin) {
            const d    = new Date(centerDate.getTime() + m * 60000);
            const pv   = satellite.propagate(satrec, d);
            if (!pv || !pv.position) continue;
            const gmst = satellite.gstime(d);
            const geo  = satellite.eciToGeodetic(pv.position, gmst);
            coords.push([
                satellite.degreesLat(geo.latitude),
                satellite.degreesLong(geo.longitude),
            ]);
        }
        return coords;
    }

    // ── Helper: [lat,lon]... → [lon0,lat0,lon1,lat1,...] (Cesium ordering) ────
    function _flatLonLat(coords) {
        const flat = [];
        for (const [lat, lon] of coords) {
            flat.push(lon, lat);
        }
        return flat;
    }

    // ── Public API ─────────────────────────────────────────────────────────────
    return {
        init,
        onSatellitesReady: _startGroundTracks,
    };

})();
