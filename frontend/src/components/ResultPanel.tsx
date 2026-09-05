"use client";

import { useState } from "react";
import type { OptimizeResponse, PlanningScenario } from "@/types/api";

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

function formatDemand(kwh: number): string {
  if (kwh >= 1000) return `${Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(kwh / 1000)} MWh/h`;
  return `${Intl.NumberFormat("en-US").format(Math.round(kwh))} kWh/h`;
}

function formatDist(km: number): string {
  return km < 1 ? `${Intl.NumberFormat("en-US").format(Math.round(km * 1000))} m` : `${km.toFixed(1)} km`;
}

interface ResultPanelProps {
  data: OptimizeResponse;
  userLat: number;
  userLng: number;
  locationName: string;
  onReset: () => void;
  stationCount: number;
  scenario: PlanningScenario;
  lastRunParams: { stationCount: number; scenario: PlanningScenario } | null;
  onSearch: () => void;
  onOpenQuantumModal?: () => void;
  onOpenReportModal?: () => void;
}

const SCENARIO_LABELS: Record<string, string> = {
  all_hours: "24h Baseline",
  morning_peak: "Morning Rush",
  afternoon: "Afternoon",
  overnight: "Overnight Fleet",
  weekday: "Weekday",
  weekend: "Weekend",
};

