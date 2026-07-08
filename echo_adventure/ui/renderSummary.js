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

const PUZZLE_SUBMARINE_IMAGE = "/ui/assets/virginia-submarine-cutout.png";
const PUZZLE_IMAGE_WIDTH = 1269;
const PUZZLE_IMAGE_HEIGHT = 260;
const PUZZLE_IMAGE_ASPECT = PUZZLE_IMAGE_WIDTH / PUZZLE_IMAGE_HEIGHT;

function submarineImageSlices(total) {
  return Array.from({ length: Math.max(0, total) }, (_, index) => ({
    index,
    total,
    part: `submarine image section ${index + 1}`,
  }));
}

function scrambleKey(index, total) {
  return (Math.imul(index + 1, 2654435761) ^ Math.imul(total + 17, 2246822519)) >>> 0;
}

function scrambledUnplacedItems(items, total) {
  return [...items].sort((a, b) => scrambleKey(a.index, total) - scrambleKey(b.index, total));
}

function sliceAspect(slice) {
  return PUZZLE_IMAGE_ASPECT / Math.max(1, slice.total);
}

function sliceStyle(slice, loose = false) {
  const aspect = sliceAspect(slice);
  const values = [
    `--slice-count:${slice.total}`,
    `--slice-index:${slice.index}`,
    `--slice-aspect:${aspect.toFixed(5)}`,
  ];
  if (loose) {
    values.push(`--slice-width:${Math.max(30, Math.min(132, 96 * aspect)).toFixed(1)}px`);
  }
  return values.join("; ");
}

function renderPuzzleSection(tile, slice, className) {
  const label = escapeHtml(tile.label || tile.id || "");
  const assembled = className === "placed";
  const status = assembled
    ? `Assembled${tile.completedAt ? ` at ${tile.completedAt}` : ""}`
    : `Waiting outside${tile.due ? `; due ${tile.due}` : ""}`;
  const title = `${tile.name || tile.id}: ${slice.part}. ${status}.`;
  const newlyPlaced = assembled && tile.newlyCompleted ? " newly-placed" : "";
  const loose = className === "unplaced";
  return `
    <div class="puzzle-image-slice ${className}${newlyPlaced}" style="${sliceStyle(slice, loose)}" role="img" aria-label="${escapeHtml(`${label}: ${title}`)}" title="${escapeHtml(title)}">
      <img src="${PUZZLE_SUBMARINE_IMAGE}" alt="" aria-hidden="true" draggable="false">
    </div>
  `;
}

function renderPuzzlePlaceholder(tile, slice) {
  const title = `${tile.name || tile.id}: ${slice.part}. Waiting${tile.due ? `; due ${tile.due}` : ""}.`;
  return `
    <div class="puzzle-image-slice puzzle-image-placeholder" style="${sliceStyle(slice)}" aria-hidden="true" title="${escapeHtml(title)}"></div>
  `;
}

export function renderSubmarinePuzzle(puzzle, instanceId) {
  const tiles = Array.isArray(puzzle?.tiles) ? puzzle.tiles : [];
  if (!tiles.length) return "";

  const total = tiles.length;
  const slices = submarineImageSlices(total);
  const unplacedItems = tiles
    .map((tile, index) => ({ tile, index, slice: slices[index] }))
    .filter((item) => !item.tile.completed);
  const scrambledItems = scrambledUnplacedItems(unplacedItems, total);
  const placedMarkup = tiles.map((tile, index) => (
    tile.completed ? renderPuzzleSection(tile, slices[index], "placed") : renderPuzzlePlaceholder(tile, slices[index])
  )).join("");
  const unplacedMarkup = scrambledItems
    .map(item => renderPuzzleSection(item.tile, item.slice, "unplaced"))
    .join("");
  const placedToday = tiles.filter(tile => tile.completed && tile.newlyCompleted);
  const placedMarkupToday = placedToday.length
    ? placedToday.map(tile => `<span class="badge">${escapeHtml(tile.label)}</span>`).join("")
    : `<span class="subtle">No jobs were placed today.</span>`;

  return `
    <div class="submarine-puzzle">
      <div class="puzzle-caption">
        <strong>Assembly</strong>
      </div>
      <div class="puzzle-stage" aria-label="Submarine puzzle showing assembled and waiting image sections">
        <div class="puzzle-assembled-row${unplacedItems.length ? " has-incomplete" : ""}" style="--slice-total:${total}">
          ${placedMarkup}
        </div>
        ${unplacedItems.length ? `<div class="puzzle-loose-row">${unplacedMarkup}</div>` : ""}
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
