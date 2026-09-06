"use client";

import { useState, useEffect, useCallback } from "react";
import { fetchLiveStations } from "@/lib/api";
import type { LiveDataResponse } from "@/types/api";

export function useLiveData(city: string) {
  const [data, setData] = useState<LiveDataResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async (targetCity: string) => {
    if (!targetCity) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchLiveStations(targetCity);
      setData(res);
    } catch (err: any) {
      console.warn("[QuantEV] Live data fetch failed:", err);
      setError(err?.message || "Failed to load live station data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;

    async function fetch() {
      if (!city) return;
      setLoading(true);
      setError(null);
      try {
        const res = await fetchLiveStations(city);
        if (!ignore) {
          setData(res);
        }
      } catch (err: any) {
        if (!ignore) {
          console.warn("[QuantEV] Live data fetch failed:", err);
          setError(err?.message || "Failed to load live station data");
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    fetch();

    return () => {
      ignore = true;
    };
  }, [city]);

  // Format last updated time (e.g. "12:45:02 PM" or formatted timestamp)
  const formatTime = (isoString?: string | null): string => {
    if (!isoString) return "Just now";
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return "Just now";
    }
  };

  const isLive = data?.is_live ?? false;
  const stationCount = data?.live_station_count ?? data?.stations?.length ?? 0;
  const lastUpdatedTime = formatTime(data?.last_updated);
  const source = data?.source ?? "kaggle_baseline";
  const fallbackReason = data?.fallback_reason;

  return {
    data,
    loading,
    error,
    isLive,
    stationCount,
    lastUpdatedTime,
    source,
    fallbackReason,
    refetch: () => loadData(city),
  };
}
