"""
backend/data/open_charge_map.py
================================
Lightweight live-data enrichment service using the Open Charge Map (OCM) API v3.
Fetches nearby EV charging-station status and location data for a selected city.

Fallback Behavior
-----------------
If the Open Charge Map API fails (e.g. 403 Forbidden without API key, rate limits,
network timeout, or unreachable host), it gracefully falls back to the baseline
Kaggle dataset for that city without breaking or modifying the optimization pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from backend.data.loader import get_loader

log = logging.getLogger(__name__)

# Known metropolitan city centers (lat, lon)
CITY_COORDINATES: Dict[str, Tuple[float, float]] = {
    "Mumbai": (19.0467, 72.8911),
    "San Francisco": (37.8032, -122.4005),
    "Los Angeles": (34.0923, -118.2904),
    "Chicago": (41.9003, -87.7022),
    "Shenzhen": (22.6349, 114.0808),
    "Beijing": (39.9096, 116.3445),
    "Toronto": (43.6532, -79.3832),
    "Berlin": (52.5200, 13.4050),
    "Seoul": (37.5665, 126.9780),
    "Bangkok": (13.7563, 100.5018),
    "Dubai": (25.2048, 55.2708),
    "Sydney": (-33.8688, 151.2093),
    "Cape Town": (-33.9249, 18.4241),
    "Mexico City": (19.4326, -99.1332),
    "São Paulo": (-23.5505, -46.6333),
    "Moscow": (55.7558, 37.6173),
}

OCM_API_BASE_URL = "https://api.openchargemap.io/v3/poi"
DEFAULT_TIMEOUT_SECONDS = 4.0
CACHE_TTL_SECONDS = 300.0  # 5 minutes


@dataclass
class NormalizedStation:
    station_id: str
    name: str
    latitude: float
    longitude: float
    address: Optional[str] = None
    operator: Optional[str] = None
    status: str = "Operational"
    is_operational: bool = True
    power_kw: Optional[float] = None
    bays: int = 1
    connector_types: List[str] = field(default_factory=list)
    usage_cost: Optional[str] = None
    source: str = "open_charge_map"  # "open_charge_map" or "kaggle_baseline"
    last_status_update: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "station_id": self.station_id,
            "name": self.name,
            "latitude": round(self.latitude, 6),
            "longitude": round(self.longitude, 6),
            "address": self.address,
            "operator": self.operator,
            "status": self.status,
            "is_operational": self.is_operational,
            "power_kw": self.power_kw,
            "bays": self.bays,
            "connector_types": self.connector_types,
            "usage_cost": self.usage_cost,
            "source": self.source,
            "last_status_update": self.last_status_update,
        }


@dataclass
class LiveEnrichmentResult:
    city: str
    is_live: bool
    source: str
    status_message: str
    live_station_count: int
    last_updated: str
    stations: List[NormalizedStation]
    fallback_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "city": self.city,
            "is_live": self.is_live,
            "source": self.source,
            "status_message": self.status_message,
            "live_station_count": self.live_station_count,
            "last_updated": self.last_updated,
            "stations": [s.to_dict() for s in self.stations],
            "fallback_reason": self.fallback_reason,
        }


class OpenChargeMapService:
    """Service to fetch live stations from OCM API with graceful fallback to Kaggle baseline."""

    def __init__(self):
        self._cache: Dict[str, Tuple[float, LiveEnrichmentResult]] = {}

    def get_api_key(self) -> Optional[str]:
        return os.getenv("OPEN_CHARGE_MAP_API_KEY") or os.getenv("OCM_API_KEY")

    def resolve_city_center(self, canonical_city: str) -> Tuple[float, float]:
        """Resolves (lat, lon) for a given city."""
        if canonical_city in CITY_COORDINATES:
            return CITY_COORDINATES[canonical_city]

        # Try to look up in loader
        try:
            loader = get_loader()
            df = loader.filter_by_city(canonical_city)
            if len(df) > 0:
                lat = float(df["latitude"].mean())
                lon = float(df["longitude"].mean())
                return (lat, lon)
        except Exception:
            pass

        return (19.0467, 72.8911)  # Default Mumbai

    def _parse_ocm_poi(self, poi: Dict[str, Any]) -> NormalizedStation:
        """Parses a single Open Charge Map POI dictionary into a NormalizedStation."""
        poi_id = str(poi.get("ID", f"OCM-{int(time.time()*1000)}"))
        addr_info = poi.get("AddressInfo") or {}
        title = addr_info.get("Title") or f"Station {poi_id}"
        lat = float(addr_info.get("Latitude", 0.0))
        lng = float(addr_info.get("Longitude", 0.0))
        address = addr_info.get("AddressLine1") or addr_info.get("Town")

        op_info = poi.get("OperatorInfo") or {}
        operator = op_info.get("Title")

        status_type = poi.get("StatusType") or {}
        status_title = status_type.get("Title", "Operational")
        is_operational = status_type.get("IsOperational", True)

        num_points = poi.get("NumberOfPoints") or 1
        usage_cost = poi.get("UsageCost")

        # Parse connections for power and connector types
        connections = poi.get("Connections") or []
        power_values = []
        conn_types = []
        for c in connections:
            p = c.get("PowerKW")
            if p is not None:
                try:
                    power_values.append(float(p))
                except (ValueError, TypeError):
                    pass
            ct = c.get("ConnectionType") or {}
            ct_title = ct.get("Title")
            if ct_title and ct_title not in conn_types:
                conn_types.append(ct_title)

        max_power = max(power_values) if power_values else None
        last_status = poi.get("DateLastStatusUpdate")

        return NormalizedStation(
            station_id=f"OCM-{poi_id}",
            name=title,
            latitude=lat,
            longitude=lng,
            address=address,
            operator=operator,
            status=status_title,
            is_operational=bool(is_operational),
            power_kw=max_power,
            bays=int(num_points),
            connector_types=conn_types,
            usage_cost=usage_cost,
            source="open_charge_map",
            last_status_update=last_status or datetime.now(timezone.utc).isoformat(),
        )

    def _fallback_to_baseline(
        self,
        canonical_city: str,
        reason: str,
        max_results: int = 50,
    ) -> LiveEnrichmentResult:
        """Falls back to local Kaggle baseline dataset."""
        log.info(
            "Using baseline dataset for city '%s' (fallback reason: %s)",
            canonical_city,
            reason,
        )
        try:
            loader = get_loader()
            city_df = loader.filter_by_city(canonical_city)
            subset = city_df.head(max_results)
            stations: List[NormalizedStation] = []
            for _, row in subset.iterrows():
                conn_raw = str(row.get("connector_types", ""))
                conn_list = [c.strip() for c in conn_raw.split(",") if c.strip()]
                stations.append(
                    NormalizedStation(
                        station_id=str(row.get("station_id", "")),
                        name=str(row.get("address", "")).split(",")[0] or f"Station {row.get('station_id')}",
                        latitude=float(row.get("latitude", 0.0)),
                        longitude=float(row.get("longitude", 0.0)),
                        address=str(row.get("address", "")),
                        operator=str(row.get("station_operator", "Standard EV")),
                        status="Operational (Baseline)",
                        is_operational=True,
                        power_kw=float(row.get("charging_capacity_kw", 120.0)) if pd.notna(row.get("charging_capacity_kw")) else 120.0,
                        bays=int(row.get("parking_spots", 2)) if pd.notna(row.get("parking_spots")) else 2,
                        connector_types=conn_list,
                        usage_cost=f"${float(row.get('cost_usd_per_kwh', 0.25)):.2f}/kWh" if pd.notna(row.get("cost_usd_per_kwh")) else None,
                        source="kaggle_baseline",
                        last_status_update=datetime.now(timezone.utc).isoformat(),
                    )
                )

            total_count = len(city_df)
        except Exception as exc:
            log.warning("Fallback extraction failed for city %s: %s", canonical_city, exc)
            stations = []
            total_count = 0

        now_iso = datetime.now(timezone.utc).isoformat()
        return LiveEnrichmentResult(
            city=canonical_city,
            is_live=False,
            source="kaggle_baseline",
            status_message="Baseline dataset (Open Charge Map API fallback)",
            live_station_count=total_count,
            last_updated=now_iso,
            stations=stations,
            fallback_reason=reason,
        )

    def fetch_city_stations(
        self,
        city_name: str,
        distance_km: float = 25.0,
        max_results: int = 50,
    ) -> LiveEnrichmentResult:
        """
        Fetches live charging stations from Open Charge Map for the given city.
        Caches responses for 5 minutes.
        Falls back to baseline Kaggle dataset if API is unreachable, forbidden, or rate-limited.
        """
        try:
            canonical_city = get_loader().canonicalize_city_name(city_name)
        except Exception:
            canonical_city = city_name.strip().title()

        cache_key = f"{canonical_city}_{distance_km}_{max_results}"
        now = time.time()
        if cache_key in self._cache:
            ts, cached_result = self._cache[cache_key]
            if (now - ts) < CACHE_TTL_SECONDS:
                return cached_result

        lat, lon = self.resolve_city_center(canonical_city)
        api_key = self.get_api_key()

        # Build query parameters
        params = {
            "output": "json",
            "latitude": str(lat),
            "longitude": str(lon),
            "distance": str(distance_km),
            "distanceunit": "KM",
            "maxresults": str(max_results),
            "compact": "true",
            "verbose": "false",
        }
        if api_key:
            params["key"] = api_key

        query_string = urllib.parse.urlencode(params)
        request_url = f"{OCM_API_BASE_URL}?{query_string}"

        req = urllib.request.Request(
            request_url,
            headers={
                "User-Agent": "QuantEV/1.0 (EV-Infrastructure-Optimization)",
                "Accept": "application/json",
                **({"X-API-Key": api_key} if api_key else {}),
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
                if response.status != 200:
                    result = self._fallback_to_baseline(
                        canonical_city,
                        f"OCM API returned HTTP {response.status}",
                        max_results=max_results,
                    )
                else:
                    raw_data = json.loads(response.read().decode("utf-8"))
                    if isinstance(raw_data, list) and len(raw_data) > 0:
                        stations = [self._parse_ocm_poi(poi) for poi in raw_data if isinstance(poi, dict)]
                        now_iso = datetime.now(timezone.utc).isoformat()
                        result = LiveEnrichmentResult(
                            city=canonical_city,
                            is_live=True,
                            source="open_charge_map",
                            status_message="Live station data from Open Charge Map",
                            live_station_count=len(stations),
                            last_updated=now_iso,
                            stations=stations,
                            fallback_reason=None,
                        )
                        log.info(
                            "Successfully retrieved %d live stations from Open Charge Map for %s",
                            len(stations),
                            canonical_city,
                        )
                    else:
                        result = self._fallback_to_baseline(
                            canonical_city,
                            "OCM API returned empty station list",
                            max_results=max_results,
                        )
        except urllib.error.HTTPError as http_err:
            result = self._fallback_to_baseline(
                canonical_city,
                f"OCM API HTTP {http_err.code} ({http_err.reason})",
                max_results=max_results,
            )
        except Exception as exc:
            result = self._fallback_to_baseline(
                canonical_city,
                f"OCM API request failed ({type(exc).__name__}: {exc})",
                max_results=max_results,
            )

        self._cache[cache_key] = (now, result)
        return result


_DEFAULT_OCM_SERVICE: Optional[OpenChargeMapService] = None


def get_ocm_service() -> OpenChargeMapService:
    global _DEFAULT_OCM_SERVICE
    if _DEFAULT_OCM_SERVICE is None:
        _DEFAULT_OCM_SERVICE = OpenChargeMapService()
    return _DEFAULT_OCM_SERVICE
