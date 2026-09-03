"use client";



import { useRef, useState, useCallback } from "react";

import dynamic from "next/dynamic";

import { useOptimize } from "@/hooks/useOptimize";

import { SearchBar } from "@/components/SearchBar";

import { OptimizationSequence } from "@/components/OptimizationSequence";

import { ResultPanel } from "@/components/ResultPanel";

import { PlanningControls } from "@/components/PlanningControls";

import { HowItWorks } from "@/components/HowItWorks";

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



  const [phase, setPhase] = useState<UIPhase>("idle");

  const [userLat, setUserLat] = useState(22.625);

  const [userLng, setUserLng] = useState(114.075);

  const [locationName, setLocationName] = useState("Shenzhen");

  const [stationCount, setStationCount] = useState(3);

  const [scenario, setScenario] = useState<PlanningScenario>("all_hours");

  const [sequenceStep, setSequenceStep] = useState(0);



  const handleLocationSelect = useCallback((lat: number, lng: number, name: string) => {

    setUserLat(lat);

    setUserLng(lng);

    setLocationName(name);

    setPhase("located");

    mapRef.current?.setUserLocation(lat, lng);

  }, []);



  const handleSearch = useCallback(async () => {

    setPhase("searching");

    setSequenceStep(0);

    // Run the optimization sequence animation in parallel with the API call

    // We drive the sequence steps manually via the map

    const apiPromise = run(stationCount, scenario);



    // The map sequence runs independently; sequence steps 0-4 are paced below

    // We pass setSequenceStep as the callback

    // (zones will be empty for animation — we just need the sequence)

    // Start with a placeholder animation using cached zone positions if available

    // After API resolves, showResults drives the final map state

    await apiPromise;

  }, [run, stationCount, scenario]);



  // Transition on API state change (render-phase ref pattern)

  const prevStatusRef = useRef(state.status);

  if (state.status !== prevStatusRef.current) {

    prevStatusRef.current = state.status;

    if (state.status === "success") {

      // Drive map animation with microtask

      Promise.resolve().then(async () => {

        if (state.status !== "success") return;

        const { zone_details, selected_zones } = state.data.recommendation;

        // Run the full 5-stage optimization sequence on the map

        await mapRef.current?.runOptimizationSequence(zone_details);



        // Force sequence to completion state briefly before transitioning

        setSequenceStep(5);

        await new Promise((r) => setTimeout(r, 600));



        // Then reveal the results

        setPhase("result");

        mapRef.current?.showResults(zone_details, selected_zones);



        setTimeout(() => {

          resultScrollRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });

        }, 300);

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

    idle: "Infrastructure Planning · Shenzhen",

    located: "Planning area selected",

    searching: "Analysing…",

    result: "Recommendation ready",

    error: "Analysis failed",

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

        {phase === "idle" && <div style={{ width: "80px" }} />}

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



          {/* ── IDLE ──────────────────────────────────────── */}

          {phase === "idle" && (

            <div className="anim-fade-in">

              <div className="glass" style={{ borderRadius: "20px", marginBottom: "10px", boxShadow: "0 8px 32px rgba(10,22,40,0.1)", overflow: "hidden" }}>

                <div style={{ padding: "20px 22px 16px" }}>

                  <h1 style={{ fontFamily: "Times New Roman, serif", fontSize: "21px", fontWeight: 400, letterSpacing: "-0.015em", color: "var(--color-ink)", marginBottom: "6px", lineHeight: 1.2 }}>

                    Find the best locations for

                    <br /><em style={{ color: "var(--color-navy-700)" }}>new charging infrastructure</em>

                  </h1>

                  <p style={{ fontFamily: "Times New Roman, serif", fontSize: "13px", color: "var(--color-ink-3)", lineHeight: 1.5, margin: 0 }}>

                    Select a planning area, set your station budget, and let AI and quantum optimisation identify the ideal sites.

                  </p>

                </div>



                {/* Default planning area row */}

                <div style={{ padding: "12px 22px", borderTop: "1px solid var(--color-border-subtle)", display: "flex", alignItems: "center", gap: "10px" }}>

                  <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "var(--color-navy-900)", border: "2px solid white", boxShadow: "0 1px 4px rgba(10,22,40,0.25)", flexShrink: 0 }} />

                  <div style={{ flex: 1 }}>

                    <div style={{ fontFamily: "Times New Roman, serif", fontSize: "14px", color: "var(--color-ink)" }}>{locationName}</div>

                    <div className="numeric" style={{ fontSize: "11px", color: "var(--color-ink-4)" }}>

                      {userLat.toFixed(4)}°N, {userLng.toFixed(4)}°E

                    </div>

                  </div>

                  <span style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", color: "var(--color-ink-4)", letterSpacing: "0.04em" }}>

                    Default area

                  </span>

                </div>



                <PlanningControls

                  stationCount={stationCount}

                  onStationCountChange={setStationCount}

                  scenario={scenario}

                  onScenarioChange={setScenario}

                />



                {/* Run analysis button */}

                <div style={{ padding: "14px 22px" }}>

                  <button

                    onClick={handleSearch}

                    style={{

                      width: "100%", padding: "13px", borderRadius: "12px", border: "none",

                      background: "var(--color-navy-900)", color: "white",

                      fontFamily: "Times New Roman, serif", fontSize: "15px", letterSpacing: "-0.005em",

                      cursor: "pointer", transition: "opacity 0.2s ease, transform 0.15s ease",

                      boxShadow: "0 4px 16px rgba(10,22,40,0.22)",

                    }}

                    onMouseEnter={(e) => { e.currentTarget.style.opacity = "0.9"; e.currentTarget.style.transform = "translateY(-1px)"; }}

                    onMouseLeave={(e) => { e.currentTarget.style.opacity = "1"; e.currentTarget.style.transform = "translateY(0)"; }}

                  >

                    Run infrastructure analysis →

                  </button>

                </div>

              </div>

              <SearchBar onLocationSelect={handleLocationSelect} />

            </div>

          )}



          {/* ── LOCATED ───────────────────────────────────── */}

          {phase === "located" && (

            <div className="anim-scale-in">

              <div className="glass" style={{ borderRadius: "20px", overflow: "hidden", boxShadow: "0 8px 32px rgba(10,22,40,0.12)" }}>

                {/* Location row */}

                <div style={{ padding: "16px 22px", borderBottom: "1px solid var(--color-border-subtle)", display: "flex", alignItems: "center", gap: "10px" }}>

                  <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "var(--color-navy-900)", border: "2px solid white", boxShadow: "0 1px 4px rgba(10,22,40,0.25)", flexShrink: 0 }} />

                  <div style={{ flex: 1 }}>

                    <div style={{ fontFamily: "Times New Roman, serif", fontSize: "14px", color: "var(--color-ink)" }}>{locationName}</div>

                    <div className="numeric" style={{ fontSize: "11px", color: "var(--color-ink-4)" }}>

                      {userLat.toFixed(4)}°N, {userLng.toFixed(4)}°E

                    </div>

                  </div>

                  <button onClick={() => setPhase("idle")} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-ink-4)", fontFamily: "Times New Roman, serif", fontSize: "13px", padding: "4px 8px" }}>

                    Change

                  </button>

                </div>



                {/* Planning controls */}

                <PlanningControls

                  stationCount={stationCount}

                  onStationCountChange={setStationCount}

                  scenario={scenario}

                  onScenarioChange={setScenario}

                />



                {/* Analyse button */}

                <div style={{ padding: "14px 22px" }}>

                  <button

                    onClick={handleSearch}

                    style={{

                      width: "100%", padding: "13px", borderRadius: "12px", border: "none",

                      background: "var(--color-navy-900)", color: "white",

                      fontFamily: "Times New Roman, serif", fontSize: "15px", letterSpacing: "-0.005em",

                      cursor: "pointer", transition: "opacity 0.2s ease, transform 0.15s ease",

                      boxShadow: "0 4px 16px rgba(10,22,40,0.22)",

                    }}

                    onMouseEnter={(e) => { e.currentTarget.style.opacity = "0.9"; e.currentTarget.style.transform = "translateY(-1px)"; }}

                    onMouseLeave={(e) => { e.currentTarget.style.opacity = "1"; e.currentTarget.style.transform = "translateY(0)"; }}

                  >

                    Run infrastructure analysis →

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

                8 candidate zones · Shenzhen

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

    </div>

  );

}
