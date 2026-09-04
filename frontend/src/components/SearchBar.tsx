"use client";

import { useState, useRef, useEffect } from "react";

export interface PlanningAreaOption {
  name: string;
  district: string;
  lat: number;
  lng: number;
  desc: string;
  isOverview?: boolean;
}

export const SHENZHEN_LOCATIONS: PlanningAreaOption[] = [
  {
    name: "Shenzhen (Central Overview)",
    district: "Shenzhen Central",
    lat: 22.625,
    lng: 114.075,
    desc: "Default Planning Area · Citywide Analysis",
    isOverview: true,
  },
  {
    name: "Futian CBD",
    district: "Futian",
    lat: 22.5415,
    lng: 114.0573,
    desc: "Financial & Administrative Center",
  },
  {
    name: "Nanshan Tech Park",
    district: "Nanshan",
    lat: 22.5442,
    lng: 113.9371,
    desc: "High-Tech Corridor & Innovation Core",
  },
  {
    name: "Luohu District",
    district: "Luohu",
    lat: 22.5509,
    lng: 114.1174,
    desc: "Commercial & Railway Port Hub",
  },
  {
    name: "Bantian, Longgang",
    district: "Longgang",
    lat: 22.635,
    lng: 114.082,
    desc: "Huawei Tech & ICT Cluster",
  },
  {
    name: "Longhua District",
    district: "Longhua",
    lat: 22.6876,
    lng: 114.0401,
    desc: "North Transport Hub & Manufacturing",
  },
  {
    name: "Bao'an International Airport",
    district: "Bao'an",
    lat: 22.6395,
    lng: 113.8144,
    desc: "Aviation & Air Logistics Zone",
  },
  {
    name: "Shekou Ferry Terminal",
    district: "Nanshan",
    lat: 22.4847,
    lng: 113.9059,
    desc: "Maritime Free Trade & Cruise Port",
  },
  {
    name: "Window of the World",
    district: "Nanshan",
    lat: 22.5352,
    lng: 113.9706,
    desc: "Overseas Chinese Town & Tourism",
  },
  {
    name: "Shenzhen Bay Park",
    district: "Nanshan",
    lat: 22.5066,
    lng: 113.9557,
    desc: "Coastal Ecological & CBD Gateway",
  },
  {
    name: "OCT Harbour",
    district: "Nanshan",
    lat: 22.5373,
    lng: 114.0455,
    desc: "Waterfront Cultural & Leisure Zone",
  },
  {
    name: "Longgang District",
    district: "Longgang",
    lat: 22.7208,
    lng: 114.249,
    desc: "Eastern Industrial & University Town",
  },
  {
    name: "Guangming District",
    district: "Guangming",
    lat: 22.7472,
    lng: 113.934,
    desc: "Science City & Emerging Tech",
  },
  {
    name: "Yantian Port",
    district: "Yantian",
    lat: 22.5688,
    lng: 114.2709,
    desc: "Deep-water Container Terminal",
  },
  {
    name: "Pingshan District",
    district: "Pingshan",
    lat: 22.6813,
    lng: 114.3661,
    desc: "EV Manufacturing & Bio-tech Base",
  },
  {
    name: "Dameisha Beach",
    district: "Yantian",
    lat: 22.5916,
    lng: 114.3139,
    desc: "Eastern Marine Tourism & Resort",
  },
];

interface SearchBarProps {
  selectedName?: string;
  selectedLat?: number;
  selectedLng?: number;
  onLocationSelect: (lat: number, lng: number, name: string) => void;
  disabled?: boolean;
}

