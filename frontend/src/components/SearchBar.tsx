"use client";

import { useState, useRef } from "react";

// Shenzhen landmarks for search suggestions
const SHENZHEN_LOCATIONS = [
  { name: "Futian CBD", lat: 22.5415, lng: 114.0573 },
  { name: "Nanshan Tech Park", lat: 22.5442, lng: 113.9371 },
  { name: "Luohu District", lat: 22.5509, lng: 114.1174 },
  { name: "Bao'an International Airport", lat: 22.6395, lng: 113.8144 },
  { name: "Longhua District", lat: 22.6876, lng: 114.0401 },
  { name: "Shekou Ferry Terminal", lat: 22.4847, lng: 113.9059 },
  { name: "Window of the World", lat: 22.5352, lng: 113.9706 },
  { name: "Shenzhen Bay Park", lat: 22.5066, lng: 113.9557 },
  { name: "OCT Harbour", lat: 22.5373, lng: 114.0455 },
  { name: "Longgang District", lat: 22.7208, lng: 114.2490 },
  { name: "Pingshan District", lat: 22.6813, lng: 114.3661 },
  { name: "Dameisha Beach", lat: 22.5916, lng: 114.3139 },
  { name: "Yantian Port", lat: 22.5688, lng: 114.2709 },
  { name: "Guangming District", lat: 22.7472, lng: 113.9340 },
  { name: "Bantian, Longgang", lat: 22.6350, lng: 114.0820 },
];

interface SearchBarProps {
  onLocationSelect: (lat: number, lng: number, name: string) => void;
  disabled?: boolean;
}

