"use client";

import {
  useEffect,
  useState,
  useRef,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from "react";
import type { ZoneDetail } from "@/types/api";

export interface ChargingMapHandle {
  setUserLocation: (lat: number, lng: number) => void;
  runOptimizationSequence: (zones: ZoneDetail[]) => Promise<void>;
  showResults: (zones: ZoneDetail[], selected: string[]) => void;
  showScenario: (zones: ZoneDetail[], selected: string[], k: number) => void;
  resetToIdle: () => void;
}

interface ChargingMapProps {
  onSequenceStep?: (step: number) => void;
  onReady?: () => void;
}

function haversine(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) *
    Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function demandColor(demand: number, maxDemand: number): string {
  const ratio = maxDemand > 0 ? demand / maxDemand : 0;
  if (ratio >= 0.7) return "rgba(10,22,40,0.55)";
  if (ratio >= 0.35) return "rgba(30,61,117,0.38)";
  if (ratio >= 0.15) return "rgba(64,114,184,0.25)";
  return "rgba(169,196,232,0.18)";
}

function demandBorder(demand: number, maxDemand: number): string {
  const ratio = maxDemand > 0 ? demand / maxDemand : 0;
  if (ratio >= 0.7) return "rgba(10,22,40,0.7)";
  if (ratio >= 0.35) return "rgba(30,61,117,0.55)";
  return "rgba(64,114,184,0.4)";
}

function formatDemand(kwh: number): string {
  return kwh >= 1000 ? `${(kwh / 1000).toFixed(1)} MWh/h` : `${Math.round(kwh)} kWh/h`;
}

function delay(ms: number) {
  return new Promise<void>((r) => setTimeout(r, ms));
}

const ChargingMap = forwardRef<ChargingMapHandle, ChargingMapProps>(
  ({ onSequenceStep, onReady }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const mapRef = useRef<any>(null);
    const userMarkerRef = useRef<any>(null);
    const layersRef = useRef<any[]>([]);
    const userLatLngRef = useRef<[number, number]>([22.625, 114.075]);

    const [showCoverage, setShowCoverage] = useState(true);
    const [showHeatmap, setShowHeatmap] = useState(false);
    const [showFleetFlow, setShowFleetFlow] = useState(true);
    const [hasResults, setHasResults] = useState(false);
    const lastResultsRef = useRef<{ zones: ZoneDetail[]; selected: string[] } | null>(null);

    const clearLayers = useCallback(() => {
      layersRef.current.forEach((l) => { try { l.remove(); } catch {} });
      layersRef.current = [];
    }, []);

    useEffect(() => {
      let cancelled = false;
      let ro: ResizeObserver | null = null;

      (async () => {
        const el = containerRef.current;
        if (!el) return;

        const L = (await import("leaflet")).default;

        // Guard: if this effect was cleaned up while we awaited the import,
        // or if another mount already initialised the map on this container,
        // bail out to avoid the "Map container is already initialized" error.
        if (cancelled || mapRef.current) return;
        if ((el as any)._leaflet_id) return;

        el.style.width = "100%";
        el.style.height = "100%";

        const map = L.map(el, {
          center: [22.625, 114.075],
          zoom: 13,
          zoomControl: false,
          scrollWheelZoom: true,
          attributionControl: true,
        });

        // Base tile layers (English names prioritized)
        const googleEnglish = L.tileLayer(
          "https://mt{s}.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}",
          {
            attribution: '© Google Maps',
            subdomains: ["0", "1", "2", "3"],
            maxZoom: 20,
          }
        );

        const esriStreets = L.tileLayer(
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
          {
            attribution: '© <a href="https://www.esri.com/">Esri</a>',
            maxZoom: 19,
          }
        );

        const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
          maxZoom: 19,
        });

        // Default to Google English map layer
        googleEnglish.addTo(map);

        // Layer switcher at bottom-right
        L.control.layers(
          {
            "English (Google)": googleEnglish,
            "English (Esri)": esriStreets,
            "OpenStreetMap (Local)": osm,
          },
          undefined,
          { position: "bottomright" }
        ).addTo(map);

        L.control.zoom({ position: "bottomright" }).addTo(map);
        mapRef.current = map;
        requestAnimationFrame(() => map.invalidateSize());
        setTimeout(() => mapRef.current?.invalidateSize(), 300);
        onReady?.();

        if (el && typeof ResizeObserver !== "undefined") {
          ro = new ResizeObserver(() => mapRef.current?.invalidateSize());
          ro.observe(el);
        }
      })();

      return () => {
        cancelled = true;
        ro?.disconnect();
        if (mapRef.current) {
          try { mapRef.current.remove(); } catch {}
          mapRef.current = null;
        }
      };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const renderOverlayLayers = useCallback(
      (zones: ZoneDetail[], selected: string[], isNew: boolean = false) => {
        import("leaflet").then(({ default: L }) => {
          const map = mapRef.current;
          if (!map) return;
          clearLayers();

          const selectedSet = new Set(selected);
          const maxDemand = Math.max(...zones.map((z) => z.predicted_demand_kwh_h), 1);
          const [uLat, uLng] = userLatLngRef.current;
          const selZones = zones.filter((z) => selectedSet.has(z.label));

          // 1. Demand Heatmap Layer (if active)
          if (showHeatmap) {
            zones.forEach((z) => {
              const ratio = z.predicted_demand_kwh_h / maxDemand;
              const color = ratio > 0.6 ? "#e11d48" : ratio > 0.3 ? "#f59e0b" : "#3b82f6";
              const heatCircle = L.circle([z.latitude, z.longitude], {
                radius: Math.max(900, ratio * 2400),
                color: "transparent",
                fillColor: color,
                fillOpacity: 0.16,
              }).addTo(map);
              layersRef.current.push(heatCircle);
            });
          }

          // 2. Fleet Dispatch Flow Rays (if active)
          if (showFleetFlow && selZones.length > 0) {
            zones.filter((z) => !selectedSet.has(z.label)).forEach((unsel) => {
              let nearest = selZones[0];
              let minDist = haversine(unsel.latitude, unsel.longitude, nearest.latitude, nearest.longitude);
              for (const s of selZones) {
                const d = haversine(unsel.latitude, unsel.longitude, s.latitude, s.longitude);
                if (d < minDist) {
                  minDist = d;
                  nearest = s;
                }
              }
              const ray = L.polyline(
                [[unsel.latitude, unsel.longitude], [nearest.latitude, nearest.longitude]],
                { color: "#1e3d75", weight: 1.5, dashArray: "4 6", opacity: 0.45 }
              ).addTo(map);
              layersRef.current.push(ray);
            });
          }

          // 3. Candidate site markers (non-selected)
          zones.filter((z) => !selectedSet.has(z.label)).forEach((z) => {
            const icon = L.divIcon({
              className: "",
              html: `<div style="width:14px;height:14px;border-radius:50%;background:rgba(255,255,255,0.95);border:1.5px solid rgba(10,22,40,0.25);box-shadow:0 1px 4px rgba(10,22,40,0.1);transform:translate(-7px,-7px);"></div>`,
              iconSize: [0, 0], iconAnchor: [0, 0],
            });
            const dist = haversine(uLat, uLng, z.latitude, z.longitude);
            const m = L.marker([z.latitude, z.longitude], { icon, zIndexOffset: 600 }).addTo(map);
            m.bindPopup(L.popup({ closeButton: true, maxWidth: 220, offset: [0, -5] }).setContent(`
              <div style="font-family:Times New Roman,serif;padding:16px 18px;min-width:180px;">
                <div style="display:inline-block;background:var(--color-grey-100);color:var(--color-ink-3);font-size:10px;letter-spacing:0.08em;padding:3px 8px;border-radius:4px;margin-bottom:10px;">Candidate Zone</div>
                <div style="font-size:20px;color:var(--color-ink);letter-spacing:-0.02em;margin-bottom:10px;">${z.name_primary || `Site ${z.label}`}</div>
                <div style="display:flex;flex-direction:column;gap:6px;border-top:1px solid var(--color-border);padding-top:10px;font-size:12px;">
                  <div style="display:flex;justify-content:space-between;"><span style="color:var(--color-ink-4);">Predicted demand</span><span style="color:var(--color-ink);font-weight:600;">${formatDemand(z.predicted_demand_kwh_h)}</span></div>
                  <div style="display:flex;justify-content:space-between;"><span style="color:var(--color-ink-4);">QUBO score</span><span>${z.qubo_c_value.toFixed(3)}</span></div>
                  <div style="display:flex;justify-content:space-between;"><span style="color:var(--color-ink-4);">Distance from area</span><span>${dist < 1 ? `${Math.round(dist * 1000)} m` : `${dist.toFixed(1)} km`}</span></div>
                </div>
              </div>`));
            layersRef.current.push(m);
          });

          // 4. Selected stations (3km isochrone reach + pulsing station marker)
          selZones.forEach((z, idx) => {
            if (showCoverage) {
              // 3km mathematical boundary
              const cov3k = L.circle([z.latitude, z.longitude], {
                radius: 3000,
                color: "rgba(22,45,88,0.22)",
                fillColor: "rgba(22,45,88,0.04)",
                fillOpacity: 1,
                weight: 1.5,
                dashArray: "4 8",
              }).addTo(map);

              // 1.2km core service radius
              const covCore = L.circle([z.latitude, z.longitude], {
                radius: 1200,
                color: "rgba(22,45,88,0.3)",
                fillColor: "rgba(22,45,88,0.08)",
                fillOpacity: 1,
                weight: 1,
              }).addTo(map);

              layersRef.current.push(cov3k, covCore);
            }

            const dist = haversine(uLat, uLng, z.latitude, z.longitude);
            const icon = L.divIcon({
              className: "",
              html: `<div style="position:relative;width:56px;height:56px;transform:translate(-28px,-28px);">
                <div style="position:absolute;inset:0;border-radius:50%;background:rgba(10,22,40,0.14);animation:pulse-1 2.4s ease-out infinite;"></div>
                <div style="position:absolute;inset:0;border-radius:50%;background:rgba(10,22,40,0.08);animation:pulse-2 2.4s ease-out 0.8s infinite;"></div>
                <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:28px;height:28px;border-radius:50%;background:var(--color-navy-900);border:3.5px solid white;box-shadow:0 6px 24px rgba(10,22,40,0.40);display:flex;align-items:center;justify-content:center;">
                  <div style="width:8px;height:8px;border-radius:50%;background:white;opacity:0.9;"></div>
                </div>
              </div>`,
              iconSize: [0, 0], iconAnchor: [0, 0],
            });
            const m = L.marker([z.latitude, z.longitude], { icon, zIndexOffset: 1500 }).addTo(map);
            m.bindPopup(L.popup({ closeButton: true, maxWidth: 280, offset: [0, -10] }).setContent(`
              <div style="font-family:Times New Roman,serif;padding:20px 22px;min-width:240px;">
                <div style="display:inline-flex;align-items:center;gap:6px;background:var(--color-navy-900);color:white;font-size:10px;letter-spacing:0.08em;padding:4px 10px;border-radius:99px;margin-bottom:14px;">
                  <svg width="8" height="8" viewBox="0 0 8 8" fill="none"><circle cx="4" cy="4" r="2.5" fill="white"/></svg>
                  Recommended Site (3km Reach)
                </div>
                <div style="font-size:24px;letter-spacing:-0.02em;color:var(--color-ink);margin-bottom:2px;">${z.name_primary || `Site ${z.label}`}</div>
                <div style="font-size:13px;color:var(--color-ink-3);margin-bottom:14px;">${z.latitude.toFixed(4)}°N, ${z.longitude.toFixed(4)}°E</div>
                <div style="display:flex;flex-direction:column;gap:8px;border-top:1px solid var(--color-border);padding-top:12px;font-size:13px;">
                  <div style="display:flex;justify-content:space-between;"><span style="color:var(--color-ink-4);">Predicted demand</span><span style="font-weight:600;color:var(--color-ink);">${formatDemand(z.predicted_demand_kwh_h)}</span></div>
                  <div style="display:flex;justify-content:space-between;"><span style="color:var(--color-ink-4);">QUBO score</span><span>${z.qubo_c_value.toFixed(3)}</span></div>
                  <div style="display:flex;justify-content:space-between;"><span style="color:var(--color-ink-4);">Distance</span><span>${dist < 1 ? `${Math.round(dist * 1000)} m` : `${dist.toFixed(1)} km`}</span></div>
                </div>
              </div>`));
            layersRef.current.push(m);

            if (isNew && idx === 0) {
              setTimeout(() => m.openPopup(), 600);
            }
          });

          if (isNew && selZones.length > 0) {
            const pts: [number, number][] = [
              ...selZones.map((z) => [z.latitude, z.longitude] as [number, number]),
              userLatLngRef.current,
            ];
            map.flyToBounds(L.latLngBounds(pts).pad(0.32), {
              duration: 1.5, easeLinearity: 0.2,
            });
          }
        });
      },
      [clearLayers, showCoverage, showHeatmap, showFleetFlow]
    );

    // Re-render when toggling layers
    useEffect(() => {
      if (lastResultsRef.current && mapRef.current) {
        renderOverlayLayers(lastResultsRef.current.zones, lastResultsRef.current.selected, false);
      }
    }, [showCoverage, showHeatmap, showFleetFlow, renderOverlayLayers]);

    useImperativeHandle(ref, () => ({

      setUserLocation(lat: number, lng: number) {
        if (!mapRef.current) return;
        import("leaflet").then(({ default: L }) => {
          const map = mapRef.current;
          if (!map) return;
          userLatLngRef.current = [lat, lng];
          if (userMarkerRef.current) { userMarkerRef.current.remove(); userMarkerRef.current = null; }
          const icon = L.divIcon({
            className: "",
            html: `<div style="position:relative;width:48px;height:48px;transform:translate(-24px,-24px);">
              <div style="position:absolute;inset:0;border-radius:50%;background:rgba(10,22,40,0.12);animation:pulse-1 2s ease-out infinite;"></div>
              <div style="position:absolute;inset:0;border-radius:50%;background:rgba(10,22,40,0.07);animation:pulse-2 2s ease-out 0.6s infinite;"></div>
              <div style="position:absolute;inset:0;border-radius:50%;background:rgba(10,22,40,0.04);animation:pulse-3 2s ease-out 1.2s infinite;"></div>
              <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:20px;height:20px;border-radius:50%;background:var(--color-navy-900);border:3px solid white;box-shadow:0 4px 16px rgba(10,22,40,0.35);animation:drop-in 0.5s cubic-bezier(0.22,1,0.36,1) both;"></div>
            </div>`,
            iconSize: [0, 0], iconAnchor: [0, 0],
          });
          userMarkerRef.current = L.marker([lat, lng], { icon, zIndexOffset: 2000 }).addTo(map);
          map.flyTo([lat, lng], 13, { duration: 1.4, easeLinearity: 0.25 });
        });
      },

      async runOptimizationSequence(zones: ZoneDetail[]) {
        const L = (await import("leaflet")).default;
        const map = mapRef.current;
        if (!map) return;

        clearLayers();
        const maxDemand = Math.max(...zones.map((z) => z.predicted_demand_kwh_h), 1);
        const [uLat, uLng] = userLatLngRef.current;

        // ── Step 0: Fit map to show all zones ──────────────────────────────
        const bounds = L.latLngBounds(zones.map((z) => [z.latitude, z.longitude] as [number, number])).pad(0.2);
        map.flyToBounds(bounds, { duration: 1.2, easeLinearity: 0.25 });
        await delay(1400);

        // ── Step 1: Demand heatmap — zones pulse in with fill intensity ───
        onSequenceStep?.(0);
        const heatLayers: any[] = [];
        for (let i = 0; i < zones.length; i++) {
          await delay(i === 0 ? 0 : 120);
          const z = zones[i];
          const ratio = z.predicted_demand_kwh_h / maxDemand;
          const r = 800 + ratio * 1600; // radius proportional to demand
          const circle = L.circle([z.latitude, z.longitude], {
            radius: r,
            color: demandBorder(z.predicted_demand_kwh_h, maxDemand),
            fillColor: demandColor(z.predicted_demand_kwh_h, maxDemand),
            fillOpacity: 0.85,
            weight: 1.5,
            className: "",
          }).addTo(map);
          heatLayers.push(circle);
          layersRef.current.push(circle);

          // Demand label
          const label = L.divIcon({
            className: "",
            html: `<div style="
              background:rgba(255,255,255,0.92);
              border:1px solid rgba(10,22,40,0.12);
              border-radius:8px;
              padding:3px 8px;
              font-family:'Times New Roman',serif;
              font-size:11px;
              color:var(--color-ink-2);
              white-space:nowrap;
              box-shadow:0 2px 8px rgba(10,22,40,0.08);
              transform:translate(-50%,-50%);
              opacity:0;
              animation:fade-in 0.4s ease ${0.1 + i * 0.08}s both;
            ">
              <span style="font-weight:600;color:var(--color-navy-700)">${z.name_primary || `Site ${z.label}`}</span>
              <span style="margin-left:4px;color:var(--color-ink-3)">${formatDemand(z.predicted_demand_kwh_h)}</span>
            </div>`,
            iconSize: [0, 0], iconAnchor: [0, 0],
          });
          const lm = L.marker([z.latitude, z.longitude], { icon: label, zIndexOffset: 500 }).addTo(map);
          layersRef.current.push(lm);
        }
        await delay(1200);

        // ── Step 2: Coverage gap scan — sweep circles from user area ──────
        onSequenceStep?.(1);
        for (let i = 0; i < 3; i++) {
          const sweep = L.circle([uLat, uLng], {
            radius: 1000 + i * 1200,
            color: "rgba(10,22,40,0.08)",
            fillColor: "rgba(10,22,40,0.02)",
            fillOpacity: 1,
            weight: 1,
            dashArray: "3 5",
          }).addTo(map);
          layersRef.current.push(sweep);
          await delay(350);
        }
        await delay(900);

        // ── Step 3: Candidate evaluation — highlight each zone briefly ────
        onSequenceStep?.(2);
        for (let i = 0; i < zones.length; i++) {
          const z = zones[i];
          const ring = L.circle([z.latitude, z.longitude], {
            radius: 400,
            color: "rgba(64,114,184,0.6)",
            fillColor: "rgba(64,114,184,0.08)",
            fillOpacity: 1,
            weight: 2,
          }).addTo(map);
          layersRef.current.push(ring);
          await delay(180);
          // Fade ring out
          setTimeout(() => { try { ring.setStyle({ opacity: 0.15, fillOpacity: 0.03 }); } catch {} }, 300);
        }
        await delay(600);

        // ── Step 4: QAOA solving — pulsing wave effect ────────────────────
        onSequenceStep?.(3);
        for (let wave = 0; wave < 2; wave++) {
          for (const z of zones) {
            const r = L.circleMarker([z.latitude, z.longitude], {
              radius: 6,
              color: "rgba(64,114,184,0.8)",
              fillColor: "rgba(64,114,184,0.4)",
              fillOpacity: 1,
              weight: 2,
            }).addTo(map);
            layersRef.current.push(r);
            setTimeout(() => { try { r.setStyle({ color: "rgba(10,22,40,0.15)", fillOpacity: 0.05 }); } catch {} }, 400);
          }
          await delay(500);
        }
        await delay(600);

        // ── Step 5: Clear intermediate layers, keep heatmap faded ─────────
        onSequenceStep?.(4);
        // Fade down heatmap circles
        heatLayers.forEach((c) => {
          try {
            c.setStyle({ fillOpacity: 0.15, weight: 0.5, opacity: 0.25 });
          } catch {}
        });
        await delay(400);
      },

      showResults(zones: ZoneDetail[], selected: string[]) {
        lastResultsRef.current = { zones, selected };
        setHasResults(true);
        renderOverlayLayers(zones, selected, true);
      },

      showScenario(zones: ZoneDetail[], selected: string[], k: number) {
        lastResultsRef.current = { zones, selected };
        setHasResults(true);
        renderOverlayLayers(zones, selected, false);
      },

      resetToIdle() {
        if (userMarkerRef.current) { userMarkerRef.current.remove(); userMarkerRef.current = null; }
        clearLayers();
        lastResultsRef.current = null;
        setHasResults(false);
        userLatLngRef.current = [22.625, 114.075];
        if (mapRef.current) {
          mapRef.current.flyTo([22.625, 114.075], 13, { duration: 1.2, easeLinearity: 0.3 });
        }
      },
    }));

    return (
      <div style={{ position: "relative", width: "100%", height: "100%" }}>
        <div ref={containerRef} style={{ position: "absolute", inset: 0, background: "#e8edf4" }} />

        {/* GIS Map Layer Controls */}
        {hasResults && (
          <div
            className="anim-fade-in glass"
            style={{
              position: "absolute",
              top: "70px",
              right: "20px",
              zIndex: 35,
              borderRadius: "12px",
              padding: "6px 10px",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              boxShadow: "0 4px 20px rgba(10,22,40,0.12)",
              border: "1px solid rgba(255,255,255,0.8)",
            }}
          >
            <span style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-ink-4)", marginRight: "2px" }}>
              Layers:
            </span>
            <button
              onClick={() => setShowCoverage((prev: boolean) => !prev)}
              style={{
                padding: "4px 10px",
                borderRadius: "6px",
                border: "none",
                background: showCoverage ? "var(--color-navy-900)" : "var(--color-grey-100)",
                color: showCoverage ? "white" : "var(--color-ink-3)",
                fontFamily: "Times New Roman, serif",
                fontSize: "12px",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
              title="Toggle 3km adjacency coverage reach"
            >
              {showCoverage ? "✓ " : ""}3km Reach
            </button>
            <button
              onClick={() => setShowHeatmap((prev: boolean) => !prev)}
              style={{
                padding: "4px 10px",
                borderRadius: "6px",
                border: "none",
                background: showHeatmap ? "var(--color-navy-900)" : "var(--color-grey-100)",
                color: showHeatmap ? "white" : "var(--color-ink-3)",
                fontFamily: "Times New Roman, serif",
                fontSize: "12px",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
              title="Toggle predicted EV demand intensity heat circles"
            >
              {showHeatmap ? "✓ " : ""}Demand Heatmap
            </button>
            <button
              onClick={() => setShowFleetFlow((prev: boolean) => !prev)}
              style={{
                padding: "4px 10px",
                borderRadius: "6px",
                border: "none",
                background: showFleetFlow ? "var(--color-navy-900)" : "var(--color-grey-100)",
                color: showFleetFlow ? "white" : "var(--color-ink-3)",
                fontFamily: "Times New Roman, serif",
                fontSize: "12px",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
              title="Toggle commercial fleet dispatch vectors to nearest charging hubs"
            >
              {showFleetFlow ? "✓ " : ""}Fleet Dispatch
            </button>
          </div>
        )}
      </div>
    );
  }
);

ChargingMap.displayName = "ChargingMap";
export default ChargingMap;
