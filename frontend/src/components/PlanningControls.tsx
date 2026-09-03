"use client";

import type { PlanningScenario } from "@/types/api";

interface PlanningControlsProps {
  stationCount: number;
  onStationCountChange: (n: number) => void;
  scenario: PlanningScenario;
  onScenarioChange: (s: PlanningScenario) => void;
  disabled?: boolean;
}

const STATION_OPTIONS = [2, 3, 4, 5];

const SCENARIO_OPTIONS: { id: PlanningScenario; label: string; timeDesc: string }[] = [
  { id: "all_hours", label: "24h Baseline", timeDesc: "All-day average demand across candidate zones" },
  { id: "morning_peak", label: "Morning Rush (07:00–11:00)", timeDesc: "Commute window charging demand" },
  { id: "afternoon", label: "Afternoon (12:00–18:00)", timeDesc: "Daytime operational & taxi demand (shifts zone rankings)" },
  { id: "overnight", label: "Overnight (00:00–06:00)", timeDesc: "Nocturnal commercial fleet depot surge" },
  { id: "weekday", label: "Weekday (Mon–Fri)", timeDesc: "Business day commercial charging patterns" },
  { id: "weekend", label: "Weekend (Sat–Sun)", timeDesc: "Weekend public & leisure charging profiles" },
];

export function PlanningControls({
  stationCount,
  onStationCountChange,
  scenario,
  onScenarioChange,
  disabled,
}: PlanningControlsProps) {
  const activeScenarioObj = SCENARIO_OPTIONS.find((s) => s.id === scenario) || SCENARIO_OPTIONS[0];

  return (
    <div style={{ padding: "16px 22px", borderBottom: "1px solid var(--color-border-subtle)", display: "flex", flexDirection: "column", gap: "14px" }}>
      <div style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-ink-4)" }}>
        Planning parameters
      </div>

      {/* Station count selector */}
      <div>
        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "13px", color: "var(--color-ink-2)", marginBottom: "8px" }}>
          Stations to place
        </div>
        <div style={{ display: "flex", gap: "6px" }}>
          {STATION_OPTIONS.map((n) => (
            <button
              key={n}
              onClick={() => !disabled && onStationCountChange(n)}
              disabled={disabled}
              style={{
                flex: 1,
                padding: "8px 0",
                borderRadius: "8px",
                border: n === stationCount ? "1.5px solid var(--color-navy-700)" : "1px solid var(--color-border)",
                background: n === stationCount ? "var(--color-navy-900)" : "transparent",
                color: n === stationCount ? "white" : "var(--color-ink-3)",
                fontFamily: "Times New Roman, serif",
                fontSize: "15px",
                cursor: disabled ? "not-allowed" : "pointer",
                transition: "all 0.15s ease",
                opacity: disabled ? 0.6 : 1,
              }}
              onMouseEnter={(e) => {
                if (!disabled && n !== stationCount) {
                  e.currentTarget.style.borderColor = "var(--color-navy-300)";
                  e.currentTarget.style.color = "var(--color-ink)";
                }
              }}
              onMouseLeave={(e) => {
                if (n !== stationCount) {
                  e.currentTarget.style.borderColor = "var(--color-border)";
                  e.currentTarget.style.color = "var(--color-ink-3)";
                }
              }}
            >
              <span className="numeric">{n}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Demand scenario selector */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
          <span style={{ fontFamily: "Times New Roman, serif", fontSize: "13px", color: "var(--color-ink-2)" }}>
            Demand scenario
          </span>
        </div>
        <select
          value={scenario}
          onChange={(e) => !disabled && onScenarioChange(e.target.value as PlanningScenario)}
          disabled={disabled}
          style={{
            width: "100%",
            padding: "9px 12px",
            borderRadius: "8px",
            border: "1px solid var(--color-border)",
            background: "white",
            color: "var(--color-ink)",
            fontFamily: "Times New Roman, serif",
            fontSize: "13px",
            cursor: disabled ? "not-allowed" : "pointer",
            outline: "none",
            transition: "border-color 0.15s ease",
          }}
        >
          {SCENARIO_OPTIONS.map((opt) => (
            <option key={opt.id} value={opt.id}>
              {opt.label}
            </option>
          ))}
        </select>
        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", color: "var(--color-ink-4)", marginTop: "5px", lineHeight: 1.4 }}>
          {activeScenarioObj.timeDesc}
        </div>
      </div>
    </div>
  );
}