"use client";

import { useState } from "react";
import type { OptimizeResponse } from "@/types/api";

interface HowItWorksProps {
  data?: OptimizeResponse;
}

export function HowItWorks({ data }: HowItWorksProps) {
  const [techOpen, setTechOpen] = useState(false);

  return (
    <section
      style={{
        background: "var(--color-fog)",
        borderTop: "1px solid var(--color-border-subtle)",
        padding: "80px 0 100px",
      }}
    >
      <div style={{ maxWidth: "800px", margin: "0 auto", padding: "0 32px" }}>
        {/* Header */}
        <div style={{ marginBottom: "56px" }}>
          <p
            style={{
              fontFamily: "Times New Roman, serif",
              fontSize: "12px",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--color-ink-4)",
              marginBottom: "12px",
            }}
          >
            Technology
          </p>
          <h2
            style={{
              fontFamily: "Times New Roman, serif",
              fontSize: "clamp(26px, 3vw, 38px)",
              fontWeight: 400,
              letterSpacing: "-0.02em",
              color: "var(--color-ink)",
              marginBottom: "16px",
              lineHeight: 1.2,
            }}
          >
            How QuantEV works
          </h2>
          <p
            style={{
              fontFamily: "Times New Roman, serif",
              fontSize: "16px",
              color: "var(--color-ink-3)",
              lineHeight: 1.7,
              maxWidth: "520px",
            }}
          >
            QuantEV is an infrastructure planning platform that uses AI demand forecasting
            and quantum optimisation to identify where new EV charging stations will
            have the greatest impact.
          </p>
        </div>

        {/* Five steps */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0", marginBottom: "48px" }}>
          {[
            {
              num: "01",
              title: "AI Demand Prediction",
              body: "A Random Forest machine learning model predicts the future EV charging demand (in kWh) needed at each candidate site, based on historical patterns and the selected temporal scenario.",
            },
            {
              num: "02",
              title: "Mathematical Objective",
              body: "The problem is formulated as a proximity-weighted demand objective. It balances the local predicted demand of a site with the spillover coverage it provides to nearby zones within a 3km radius.",
            },
            {
              num: "03",
              title: "Quantum Mapping (QUBO)",
              body: "This objective is mathematically encoded into a Quadratic Unconstrained Binary Optimization (QUBO) problem. An 8-qubit system is constructed, with penalty parameters enforcing the exact constraint of K stations.",
            },
            {
              num: "04",
              title: "Quantum Optimization (QAOA)",
              body: "A Quantum Approximate Optimization Algorithm (QAOA) circuit is executed on a quantum simulator. By evolving the quantum state over multiple layers, it converges toward the optimal infrastructure layout.",
            },
            {
              num: "05",
              title: "Classical Verification",
              body: "An exhaustive classical solver simultaneously evaluates all 256 possible states to find the absolute global mathematical minimum. The QAOA result is then verified against this theoretical optimum to guarantee correctness.",
            },
          ].map(({ num, title, body }, i) => (
            <div
              key={num}
              style={{
                display: "flex",
                gap: "24px",
                padding: "28px 0",
                borderBottom:
                  i < 4 ? "1px solid var(--color-border-subtle)" : "none",
              }}
            >
              <div
                style={{
                  fontFamily: "Times New Roman, serif",
                  fontSize: "13px",
                  color: "var(--color-ink-4)",
                  minWidth: "28px",
                  paddingTop: "3px",
                }}
              >
                {num}
              </div>
              <div>
                <div
                  style={{
                    fontFamily: "Times New Roman, serif",
                    fontSize: "18px",
                    color: "var(--color-ink)",
                    letterSpacing: "-0.01em",
                    marginBottom: "8px",
                    lineHeight: 1.3,
                  }}
                >
                  {title}
                </div>
                <div
                  style={{
                    fontFamily: "Times New Roman, serif",
                    fontSize: "14px",
                    color: "var(--color-ink-3)",
                    lineHeight: 1.7,
                  }}
                >
                  {body}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Technical details accordion — for judges */}
        {data && (
          <div>
            <button
              onClick={() => setTechOpen((v) => !v)}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                width: "100%",
                padding: "16px 20px",
                background: "white",
                border: "1px solid var(--color-border)",
                borderRadius: techOpen ? "14px 14px 0 0" : "14px",
                cursor: "pointer",
                transition: "border-color 0.2s",
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.borderColor = "var(--color-navy-300)")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.borderColor = techOpen ? "var(--color-border)" : "var(--color-border)")
              }
            >
              <span
                style={{
                  fontFamily: "Times New Roman, serif",
                  fontSize: "15px",
                  color: "var(--color-ink-2)",
                }}
              >
                Technical details
              </span>
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                style={{
                  color: "var(--color-ink-4)",
                  transform: techOpen ? "rotate(180deg)" : "none",
                  transition: "transform 0.25s ease",
                }}
              >
                <path
                  d="M2 4.5l5 5 5-5"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>

            {techOpen && (
              <div
                className="anim-slide-down"
                style={{
                  background: "white",
                  border: "1px solid var(--color-border)",
                  borderTop: "none",
                  borderRadius: "0 0 14px 14px",
                  overflow: "hidden",
                }}
              >
                {/* AI model */}
                <TechRow label="AI Model">
                  <div style={{ display: "flex", gap: "32px", flexWrap: "wrap" }}>
                    <TechStat label="Model" value={data.demand_prediction.model.replace("Regressor", "")} />
                    <TechStat
                      label="R²"
                      value={
                        data.demand_prediction.test_r2 != null
                          ? data.demand_prediction.test_r2.toFixed(3)
                          : "—"
                      }
                    />
                    <TechStat
                      label="MAE"
                      value={
                        data.demand_prediction.test_mae != null
                          ? `${data.demand_prediction.test_mae.toFixed(1)} kWh/h`
                          : "—"
                      }
                    />
                    <TechStat label="Inference" value={`${data.demand_prediction.prediction_time_ms.toFixed(0)} ms`} />
                  </div>
                </TechRow>

                {/* QUBO */}
                <TechRow label="Optimisation model (QUBO)">
                  <div style={{ display: "flex", gap: "32px", flexWrap: "wrap" }}>
                    <TechStat label="Variables" value={`${data.qubo.n_qubits} binary (one per zone)`} />
                    <TechStat label="Constraint K" value={`${data.qubo.budget_k} stations`} />
                    <TechStat label="Penalty λ" value={String(data.qubo.lambda)} />
                    <TechStat label="Min. energy" value={data.qubo.global_minimum_energy.toFixed(3)} />
                  </div>
                </TechRow>

                {/* QAOA */}
                <TechRow label="Quantum solver (QAOA)">
                  <div style={{ display: "flex", gap: "32px", flexWrap: "wrap" }}>
                    <TechStat label="Circuit depth" value={String(data.qaoa.circuit_depth)} />
                    <TechStat label="Ansatz reps (p)" value={String(data.qaoa.reps)} />
                    <TechStat label="Shots" value={data.qaoa.shots.toLocaleString()} />
                    <TechStat label="Runtime" value={`${data.qaoa.runtime_s.toFixed(2)} s`} />
                    <TechStat
                      label="Optimal found"
                      value={data.qaoa.matches_qubo_optimum ? "Yes ✓" : "Near-optimal"}
                    />
                    <TechStat label="Δ from optimum" value={data.qaoa.energy_gap.toFixed(4)} />
                  </div>
                </TechRow>

                {/* Classical comparison */}
                <TechRow label="Classical benchmark" noBorder>
                  <div style={{ display: "flex", gap: "32px", flexWrap: "wrap" }}>
                    <TechStat label="Method" value="Exhaustive search" />
                    <TechStat label="Zones found" value={data.classical.selected_zones.join(", ")} />
                    <TechStat label="Energy" value={data.classical.qubo_energy.toFixed(3)} />
                    <TechStat
                      label="Runtime"
                      value={
                        data.classical.runtime_s < 0.01
                          ? `${(data.classical.runtime_s * 1000).toFixed(1)} ms`
                          : `${data.classical.runtime_s.toFixed(3)} s`
                      }
                    />
                  </div>
                </TechRow>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function TechRow({
  label,
  children,
  noBorder,
}: {
  label: string;
  children: React.ReactNode;
  noBorder?: boolean;
}) {
  return (
    <div
      style={{
        padding: "20px 24px",
        borderBottom: noBorder ? "none" : "1px solid var(--color-border-subtle)",
      }}
    >
      <div
        style={{
          fontFamily: "Times New Roman, serif",
          fontSize: "11px",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--color-ink-4)",
          marginBottom: "12px",
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

function TechStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div
        style={{
          fontFamily: "Times New Roman, serif",
          fontSize: "11px",
          color: "var(--color-ink-4)",
          marginBottom: "3px",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: "Times New Roman, serif",
          fontSize: "16px",
          color: "var(--color-ink)",
          letterSpacing: "-0.01em",
        }}
      >
        {value}
      </div>
    </div>
  );
}
