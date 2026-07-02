"use strict";

export const $ = (id) => document.getElementById(id);

export const fmtNum = (value) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
}
