"""
experiments/test_live_data.py
==============================
Automated verification script for Open Charge Map live data enrichment layer
and Kaggle baseline fallback.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.data.open_charge_map import (
    OpenChargeMapService,
    get_ocm_service,
    NormalizedStation,
    LiveEnrichmentResult,
)
from fastapi.testclient import TestClient
from backend.api.main import app


class TestOpenChargeMapService(unittest.TestCase):
    def setUp(self):
        self.service = OpenChargeMapService()

    def test_city_coordinates_resolution(self):
        lat, lon = self.service.resolve_city_center("Mumbai")
        self.assertAlmostEqual(lat, 19.0467, places=2)
        self.assertAlmostEqual(lon, 72.8911, places=2)

        lat_sf, lon_sf = self.service.resolve_city_center("San Francisco")
        self.assertAlmostEqual(lat_sf, 37.8032, places=2)
        self.assertAlmostEqual(lon_sf, -122.4005, places=2)

    def test_fallback_to_baseline_when_api_fails(self):
        # Without valid OCM key, OCM returns 403 or network failure -> fallback to Kaggle baseline
        res = self.service.fetch_city_stations("Mumbai", max_results=10)
        self.assertIsInstance(res, LiveEnrichmentResult)
        self.assertEqual(res.city, "Mumbai")
        self.assertFalse(res.is_live)
        self.assertEqual(res.source, "kaggle_baseline")
        self.assertGreater(res.live_station_count, 0)
        self.assertEqual(len(res.stations), 10)

        first_st = res.stations[0]
        self.assertIsInstance(first_st, NormalizedStation)
        self.assertTrue(first_st.station_id.startswith("EVS"))
        self.assertIsNotNone(first_st.name)
        self.assertTrue(first_st.is_operational)
        self.assertEqual(first_st.source, "kaggle_baseline")

    def test_caching_behavior(self):
        res1 = self.service.fetch_city_stations("Chicago", max_results=10)
        res2 = self.service.fetch_city_stations("Chicago", max_results=10)
        self.assertIs(res1, res2)

    def test_live_ocm_parsing_mock(self):
        # Mocking an actual OCM API payload
        mock_ocm_payload = [
            {
                "ID": 12345,
                "AddressInfo": {
                    "Title": "Supercharger Central Hub",
                    "AddressLine1": "100 Market St",
                    "Latitude": 37.79,
                    "Longitude": -122.40,
                },
                "OperatorInfo": {
                    "Title": "Tesla",
                },
                "StatusType": {
                    "Title": "Operational",
                    "IsOperational": True,
                },
                "NumberOfPoints": 8,
                "Connections": [
                    {
                        "PowerKW": 250,
                        "ConnectionType": {"Title": "Tesla Supercharger"},
                    }
                ],
                "UsageCost": "$0.32/kWh",
                "DateLastStatusUpdate": "2026-09-01T12:00:00Z",
            }
        ]

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            import json
            mock_resp.read.return_value = json.dumps(mock_ocm_payload).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            service = OpenChargeMapService()
            result = service.fetch_city_stations("San Francisco", max_results=10)

            self.assertTrue(result.is_live)
            self.assertEqual(result.source, "open_charge_map")
            self.assertEqual(result.live_station_count, 1)
            self.assertEqual(result.stations[0].name, "Supercharger Central Hub")
            self.assertEqual(result.stations[0].power_kw, 250)
            self.assertEqual(result.stations[0].bays, 8)
            self.assertEqual(result.stations[0].operator, "Tesla")


class TestLiveStationsEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_live_stations_endpoint(self):
        resp = self.client.get("/api/v1/live-stations?city=Mumbai&max_results=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["city"], "Mumbai")
        self.assertIn("is_live", data)
        self.assertIn("source", data)
        self.assertIn("live_station_count", data)
        self.assertIn("last_updated", data)
        self.assertIn("stations", data)
        self.assertGreaterEqual(len(data["stations"]), 5)

    def test_optimize_endpoint_unaffected(self):
        # Verify optimize pipeline produces valid output unchanged
        payload = {
            "city": "Mumbai",
            "station_count": 3,
            "scenario": "all_hours",
            "reps": 1,
            "shots": 128,
            "seed": 42,
        }
        resp = self.client.post("/api/v1/optimize", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["recommendation"]["feasible"])
        self.assertEqual(data["recommendation"]["n_stations"], 3)
        self.assertEqual(len(data["recommendation"]["selected_zones"]), 3)


if __name__ == "__main__":
    unittest.main()
