const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const { timeoutMs = 0, ...fetchOptions } = options;
  const controller = new AbortController();
  const timer = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null;
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(fetchOptions.headers || {}),
      },
      ...fetchOptions,
      signal: controller.signal,
    });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error("The recommendation request timed out. The server may be unavailable; please try again.");
    }
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail || body);
    } catch {}
    throw new Error(message);
  }

  return response.json();
}

export const getHealth = () => request("/api/health");
export const getAspects = () => request("/api/aspects");
export const getFilters = () => request("/api/filters");
export const getLaptop = (id) =>
  request(`/api/laptops/${encodeURIComponent(id)}`);

export const getRecommendations = (payload) =>
  request("/api/recommendations", {
    timeoutMs: 150000, // Allow Render cold starts without waiting indefinitely.
    method: "POST",
    body: JSON.stringify(payload),
  });

export const refineRecommendations = (payload) =>
  request("/api/recommendations/refine", {
    timeoutMs: 150000,
    method: "POST",
    body: JSON.stringify(payload),
  });


export const getAspectEvidence = (
  laptopId,
  aspectId,
  limit = 6
) =>
  request(
    `/api/laptops/${encodeURIComponent(
      laptopId
    )}/aspects/${encodeURIComponent(
      aspectId
    )}/evidence?limit=${encodeURIComponent(limit)}`
  );
