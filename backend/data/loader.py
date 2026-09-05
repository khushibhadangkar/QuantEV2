"""
backend/data/loader.py
======================
Global EV Charging Stations data layer.

Loads and normalizes data/raw/global_ev_charging_stations.csv, supports 15 global
metropolitan cities, maps them to their respective countries, and provides fast,
validated filtering and metadata extraction.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_MODULE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _MODULE_DIR.parents[1]
_DEFAULT_CSV_PATH = _PROJECT_ROOT / "data" / "raw" / "global_ev_charging_stations.csv"
_FALLBACK_CSV_PATH = _PROJECT_ROOT / "data" / "raw" / "detailed_ev_charging_stations.csv"

# ── 15 Supported Global Cities & Country Mapping ──────────────────────────────
CITY_TO_COUNTRY: Dict[str, str] = {
    "San Francisco": "United States",
    "Los Angeles": "United States",
    "Chicago": "United States",
    "Toronto": "Canada",
    "Berlin": "Germany",
    "Mumbai": "India",
    "Beijing": "China",
    "Seoul": "South Korea",
    "Bangkok": "Thailand",
    "Dubai": "United Arab Emirates",
    "Sydney": "Australia",
    "Cape Town": "South Africa",
    "Mexico City": "Mexico",
    "São Paulo": "Brazil",
    "Moscow": "Russia",
}

# Standardized column name mapping (raw CSV → normalized snake_case)
COLUMN_MAPPING: Dict[str, str] = {
    "Station ID": "station_id",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Address": "address",
    "Charger Type": "charger_type",
    "Cost (USD/kWh)": "cost_usd_per_kwh",
    "Availability": "availability",
    "Distance to City (km)": "distance_to_city_km",
    "Usage Stats (avg users/day)": "usage_stats_users_per_day",
    "Station Operator": "station_operator",
    "Charging Capacity (kW)": "charging_capacity_kw",
    "Connector Types": "connector_types",
    "Installation Year": "installation_year",
    "Renewable Energy Source": "renewable_energy_source",
    "Reviews (Rating)": "reviews_rating",
    "Parking Spots": "parking_spots",
    "Maintenance Frequency": "maintenance_frequency",
}


def _normalize_key(text: str) -> str:
    """Normalize string for robust, case- and diacritic-insensitive matching."""
    if not text:
        return ""
    # Strip accents (e.g. "São Paulo" -> "sao paulo")
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return ascii_only.strip().lower().replace("_", " ").replace("-", " ")


# Precomputed lookup mapping for normalized variants -> canonical city name
_NORMALIZED_CITY_LOOKUP: Dict[str, str] = {}
for canonical_city in CITY_TO_COUNTRY:
    _NORMALIZED_CITY_LOOKUP[_normalize_key(canonical_city)] = canonical_city

# Additional common aliases
_NORMALIZED_CITY_LOOKUP["sf"] = "San Francisco"
_NORMALIZED_CITY_LOOKUP["la"] = "Los Angeles"
_NORMALIZED_CITY_LOOKUP["sao paulo"] = "São Paulo"


@dataclass
class CityMetadata:
    """Geographic and summary metadata for a supported city."""
    city: str
    country: str
    station_count: int
    center_latitude: float
    center_longitude: float
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    avg_users_per_day: float
    avg_capacity_kw: float
    total_parking_spots: int


class GlobalDataLoader:
    """
    Data loader and filter for the Global EV Charging Stations dataset.
    """

    def __init__(self, csv_path: Optional[Union[str, Path]] = None):
        if csv_path is not None:
            self.csv_path = Path(csv_path)
        elif _DEFAULT_CSV_PATH.exists():
            self.csv_path = _DEFAULT_CSV_PATH
        elif _FALLBACK_CSV_PATH.exists():
            self.csv_path = _FALLBACK_CSV_PATH
        else:
            raise FileNotFoundError(
                f"Global EV dataset not found at {_DEFAULT_CSV_PATH} or {_FALLBACK_CSV_PATH}"
            )

        self._raw_df: Optional[pd.DataFrame] = None
        self._normalized_df: Optional[pd.DataFrame] = None
        self._city_cache: Dict[str, pd.DataFrame] = {}

    def load_data(self, reload: bool = False) -> pd.DataFrame:
        """
        Loads the CSV and returns the normalized, enriched DataFrame.
        Cached after the first load.
        """
        if self._normalized_df is not None and not reload:
            return self._normalized_df

        if not self.csv_path.exists():
            raise FileNotFoundError(f"Global dataset not found: {self.csv_path}")

        log.info("Loading global EV charging station data from %s ...", self.csv_path)
        raw = pd.read_csv(self.csv_path)
        self._raw_df = raw

        # Normalize column names
        df = raw.rename(columns=COLUMN_MAPPING).copy()

        # Parse city from the address (e.g. "8970 San Francisco Ave, San Francisco" -> "San Francisco")
        def _extract_city(addr: Any) -> Optional[str]:
            if not isinstance(addr, str) or "," not in addr:
                return None
            candidate = addr.split(",")[-1].strip()
            # Match against known canonical cities
            norm = _normalize_key(candidate)
            return _NORMALIZED_CITY_LOOKUP.get(norm, candidate)

        df["city"] = df["address"].apply(_extract_city)

        # Map country
        df["country"] = df["city"].map(CITY_TO_COUNTRY)

        # Ensure correct numeric types
        numeric_cols = [
            "latitude",
            "longitude",
            "cost_usd_per_kwh",
            "distance_to_city_km",
            "usage_stats_users_per_day",
            "charging_capacity_kw",
            "installation_year",
            "reviews_rating",
            "parking_spots",
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        self._normalized_df = df
        self._city_cache.clear()
        return self._normalized_df

    def canonicalize_city_name(self, city_name: str) -> str:
        """
        Resolves a user-input city name/alias to the canonical city name.
        Raises ValueError if the city is not in the 15 supported cities.
        """
        norm = _normalize_key(city_name)
        if norm in _NORMALIZED_CITY_LOOKUP:
            return _NORMALIZED_CITY_LOOKUP[norm]

        valid = ", ".join(sorted(CITY_TO_COUNTRY.keys()))
        raise ValueError(
            f"Unsupported city '{city_name}'. Supported cities are: {valid}"
        )

    def get_supported_cities(self) -> List[str]:
        """Returns the list of the 15 supported canonical city names."""
        return list(CITY_TO_COUNTRY.keys())

    def filter_by_city(
        self,
        city_name: str,
        as_records: bool = False,
    ) -> Union[pd.DataFrame, List[Dict[str, Any]]]:
        """
        Filters charging station records for the selected city.

        Parameters
        ----------
        city_name : Name of the city (case-insensitive, diacritic-insensitive).
        as_records: If True, returns a list of dictionaries instead of a DataFrame.

        Returns
        -------
        pd.DataFrame or List[dict] of stations for that city.
        """
        canonical_city = self.canonicalize_city_name(city_name)

        if canonical_city not in self._city_cache:
            df = self.load_data()
            city_df = df[df["city"] == canonical_city].copy().reset_index(drop=True)
            self._city_cache[canonical_city] = city_df

        city_df = self._city_cache[canonical_city]

        if as_records:
            return city_df.to_dict(orient="records")
        return city_df

    def get_all_city_counts(self) -> Dict[str, int]:
        """Returns a dictionary of {city_name: station_count} for all 15 supported cities."""
        df = self.load_data()
        counts: Dict[str, int] = {}
        for city in CITY_TO_COUNTRY:
            counts[city] = int((df["city"] == city).sum())
        return counts

    def get_city_metadata(self, city_name: str) -> CityMetadata:
        """
        Computes geographic bounding box and summary stats for a supported city.
        """
        canonical_city = self.canonicalize_city_name(city_name)
        city_df = self.filter_by_city(canonical_city)

        if len(city_df) == 0:
            raise ValueError(f"No records found for city '{canonical_city}'")

        return CityMetadata(
            city=canonical_city,
            country=CITY_TO_COUNTRY[canonical_city],
            station_count=len(city_df),
            center_latitude=round(float(city_df["latitude"].mean()), 6),
            center_longitude=round(float(city_df["longitude"].mean()), 6),
            lat_min=round(float(city_df["latitude"].min()), 6),
            lat_max=round(float(city_df["latitude"].max()), 6),
            lon_min=round(float(city_df["longitude"].min()), 6),
            lon_max=round(float(city_df["longitude"].max()), 6),
            avg_users_per_day=round(float(city_df["usage_stats_users_per_day"].mean()), 2),
            avg_capacity_kw=round(float(city_df["charging_capacity_kw"].mean()), 2),
            total_parking_spots=int(city_df["parking_spots"].sum()),
        )

    def get_all_cities_metadata(self) -> Dict[str, CityMetadata]:
        """Returns metadata for all 15 supported cities."""
        return {city: self.get_city_metadata(city) for city in CITY_TO_COUNTRY}


# ── Module-level convenience singleton & helper functions ─────────────────────
_DEFAULT_LOADER: Optional[GlobalDataLoader] = None


def get_loader(csv_path: Optional[Union[str, Path]] = None) -> GlobalDataLoader:
    """Returns a shared or custom GlobalDataLoader instance."""
    global _DEFAULT_LOADER
    if csv_path is not None:
        return GlobalDataLoader(csv_path)
    if _DEFAULT_LOADER is None:
        _DEFAULT_LOADER = GlobalDataLoader()
    return _DEFAULT_LOADER


def load_global_ev_data(csv_path: Optional[Union[str, Path]] = None) -> pd.DataFrame:
    """Convenience helper to load the normalized global EV dataset."""
    return get_loader(csv_path).load_data()


def filter_stations_by_city(
    city: str,
    csv_path: Optional[Union[str, Path]] = None,
    as_records: bool = False,
) -> Union[pd.DataFrame, List[Dict[str, Any]]]:
    """Convenience helper to filter stations for a given city."""
    return get_loader(csv_path).filter_by_city(city, as_records=as_records)


def get_city_counts(csv_path: Optional[Union[str, Path]] = None) -> Dict[str, int]:
    """Convenience helper to get station counts for all 15 cities."""
    return get_loader(csv_path).get_all_city_counts()
