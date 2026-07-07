"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml } from "./html.js";

function renderSummaryMetricBar(summary, piecesTotal) {
  const risk = Math.round(Number(summary.risk || 0));
  const metrics = [
    {
      label: "Subjobs Today",
      value: Number(summary.completedToday || 0),
      tone: Number(summary.completedToday || 0) > 0 ? "good" : "warn",
    },
    {
      label: "Subjobs Remaining",
      value: Number(summary.jobsRemaining || 0),
      tone: Number(summary.jobsRemaining || 0) > 0 ? "warn" : "good",
    },
    {
      label: "Jobs Complete",
      value: `${Number(summary.piecesCompleted || 0)}/${Math.max(1, Number(piecesTotal || 0))}`,
      tone: Number(summary.piecesCompleted || 0) >= Number(piecesTotal || 0) ? "good" : "warn",
    },
    {
      label: "Behind Schedule",
      value: Number(summary.jobsBehindSchedule || 0),
      tone: Number(summary.jobsBehindSchedule || 0) > 0 ? "warn" : "good",
    },
    {
      label: "Late Subjobs",
      value: Number(summary.jobsLate || 0),
      tone: Number(summary.jobsLate || 0) > 0 ? "danger" : "good",
    },
    {
      label: "Risk",
      value: `${risk}/100`,
      tone: risk > 70 ? "danger" : risk > 40 ? "warn" : "good",
    },
    {
      label: "Projected Finish",
      value: summary.projectedCompletion || "-",
      tone: "good",
    },
  ];

  return `
    <div class="summary-metrics-bar">
      ${metrics.map(metric => `
        <div class="metric summary-metric summary-metric-${metric.tone}">
          <div class="metric-title-row">
            <span class="subtle metric-label">${escapeHtml(metric.label)}</span>
          </div>
          <div class="metric-value-row summary-metric-value-row">
            <strong>${escapeHtml(metric.value)}</strong>
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderSummaryGrid(summary, piecesTotal, puzzleInstanceId) {
  const notesMarkup = (summary.notes || [])
    .map(note => `<li>${escapeHtml(note)}</li>`)
    .join("") || "<li>No notable notes recorded.</li>";
  return `
    ${renderSummaryMetricBar(summary, piecesTotal)}
    <div class="summary-updates-banner" role="status">
      <h3>Updates</h3>
      <ul class="notes">${notesMarkup}</ul>
    </div>
    <div class="reveal-panel summary-puzzle-panel">
      ${renderSubmarinePuzzle(summary.puzzle, puzzleInstanceId)}
    </div>
  `;
}

function submarinePieceSlots(total) {
  if (total <= 0) return [];
  const n = (value) => Number(value).toFixed(1);
  const hullTop = (x) => 154 + Math.pow(Math.abs(x - 350) / 230, 1.75) * 19;
  const hullBottom = (x) => 286 - Math.pow(Math.abs(x - 350) / 230, 1.75) * 19;
  const wholePath = "M 70 220 C 70 138, 184 144, 365 144 C 630 144, 730 174, 730 220 C 730 266, 630 296, 365 296 C 184 296, 70 302, 70 220 Z";
  const tailSlot = () => ({
    part: "tail section",
    path: "M 126 188 L 66 166 L 84 220 L 66 274 L 126 252 L 150 220 Z",
    centerX: 106,
    centerY: 220,
    labelY: 222,
    labelSize: 10,
    bounds: { minX: 66, maxX: 150, minY: 166, maxY: 274 },
    details: [],
  });
  const noseSlot = () => ({
    part: "front section",
    path: "M 570 172 C 660 172 724 188 738 220 C 724 252 660 268 570 268 Z",
    centerX: 640,
    centerY: 220,
    labelY: 241,
    labelSize: 11,
    bounds: { minX: 570, maxX: 738, minY: 172, maxY: 268 },
    details: [`<circle class="piece-detail-fill" cx="640" cy="209" r="12"></circle>`],
  });
  const sailSlot = () => ({
    part: "sail and mast",
    path: "M 340 154 L 354 90 L 424 90 L 438 154 Z",
    centerX: 389,
    centerY: 124,
    labelY: 128,
    labelSize: 10,
    bounds: { minX: 340, maxX: 438, minY: 68, maxY: 154 },
    details: [
      `<path class="piece-detail" d="M 376 90 L 376 68 L 390 68 M 408 90 L 408 72"></path>`,
    ],
  });
  const bodySlot = (index, count) => {
    const startX = 130;
    const endX = 570;
    const width = (endX - startX) / count;
    const x1 = startX + index * width;
    const x2 = index === count - 1 ? endX : startX + (index + 1) * width;
    const top1 = hullTop(x1);
    const top2 = hullTop(x2);
    const bottom1 = hullBottom(x1);
    const bottom2 = hullBottom(x2);
    const curve = Math.max(18, width * 0.32);
    const path = [
      `M ${n(x1)} ${n(top1)}`,
      `C ${n(x1 + curve)} ${n(top1 - 8)} ${n(x2 - curve)} ${n(top2 - 8)} ${n(x2)} ${n(top2)}`,
      `L ${n(x2)} ${n(bottom2)}`,
      `C ${n(x2 - curve)} ${n(bottom2 + 8)} ${n(x1 + curve)} ${n(bottom1 + 8)} ${n(x1)} ${n(bottom1)}`,
      "Z",
    ].join(" ");
    const portholes = [218, 282, 456, 520]
      .filter((x) => x > x1 + 16 && x < x2 - 16)
      .map((x) => `<circle class="piece-detail-fill" cx="${x}" cy="207" r="12"></circle>`);
    let part = "middle hull";
    if (count === 1) part = "main hull";
    else if (index === 0) part = "aft hull";
    else if (index === count - 1) part = "forward hull";
    else part = `middle hull ${index}`;
    return {
      part,
      path,
      centerX: (x1 + x2) / 2,
      centerY: (top1 + top2 + bottom1 + bottom2) / 4,
      labelY: portholes.length ? 242 : 222,
      labelSize: Math.max(9, Math.min(12, width * 0.13)),
      bounds: {
        minX: x1,
        maxX: x2,
        minY: Math.min(top1, top2) - 10,
        maxY: Math.max(bottom1, bottom2) + 10,
      },
      details: portholes,
    };
  };

  if (total === 1) {
    return [{
      part: "submarine",
      path: wholePath,
      centerX: 400,
      centerY: 220,
      labelY: 222,
      labelSize: 13,
      bounds: { minX: 70, maxX: 730, minY: 138, maxY: 302 },
      details: [],
    }];
  }
  if (total === 2) {
    return [tailSlot(), noseSlot()];
  }
  if (total === 3) {
    return [
      bodySlot(0, 1),
      noseSlot(),
      sailSlot(),
    ];
  }

  const bodyCount = Math.max(1, total - 3);
  const slots = [tailSlot()];
  for (let index = 0; index < bodyCount; index += 1) {
    slots.push(bodySlot(index, bodyCount));
  }
  slots.push(noseSlot(), sailSlot());
  return slots.slice(0, total);
}

const PUZZLE_SUBMARINE_VIEWBOX_WIDTH = 800;
const PUZZLE_SUBMARINE_CENTER_Y = 220;
const PUZZLE_SUBMARINE_WITH_LOOSE_OFFSET_Y = -64;
const PUZZLE_WIDTH = 1080;
const PUZZLE_MIN_HEIGHT = 430;
const PUZZLE_LOOSE_ROW_Y = 292;
const PUZZLE_LOOSE_SIDE_PADDING = 74;
const PUZZLE_LOOSE_GAP = 22;
const PUZZLE_LOOSE_MAX_WIDTH = 150;
const PUZZLE_LOOSE_MAX_HEIGHT = 70;

function loosePieceStageHeight() {
  return PUZZLE_MIN_HEIGHT;
}

function slotBounds(slot) {
  return slot.bounds || {
    minX: slot.centerX - 80,
    maxX: slot.centerX + 80,
    minY: slot.centerY - 60,
    maxY: slot.centerY + 60,
  };
}

function loosePieceScale(slot) {
  const bounds = slotBounds(slot);
  const width = Math.max(1, bounds.maxX - bounds.minX);
  const height = Math.max(1, bounds.maxY - bounds.minY);
  return Math.min(1, PUZZLE_LOOSE_MAX_WIDTH / width, PUZZLE_LOOSE_MAX_HEIGHT / height);
}

function loosePieceLineLayout(items) {
  if (!items.length) return [];

  const base = items.map((item) => {
    const bounds = slotBounds(item.slot);
    const scale = loosePieceScale(item.slot);
    return {
      scale,
      width: Math.max(1, (bounds.maxX - bounds.minX) * scale),
    };
  });
  const availableWidth = PUZZLE_WIDTH - (PUZZLE_LOOSE_SIDE_PADDING * 2);
  const gapTotal = PUZZLE_LOOSE_GAP * Math.max(0, items.length - 1);
  const widthTotal = base.reduce((sum, item) => sum + item.width, 0);
  const fitScale = Math.min(1, Math.max(0.42, (availableWidth - gapTotal) / Math.max(1, widthTotal)));
  const rowWidth = (widthTotal * fitScale) + gapTotal;
  let cursor = (PUZZLE_WIDTH - rowWidth) / 2;

  return base.map((item) => {
    const width = item.width * fitScale;
    const position = {
      x: cursor + (width / 2),
      y: PUZZLE_LOOSE_ROW_Y,
      angle: 0,
    };
    cursor += width + PUZZLE_LOOSE_GAP;
    return {
      position,
      scale: item.scale * fitScale,
    };
  });
}

function loosePieceTransform(slot, position, scale) {
  const radians = position.angle * Math.PI / 180;
  const cos = Math.cos(radians) * scale;
  const sin = Math.sin(radians) * scale;
  const a = cos;
  const b = sin;
  const c = -sin;
  const d = cos;
  const e = position.x - (a * slot.centerX) - (c * slot.centerY);
  const f = position.y - (b * slot.centerX) - (d * slot.centerY);
  return `matrix(${[a, b, c, d, e, f].map((value) => value.toFixed(3)).join(" ")})`;
}

function renderPuzzleSection(tile, slot, className, transform = "") {
  const label = escapeHtml(tile.label || tile.id || "");
  const assembled = className === "placed";
  const status = assembled
    ? `Assembled${tile.completedAt ? ` at ${tile.completedAt}` : ""}`
    : `Waiting outside${tile.due ? `; due ${tile.due}` : ""}`;
  const title = `${tile.name || tile.id}: ${slot.part}. ${status}.`;
  const transformAttr = transform ? ` transform="${transform}"` : "";
  const newlyPlaced = assembled && tile.newlyCompleted ? " newly-placed" : "";
  const labelFill = assembled ? "#ffffff" : "var(--ink)";
  return `
    <g class="puzzle-section ${className}"${transformAttr}>
      <path class="puzzle-piece ${className}${newlyPlaced}" d="${slot.path}">
        <title>${escapeHtml(title)}</title>
      </path>
      ${(slot.details || []).join("")}
      <text class="puzzle-label" x="${slot.centerX.toFixed(1)}" y="${(slot.labelY || slot.centerY).toFixed(1)}" font-size="${(slot.labelSize || 11).toFixed(1)}" fill="${labelFill}">${label}</text>
    </g>
  `;
}

export function renderSubmarinePuzzle(puzzle, instanceId) {
  const tiles = Array.isArray(puzzle?.tiles) ? puzzle.tiles : [];
  if (!tiles.length) return "";

  const total = tiles.length;
  const width = PUZZLE_WIDTH;
  const slots = submarinePieceSlots(total);
  const unplacedItems = tiles
    .map((tile, index) => ({ tile, index, slot: slots[index] }))
    .filter((item) => !item.tile.completed);
  const height = loosePieceStageHeight();
  const submarineOffsetX = (PUZZLE_WIDTH - PUZZLE_SUBMARINE_VIEWBOX_WIDTH) / 2;
  const submarineOffsetY = unplacedItems.length
    ? PUZZLE_SUBMARINE_WITH_LOOSE_OFFSET_Y
    : (height / 2) - PUZZLE_SUBMARINE_CENTER_Y;
  const submarineTransform = `translate(${submarineOffsetX.toFixed(1)} ${submarineOffsetY.toFixed(1)})`;
  const slotMarkup = slots.map((slot) => `
    <path class="puzzle-slot" d="${slot.path}">
      <title>${escapeHtml(`${slot.part} slot`)}</title>
    </path>
  `).join("");
  const placedMarkup = tiles.map((tile, index) => (
    tile.completed ? renderPuzzleSection(tile, slots[index], "placed") : ""
  )).join("");
  const looseLayouts = loosePieceLineLayout(unplacedItems);
  const unplacedMarkup = unplacedItems
    .map((item, looseIndex) => {
      const layout = looseLayouts[looseIndex];
      const transform = loosePieceTransform(item.slot, layout.position, layout.scale);
      return renderPuzzleSection(item.tile, item.slot, "unplaced", transform);
    }).join("");
  const placedToday = tiles.filter(tile => tile.completed && tile.newlyCompleted);
  const placedMarkupToday = placedToday.length
    ? placedToday.map(tile => `<span class="badge">${escapeHtml(tile.label)}</span>`).join("")
    : `<span class="subtle">No jobs were placed today.</span>`;

  return `
    <div class="submarine-puzzle">
      <div class="puzzle-caption">
        <strong>Assembly</strong>
      </div>
      <div class="puzzle-stage">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Submarine puzzle showing assembled and waiting sections">
          <g class="puzzle-submarine-center" transform="${submarineTransform}">
            <g aria-hidden="true">${slotMarkup}</g>
            <g>${placedMarkup}</g>
          </g>
          <g>${unplacedMarkup}</g>
        </svg>
      </div>
      <div class="puzzle-added"><span>Placed today:</span>${placedMarkupToday}</div>
    </div>
  `;
}

export function renderSummaryModal() {
  const payload = uiState.pendingAdvanceState || uiState.state;
  const summary = payload.lastSummary;
  const overlay = document.getElementById("summaryModalOverlay");
  const body = document.getElementById("summaryModalBody");
  if (!overlay || !body) return;
  if (!summary || !uiState.modalVisible) {
    overlay.classList.remove("active");
    return;
  }
  // The day has already been simulated on the server, but the summary modal
  // lets the player read consequences before committing that uiState.state locally.
  overlay.classList.add("active");
  body.innerHTML = `<div class="summary-grid">${renderSummaryGrid(summary, payload.pieces.length, "summary-modal")}</div>`;
  body.scrollTop = 0;
}

export function renderSummary() {
  const puzzle = uiState.state.livePuzzle;
  $("summarySection").classList.toggle("hidden", !puzzle);
  if (!puzzle) return;
  $("summaryGrid").innerHTML = `
    <div class="reveal-panel summary-puzzle-panel live-submarine-panel">
      ${renderSubmarinePuzzle(puzzle, "live-submarine")}
    </div>
  `;
}
