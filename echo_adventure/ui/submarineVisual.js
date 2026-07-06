"use strict";

export function renderSubmarineImage({
  idPrefix = "submarine",
  className = "",
  ariaLabel = "Submarine underway",
  decorative = false,
} = {}) {
  const bodyGradientId = `${idPrefix}Body`;
  const classAttribute = className ? ` class="${className}"` : "";
  const accessibilityAttributes = decorative
    ? `aria-hidden="true" focusable="false"`
    : `role="img" aria-label="${ariaLabel}"`;

  return `
    <svg${classAttribute} viewBox="0 0 720 250" ${accessibilityAttributes}>
      <defs>
        <linearGradient id="${bodyGradientId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#0072b2"></stop>
          <stop offset="100%" stop-color="#004f7c"></stop>
        </linearGradient>
      </defs>

      <path d="M 60 135 L 85 135 M 50 100 L 60 135 L 50 170" fill="none" stroke="#004f7c" stroke-width="8" stroke-linecap="round"></path>
      <path d="M 110 105 L 75 90 L 85 135 Z" fill="#00649b"></path>
      <path d="M 110 165 L 75 180 L 85 135 Z" fill="#00649b"></path>
      <path d="M 80 135 C 80 80, 160 85, 350 85 C 560 85, 660 100, 660 135 C 660 170, 560 185, 350 185 C 160 185, 80 190, 80 135 Z" fill="url(#${bodyGradientId})"></path>
      <path d="M 300 86 L 310 35 L 380 35 L 390 86 Z" fill="#00649b"></path>
      <path d="M 330 35 L 330 15 L 340 15 M 360 35 L 360 20" fill="none" stroke="#004f7c" stroke-width="5" stroke-linecap="round"></path>
      <path d="M 140 105 C 260 100, 480 100, 620 115" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="4" stroke-linecap="round"></path>
      <g fill="#e6f2fa" stroke="#003a5d" stroke-width="4">
        <circle cx="200" cy="135" r="14"></circle>
        <circle cx="260" cy="135" r="14"></circle>
        <circle cx="460" cy="135" r="14"></circle>
        <circle cx="520" cy="135" r="14"></circle>
      </g>
    </svg>
  `;
}
