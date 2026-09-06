"""
backend/api/routers/live_data.py
================================
Router for live EV charging station enrichment data.

Endpoints
---------
GET /api/v1/live-stations   Fetch live or fallback stations for a selected city.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.data.open_charge_map import get_ocm_service

log = logging.getLogger(__name__)
router = APIRouter()


class LiveStation(BaseModel):
    station_id: str = Field(description="Unique station identifier")
    name: str = Field(description="Display name or location title")
    latitude: float = Field(description="Station latitude")
    longitude: float = Field(description="Station longitude")
    address: Optional[str] = Field(default=None, description="Full street address")
    operator: Optional[str] = Field(default=None, description="Charging network operator")
    status: str = Field(default="Operational", description="Operational status title")
    is_operational: bool = Field(default=True, description="Whether the station is currently operational")
    power_kw: Optional[float] = Field(default=None, description="Maximum charging capacity in kW")
    bays: int = Field(default=1, description="Number of charging points or parking bays")
    connector_types: List[str] = Field(default_factory=list, description="Available connector plug types")
    usage_cost: Optional[str] = Field(default=None, description="Tariff or usage cost description")
    source: str = Field(default="open_charge_map", description="Data source: 'open_charge_map' or 'kaggle_baseline'")
    last_status_update: Optional[str] = Field(default=None, description="ISO timestamp of last known status update")


class LiveDataResponse(BaseModel):
    city: str = Field(description="Target city name")
    is_live: bool = Field(description="True if live data was retrieved from Open Charge Map; False if fallback")
    source: str = Field(description="Source identifier ('open_charge_map' or 'kaggle_baseline')")
    status_message: str = Field(description="Human-readable status description")
    live_station_count: int = Field(description="Total number of stations returned or available")
    last_updated: str = Field(description="ISO timestamp of last update")
    stations: List[LiveStation] = Field(default_factory=list, description="List of normalized station objects")
    fallback_reason: Optional[str] = Field(default=None, description="Reason for fallback if API was unavailable")


@router.get(
    "/live-stations",
    response_model=LiveDataResponse,
    summary="Get live or baseline EV charging stations for a city",
    description=(
        "Queries Open Charge Map for real-time station statuses and locations within "
        "the selected city metropolitan area. Gracefully falls back to the baseline Kaggle "
        "dataset if the external API is unreachable or rate-limited."
    ),
)
async def get_live_stations(
    city: str = Query(default="Mumbai", description="City name (e.g. Mumbai, San Francisco, Los Angeles, Chicago, Shenzhen)"),
    distance_km: float = Query(default=25.0, ge=1.0, le=100.0, description="Search radius in kilometers"),
    max_results: int = Query(default=50, ge=5, le=200, description="Maximum number of stations to return"),
) -> LiveDataResponse:
    service = get_ocm_service()
    result = service.fetch_city_stations(
        city_name=city,
        distance_km=distance_km,
        max_results=max_results,
    )
    return LiveDataResponse(**result.to_dict())
