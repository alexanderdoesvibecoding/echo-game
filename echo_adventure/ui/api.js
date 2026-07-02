"use strict";

export async function api(path, options = {}) {
  // All API endpoints return JSON, including errors. Throwing here keeps
  // button handlers small and centralizes user-facing error display.
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}
