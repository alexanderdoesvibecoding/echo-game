"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml } from "./html.js";

function renderPastDueJobs(pastDueJobs) {
  if (!pastDueJobs || pastDueJobs.length === 0) {
    return `<p class="subtle">No past due subjobs.</p>`;
  }

  return `
    <table>
      <thead>
        <tr>
          <th>Subjob</th>
          <th>Shop</th>
          <th>Due</th>
          <th>Late</th>
          <th>Remaining</th>
        </tr>
      </thead>
      <tbody>
        ${pastDueJobs.map(job => `
          <tr>
            <td>${escapeHtml(job.id)}</td>
            <td>${escapeHtml(job.shop)}</td>
            <td>${escapeHtml(job.due)}</td>
            <td>${job.daysLate} day${job.daysLate === 1 ? "" : "s"}</td>
            <td>${job.remaining} shift${job.remaining === 1 ? "" : "s"}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderSummaryStatsTable(summary, piecesTotal) {
  return `
    <table>
      <tbody>
        <tr><td>Subjobs completed today</td><td>${summary.completedToday}</td></tr>
        <tr><td>Subjobs remaining</td><td>${summary.jobsRemaining}</td></tr>
        <tr><td>Jobs complete</td><td>${summary.piecesCompleted}/${piecesTotal}</td></tr>
        <tr><td>Subjobs behind schedule</td><td>${summary.jobsBehindSchedule}</td></tr>
        <tr><td>Subjobs late</td><td>${summary.jobsLate}</td></tr>
        <tr><td>Risk</td><td>${Math.round(summary.risk)}/100</td></tr>
        <tr><td>Projected completion</td><td>${summary.projectedCompletion}</td></tr>
      </tbody>
    </table>
  `;
}

function renderSummaryGrid(summary, piecesTotal, puzzleInstanceId) {
  const notesMarkup = (summary.notes || [])
    .map(note => `<li>${escapeHtml(note)}</li>`)
    .join("") || "<li>No notable notes recorded.</li>";
  return `
    <div class="summary-main-column">
      <div class="reveal-panel summary-puzzle-panel">
        ${renderSubmarinePuzzle(summary.puzzle, puzzleInstanceId)}
      </div>
    </div>
    <div class="summary-side-column">
      <div class="reveal-panel summary-stats-panel">
        <h3>Stats</h3>
        <div class="summary-table-scroll">${renderSummaryStatsTable(summary, piecesTotal)}</div>
      </div>
      <div class="reveal-panel summary-updates-panel">
        <h3>Updates</h3>
        <ul class="notes">${notesMarkup}</ul>
      </div>
      <div class="reveal-panel summary-past-due-panel">
        <h3>Past Due Subjobs</h3>
        <div class="summary-table-scroll">${renderPastDueJobs(summary.pastDueJobs)}</div>
      </div>
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
    details: [],
  });
  const noseSlot = () => ({
    part: "front section",
    path: "M 570 172 C 660 172 724 188 738 220 C 724 252 660 268 570 268 Z",
    centerX: 640,
    centerY: 220,
    labelY: 241,
    labelSize: 11,
    details: [`<circle class="piece-detail-fill" cx="640" cy="209" r="12"></circle>`],
  });
  const sailSlot = () => ({
    part: "sail and mast",
    path: "M 340 154 L 354 90 L 424 90 L 438 154 Z",
    centerX: 389,
    centerY: 124,
    labelY: 128,
    labelSize: 10,
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

function loosePieceColumnCount(total) {
  if (total <= 3) return 1;
  if (total <= 8) return 4;
  return 5;
}

function loosePieceRows(total) {
  if (total <= 0) return 0;
  return Math.ceil(total / loosePieceColumnCount(total));
}

function loosePieceStageHeight(total) {
  const rows = loosePieceRows(total);
  return rows ? 550 + (rows - 1) * 170 : 500;
}

function loosePiecePosition(index, total) {
  const columns = loosePieceColumnCount(total);
  const column = index % columns;
  const row = Math.floor(index / columns);
  const laneWidth = 800 / columns;
  const angles = [-7, 5, -4, 7, -5];
  return {
    x: columns === 1 ? 400 : laneWidth * column + laneWidth / 2,
    y: 420 + row * 170,
    angle: angles[index % angles.length],
  };
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

function renderSubmarinePuzzle(puzzle, instanceId) {
  const tiles = Array.isArray(puzzle?.tiles) ? puzzle.tiles : [];
  if (!tiles.length) return "";

  const total = tiles.length;
  const width = 800;
  const slots = submarinePieceSlots(total);
  const unplacedItems = tiles
    .map((tile, index) => ({ tile, index, slot: slots[index] }))
    .filter((item) => !item.tile.completed);
  const height = loosePieceStageHeight(unplacedItems.length);
  const slotMarkup = slots.map((slot) => `
    <path class="puzzle-slot" d="${slot.path}">
      <title>${escapeHtml(`${slot.part} slot`)}</title>
    </path>
  `).join("");
  const placedMarkup = tiles.map((tile, index) => (
    tile.completed ? renderPuzzleSection(tile, slots[index], "placed") : ""
  )).join("");
  const unplacedMarkup = unplacedItems
    .map((item, looseIndex) => {
      const position = loosePiecePosition(looseIndex, unplacedItems.length);
      const dx = position.x - item.slot.centerX;
      const dy = position.y - item.slot.centerY;
      const transform = `translate(${dx.toFixed(1)} ${dy.toFixed(1)}) rotate(${position.angle} ${item.slot.centerX.toFixed(1)} ${item.slot.centerY.toFixed(1)})`;
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
          <g aria-hidden="true">${slotMarkup}</g>
          <g>${placedMarkup}</g>
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
  const summary = uiState.state.lastSummary;
  $("summarySection").classList.toggle("hidden", !summary);
  if (!summary) return;
  $("summaryGrid").innerHTML = renderSummaryGrid(summary, uiState.state.pieces.length, "summary-panel");
}
