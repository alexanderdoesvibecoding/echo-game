/** JSON request helper for the browser-facing game API. */

"use strict";

/** Send an API request with JSON defaults and surface server error messages. */
export async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}
