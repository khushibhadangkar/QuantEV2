"use client";



import { useRef, useState, useCallback } from "react";

import dynamic from "next/dynamic";

import { useOptimize } from "@/hooks/useOptimize";

import { CountryCitySelector, CITY_CONFIGS } from "@/components/CountryCitySelector";
import { OptimizationSequence } from "@/components/OptimizationSequence";
import { ResultPanel } from "@/components/ResultPanel";
import { PlanningControls } from "@/components/PlanningControls";
import { HowItWorks } from "@/components/HowItWorks";
import { QuantumAdvantageModal } from "@/components/QuantumAdvantageModal";
import { ExecutiveReportModal } from "@/components/ExecutiveReportModal";
import type { ChargingMapHandle } from "@/components/ChargingMap";
import type { PlanningScenario } from "@/types/api";

const ChargingMap = dynamic(
  () => import("@/components/ChargingMap"),
  {
    ssr: false,
    loading: () => (
      <div style={{ width: "100%", height: "100%", background: "#dde4ed" }} className="skeleton" />
    ),
  }
);

type UIPhase = "idle" | "located" | "searching" | "result" | "error";

export default function Page() {
  const { state, run, reset, lastRunParams } = useOptimize();
  const mapRef = useRef<ChargingMapHandle>(null);
  const resultScrollRef = useRef<HTMLDivElement>(null);

  const [selectedCountry, setSelectedCountry] = useState("India");
  const [selectedCity, setSelectedCity] = useState("Mumbai");
  const [phase, setPhase] = useState<UIPhase>("idle");
  const [userLat, setUserLat] = useState(CITY_CONFIGS["Mumbai"].lat);
  const [userLng, setUserLng] = useState(CITY_CONFIGS["Mumbai"].lng);
  const [locationName, setLocationName] = useState("Mumbai");
  const [stationCount, setStationCount] = useState(3);
  const [scenario, setScenario] = useState<PlanningScenario>("all_hours");
  const [sequenceStep, setSequenceStep] = useState(0);

  // Winner feature modals
  const [quantumModalOpen, setQuantumModalOpen] = useState(false);
  const [reportModalOpen, setReportModalOpen] = useState(false);

  const handleCountrySelect = useCallback((country: string) => {
    setSelectedCountry(country);
  }, []);

  const handleTriggerCityOptimization = useCallback(
    async (city: string, country: string, lat: number, lng: number, count?: number, scen?: PlanningScenario) => {
      const finalCount = count ?? stationCount;
      const finalScen = scen ?? scenario;
      setSelectedCity(city);
      setSelectedCountry(country);
      setUserLat(lat);
      setUserLng(lng);
      setLocationName(city);
      if (count !== undefined) setStationCount(count);
      if (scen !== undefined) setScenario(scen);

      // Smoothly navigate map to selected city
      mapRef.current?.setUserLocation(lat, lng);

      // Immediately run quantum optimization analysis
      setPhase("searching");
      setSequenceStep(0);
      await run(finalCount, finalScen, city);
    },
    [stationCount, scenario, run]
  );

  const handleCitySelect = useCallback(
    (city: string, country: string, lat: number, lng: number) => {
      handleTriggerCityOptimization(city, country, lat, lng);
    },
    [handleTriggerCityOptimization]
  );

  const handleSearch = useCallback(async () => {
    setPhase("searching");
    setSequenceStep(0);
    const apiPromise = run(stationCount, scenario, selectedCity);
    await apiPromise;
  }, [run, stationCount, scenario, selectedCity]);

  // Transition on API state change (render-phase ref pattern)
  const prevStatusRef = useRef(state.status);
  if (state.status !== prevStatusRef.current) {
    prevStatusRef.current = state.status;
    if (state.status === "success") {
      // Drive map animation with microtask
      Promise.resolve().then(async () => {
        if (state.status !== "success") return;
        const { zone_details, selected_zones } = state.data.recommendation;

        // Run the fast, sleek optimization sequence on the map
        await mapRef.current?.runOptimizationSequence(zone_details);

        setSequenceStep(5);
        await new Promise((r) => setTimeout(r, 150));

        // Then reveal the results
        setPhase("result");
        mapRef.current?.showResults(zone_details, selected_zones);

        setTimeout(() => {
          resultScrollRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }, 150);
      });
    }

    if (state.status === "error") {

      setPhase("error");

    }

  }



  const handleReset = useCallback(() => {

    reset();

    setPhase("idle");

    setSequenceStep(0);

    mapRef.current?.resetToIdle();

  }, [reset]);



  // Phase label for header
  const phaseLabel: Record<UIPhase, string> = {
    idle: `Global Infrastructure Planning · ${selectedCity}, ${selectedCountry}`,
    located: `Planning Area: ${selectedCity}, ${selectedCountry}`,
    searching: "Running QAOA Quantum Optimization…",
    result: `Optimal Sites Identified · ${selectedCity}`,
    error: "Optimization failed",
  };



  return (

    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "white" }}>



      {/* ── HEADER ─────────────────────────────────────────── */}

      <header

        className="glass"

        style={{ position: "fixed", top: 0, left: 0, right: 0, zIndex: 50, height: "56px", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 24px", borderBottom: "1px solid rgba(255,255,255,0.5)" }}

      >

        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>

          <div style={{ width: "28px", height: "28px", borderRadius: "50%", background: "var(--color-navy-900)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>

            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">

              <circle cx="6" cy="6" r="2" fill="white" />

              <circle cx="6" cy="6" r="4.5" stroke="white" strokeWidth="0.8" fill="none" opacity="0.45" />

              <circle cx="6" cy="6" r="6" stroke="white" strokeWidth="0.4" fill="none" opacity="0.2" />

            </svg>

          </div>

          <span style={{ fontFamily: "Times New Roman, serif", fontSize: "16px", color: "var(--color-ink)", letterSpacing: "-0.01em" }}>

            QuantEV

          </span>

        </div>



        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "13px", color: "var(--color-ink-4)" }}>

          {phaseLabel[phase]}

        </div>



        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <button
            type="button"
            onClick={() => setQuantumModalOpen(true)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "5px 12px",
              borderRadius: "8px",
              border: "1px solid var(--color-navy-200)",
              background: "var(--color-navy-50)",
              color: "var(--color-navy-900)",
              fontFamily: "Times New Roman, serif",
              fontSize: "12px",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
            title="Inspect Combinatorial Scaling & IBM Fez Heron QPU Verification"
          >
            <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#00d084" }} />
            Quantum Scalability (IBM Fez)
          </button>

          <button
            type="button"
            onClick={() => setReportModalOpen(true)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "5px 12px",
              borderRadius: "8px",
              border: "1px solid var(--color-border)",
              background: "white",
              color: "var(--color-ink-2)",
              fontFamily: "Times New Roman, serif",
              fontSize: "12px",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
            title="Generate Municipal Infrastructure Briefing (PDF)"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            Municipal Briefing
          </button>

          {phase !== "idle" && (
            <button
              onClick={handleReset}
              style={{ fontFamily: "Times New Roman, serif", fontSize: "13px", color: "var(--color-ink-3)", background: "none", border: "none", cursor: "pointer", padding: "6px 10px", borderRadius: "8px", transition: "color 0.15s ease" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--color-ink)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--color-ink-3)")}
            >
              New analysis
            </button>
          )}
        </div>

      </header>



      {/* ── MAP + OVERLAY PANEL ────────────────────────────── */}

      <div style={{ position: "relative", height: "calc(100vh - 56px)", marginTop: "56px", flexShrink: 0 }}>



        {/* Full-bleed map */}

        <div style={{ position: "absolute", inset: 0, zIndex: 0 }}>

          <ChargingMap

            ref={mapRef}

            onSequenceStep={setSequenceStep}

          />

        </div>



        {/* ── LEFT OVERLAY PANEL ─────────────────────────── */}

        <div

          style={{

            position: "absolute",

            top: "20px",

            left: "20px",

            width: "360px",

            maxWidth: "calc(100vw - 40px)",

            zIndex: 30,

            display: "flex",

            flexDirection: "column",

            gap: "10px",

            maxHeight: "calc(100vh - 100px)",

            overflowY: "auto",

          }}

        >



          {/* ── IDLE & LOCATED (PLANNING) ────────────────── */}

          {(phase === "idle" || phase === "located") && (

            <div className="anim-fade-in">

              <div className="glass" style={{ borderRadius: "20px", boxShadow: "0 8px 32px rgba(10,22,40,0.1)", overflow: "visible" }}>

                <div style={{ padding: "20px 22px 14px" }}>
                  <h1 style={{ fontFamily: "Times New Roman, serif", fontSize: "21px", fontWeight: 400, letterSpacing: "-0.015em", color: "var(--color-ink)", marginBottom: "6px", lineHeight: 1.2 }}>
                    Find the best locations for
                    <br /><em style={{ color: "var(--color-navy-700)" }}>new charging infrastructure</em>
                  </h1>
                  <p style={{ fontFamily: "Times New Roman, serif", fontSize: "13px", color: "var(--color-ink-3)", lineHeight: 1.5, margin: "0 0 12px" }}>
                    Select a planning area, set your station budget, and let AI and quantum optimisation identify the ideal sites.
                  </p>

                  {/* Story Presets for rapid presentation / judge demo */}
                  <div>
                    <div style={{ fontFamily: "Times New Roman, serif", fontSize: "10px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-ink-4)", marginBottom: "6px" }}>
                      Quick City Presets:
                    </div>
                    <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                      {[
                        { label: "🇺🇸 San Francisco", city: "San Francisco", country: "United States", lat: 37.8032, lng: -122.4005, count: 3, scen: "morning_peak" as const },
                        { label: "🇨🇳 Beijing", city: "Beijing", country: "China", lat: 39.9096, lng: 116.3445, count: 3, scen: "afternoon" as const },
                        { label: "🇮🇳 Mumbai", city: "Mumbai", country: "India", lat: 19.0467, lng: 72.8911, count: 3, scen: "all_hours" as const },
                        { label: "🇺🇸 Chicago", city: "Chicago", country: "United States", lat: 41.9003, lng: -87.7022, count: 3, scen: "weekday" as const },
                        { label: "🇺🇸 Los Angeles", city: "Los Angeles", country: "United States", lat: 34.0923, lng: -118.2904, count: 3, scen: "overnight" as const },
                      ].map((preset) => (
                        <button
                          key={preset.label}
                          type="button"
                          onClick={() => {
                            handleTriggerCityOptimization(
                              preset.city,
                              preset.country,
                              preset.lat,
                              preset.lng,
                              preset.count,
                              preset.scen
                            );
                          }}
                          style={{
                            padding: "4px 8px",
                            borderRadius: "6px",
                            border: "1px solid var(--color-border)",
                            background: "var(--color-grey-50)",
                            fontFamily: "Times New Roman, serif",
                            fontSize: "11px",
                            color: "var(--color-navy-900)",
                            cursor: "pointer",
                            transition: "all 0.12s ease",
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = "var(--color-navy-100)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = "var(--color-grey-50)";
                          }}
                        >
                          {preset.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Country and City Selector */}
                <div style={{ padding: "14px 22px 14px", borderTop: "1px solid var(--color-border-subtle)" }}>
                  <CountryCitySelector
                    selectedCountry={selectedCountry}
                    selectedCity={selectedCity}
                    onCountrySelect={handleCountrySelect}
                    onCitySelect={handleCitySelect}
                  />
                </div>

                <PlanningControls
                  stationCount={stationCount}
                  onStationCountChange={setStationCount}
                  scenario={scenario}
                  onScenarioChange={setScenario}
                />

                {/* Find Optimal Locations CTA button */}
                <div style={{ padding: "14px 22px" }}>
                  <button
                    onClick={handleSearch}
                    style={{
                      width: "100%", padding: "14px", borderRadius: "12px", border: "none",
                      background: "var(--color-navy-900)", color: "white",
                      fontFamily: "Times New Roman, serif", fontSize: "15px", fontWeight: 600, letterSpacing: "-0.005em",
                      cursor: "pointer", transition: "opacity 0.2s ease, transform 0.15s ease",
                      boxShadow: "0 4px 16px rgba(10,22,40,0.22)",
                      display: "flex", alignItems: "center", justifyContent: "center", gap: "8px",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.opacity = "0.9"; e.currentTarget.style.transform = "translateY(-1px)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.opacity = "1"; e.currentTarget.style.transform = "translateY(0)"; }}
                  >
                    <span>⚡ Find Optimal Locations</span>
                    <span>→</span>
                  </button>
                </div>

              </div>

            </div>

          )}



          {/* ── SEARCHING ─────────────────────────────────── */}

          {phase === "searching" && (

            <div className="anim-scale-in">

              <div className="glass" style={{ borderRadius: "20px", overflow: "hidden", boxShadow: "0 8px 32px rgba(10,22,40,0.12)" }}>

                <OptimizationSequence currentStep={sequenceStep} />

              </div>

            </div>

          )}



          {/* ── RESULT ────────────────────────────────────── */}

          {phase === "result" && state.status === "success" && (

            <div className="anim-slide-up" ref={resultScrollRef}>

              <div className="glass" style={{ borderRadius: "20px", overflow: "hidden", boxShadow: "0 12px 48px rgba(10,22,40,0.16)" }}>

                <PlanningControls

                  stationCount={stationCount}

                  onStationCountChange={setStationCount}

                  scenario={scenario}

                  onScenarioChange={setScenario}

                />

                <ResultPanel
                  data={state.data}
                  userLat={userLat}
                  userLng={userLng}
                  locationName={locationName}
                  onReset={handleReset}
                  stationCount={stationCount}
                  scenario={scenario}
                  lastRunParams={lastRunParams}
                  onSearch={handleSearch}
                  onOpenQuantumModal={() => setQuantumModalOpen(true)}
                  onOpenReportModal={() => setReportModalOpen(true)}
                />

              </div>

            </div>

          )}



          {/* ── ERROR ─────────────────────────────────────── */}

          {phase === "error" && state.status === "error" && (

            <div className="anim-scale-in">

              <div className="glass" style={{ borderRadius: "20px", padding: "24px", boxShadow: "0 8px 32px rgba(10,22,40,0.12)" }}>

                <div style={{ width: "40px", height: "40px", borderRadius: "12px", background: "var(--color-negative-bg)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: "14px" }}>

                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">

                    <circle cx="8" cy="8" r="6.5" stroke="var(--color-negative)" strokeWidth="1.3" />

                    <path d="M8 5v3.5" stroke="var(--color-negative)" strokeWidth="1.3" strokeLinecap="round" />

                    <circle cx="8" cy="11" r="0.75" fill="var(--color-negative)" />

                  </svg>

                </div>

                <div style={{ fontFamily: "Times New Roman, serif", fontSize: "17px", color: "var(--color-ink)", marginBottom: "8px" }}>Analysis failed</div>

                <div style={{ fontFamily: "Times New Roman, serif", fontSize: "13px", color: "var(--color-ink-3)", lineHeight: 1.6, marginBottom: "18px" }}>

                  {state.message}

                </div>

                <button

                  onClick={handleSearch}

                  style={{ width: "100%", padding: "11px", borderRadius: "10px", border: "none", background: "var(--color-navy-900)", color: "white", fontFamily: "Times New Roman, serif", fontSize: "14px", cursor: "pointer" }}

                >

                  Try again

                </button>

              </div>

            </div>

          )}

        </div>



        {/* ── BOTTOM LEGEND ──────────────────────────────── */}

        {phase === "idle" && (

          <div className="anim-fade-in d-3" style={{ position: "absolute", bottom: "28px", left: "50%", transform: "translateX(-50%)", zIndex: 20, pointerEvents: "none" }}>

            <div className="glass" style={{ borderRadius: "99px", padding: "7px 16px", boxShadow: "0 4px 20px rgba(10,22,40,0.1)", display: "flex", alignItems: "center", gap: "16px" }}>

              <span style={{ fontFamily: "Times New Roman, serif", fontSize: "12px", color: "var(--color-ink-3)", whiteSpace: "nowrap" }}>
                8 candidate deployment zones · {selectedCity}, {selectedCountry}
              </span>

            </div>

          </div>

        )}



        {/* ── MAP LEGEND (result state) ───────────────────── */}

        {phase === "result" && (

          <div

            className="anim-fade-in"

            style={{

              position: "absolute", bottom: "28px", right: "60px", zIndex: 20,

              pointerEvents: "none",

            }}

          >

            <div className="glass" style={{ borderRadius: "12px", padding: "10px 14px", boxShadow: "0 4px 20px rgba(10,22,40,0.1)" }}>

              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>

                {[

                  { color: "var(--color-navy-900)", border: "2.5px solid white", label: "Recommended site" },

                  { color: "rgba(10,22,40,0.05)", border: "1.5px dashed rgba(10,22,40,0.2)", label: "Coverage area" },

                  { color: "white", border: "1.5px solid rgba(10,22,40,0.25)", label: "Candidate site" },

                ].map(({ color, border, label }) => (

                  <div key={label} style={{ display: "flex", alignItems: "center", gap: "8px" }}>

                    <div style={{ width: "12px", height: "12px", borderRadius: "50%", background: color, border, flexShrink: 0 }} />

                    <span style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", color: "var(--color-ink-3)", whiteSpace: "nowrap" }}>{label}</span>

                  </div>

                ))}

              </div>

            </div>

          </div>

        )}

      </div>



      {/* ── HOW IT WORKS ───────────────────────────────────── */}
      <HowItWorks data={state.status === "success" ? state.data : undefined} />

      {/* Quantum Scalability & IBM Hardware Modal */}
      <QuantumAdvantageModal
        isOpen={quantumModalOpen}
        onClose={() => setQuantumModalOpen(false)}
      />

      {/* Municipal Executive Briefing Export Modal */}
      <ExecutiveReportModal
        isOpen={reportModalOpen}
        onClose={() => setReportModalOpen(false)}
        data={state.status === "success" ? state.data : null}
        locationName={locationName}
        stationCount={stationCount}
        scenario={scenario}
      />
    </div>
  );
}
