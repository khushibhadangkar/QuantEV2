/**
 * API client for the QuantEV FastAPI backend.
 * Base URL: http://localhost:8000
 */

import type { OptimizeRequest, OptimizeResponse } from "@/types/api";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Sanitise error messages ───────────────────────────────────────────────────
// Backend 500 detail strings can contain raw binary data from Qiskit/C
// extensions. Strip any non-printable / non-ASCII characters before
// surfacing them to the UI.
function sanitiseDetail(raw: unknown): string {
  if (typeof raw !== "string") return "The optimization pipeline returned an error.";

  // Remove null bytes, control characters and garbled binary sequences.
  const cleaned = raw
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/g, "")
    .replace(/[^\x20-\x7e\n\r\t]/g, "")
    .trim();

  // If nothing legible remains, return a generic message.
  if (!cleaned || cleaned.length < 4) {
    return "The optimization pipeline encountered an internal error. Check the server logs for details.";
  }

  // Strip the "Optimization pipeline failed: " prefix FastAPI adds so the
  // UI message is friendlier.
  return cleaned
    .replace(/^Optimization pipeline failed:\s*/i, "")
    .replace(/^Unknown error:\s*/i, "");
}

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly rawDetail?: string,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`;
  let response: Response;

  try {
    response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...options?.headers },
      ...options,
    });
  } catch (err) {
    // Network error — server not reachable
    console.error("[QuantEV] Network error calling", url, err);
    throw new ApiClientError(
      "Cannot reach the QuantEV backend. Make sure the server is running on port 8000.",
    );
  }

  if (!response.ok) {
    // Attempt to read the error body as text first (handles binary/garbled bodies)
    let rawText = "";
    try {
      rawText = await response.text();
    } catch {
      rawText = "";
    }

    // Log the full raw error for debugging
    console.error(
      `[QuantEV] API error ${response.status} from ${url}:`,
      rawText,
    );

    // Try to parse as JSON to get the FastAPI "detail" field
    let detail = "";
    try {
      const body = JSON.parse(rawText);
      detail = sanitiseDetail(body?.detail ?? "");
    } catch {
      detail = sanitiseDetail(rawText);
    }

    // Fallback to a human-readable status-code message
    if (!detail) {
      const statusMessages: Record<number, string> = {
        422: "The request was rejected by the server — invalid parameters.",
        500: "The optimization pipeline encountered an internal error. Check the server logs for details.",
        503: "The server is unavailable. Please try again shortly.",
      };
      detail = statusMessages[response.status] ?? `Server error (HTTP ${response.status}).`;
    }

    throw new ApiClientError(detail, response.status, rawText);
  }

  // Parse successful response
  try {
    return (await response.json()) as T;
  } catch (err) {
    console.error("[QuantEV] Failed to parse successful response from", url, err);
    throw new ApiClientError(
      "The server returned an unreadable response. Check the console for details.",
    );
  }
}

// ── Endpoints ─────────────────────────────────────────────────────────────────

/**
 * POST /api/v1/optimize
 * Run the full AI → QUBO → QAOA pipeline.
 */
export async function runOptimize(
  params: OptimizeRequest = {},
): Promise<OptimizeResponse> {
  return request<OptimizeResponse>("/api/v1/optimize", {
    method: "POST",
    body: JSON.stringify({
      station_count: params.station_count ?? 3,
      scenario: params.scenario ?? "all_hours",
      reps:  params.reps  ?? 1,
      shots: params.shots ?? 2048,
      seed:  params.seed  ?? 42,
    }),
  });
}

/**
 * GET /api/v1/health
 */
export async function getHealth(): Promise<{ status: string; service: string }> {
  return request("/api/v1/health");
}
