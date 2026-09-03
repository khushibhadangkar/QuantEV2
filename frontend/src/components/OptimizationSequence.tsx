"use client";



import { useEffect, useState } from "react";



const STAGES = [

  {

    id: "demand",

    num: "01",

    label: "FORECASTING EV DEMAND",

    detail: "Random Forest · 8 candidate zones",

    mapAction: "Plotting predicted demand heatmap…",

  },

  {

    id: "gaps",

    num: "02",

    label: "DETECTING COVERAGE GAPS",

    detail: "Evaluating coverage gaps",

    mapAction: "Scanning for infrastructure gaps…",

  },

  {

    id: "eval",

    num: "03",

    label: "EVALUATING CANDIDATE SITES",

    detail: "Demand-weighted proximity objective",

    mapAction: "Evaluating 8 candidate locations…",

  },

  {

    id: "qaoa",

    num: "04",

    label: "RUNNING QAOA OPTIMISATION",

    detail: "8 qubits · QAOA",

    mapAction: "Quantum circuit executing…",

  },

  {

    id: "result",

    num: "05",

    label: "BUILDING FINAL RECOMMENDATION",

    detail: "Exact optimum verified",

    mapAction: "Finalising infrastructure plan…",

  },

];



interface OptimizationSequenceProps {

  currentStep?: number; // externally driven step (0-4)

}



export function OptimizationSequence({ currentStep }: OptimizationSequenceProps) {

  const activeStep = currentStep ?? 0;



  return (

    <div className="anim-slide-up" style={{ padding: "20px 22px", display: "flex", flexDirection: "column", gap: "4px" }}>

      {/* Header */}

      <div style={{ marginBottom: "14px" }}>

        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-ink-4)", marginBottom: "4px" }}>

          Infrastructure analysis

        </div>

        <div style={{ fontFamily: "Times New Roman, serif", fontSize: "16px", color: "var(--color-ink)", letterSpacing: "-0.01em" }}>

          Optimising station placement…

        </div>

      </div>



      {STAGES.map((stage, i) => {

        const isActive = i === activeStep;

        const isDone = i < activeStep;

        const isFuture = i > activeStep;



        return (

          <div

            key={stage.id}

            style={{

              display: "flex",

              alignItems: "flex-start",

              gap: "12px",

              padding: "10px 0",

              borderBottom: i < STAGES.length - 1 ? "1px solid var(--color-border-subtle)" : "none",

              opacity: isFuture ? 0.35 : 1,

              transition: "opacity 0.4s ease",

            }}

          >

            {/* Step indicator */}

            <div style={{

              fontFamily: "var(--font-mono)",

              fontSize: "11px",

              color: isDone ? "var(--color-positive)" : (isActive ? "var(--color-navy-700)" : "var(--color-ink-4)"),

              marginTop: "2px",

              width: "16px",

              flexShrink: 0,

            }}>

              {isDone ? (

                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ marginTop: "-2px" }}>

                  <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />

                </svg>

              ) : stage.num}

            </div>



            {/* Label + detail */}

            <div style={{ flex: 1, minWidth: 0 }}>

              <div style={{

                fontFamily: "Times New Roman, serif",

                fontSize: "11px",

                letterSpacing: "0.06em",

                textTransform: "uppercase",

                color: isActive ? "var(--color-ink)" : "var(--color-ink-4)",

                transition: "color 0.3s ease",

                lineHeight: 1.3

              }}>

                {stage.label}

              </div>

              {(isActive || isDone) && (

                <div

                  className="anim-fade-in"

                  style={{

                    fontFamily: "Times New Roman, serif",

                    fontSize: "13px",

                    color: isActive ? "var(--color-ink-2)" : "var(--color-ink-4)",

                    marginTop: "2px",

                    lineHeight: 1.4

                  }}

                >

                  {stage.detail}

                </div>

              )}

            </div>



            {/* Map action tag — only active */}

            {isActive && (

              <div

                className="anim-fade-in"

                style={{

                  flexShrink: 0,

                  fontFamily: "Times New Roman, serif",

                  fontSize: "11px",

                  color: "var(--color-navy-400)",

                  fontStyle: "italic",

                  whiteSpace: "nowrap",

                  marginTop: "1px",

                }}

              >

                {stage.mapAction}

              </div>

            )}

          </div>

        );

      })}

    </div>

  );

}
