"use strict";

export const SUBMARINE_IMAGE_SRC = "/ui/assets/virginia-submarine-cutout.png";

function escapeAttribute(value) {
  return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
}

export function renderSubmarineImage({
  idPrefix = "submarine",
  className = "",
  ariaLabel = "Submarine underway",
  decorative = false,
} = {}) {
  const classAttribute = className ? ` class="${className}"` : "";
  const accessibilityAttributes = decorative
    ? `alt="" aria-hidden="true"`
    : `alt="${escapeAttribute(ariaLabel)}"`;

  return `
    <img${classAttribute} src="${SUBMARINE_IMAGE_SRC}" ${accessibilityAttributes} data-visual-id="${escapeAttribute(idPrefix)}" draggable="false">
  `;
}
