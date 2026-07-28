/** Small DOM lookup and HTML-escaping helpers shared by UI modules. */

"use strict";

/** Look up one DOM element by identifier. */
export const $ = (id) => document.getElementById(id);

/** Escape untrusted display text before interpolating it into HTML. */
export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
}