export function SearchBar({ onLocationSelect, disabled }: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [geoLoading, setGeoLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = query.trim().length > 0
    ? SHENZHEN_LOCATIONS.filter((l) =>
        l.name.toLowerCase().includes(query.toLowerCase())
      )
    : SHENZHEN_LOCATIONS;

  const showDropdown = (focused || dropdownOpen) && !disabled;

  function handleSelect(loc: typeof SHENZHEN_LOCATIONS[0]) {
    setQuery(loc.name);
    setFocused(false);
    setDropdownOpen(false);
    inputRef.current?.blur();
    onLocationSelect(loc.lat, loc.lng, loc.name);
  }

  function toggleDropdown() {
    if (disabled) return;
    if (showDropdown) {
      setDropdownOpen(false);
      setFocused(false);
      inputRef.current?.blur();
    } else {
      inputRef.current?.focus();
      setDropdownOpen(true);
      setFocused(true);
    }
  }

  function handleUseLocation() {
    if (!navigator.geolocation) return;
    setGeoLoading(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeoLoading(false);
        const { latitude, longitude } = pos.coords;
        setQuery("Current area");
        onLocationSelect(latitude, longitude, "Current area");
      },
      () => {
        setGeoLoading(false);
        // Fallback to Shenzhen center if permission denied
        const fallback = { lat: 22.5431, lng: 114.0579 };
        setQuery("Shenzhen (approximate)");
        onLocationSelect(fallback.lat, fallback.lng, "Shenzhen");
      },
      { timeout: 6000 }
    );
  }

  return (
    <div style={{ position: "relative", width: "100%" }}>
      {/* Search input */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0",
          background: "rgba(255,255,255,0.96)",
          border: focused
            ? "1.5px solid rgba(10,22,40,0.4)"
            : "1.5px solid rgba(255,255,255,0.8)",
          borderRadius: showDropdown ? "16px 16px 0 0" : "16px",
          overflow: "hidden",
          transition: "border-color 0.2s ease, box-shadow 0.2s ease",
          boxShadow: focused
            ? "0 8px 32px rgba(10,22,40,0.18)"
            : "0 4px 24px rgba(10,22,40,0.12)",
        }}
      >
        {/* Search icon */}
        <div
          style={{
            padding: "0 14px 0 18px",
            display: "flex",
            alignItems: "center",
            flexShrink: 0,
          }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            style={{ color: "var(--color-ink-4)" }}
          >
            <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5" />
            <path d="M10.5 10.5l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </div>

        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setDropdownOpen(true);
          }}
          onFocus={() => {
            setFocused(true);
            setDropdownOpen(true);
          }}
          onBlur={() => {
            setTimeout(() => {
              setFocused(false);
              setDropdownOpen(false);
            }, 160);
          }}
          placeholder="Select a planning area in Shenzhen…"
          disabled={disabled}
          style={{
            flex: 1,
            border: "none",
            outline: "none",
            background: "transparent",
            fontFamily: "Times New Roman, serif",
            fontSize: "16px",
            color: "var(--color-ink)",
            padding: "16px 0",
            letterSpacing: "-0.005em",
          }}
        />

        {/* Dropdown toggle chevron */}
        <button
          onClick={toggleDropdown}
          onMouseDown={(e) => e.preventDefault()}
          disabled={disabled}
          title="Show all locations"
          style={{
            padding: "0 10px",
            height: "100%",
            border: "none",
            background: "transparent",
            cursor: disabled ? "not-allowed" : "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--color-ink-4)",
            transition: "color 0.15s ease",
          }}
          onMouseEnter={(e) => {
            if (!disabled) e.currentTarget.style.color = "var(--color-ink)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "var(--color-ink-4)";
          }}
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="none"
            style={{
              transform: showDropdown ? "rotate(180deg)" : "rotate(0deg)",
              transition: "transform 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
            }}
          >
            <path
              d="M2.5 4.5L6 8L9.5 4.5"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>

        {/* Use my location */}
        <button
          onClick={handleUseLocation}
          disabled={disabled || geoLoading}
          title="Use my location"
          style={{
            padding: "0 18px",
            height: "100%",
            border: "none",
            borderLeft: "1px solid var(--color-border)",
            background: "transparent",
            cursor: disabled || geoLoading ? "not-allowed" : "pointer",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            flexShrink: 0,
            transition: "background 0.15s ease",
            borderRadius: "0 14px 14px 0",
          }}
          onMouseEnter={(e) => {
            if (!disabled) e.currentTarget.style.background = "var(--color-grey-50)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
          }}
        >
          {geoLoading ? (
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              style={{
                animation: "spin 1s linear infinite",
                color: "var(--color-navy-500)",
              }}
              fill="none"
            >
              <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.5" strokeDasharray="8 6" />
            </svg>
          ) : (
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              style={{ color: "var(--color-navy-500)" }}
            >
              <circle cx="7" cy="7" r="2.5" fill="currentColor" />
              <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.2" />
              <line x1="7" y1="0" x2="7" y2="2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
              <line x1="7" y1="12" x2="7" y2="14" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
              <line x1="0" y1="7" x2="2" y2="7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
              <line x1="12" y1="7" x2="14" y2="7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
            </svg>
          )}
          <span
            style={{
              fontFamily: "Times New Roman, serif",
              fontSize: "13px",
              color: "var(--color-navy-600)",
              whiteSpace: "nowrap",
            }}
          >
            My area
          </span>
        </button>
      </div>

      {/* Dropdown suggestions */}
      {showDropdown && (
        <div
          className="anim-slide-down"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            background: "rgba(255,255,255,0.98)",
            borderRadius: "0 0 16px 16px",
            border: "1.5px solid rgba(10,22,40,0.18)",
            borderTop: "1px solid var(--color-border-subtle)",
            overflowY: "auto",
            maxHeight: "260px",
            zIndex: 100,
            boxShadow: "0 12px 40px rgba(10,22,40,0.14)",
          }}
        >
          {query.trim().length > 0 && filtered.length === 0 ? (
            <div
              style={{
                padding: "16px 20px",
                fontFamily: "Times New Roman, serif",
                fontSize: "14px",
                color: "var(--color-ink-4)",
              }}
            >
              No locations found
            </div>
          ) : (
            filtered.map((loc, i) => (
              <button
                key={loc.name}
                onMouseDown={() => handleSelect(loc)}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                  padding: "13px 18px",
                  border: "none",
                  borderBottom:
                    i < filtered.length - 1
                      ? "1px solid var(--color-border-subtle)"
                      : "none",
                  background: "transparent",
                  cursor: "pointer",
                  textAlign: "left",
                  transition: "background 0.12s ease",
                }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background = "var(--color-navy-50)")
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = "transparent")
                }
              >
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 12 12"
                  fill="none"
                  style={{ color: "var(--color-ink-4)", flexShrink: 0 }}
                >
                  <circle cx="6" cy="5" r="2.5" stroke="currentColor" strokeWidth="1.2" />
                  <path
                    d="M6 1C3.79 1 2 2.79 2 5c0 3.5 4 7 4 7s4-3.5 4-7c0-2.21-1.79-4-4-4z"
                    stroke="currentColor"
                    strokeWidth="1.2"
                    fill="none"
                  />
                </svg>
                <span
                  style={{
                    fontFamily: "Times New Roman, serif",
                    fontSize: "14px",
                    color: "var(--color-ink)",
                  }}
                >
                  {loc.name}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