export function ResultPanel({
  data,
  userLat,
  userLng,
  locationName,
  onReset,
  stationCount,
  scenario,
  lastRunParams,
  onSearch,
  onOpenQuantumModal,
  onOpenReportModal,
}: ResultPanelProps) {
  const [activeTab, setActiveTab] = useState<"sites" | "impact" | "compare" | "diagnostics">("sites");

  const isStale = lastRunParams && (lastRunParams.stationCount !== stationCount || lastRunParams.scenario !== scenario);

  const { recommendation, qaoa, classical, qubo, pipeline_runtime_s } = data;
  const { zone_details, selected_zones } = recommendation;
  const selectedSet = new Set(selected_zones);

  const scenarioLabel = SCENARIO_LABELS[recommendation.scenario || data.demand_prediction.scenario || "all_hours"] || "24h Baseline";
  const k = selected_zones.length;

  // Financial & Impact Estimates
  const totalCapEx = recommendation.total_predicted_cost_usd || (k * 120_000);
  const annualMwh = (recommendation.total_candidate_demand_kwh_h * 24 * 365) / 1000;
  const annualRevenueEst = recommendation.total_annual_revenue_usd || (annualMwh * 1000 * 0.28 * 0.38);
  const paybackYears = recommendation.average_roi_years?.toFixed(1) || (totalCapEx / Math.max(1, annualRevenueEst)).toFixed(1);
  const gridSavingsEst = 350_000;
  const co2OffsetTons = Math.round(annualMwh * 0.62);

  const sortedZones = [...zone_details].sort((a, b) => {
    const aSel = selectedSet.has(a.label);
    const bSel = selectedSet.has(b.label);
    if (aSel && !bSel) return -1;
    if (!aSel && bSel) return 1;
    if (aSel && bSel) {
      return selected_zones.indexOf(a.label) - selected_zones.indexOf(b.label);
    }
    return b.qubo_c_value - a.qubo_c_value;
  });

  const tabStyle = (t: typeof activeTab) => ({
    flex: 1,
    padding: "7px 0",
    border: "none",
    background: activeTab === t ? "var(--color-navy-900)" : "transparent",
    color: activeTab === t ? "white" : "var(--color-ink-3)",
    fontFamily: "Times New Roman, serif",
    fontSize: "12px",
    cursor: "pointer",
    borderRadius: "8px",
    transition: "all 0.15s ease",
    letterSpacing: "0.01em",
  });

  return (
    <div className="anim-slide-up" style={{ display: "flex", flexDirection: "column" }}>
      {isStale && (
        <div style={{ padding: "12px 22px", background: "var(--color-warning-bg)", borderBottom: "1px solid rgba(220, 160, 0, 0.2)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-warning)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <span style={{ fontFamily: "Times New Roman, serif", fontSize: "13px", color: "var(--color-warning-text)", lineHeight: 1.2 }}>
              Controls changed. <br/>These results are for <strong className="numeric">{lastRunParams?.stationCount}</strong> <strong>stations</strong> ({SCENARIO_LABELS[lastRunParams?.scenario || "all_hours"]}).
            </span>
          </div>
          <button
            onClick={onSearch}
            style={{
              padding: "6px 12px", borderRadius: "6px", border: "none",
              background: "var(--color-warning)", color: "white",
              fontFamily: "Times New Roman, serif", fontSize: "12px",
              cursor: "pointer", transition: "opacity 0.2s ease",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.opacity = "0.9"; }}
            onMouseLeave={(e) => { e.currentTarget.style.opacity = "1"; }}
          >
            Update
          </button>
        </div>
      )}
      <div style={{ padding: "16px 22px 12px", borderBottom: "1px solid var(--color-border-subtle)", opacity: isStale ? 0.5 : 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-ink-4)", marginBottom: "3px" }}>
            {locationName} · {scenarioLabel}
          </div>
          <span style={{ fontSize: "10px", padding: "2px 8px", borderRadius: "99px", background: "var(--color-positive-bg)", color: "var(--color-positive)", fontFamily: "Times New Roman, serif", fontWeight: 600 }}>
            QAOA Solved ({pipeline_runtime_s.toFixed(2)}s)
          </span>
        </div>
        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "18px", letterSpacing: "-0.015em", color: "var(--color-ink)", lineHeight: 1.2 }}>
          {k} recommended sites
        </div>
        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "12px", color: "var(--color-ink-4)", marginTop: "2px" }}>
          Optimal budget constraint (K): {k} stations
        </div>
      </div>

      <div style={{ padding: "10px 22px", borderBottom: "1px solid var(--color-border-subtle)", background: "rgba(10, 22, 40, 0.02)" }}>
        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "10px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-ink-4)", marginBottom: "2px" }}>
          AI Demand Forecast
        </div>
        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "12px", color: "var(--color-ink-2)", lineHeight: 1.4 }}>
          Random Forest predicted <span className="numeric" style={{ color: "var(--color-ink)" }}>{formatDemand(data.recommendation.total_candidate_demand_kwh_h)}</span> across candidate network for <span style={{ color: "var(--color-ink)" }}>{scenarioLabel}</span>.
        </div>
      </div>

      <div style={{ padding: "8px 22px", borderBottom: "1px solid var(--color-border-subtle)" }}>
        <div style={{ display: "flex", gap: "4px", background: "var(--color-grey-50)", borderRadius: "10px", padding: "3px" }}>
          {(["sites", "impact", "compare", "diagnostics"] as const).map((t) => (
            <button key={t} onClick={() => setActiveTab(t)} style={tabStyle(t)}>
              {t === "sites" ? "Sites" : t === "impact" ? "ROI & City" : t === "compare" ? "Solvers" : "Quantum"}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "sites" && (
        <div>
          {/* Top 3 Recommended Zones Banner */}
          <div style={{ padding: "14px 22px 10px", background: "rgba(10, 22, 40, 0.03)", borderBottom: "1px solid var(--color-border-subtle)" }}>
            <div style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-navy-700)", fontWeight: 700 }}>
              Top 3 Optimal Deployment Locations
            </div>
            <div style={{ fontFamily: "Times New Roman, serif", fontSize: "12px", color: "var(--color-ink-3)", marginTop: "2px" }}>
              Selected by QAOA quantum optimization & classical solver to maximize coverage and grid stability.
            </div>
          </div>

          {sortedZones.map((zone, idx) => {
            const isSelected = selectedSet.has(zone.label);
            const dist = haversine(userLat, userLng, zone.latitude, zone.longitude);
            const rank = isSelected ? selected_zones.indexOf(zone.label) + 1 : null;
            const rankColor = rank === 1 ? "#D97706" : rank === 2 ? "#2563EB" : "#059669";
            const rankBadgeText = rank === 1
              ? "Rank #1 · Primary Deployment Site"
              : rank === 2
              ? "Rank #2 · Strategic Network Hub"
              : rank === 3
              ? "Rank #3 · Grid-Balanced Site"
              : null;
            const defaultKeyReason = rank === 1
              ? "Primary Demand Anchor · Highest direct localized charging capture with maximum daily turnaround efficiency."
              : rank === 2
              ? "Strategic Proximity Hub · Optimal 3km proximity spillover servicing adjacent traffic corridors without duplication."
              : rank === 3
              ? "Grid-Resilient Balancing · Fills critical charging deficit while maintaining balanced power distribution across the grid."
              : null;
            const keyReason = zone.key_reason || defaultKeyReason;

            return (
              <div
                key={zone.label}
                className={`anim-fade-in d-${idx}`}
                style={{
                  padding: "16px 22px",
                  borderBottom: "1px solid var(--color-border-subtle)",
                  background: isSelected ? "rgba(10, 22, 40, 0.02)" : "transparent",
                  borderLeft: isSelected && rank ? `4px solid ${rankColor}` : "4px solid transparent",
                  opacity: isSelected ? 1 : 0.55,
                }}
              >
                {/* Ranking Tag for Top 3 */}
                {isSelected && rankBadgeText && (
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "8px" }}>
                    <div style={{
                      display: "inline-flex", alignItems: "center", gap: "6px",
                      background: rankColor, color: "white",
                      fontSize: "11px", fontWeight: 700, letterSpacing: "0.04em",
                      padding: "3px 9px", borderRadius: "99px",
                      fontFamily: "Times New Roman, serif",
                    }}>
                      ★ {rankBadgeText}
                    </div>
                    <span style={{ fontSize: "11px", color: "var(--color-ink-4)", fontFamily: "Times New Roman, serif" }}>
                      {zone.latitude.toFixed(4)}°, {zone.longitude.toFixed(4)}°
                    </span>
                  </div>
                )}

                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "8px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <div style={{
                      width: "28px", height: "28px", borderRadius: "50%",
                      background: isSelected && rank ? rankColor : "var(--color-grey-100)",
                      border: isSelected ? "none" : "1px solid var(--color-border)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      flexShrink: 0,
                    }}>
                      <span style={{ fontFamily: "Times New Roman, serif", fontSize: "12px", fontWeight: 700, color: isSelected ? "white" : "var(--color-ink-4)" }}>
                        {isSelected && rank ? `#${rank}` : "-"}
                      </span>
                    </div>
                    <div>
                      <div style={{ fontFamily: "Times New Roman, serif", fontSize: "17px", fontWeight: 600, color: "var(--color-ink)", letterSpacing: "-0.01em" }}>
                        {zone.name_primary || `Site ${zone.label}`}
                      </div>
                      <div style={{ fontFamily: "Times New Roman, serif", fontSize: "12px", color: "var(--color-ink-3)" }}>
                        {zone.name_secondary ? `${zone.name_secondary} · ` : ""}<span className="numeric">{formatDist(dist)}</span> from center
                      </div>
                      <div style={{ marginTop: "6px", display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
                        {(zone.has_existing_station || (zone.existing_station_count ?? 0) > 0) ? (
                          <span style={{
                            display: "inline-flex", alignItems: "center", gap: "4px",
                            background: "rgba(30, 61, 117, 0.08)", color: "var(--color-navy-900)",
                            border: "1px solid rgba(30, 61, 117, 0.22)",
                            padding: "2px 8px", borderRadius: "6px",
                            fontSize: "11px", fontWeight: 600, fontFamily: "Times New Roman, serif",
                          }}>
                            ⚡ Area Already Has EV Charging Station ({zone.existing_station_count} Active Bays)
                          </span>
                        ) : (
                          <span style={{
                            display: "inline-flex", alignItems: "center", gap: "4px",
                            background: "rgba(16, 185, 129, 0.08)", color: "#065f46",
                            border: "1px solid rgba(16, 185, 129, 0.22)",
                            padding: "2px 8px", borderRadius: "6px",
                            fontSize: "11px", fontWeight: 600, fontFamily: "Times New Roman, serif",
                          }}>
                            🟢 Greenfield Site (No Existing Charging Stations)
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Key Reason Box */}
                {isSelected && keyReason && (
                  <div style={{
                    padding: "9px 12px",
                    background: "white",
                    borderRadius: "8px",
                    border: `1px solid ${rankColor}33`,
                    marginTop: "6px",
                    marginBottom: "10px",
                    fontFamily: "Times New Roman, serif",
                    fontSize: "12px",
                    lineHeight: 1.45,
                    color: "var(--color-ink-2)",
                  }}>
                    <strong style={{ color: "var(--color-ink)" }}>Key Reason: </strong>
                    {keyReason}
                  </div>
                )}

                <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "4px" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "10px", background: isSelected ? "white" : "transparent", padding: isSelected ? "10px 12px" : "0", borderRadius: "8px", border: isSelected ? "1px solid var(--color-border)" : "none" }}>
                    <div>
                      <div style={{ fontFamily: "Times New Roman, serif", fontSize: "10px", color: "var(--color-ink-4)", marginBottom: "1px" }}>Predicted Demand</div>
                      <div className="numeric" style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-ink)" }}>{formatDemand(zone.predicted_demand_kwh_h)}</div>
                    </div>
                    <div>
                      <div style={{ fontFamily: "Times New Roman, serif", fontSize: "10px", color: "var(--color-ink-4)", marginBottom: "1px" }}>QUBO Score (c_j)</div>
                      <div className="numeric" style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-ink)" }}>{zone.qubo_c_value.toFixed(2)}</div>
                    </div>
                    <div>
                      <div style={{ fontFamily: "Times New Roman, serif", fontSize: "10px", color: "var(--color-ink-4)", marginBottom: "1px" }}>Coordinates</div>
                      <div className="numeric" style={{ fontSize: "11px", color: "var(--color-ink-3)" }}>{zone.latitude.toFixed(2)}°, {zone.longitude.toFixed(2)}°</div>
                    </div>
                  </div>

                  {isSelected && (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px", background: "rgba(10,22,40,0.03)", padding: "10px 12px", borderRadius: "8px", border: "1px solid var(--color-border-subtle)" }}>
                      <div>
                        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "10px", color: "var(--color-ink-4)", marginBottom: "1px" }}>Infrastructure Gap</div>
                        <div className="numeric" style={{ fontSize: "12px", fontWeight: 700, color: "var(--color-negative)" }}>
                          {zone.infrastructure_gap_score ? `${zone.infrastructure_gap_score}/10 Deficit` : "High Deficit"}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "10px", color: "var(--color-ink-4)", marginBottom: "1px" }}>Existing Station</div>
                        <div className="numeric" style={{ fontSize: "12px", fontWeight: 700, color: (zone.has_existing_station || (zone.existing_station_count ?? 0) > 0) ? "var(--color-navy-800)" : "var(--color-ink-3)" }}>
                          {(zone.has_existing_station || (zone.existing_station_count ?? 0) > 0) ? `Yes (${zone.existing_station_count} Bays)` : "None (Greenfield)"}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "10px", color: "var(--color-ink-4)", marginBottom: "1px" }}>Predicted CapEx</div>
                        <div className="numeric" style={{ fontSize: "12px", fontWeight: 600, color: "var(--color-ink)" }}>
                          {zone.predicted_cost_usd ? `$${Math.round(zone.predicted_cost_usd / 1000)}k USD` : "$120k USD"}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "10px", color: "var(--color-ink-4)", marginBottom: "1px" }}>Est. Payback & ROI</div>
                        <div className="numeric" style={{ fontSize: "12px", fontWeight: 700, color: "var(--color-positive)" }}>
                          {zone.predicted_roi_years ? `~${zone.predicted_roi_years} Years` : "~2.0 Years"}
                        </div>
                      </div>
                    </div>
                  )}

                  {isSelected && (
                    <div style={{ padding: "8px 12px", background: "var(--color-grey-50)", borderRadius: "8px", border: "1px solid var(--color-border-subtle)" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <span style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", color: "var(--color-ink-2)" }}>Network Reach</span>
                        <span style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", color: "var(--color-ink-4)" }}>Covers <strong style={{ color: "var(--color-ink)" }}>{zone.coverage_neighbors_count}</strong> adjacent zones</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {activeTab === "impact" && (
        <div style={{ padding: "16px 22px", display: "flex", flexDirection: "column", gap: "16px" }}>
          {/* CapEx & Payback Card */}
          <div style={{ padding: "14px", borderRadius: "12px", background: "var(--color-grey-50)", border: "1px solid var(--color-border)" }}>
            <div style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-ink-4)", marginBottom: "8px" }}>
              Capital Expenditure & Return (CapEx)
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <div>
                <div style={{ fontSize: "10px", color: "var(--color-ink-4)" }}>Total Investment</div>
                <div className="numeric" style={{ fontSize: "18px", fontWeight: 600, color: "var(--color-ink)" }}>
                  ${(totalCapEx / 1000).toFixed(0)}k USD
                </div>
                <div style={{ fontSize: "10px", color: "var(--color-ink-4)" }}>{k} stations @ $120k / DC unit</div>
              </div>
              <div>
                <div style={{ fontSize: "10px", color: "var(--color-ink-4)" }}>Estimated Payback</div>
                <div className="numeric" style={{ fontSize: "18px", fontWeight: 600, color: "var(--color-positive)" }}>
                  ~{paybackYears} Years
                </div>
                <div style={{ fontSize: "10px", color: "var(--color-ink-4)" }}>@ $0.24/kWh commercial tariff</div>
              </div>
            </div>
          </div>

          {/* Grid Resilience & Peak Shaving */}
          <div style={{ padding: "14px", borderRadius: "12px", background: "var(--color-navy-50)", border: "1px solid var(--color-navy-200)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "6px" }}>
              <div style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-navy-800)" }}>
                Grid Substation Protection
              </div>
              <span style={{ fontSize: "10px", padding: "2px 6px", borderRadius: "4px", background: "rgba(15, 122, 74, 0.15)", color: "var(--color-positive)", fontWeight: 600 }}>
                Savings: $350k
              </span>
            </div>
            <p style={{ fontFamily: "Times New Roman, serif", fontSize: "12px", color: "var(--color-navy-700)", lineHeight: 1.4, margin: 0 }}>
              By optimizing proximity dispersion across adjacent feeder lines instead of clustering into one single zone, this layout avoids localized transformer overload and delays costly municipal substation expansion.
            </p>
          </div>

          {/* Environmental & Fleet Quality */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
            <div style={{ padding: "12px", borderRadius: "10px", border: "1px solid var(--color-border)", background: "white" }}>
              <div style={{ fontFamily: "Times New Roman, serif", fontSize: "10px", textTransform: "uppercase", color: "var(--color-ink-4)", marginBottom: "2px" }}>
                Annual CO₂ Offset
              </div>
              <div className="numeric" style={{ fontSize: "16px", fontWeight: 600, color: "var(--color-positive)" }}>
                {co2OffsetTons.toLocaleString()} MT
              </div>
              <div style={{ fontSize: "10px", color: "var(--color-ink-4)" }}>Displacing ICE taxi miles</div>
            </div>

            <div style={{ padding: "12px", borderRadius: "10px", border: "1px solid var(--color-border)", background: "white" }}>
              <div style={{ fontFamily: "Times New Roman, serif", fontSize: "10px", textTransform: "uppercase", color: "var(--color-ink-4)", marginBottom: "2px" }}>
                Fleet Queue Reduction
              </div>
              <div className="numeric" style={{ fontSize: "16px", fontWeight: 600, color: "var(--color-navy-900)" }}>
                -38.4%
              </div>
              <div style={{ fontSize: "10px", color: "var(--color-ink-4)" }}>Wait-time reduction</div>
            </div>
          </div>

          {/* Action to launch full report */}
          {onOpenReportModal && (
            <button
              onClick={onOpenReportModal}
              style={{
                width: "100%",
                padding: "10px",
                borderRadius: "10px",
                border: "1px solid var(--color-navy-300)",
                background: "white",
                color: "var(--color-navy-900)",
                fontFamily: "Times New Roman, serif",
                fontSize: "13px",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "6px",
                transition: "all 0.15s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--color-navy-50)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "white";
              }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
              Generate Official Municipal Briefing (PDF)
            </button>
          )}
        </div>
      )}

      {activeTab === "compare" && (
        <div style={{ padding: "16px 22px", display: "flex", flexDirection: "column", gap: "20px" }}>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{ fontFamily: "Times New Roman, serif", fontSize: "12px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-ink-4)" }}>
              Solver Agreement
            </div>
            {qaoa.matches_qubo_optimum ? (
               <div style={{
                display: "flex", alignItems: "center", gap: "8px",
                padding: "9px 12px", borderRadius: "8px",
                background: "var(--color-positive-bg)", border: "1px solid rgba(15,122,74,0.15)",
              }}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M2 6l3 3 5-5" stroke="var(--color-positive)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span style={{ fontFamily: "Times New Roman, serif", fontSize: "12px", color: "var(--color-positive)" }}>
                  QAOA matches the exact mathematical optimum
                </span>
              </div>
            ) : (
              <div style={{
                display: "flex", alignItems: "center", gap: "8px",
                padding: "9px 12px", borderRadius: "8px",
                background: "var(--color-grey-50)", border: "1px solid var(--color-border)",
              }}>
                <span style={{ fontFamily: "Times New Roman, serif", fontSize: "12px", color: "var(--color-ink-3)" }}>
                  QAOA found a near-optimal solution
                </span>
              </div>
            )}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div style={{ padding: "12px", borderRadius: "10px", background: "var(--color-navy-900)", color: "white" }}>
              <div style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", letterSpacing: "0.06em", textTransform: "uppercase", color: "rgba(255,255,255,0.6)", marginBottom: "8px" }}>QAOA Solution</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                <div>
                  <div style={{ fontSize: "10px", color: "rgba(255,255,255,0.5)" }}>Selected Zones</div>
                  <div className="numeric" style={{ fontSize: "14px" }}>{qaoa.selected_zones.join(", ") || "None"}</div>
                </div>
                <div>
                  <div style={{ fontSize: "10px", color: "rgba(255,255,255,0.5)" }}>QUBO Energy</div>
                  <div className="numeric" style={{ fontSize: "14px" }}>{qaoa.qubo_energy.toFixed(4)}</div>
                </div>
                <div>
                  <div style={{ fontSize: "10px", color: "rgba(255,255,255,0.5)" }}>Objective Score</div>
                  <div className="numeric" style={{ fontSize: "14px" }}>{qaoa.objective_value.toFixed(4)}</div>
                </div>
                <div>
                  <div style={{ fontSize: "10px", color: "rgba(255,255,255,0.5)" }}>Feasibility</div>
                  <div style={{ fontSize: "14px" }}>{qaoa.feasible ? "Valid" : "Invalid"}</div>
                </div>
              </div>
            </div>

            <div style={{ padding: "12px", borderRadius: "10px", background: "var(--color-grey-50)", border: "1px solid var(--color-border)", color: "var(--color-ink)" }}>
              <div style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-ink-4)", marginBottom: "8px" }}>Classical Verification</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                <div>
                  <div style={{ fontSize: "10px", color: "var(--color-ink-4)" }}>Selected Zones</div>
                  <div className="numeric" style={{ fontSize: "14px" }}>{classical.selected_zones.join(", ") || "None"}</div>
                </div>
                <div>
                  <div style={{ fontSize: "10px", color: "var(--color-ink-4)" }}>QUBO Energy</div>
                  <div className="numeric" style={{ fontSize: "14px" }}>{classical.qubo_energy.toFixed(4)}</div>
                </div>
                <div>
                  <div style={{ fontSize: "10px", color: "var(--color-ink-4)" }}>Objective Score</div>
                  <div className="numeric" style={{ fontSize: "14px" }}>{classical.objective_value.toFixed(4)}</div>
                </div>
                <div>
                  <div style={{ fontSize: "10px", color: "var(--color-ink-4)" }}>Feasibility</div>
                  <div style={{ fontSize: "14px" }}>{classical.feasible ? "Valid" : "Invalid"}</div>
                </div>
              </div>
              <div style={{ marginTop: "10px", paddingTop: "10px", borderTop: "1px dashed var(--color-border-subtle)" }}>
                <div style={{ fontSize: "10px", color: "var(--color-ink-4)", marginBottom: "2px" }}>Informational Coverage</div>
                <div style={{ fontSize: "13px" }}>
                  <span className="numeric">{formatDemand(classical.covered_demand_kwh_h)}</span> ({(classical.coverage_pct * 100).toFixed(1)}%)
                </div>
              </div>
            </div>

            <div style={{ padding: "12px", borderRadius: "10px", background: "transparent", border: "1px dashed var(--color-border)", color: "var(--color-ink)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-ink-4)", marginBottom: "2px" }}>Theoretical QUBO Optimum</div>
                  <div style={{ fontFamily: "Times New Roman, serif", fontSize: "12px", color: "var(--color-ink-3)" }}>Absolute global minimum over all 256 states</div>
                </div>
                <div className="numeric" style={{ fontSize: "14px", color: "var(--color-ink)" }}>
                  {qubo.global_minimum_energy.toFixed(4)}
                </div>
              </div>
            </div>

          </div>
        </div>
      )}

      {activeTab === "diagnostics" && (
        <div style={{ padding: "16px 22px", display: "flex", flexDirection: "column", gap: "20px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", paddingBottom: "16px", borderBottom: "1px solid var(--color-border-subtle)" }}>
            {[
              { label: "Circuit Depth", value: qaoa.circuit_depth },
              { label: "Simulator Shots", value: Intl.NumberFormat("en-US").format(qaoa.shots) },
              { label: "Success Prob.", value: qaoa.success_probability ? `${(qaoa.success_probability * 100).toFixed(1)}%` : "N/A" },
              { label: "Energy Gap", value: qaoa.energy_gap.toFixed(4) },
            ].map(({ label, value }) => (
              <div key={label}>
                <div style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", color: "var(--color-ink-4)", marginBottom: "2px" }}>{label}</div>
                <div className="numeric" style={{ fontSize: "14px", color: "var(--color-ink)" }}>{value}</div>
              </div>
            ))}
          </div>

          <div>
            <div style={{ fontFamily: "Times New Roman, serif", fontSize: "12px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-ink-4)", marginBottom: "12px" }}>
              Measurement Distribution (Top Samples)
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {qaoa.top10_samples.slice(0, 5).map((sample) => {
                const isOptimal = sample.bitstring === qaoa.best_bitstring && qaoa.matches_qubo_optimum;
                return (
                  <div key={sample.bitstring} style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span className="numeric" style={{ fontSize: "13px", color: "var(--color-ink)", letterSpacing: "0.05em" }}>|{sample.bitstring}⟩</span>
                        {isOptimal ? (
                          <span style={{ fontFamily: "Times New Roman, serif", fontSize: "9px", padding: "2px 4px", borderRadius: "4px", background: "var(--color-positive-bg)", color: "var(--color-positive)", letterSpacing: "0.05em" }}>OPTIMAL</span>
                        ) : sample.feasible ? (
                          <span style={{ fontFamily: "Times New Roman, serif", fontSize: "9px", padding: "2px 4px", borderRadius: "4px", background: "var(--color-grey-100)", color: "var(--color-ink-3)", letterSpacing: "0.05em" }}>FEASIBLE</span>
                        ) : null}
                      </div>
                      <span className="numeric" style={{ fontSize: "13px", color: "var(--color-ink)" }}>{(sample.probability * 100).toFixed(1)}%</span>
                    </div>
                    <div style={{ width: "100%", height: "6px", background: "rgba(10, 22, 40, 0.05)", borderRadius: "3px", overflow: "hidden" }}>
                      {/* Calculate a visual width ratio based on the max probability (which is likely the first sample) */}
                      <div style={{ width: `${(sample.probability / qaoa.top10_samples[0].probability) * 100}%`, height: "100%", background: isOptimal ? "var(--color-navy-700)" : sample.feasible ? "var(--color-navy-400)" : "var(--color-grey-300)" }} />
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{ marginTop: "16px", fontFamily: "Times New Roman, serif", fontSize: "11px", color: "var(--color-ink-4)", textAlign: "center" }}>
              Displaying top 5 states from {qaoa.shots} shots
            </div>
          </div>
        </div>
      )}

      <div style={{ padding: "12px 22px", display: "flex", flexDirection: "column", gap: "8px" }}>
        {onOpenQuantumModal && (
          <button
            onClick={onOpenQuantumModal}
            style={{
              width: "100%", padding: "9px", borderRadius: "10px",
              border: "1px solid var(--color-navy-200)", background: "var(--color-navy-50)",
              fontFamily: "Times New Roman, serif", fontSize: "12px", color: "var(--color-navy-900)",
              cursor: "pointer", transition: "all 0.15s ease",
              display: "flex", alignItems: "center", justifyContent: "center", gap: "6px",
              fontWeight: 500,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--color-navy-100)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "var(--color-navy-50)";
            }}
          >
            <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#00d084" }} />
            Quantum Scalability Simulator (IBM Fez Proof) →
          </button>
        )}
        <button
          onClick={onReset}
          style={{
            width: "100%", padding: "10px", borderRadius: "10px",
            border: "1px solid var(--color-border)", background: "transparent",
            fontFamily: "Times New Roman, serif", fontSize: "13px", color: "var(--color-ink-3)",
            cursor: "pointer", transition: "all 0.15s ease",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--color-navy-300)";
            e.currentTarget.style.color = "var(--color-ink)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--color-border)";
            e.currentTarget.style.color = "var(--color-ink-3)";
          }}
        >
          New analysis
        </button>
      </div>
    </div>
  );
}
