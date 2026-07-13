"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml } from "./html.js";

const DEFAULT_SUMMARY_COUNTER_DURATION_MS = 1800;

function countValueParts(value) {
  const rawValue = String(value ?? "");
  const match = rawValue.match(/^(-?\d+(?:\.\d+)?)(\/\d+(?:\.\d+)?)?$/);
  if (!match) return null;
  const target = Number(match[1]);
  if (!Number.isFinite(target)) return null;
  return {
    target,
    decimals: (match[1].split(".")[1] || "").length,
    suffix: match[2] || "",
  };
}

function renderSummaryMetricValue(value) {
  const count = countValueParts(value);
  if (!count) return `<strong>${escapeHtml(value)}</strong>`;
  return `
    <strong
      data-summary-count-to="${escapeHtml(count.target)}"
      data-summary-count-decimals="${escapeHtml(count.decimals)}"
      data-summary-count-suffix="${escapeHtml(count.suffix)}"
    >${escapeHtml(value)}</strong>
  `;
}

function renderSummaryMetricBar(summary, jobsTotal) {
  const metrics = [
    { label: "Jobs Completed Today", value: Number(summary.completedToday || 0), tone: summary.completedToday ? "good" : "warn" },
    { label: "Jobs Remaining", value: Number(summary.jobsRemaining || 0), tone: summary.jobsRemaining ? "warn" : "good" },
    { label: "Jobs Complete", value: `${Number(summary.jobsComplete || 0)}/${Math.max(1, Number(jobsTotal || 0))}`, tone: summary.jobsRemaining ? "warn" : "good" },
    { label: "Remaining Job-Days", value: Number(summary.totalRemainingDays || 0), tone: summary.totalRemainingDays ? "warn" : "good" },
    { label: "Projected Finish", value: summary.projectedCompletion || "-", tone: "good" },
  ];
  return `
    <div class="summary-metrics-bar">
      ${metrics.map(metric => `
        <div class="metric summary-metric summary-metric-${metric.tone}">
          <div class="metric-title-row"><span class="subtle metric-label">${escapeHtml(metric.label)}</span></div>
          <div class="metric-value-row summary-metric-value-row">${renderSummaryMetricValue(metric.value)}</div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderSummaryGrid(summary, jobsTotal, puzzleInstanceId) {
  const notesMarkup = (summary.notes || [])
    .map(note => `<li>${escapeHtml(note)}</li>`)
    .join("") || "<li>No notable notes recorded.</li>";
  return `
    ${renderSummaryMetricBar(summary, jobsTotal)}
    <div class="summary-updates-banner" role="status">
      <h3>Updates</h3>
      <ul class="notes">${notesMarkup}</ul>
    </div>
    <div class="reveal-panel summary-puzzle-panel">
      ${renderSubmarinePuzzle(summary.puzzle, puzzleInstanceId, { showCaption: true, showPlacedToday: true })}
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
    <div class="puzzle-image-slice ${className}${newlyPlaced}" style="${sliceStyle(slice, loose)}" role="img" aria-label="${escapeHtml(`${label}: ${title}`)}">
      <img src="${PUZZLE_SUBMARINE_IMAGE}" alt="" aria-hidden="true" draggable="false">
    </div>
  `;
}

function renderPuzzlePlaceholder(tile, slice) {
  return `
    <div class="puzzle-image-slice puzzle-image-placeholder" style="${sliceStyle(slice)}" aria-hidden="true"></div>
  `;
}

export function renderSubmarinePuzzle(puzzle, instanceId, options = {}) {
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
      ${options.showCaption ? `<div class="puzzle-caption"><strong>Assembly</strong></div>` : ""}
      <div class="puzzle-stage" aria-label="Submarine puzzle showing assembled and waiting image sections">
        <div class="puzzle-assembled-row${unplacedItems.length ? " has-incomplete" : ""}" style="--slice-total:${total}">
          ${placedMarkup}
        </div>
        ${unplacedItems.length ? `<div class="puzzle-loose-row">${unplacedMarkup}</div>` : ""}
      </div>
      ${options.showPlacedToday ? `<div class="puzzle-added"><span>Placed today:</span>${placedMarkupToday}</div>` : ""}
    </div>
  `;
}

function summaryAnimationKey(payload, summary) {
  return [
    uiState.runCycleId,
    payload.seed,
    payload.day,
    payload.currentDate,
    summary.completedToday,
    summary.jobsRemaining,
    summary.jobsComplete,
    summary.totalRemainingDays,
    summary.projectedCompletion,
  ].join("|");
}

function now() {
  if (globalThis.performance && typeof globalThis.performance.now === "function") {
    return globalThis.performance.now();
  }
  return Date.now();
}

function requestFrame(callback) {
  const raf = globalThis.requestAnimationFrame || globalThis.window?.requestAnimationFrame;
  if (typeof raf === "function") {
    return raf(callback);
  }
  const timeout = globalThis.window?.setTimeout || globalThis.setTimeout;
  if (typeof timeout === "function") {
    return timeout(() => callback(now()), 16);
  }
  callback(now() + DEFAULT_SUMMARY_COUNTER_DURATION_MS);
  return null;
}

function summaryCounterDurationMs(payload = uiState.pendingAdvanceState || uiState.state) {
  const configured = Number(payload?.dailySummaryCounterDurationMs ?? DEFAULT_SUMMARY_COUNTER_DURATION_MS);
  return Number.isFinite(configured) ? Math.max(1, configured) : DEFAULT_SUMMARY_COUNTER_DURATION_MS;
}

function formatCounterValue(value, decimals, suffix) {
  const rounded = decimals > 0 ? value.toFixed(decimals) : String(Math.round(value));
  return `${rounded}${suffix}`;
}

export function animateSummaryCounters(container, options = {}) {
  if (!container || typeof container.querySelectorAll !== "function") return;
  const counters = Array.from(container.querySelectorAll("[data-summary-count-to]"));
  if (!counters.length) return;

  const duration = Math.max(0, Number(options.duration ?? DEFAULT_SUMMARY_COUNTER_DURATION_MS));
  const startTime = now();
  const entries = counters
    .map((element) => ({
      element,
      target: Number(element.dataset.summaryCountTo || 0),
      decimals: Math.max(0, Number(element.dataset.summaryCountDecimals || 0)),
      suffix: element.dataset.summaryCountSuffix || "",
    }))
    .filter((entry) => Number.isFinite(entry.target));

  entries.forEach((entry) => {
    entry.element.textContent = formatCounterValue(0, entry.decimals, entry.suffix);
  });

  if (!entries.length || duration === 0) {
    entries.forEach((entry) => {
      entry.element.textContent = formatCounterValue(entry.target, entry.decimals, entry.suffix);
    });
    return;
  }

  const step = (timestamp) => {
    const progress = Math.min(1, Math.max(0, (timestamp - startTime) / duration));
    const eased = 1 - Math.pow(1 - progress, 3);
    entries.forEach((entry) => {
      entry.element.textContent = formatCounterValue(entry.target * eased, entry.decimals, entry.suffix);
    });
    if (progress < 1) {
      requestFrame(step);
    }
  };

  requestFrame(step);
}

export function renderSummaryModal() {
  const payload = uiState.pendingAdvanceState || uiState.state;
  const summary = payload.lastSummary;
  const overlay = document.getElementById("summaryModalOverlay");
  const body = document.getElementById("summaryModalBody");
  if (!overlay || !body) return;
  if (!summary || !uiState.modalVisible) {
    overlay.classList.remove("active");
    uiState.summaryAnimationKey = null;
    return;
  }
  // The day has already been simulated on the server, but the summary modal
  // lets the player read consequences before committing that uiState.state locally.
  overlay.classList.add("active");
  const animationKey = summaryAnimationKey(payload, summary);
  if (uiState.summaryAnimationKey !== animationKey || !body.innerHTML) {
    uiState.summaryAnimationKey = animationKey;
    body.innerHTML = `<div class="summary-grid">${renderSummaryGrid(summary, payload.jobs.length, "summary-modal")}</div>`;
    body.scrollTop = 0;
    animateSummaryCounters(body, { duration: summaryCounterDurationMs(payload) });
  }
}

export function renderSummary() {
  const puzzle = uiState.state.livePuzzle;
  $("summarySection").classList.toggle("hidden", !puzzle);
  if (!puzzle) return;
  $("summaryGrid").innerHTML = `
    ${renderSubmarinePuzzle(puzzle, "live-submarine")}
  `;
}
