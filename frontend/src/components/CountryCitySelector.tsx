"use client";

import { useState, useId } from "react";

export interface GlobalCityOption {
  city: string;
  country: string;
  lat: number;
  lng: number;
  zoom: number;
  desc: string;
  flag: string;
}

export const SUPPORTED_COUNTRIES: { name: string; flag: string; cities: string[] }[] = [
  { name: "China", flag: "🇨🇳", cities: ["Beijing"] },
  { name: "India", flag: "🇮🇳", cities: ["Mumbai"] },
  { name: "United States", flag: "🇺🇸", cities: ["San Francisco", "Los Angeles", "Chicago"] },
];

export const CITY_CONFIGS: Record<string, GlobalCityOption> = {
  "Beijing": {
    city: "Beijing",
    country: "China",
    lat: 39.9096,
    lng: 116.3445,
    zoom: 12,
    desc: "Capital Metropolitan Region · 319 charging stations",
    flag: "🇨🇳",
  },
  "Mumbai": {
    city: "Mumbai",
    country: "India",
    lat: 19.0467,
    lng: 72.8911,
    zoom: 12,
    desc: "Financial Capital & Megacity · 315 charging stations",
    flag: "🇮🇳",
  },
  "San Francisco": {
    city: "San Francisco",
    country: "United States",
    lat: 37.8032,
    lng: -122.4005,
    zoom: 13,
    desc: "Bay Area Innovation Corridor · 324 charging stations",
    flag: "🇺🇸",
  },
  "Los Angeles": {
    city: "Los Angeles",
    country: "United States",
    lat: 34.0923,
    lng: -118.2904,
    zoom: 12,
    desc: "Southern California Metropolitan Core · 286 charging stations",
    flag: "🇺🇸",
  },
  "Chicago": {
    city: "Chicago",
    country: "United States",
    lat: 41.9003,
    lng: -87.7022,
    zoom: 12,
    desc: "Midwest Transit & Commercial Hub · 308 charging stations",
    flag: "🇺🇸",
  },
};

interface CountryCitySelectorProps {
  selectedCountry: string;
  selectedCity: string;
  onCountrySelect: (country: string) => void;
  onCitySelect: (city: string, country: string, lat: number, lng: number) => void;
  disabled?: boolean;
}

export function CountryCitySelector({
  selectedCountry,
  selectedCity,
  onCountrySelect,
  onCitySelect,
  disabled = false,
}: CountryCitySelectorProps) {
  const selectId = useId();
  const currentCountryObj = SUPPORTED_COUNTRIES.find((c) => c.name === selectedCountry) || SUPPORTED_COUNTRIES[2];
  const availableCities = currentCountryObj.cities;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* ── STEP 1: Country Selection ───────────────────────────── */}
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "8px" }}>
          <span style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-ink-4)" }}>
            Step 1 · Select Country
          </span>
          <span style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", color: "var(--color-navy-600)" }}>
            3 Available
          </span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px" }}>
          {SUPPORTED_COUNTRIES.map((c) => {
            const isSelected = c.name === selectedCountry;
            return (
              <button
                key={c.name}
                type="button"
                onClick={() => {
                  if (disabled) return;
                  onCountrySelect(c.name);
                  // Automatically choose the first city of that country
                  const firstCity = c.cities[0];
                  const cfg = CITY_CONFIGS[firstCity];
                  if (cfg) {
                    onCitySelect(firstCity, c.name, cfg.lat, cfg.lng);
                  }
                }}
                disabled={disabled}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "4px",
                  padding: "10px 4px",
                  borderRadius: "10px",
                  border: isSelected ? "2px solid var(--color-navy-900)" : "1px solid var(--color-border)",
                  background: isSelected ? "var(--color-navy-900)" : "white",
                  color: isSelected ? "white" : "var(--color-ink)",
                  fontFamily: "Times New Roman, serif",
                  cursor: disabled ? "not-allowed" : "pointer",
                  transition: "all 0.18s ease",
                  boxShadow: isSelected ? "0 4px 12px rgba(10,22,40,0.18)" : "0 1px 3px rgba(0,0,0,0.04)",
                  opacity: disabled ? 0.6 : 1,
                }}
              >
                <span style={{ fontSize: "18px", lineHeight: 1 }}>{c.flag}</span>
                <span style={{ fontSize: "12px", fontWeight: isSelected ? 600 : 500, textAlign: "center", lineHeight: 1.2 }}>
                  {c.name}
                </span>
                <span style={{ fontSize: "10px", color: isSelected ? "rgba(255,255,255,0.75)" : "var(--color-ink-4)" }}>
                  {c.cities.length} {c.cities.length === 1 ? "city" : "cities"}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── STEP 2: City Selection (Dynamically Filtered) ───────── */}
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "8px" }}>
          <span style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-ink-4)" }}>
            Step 2 · Select Metropolitan City
          </span>
          <span style={{ fontFamily: "Times New Roman, serif", fontSize: "11px", color: "var(--color-ink-3)" }}>
            in {selectedCountry}
          </span>
        </div>

        {availableCities.length > 1 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {availableCities.map((city) => {
              const isSelected = city === selectedCity;
              const cfg = CITY_CONFIGS[city];
              return (
                <button
                  key={city}
                  type="button"
                  onClick={() => {
                    if (disabled || !cfg) return;
                    onCitySelect(city, selectedCountry, cfg.lat, cfg.lng);
                  }}
                  disabled={disabled}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "10px 14px",
                    borderRadius: "10px",
                    border: isSelected ? "1.5px solid var(--color-navy-800)" : "1px solid var(--color-border)",
                    background: isSelected ? "rgba(10,22,40,0.05)" : "white",
                    cursor: disabled ? "not-allowed" : "pointer",
                    textAlign: "left",
                    transition: "all 0.15s ease",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontSize: "14px", fontWeight: isSelected ? 700 : 500, color: "var(--color-ink)" }}>
                        {city}
                      </span>
                      {isSelected && (
                        <span style={{ fontSize: "10px", background: "var(--color-navy-900)", color: "white", padding: "1px 6px", borderRadius: "99px" }}>
                          Active
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: "11px", color: "var(--color-ink-4)", marginTop: "2px" }}>
                      {cfg?.desc}
                    </div>
                  </div>
                  <div style={{ fontSize: "12px", color: isSelected ? "var(--color-navy-900)" : "var(--color-ink-4)" }}>
                    →
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          // Single available city (e.g. Beijing for China, Mumbai for India)
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "10px 14px",
              borderRadius: "10px",
              border: "1.5px solid var(--color-navy-800)",
              background: "rgba(10,22,40,0.05)",
            }}
          >
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-ink)" }}>
                  {availableCities[0]}
                </span>
                <span style={{ fontSize: "10px", background: "var(--color-navy-900)", color: "white", padding: "1px 6px", borderRadius: "99px" }}>
                  Selected
                </span>
              </div>
              <div style={{ fontSize: "11px", color: "var(--color-ink-4)", marginTop: "2px" }}>
                {CITY_CONFIGS[availableCities[0]]?.desc}
              </div>
            </div>
            <div style={{ fontSize: "12px", color: "var(--color-navy-900)" }}>
              ✓
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