export function SearchBar({
  selectedName = "Shenzhen (Central Overview)",
  selectedLat,
  selectedLng,
  onLocationSelect,
  disabled = false,
}: SearchBarProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [geoLoading, setGeoLoading] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  // Auto-focus search input when opening dropdown
  useEffect(() => {
    if (isOpen) {
      setSearchQuery("");
      const timer = setTimeout(() => {
        searchInputRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  function handleSelect(loc: PlanningAreaOption) {
    onLocationSelect(loc.lat, loc.lng, loc.name);
    setIsOpen(false);
    setSearchQuery("");
  }

  function handleUseLocation() {
    if (!navigator.geolocation) return;
    setGeoLoading(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeoLoading(false);
        const { latitude, longitude } = pos.coords;
        onLocationSelect(latitude, longitude, "Current area");
        setIsOpen(false);
      },
      () => {
        setGeoLoading(false);
        // Fallback to Shenzhen center
        const fallback = SHENZHEN_LOCATIONS[0];
        onLocationSelect(fallback.lat, fallback.lng, fallback.name);
        setIsOpen(false);
      },
      { timeout: 6000 }
    );
  }

  const filteredLocations = SHENZHEN_LOCATIONS.filter((loc) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      loc.name.toLowerCase().includes(q) ||
      loc.district.toLowerCase().includes(q) ||
      loc.desc.toLowerCase().includes(q)
    );
  });

  // Determine display label and coordinates
  const currentMatch = SHENZHEN_LOCATIONS.find(
    (l) => l.name.toLowerCase() === selectedName.toLowerCase()
  );
  const displayLat = selectedLat ?? currentMatch?.lat ?? 22.625;
  const displayLng = selectedLng ?? currentMatch?.lng ?? 114.075;
  const displayDistrict = currentMatch?.district ?? "Planning Area";

  return (
    <div
      ref={containerRef}
      style={{ position: "relative", width: "100%" }}
    >
      {/* Dropdown Trigger Button */}
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "10px",
          padding: "10px 14px",
          background: "white",
          border: isOpen
            ? "1.5px solid var(--color-navy-700)"
            : "1px solid var(--color-border)",
          borderRadius: "10px",
          cursor: disabled ? "not-allowed" : "pointer",
          textAlign: "left",
          boxShadow: isOpen
            ? "0 4px 16px rgba(10,22,40,0.12)"
            : "0 1px 3px rgba(10,22,40,0.04)",
          transition: "all 0.15s ease",
          opacity: disabled ? 0.6 : 1,
        }}
        onMouseEnter={(e) => {
          if (!disabled && !isOpen) {
            e.currentTarget.style.borderColor = "var(--color-navy-300)";
          }
        }}
        onMouseLeave={(e) => {
          if (!disabled && !isOpen) {
            e.currentTarget.style.borderColor = "var(--color-border)";
          }
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
          {/* Location indicator dot */}
          <div
            style={{
              width: "10px",
              height: "10px",
              borderRadius: "50%",
              background: "var(--color-navy-900)",
              border: "2px solid white",
              boxShadow: "0 1px 4px rgba(10,22,40,0.25)",
              flexShrink: 0,
            }}
          />
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                fontFamily: "Times New Roman, serif",
                fontSize: "14px",
                fontWeight: 600,
                color: "var(--color-ink)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                lineHeight: 1.25,
              }}
            >
              {selectedName}
            </div>
            <div
              className="numeric"
              style={{
                fontSize: "11px",
                color: "var(--color-ink-4)",
                lineHeight: 1.2,
                marginTop: "2px",
              }}
            >
              {displayLat.toFixed(4)}°N, {displayLng.toFixed(4)}°E · {displayDistrict}
            </div>
          </div>
        </div>

        {/* Chevron icon */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: isOpen ? "var(--color-navy-900)" : "var(--color-ink-4)",
            transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), color 0.15s ease",
            flexShrink: 0,
            marginLeft: "6px",
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path
              d="M3 5.25L7 9.25L11 5.25"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      </button>

      {/* Proper Dropdown Menu Panel */}
      {isOpen && (
        <div
          className="anim-slide-down"
          role="listbox"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            right: 0,
            background: "rgba(255, 255, 255, 0.98)",
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            borderRadius: "12px",
            border: "1px solid var(--color-border)",
            boxShadow: "0 16px 40px rgba(10,22,40,0.18)",
            overflow: "hidden",
            zIndex: 9999,
          }}
        >
          {/* Search / Filter box inside the dropdown */}
          <div
            style={{
              padding: "8px 10px",
              borderBottom: "1px solid var(--color-border-subtle)",
              background: "var(--color-grey-50)",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="none"
              style={{ color: "var(--color-ink-4)", flexShrink: 0 }}
            >
              <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5" />
              <path
                d="M10.5 10.5l3 3"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search planning areas in Shenzhen…"
              style={{
                flex: 1,
                border: "none",
                outline: "none",
                background: "transparent",
                fontFamily: "Times New Roman, serif",
                fontSize: "13px",
                color: "var(--color-ink)",
                padding: "4px 0",
              }}
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                style={{
                  border: "none",
                  background: "transparent",
                  cursor: "pointer",
                  color: "var(--color-ink-4)",
                  fontSize: "14px",
                  lineHeight: 1,
                  padding: "2px 4px",
                }}
                title="Clear filter"
              >
                ×
              </button>
            )}
          </div>

          {/* Quick Action: Use My Location */}
          <button
            type="button"
            onClick={handleUseLocation}
            disabled={geoLoading}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "10px 14px",
              border: "none",
              borderBottom: "1px solid var(--color-border-subtle)",
              background: "transparent",
              cursor: geoLoading ? "not-allowed" : "pointer",
              textAlign: "left",
              transition: "background 0.12s ease",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--color-navy-50)";
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
                  color: "var(--color-navy-600)",
                  flexShrink: 0,
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
                style={{ color: "var(--color-navy-600)", flexShrink: 0 }}
              >
                <circle cx="7" cy="7" r="2.5" fill="currentColor" />
                <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.2" />
                <line x1="7" y1="0" x2="7" y2="2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                <line x1="7" y1="12" x2="7" y2="14" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                <line x1="0" y1="7" x2="2" y2="7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                <line x1="12" y1="7" x2="14" y2="7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
              </svg>
            )}
            <div>
              <div
                style={{
                  fontFamily: "Times New Roman, serif",
                  fontSize: "13px",
                  fontWeight: 600,
                  color: "var(--color-navy-700)",
                }}
              >
                Use current location (GPS)
              </div>
              <div
                style={{
                  fontFamily: "Times New Roman, serif",
                  fontSize: "11px",
                  color: "var(--color-ink-4)",
                }}
              >
                Detect nearest coordinates via device location
              </div>
            </div>
          </button>

          {/* Scrollable list of locations */}
          <div
            style={{
              maxHeight: "230px",
              overflowY: "auto",
              overscrollBehavior: "contain",
            }}
          >
            {filteredLocations.length === 0 ? (
              <div
                style={{
                  padding: "16px",
                  textAlign: "center",
                  fontFamily: "Times New Roman, serif",
                  fontSize: "13px",
                  color: "var(--color-ink-4)",
                }}
              >
                No matching planning areas found
              </div>
            ) : (
              filteredLocations.map((loc) => {
                const isSelected =
                  loc.name.toLowerCase() === selectedName.toLowerCase();
                return (
                  <button
                    key={loc.name}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => handleSelect(loc)}
                    style={{
                      width: "100%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "10px",
                      padding: "9px 14px",
                      border: "none",
                      borderBottom: "1px solid var(--color-border-subtle)",
                      background: isSelected
                        ? "var(--color-navy-50)"
                        : "transparent",
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "background 0.12s ease",
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) {
                        e.currentTarget.style.background = "var(--color-grey-50)";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) {
                        e.currentTarget.style.background = "transparent";
                      }
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                        }}
                      >
                        <span
                          style={{
                            fontFamily: "Times New Roman, serif",
                            fontSize: "13px",
                            fontWeight: isSelected ? 600 : 500,
                            color: isSelected
                              ? "var(--color-navy-900)"
                              : "var(--color-ink)",
                          }}
                        >
                          {loc.name}
                        </span>
                        {loc.isOverview && (
                          <span
                            style={{
                              fontSize: "10px",
                              padding: "1px 6px",
                              borderRadius: "4px",
                              background: "var(--color-navy-100)",
                              color: "var(--color-navy-800)",
                              fontFamily: "Times New Roman, serif",
                            }}
                          >
                            Citywide
                          </span>
                        )}
                      </div>
                      <div
                        style={{
                          fontFamily: "Times New Roman, serif",
                          fontSize: "11px",
                          color: "var(--color-ink-4)",
                          marginTop: "1px",
                          display: "flex",
                          gap: "6px",
                        }}
                      >
                        <span>{loc.desc}</span>
                        <span>·</span>
                        <span className="numeric">
                          {loc.lat.toFixed(2)}°N, {loc.lng.toFixed(2)}°E
                        </span>
                      </div>
                    </div>

                    {/* Active checkmark */}
                    {isSelected && (
                      <div
                        style={{
                          color: "var(--color-navy-800)",
                          flexShrink: 0,
                        }}
                      >
                        <svg
                          width="14"
                          height="14"
                          viewBox="0 0 16 16"
                          fill="none"
                        >
                          <path
                            d="M3 8.5L6.5 12L13 4"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </div>
                    )}
                  </button>
                );
              })
            )}
          </div>

          {/* Footer note */}
          <div
            style={{
              padding: "7px 14px",
              background: "var(--color-grey-50)",
              borderTop: "1px solid var(--color-border-subtle)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: "11px",
              fontFamily: "Times New Roman, serif",
              color: "var(--color-ink-4)",
            }}
          >
            <span>{SHENZHEN_LOCATIONS.length} planning zones in Shenzhen</span>
            <span>Click to re-center map</span>
          </div>
        </div>
      )}
    </div>
  );
}
