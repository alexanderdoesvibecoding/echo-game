/** Daily summary metrics, submarine puzzle slices, and counter animation. */

"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml } from "./html.js";
import { SUBMARINE_IMAGE_SRC } from "./submarineVisual.js";

const DEFAULT_SUMMARY_COUNTER_DURATION_MS = 1800;

/** Return every daily workload card that can disclose a per-job breakdown. */
function workloadDropdownCards() {
  return Array.from(document.querySelectorAll(".summary-metric-dropdown"));
}

/** Synchronize one workload disclosure's visual and accessibility state. */
function setWorkloadDropdownOpen(card, open) {
  if (!card) return;
  const trigger = card.querySelector(".remaining-job-days-trigger");
  const dropdown = card.querySelector(".remaining-job-days-tooltip");
  card.classList.toggle("is-open", open);
  trigger?.setAttribute("aria-expanded", String(open));
  if (dropdown) dropdown.hidden = !open;
}

/** Close all daily workload disclosures except an optional active card. */
function closeWorkloadDropdowns(exceptCard = null) {
  workloadDropdownCards().forEach((card) => {
    if (card !== exceptCard) setWorkloadDropdownOpen(card, false);
  });
}

// The workload breakdown is an explicit disclosure: hover alone never opens it,
// while outside clicks and Escape provide predictable dismissal.
document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const trigger = target?.closest(".remaining-job-days-trigger");
  if (trigger) {
    const card = trigger.closest(".summary-metric-dropdown");
    if (!card) return;
    const shouldOpen = !card.classList.contains("is-open");
    closeWorkloadDropdowns(card);
    setWorkloadDropdownOpen(card, shouldOpen);
    event.preventDefault?.();
    return;
  }
  if (!target?.closest(".summary-metric-dropdown")) closeWorkloadDropdowns();
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const openCard = workloadDropdownCards().find(card => card.classList.contains("is-open"));
  if (!openCard) return;
  const trigger = openCard.querySelector(".remaining-job-days-trigger");
  setWorkloadDropdownOpen(openCard, false);
  trigger?.focus();
});

/** Parse integer or ratio text into animatable counter components. */
function countValueParts(value) {
  const rawValue = String(value ?? "");
  // Accept a numeric prefix and optional ratio suffix (for example "3/20");
  // dates and arbitrary prose deliberately remain static.
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

/** Render one summary value with counter metadata. */
function renderSummaryMetricValue(value, startValue = 0) {
  const count = countValueParts(value);
  if (!count) return `<strong>${escapeHtml(value)}</strong>`;
  const start = Number(startValue);
  const countFrom = Number.isFinite(start) ? start : 0;
  return `
    <strong
      data-summary-count-from="${escapeHtml(countFrom)}"
      data-summary-count-to="${escapeHtml(count.target)}"
      data-summary-count-decimals="${escapeHtml(count.decimals)}"
      data-summary-count-suffix="${escapeHtml(count.suffix)}"
    >${escapeHtml(value)}</strong>
  `;
}

/** Render aggregate and per-job remaining-work details. */
function renderRemainingJobDaysMetric(metric, remainingJobs) {
  // Normalize malformed optional payloads so the tooltip remains safe during
  // initial loading and final completion.
  const jobs = Array.isArray(remainingJobs) ? remainingJobs : [];
  const detailRows = jobs.map((job) => {
    const days = Math.max(0, Number(job.remainingDays) || 0);
    return `
      <li>
        <span>${escapeHtml(job.name || "Unnamed job")}</span>
        <strong>${escapeHtml(days)} ${days === 1 ? "day" : "days"}</strong>
      </li>
    `;
  }).join("");
  const details = detailRows
    ? `<ul class="remaining-job-days-list">${detailRows}</ul>`
    : `<p class="remaining-job-days-empty">All jobs complete.</p>`;

  return `
    <div
      class="metric summary-metric summary-metric-${metric.tone} summary-metric-dropdown"
    >
      <div class="metric-title-row">
        <button
          type="button"
          class="metric-label remaining-job-days-trigger"
          aria-label="Toggle incomplete jobs for ${escapeHtml(metric.label)}"
          aria-expanded="false"
          aria-controls="remainingJobDaysTooltip"
        >
          <span>${escapeHtml(metric.label)}</span>
          <span class="remaining-job-days-chevron" aria-hidden="true">▾</span>
        </button>
      </div>
      <div class="metric-value-row summary-metric-value-row">${renderSummaryMetricValue(metric.value, metric.startValue)}</div>
      <div class="remaining-job-days-tooltip" id="remainingJobDaysTooltip" role="region" aria-labelledby="remainingJobDaysTooltipTitle" hidden>
        <div class="remaining-job-days-tooltip-title" id="remainingJobDaysTooltipTitle">Incomplete jobs</div>
        ${details}
      </div>
    </div>
  `;
}

/** Render the daily ECD and remaining-work comparison bars. */
function renderSummaryMetricBar(summary) {
  const jobsComplete = Number(summary.jobsComplete ?? summary.completedToday ?? 0);
  const metrics = [
    {
      label: "Jobs Complete",
      value: jobsComplete,
      startValue: Number(summary.previousJobsComplete ?? 0),
      tone: jobsComplete ? "good" : "warn",
    },
    {
      label: "Jobs Remaining",
      value: Number(summary.jobsRemaining || 0),
      startValue: Number(summary.previousJobsRemaining ?? 0),
      tone: summary.jobsRemaining ? "warn" : "good",
    },
    {
      label: "Cumulative Workload",
      value: Number(summary.totalRemainingDays || 0),
      startValue: Number(summary.previousTotalRemainingDays ?? 0),
      tone: summary.totalRemainingDays ? "warn" : "good",
    },
    { label: "Projected Finish", value: summary.projectedCompletion || "-", tone: "good" },
  ];
  return `
    <div class="summary-metrics-bar">
      ${metrics.map(metric => (
        metric.label === "Cumulative Workload"
          ? renderRemainingJobDaysMetric(metric, summary.remainingJobs)
          : `
            <div class="metric summary-metric summary-metric-${metric.tone}">
              <div class="metric-title-row"><span class="subtle metric-label">${escapeHtml(metric.label)}</span></div>
              <div class="metric-value-row summary-metric-value-row">${renderSummaryMetricValue(metric.value, metric.startValue)}</div>
            </div>
          `
      )).join("")}
    </div>
  `;
}

/** Render the complete set of daily metric cards. */
function renderSummaryGrid(summary) {
  const notes = Array.isArray(summary.notes) ? summary.notes : [];
  // Completion notes are meaningful only on days that actually placed pieces.
  const showUpdates = Number(summary.completedToday || 0) > 0 && notes.length;
  const notesMarkup = notes
    .map(note => `<li>${escapeHtml(note)}</li>`)
    .join("");
  const updatesMarkup = showUpdates ? `
    <div class="summary-updates-banner" role="status">
      <h3>Updates</h3>
      <ul class="notes">${notesMarkup}</ul>
    </div>
  ` : "";
  return `
    ${renderSummaryMetricBar(summary)}
    ${updatesMarkup}
    <div class="reveal-panel summary-puzzle-panel">
      ${renderSubmarinePuzzle(summary.puzzle, {
        showCaption: true,
        animateNewlyPlaced: true,
      })}
    </div>
  `;
}

const PUZZLE_IMAGE_WIDTH = 1269;
const PUZZLE_IMAGE_HEIGHT = 260;
const PUZZLE_IMAGE_ASPECT = PUZZLE_IMAGE_WIDTH / PUZZLE_IMAGE_HEIGHT;

/** Divide the submarine image into one responsive slice per job. */
function submarineImageSlices(total) {
  return Array.from({ length: Math.max(0, total) }, (_, index) => ({
    index,
    total,
    part: `submarine image section ${index + 1}`,
  }));
}

/** Generate a stable display order for unplaced puzzle slices. */
function scrambleKey(index, total) {
  // Integer mixing creates a stable pseudo-random order without mutable RNG or
  // hydration differences across renders.
  return (Math.imul(index + 1, 2654435761) ^ Math.imul(total + 17, 2246822519)) >>> 0;
}

/** Sort unplaced puzzle items into deterministic scrambled order. */
function scrambledUnplacedItems(items, total) {
  return [...items].sort((a, b) => scrambleKey(a.index, total) - scrambleKey(b.index, total));
}

/** Return a slice's width-to-height ratio. */
function sliceAspect(slice) {
  return PUZZLE_IMAGE_ASPECT / Math.max(1, slice.total);
}

/** Build CSS custom properties for an assembled or loose slice. */
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

/** Build deterministic animation offsets for a newly placed slice. */
function placementMotionStyle(slice) {
  // Motion is derived from final position, giving outer slices longer lateral
  // travel while keeping the animation deterministic.
  const centerOffset = slice.index - ((slice.total - 1) / 2);
  const drift = (centerOffset * -18).toFixed(1);
  const delay = Math.min(420, Math.max(0, slice.index * 45));
  const rotate = (centerOffset * 1.6).toFixed(1);
  return `--placement-x:${drift}%; --placement-delay:${delay}ms; --placement-rotate:${rotate}deg`;
}

/** Render one submarine slice as semantic HTML. */
function renderPuzzleSection(tile, slice, className, options = {}) {
  const label = escapeHtml(tile.label || "");
  const assembled = className === "placed";
  const status = assembled
    ? `Assembled${tile.completedAt ? ` at ${tile.completedAt}` : ""}`
    : "Waiting outside";
  const title = `${tile.name}: ${slice.part}. ${status}.`;
  const highlightNewlyPlaced = options.highlightNewlyPlaced !== false;
  const animateNewlyPlaced = Boolean(options.animateNewlyPlaced);
  // Highlighting and physical movement are separate options because the modal
  // animates new pieces while the persistent puzzle stays still.
  const newlyPlaced = assembled && tile.newlyCompleted && highlightNewlyPlaced;
  const movingIntoPlace = newlyPlaced && animateNewlyPlaced;
  const classNames = [
    "puzzle-image-slice",
    className,
    newlyPlaced ? "newly-placed" : "",
    movingIntoPlace ? "move-into-place" : "",
  ].filter(Boolean).join(" ");
  const loose = className === "unplaced";
  const style = [
    sliceStyle(slice, loose),
    movingIntoPlace ? placementMotionStyle(slice) : "",
  ].filter(Boolean).join("; ");
  return `
    <div class="${classNames}" style="${style}" role="img" aria-label="${escapeHtml(`${label}: ${title}`)}">
      <img src="${SUBMARINE_IMAGE_SRC}" alt="" aria-hidden="true" draggable="false">
    </div>
  `;
}

/** Render a reserved assembled-position placeholder. */
function renderPuzzlePlaceholder(tile, slice) {
  return `
    <div class="puzzle-image-slice puzzle-image-placeholder" style="${sliceStyle(slice)}" aria-hidden="true"></div>
  `;
}

/** Render assembled and waiting puzzle slices for the current run. */
export function renderSubmarinePuzzle(puzzle, options = {}) {
  const tiles = Array.isArray(puzzle?.tiles) ? puzzle.tiles : [];
  if (!tiles.length) return "";

  const total = tiles.length;
  const showUnplaced = options.showUnplaced !== false;
  const highlightNewlyPlaced = options.highlightNewlyPlaced !== false;
  const animateNewlyPlaced = Boolean(options.animateNewlyPlaced);
  const slices = submarineImageSlices(total);
  const unplacedItems = tiles
    .map((tile, index) => ({ tile, index, slice: slices[index] }))
    .filter((item) => !item.tile.completed);
  // Placeholders retain exact slice widths so completed sections never shift as
  // other jobs finish.
  const placedMarkup = tiles.map((tile, index) => (
    tile.completed
      ? renderPuzzleSection(tile, slices[index], "placed", { highlightNewlyPlaced, animateNewlyPlaced })
      : renderPuzzlePlaceholder(tile, slices[index])
  )).join("");
  const unplacedMarkup = showUnplaced
    ? scrambledUnplacedItems(unplacedItems, total)
      .map(item => renderPuzzleSection(item.tile, item.slice, "unplaced"))
      .join("")
    : "";
  return `
    <div class="submarine-puzzle">
      ${options.showCaption ? `<div class="puzzle-caption"><strong>Assembly</strong></div>` : ""}
      <div class="puzzle-stage" aria-label="Submarine puzzle showing ${showUnplaced ? "assembled and waiting" : "assembled"} image sections">
        <div class="puzzle-assembled-row${unplacedItems.length ? " has-incomplete" : ""}" style="--slice-total:${total}">
          ${placedMarkup}
        </div>
        ${showUnplaced && unplacedItems.length ? `<div class="puzzle-loose-row">${unplacedMarkup}</div>` : ""}
      </div>
    </div>
  `;
}

/** Build an identity key that prevents replaying one summary animation. */
function summaryAnimationKey(payload, summary) {
  // Include run identity and every animated aggregate so only genuinely new
  // summaries replay counters.
  return [
    uiState.runCycleId,
    payload.seed,
    payload.day,
    payload.currentDate,
    summary.jobsComplete,
    summary.completedToday,
    summary.jobsRemaining,
    summary.totalRemainingDays,
    summary.projectedCompletion,
  ].join("|");
}

/** Read high-resolution time when available. */
function now() {
  if (globalThis.performance && typeof globalThis.performance.now === "function") {
    return globalThis.performance.now();
  }
  return Date.now();
}

/** Schedule an animation frame with a timer fallback for tests. */
function requestFrame(callback) {
  // The fallbacks support Node test doubles and older environments while keeping
  // production animation on requestAnimationFrame.
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

/** Return the configured or default counter animation duration. */
function summaryCounterDurationMs(payload = uiState.pendingAdvanceState || uiState.state) {
  const configured = Number(payload?.dailySummaryCounterDurationMs ?? DEFAULT_SUMMARY_COUNTER_DURATION_MS);
  return Number.isFinite(configured) ? Math.max(1, configured) : DEFAULT_SUMMARY_COUNTER_DURATION_MS;
}

/** Format an interpolated counter value with precision and suffix. */
function formatCounterValue(value, decimals, suffix) {
  const rounded = decimals > 0 ? value.toFixed(decimals) : String(Math.round(value));
  return `${rounded}${suffix}`;
}

/** Animate every marked summary counter to its final value. */
export function animateSummaryCounters(container, options = {}) {
  if (!container || typeof container.querySelectorAll !== "function") return;
  const counters = Array.from(container.querySelectorAll("[data-summary-count-to]"));
  if (!counters.length) return;

  const duration = Math.max(0, Number(options.duration ?? DEFAULT_SUMMARY_COUNTER_DURATION_MS));
  const startTime = now();
  // Ignore malformed individual counters rather than failing the entire summary.
  const entries = counters
    .map((element) => ({
      element,
      start: Number(element.dataset.summaryCountFrom || 0),
      target: Number(element.dataset.summaryCountTo || 0),
      decimals: Math.max(0, Number(element.dataset.summaryCountDecimals || 0)),
      suffix: element.dataset.summaryCountSuffix || "",
    }))
    .filter((entry) => Number.isFinite(entry.start) && Number.isFinite(entry.target));

  entries.forEach((entry) => {
    entry.element.textContent = formatCounterValue(entry.start, entry.decimals, entry.suffix);
  });

  if (!entries.length || duration === 0) {
    entries.forEach((entry) => {
      entry.element.textContent = formatCounterValue(entry.target, entry.decimals, entry.suffix);
    });
    return;
  }

  /** Render one eased animation frame and schedule the next until complete. */
  const step = (timestamp) => {
    const progress = Math.min(1, Math.max(0, (timestamp - startTime) / duration));
    // Cubic ease-out moves quickly at first and settles gently on the exact value.
    const eased = 1 - Math.pow(1 - progress, 3);
    entries.forEach((entry) => {
      const value = entry.start + ((entry.target - entry.start) * eased);
      entry.element.textContent = formatCounterValue(value, entry.decimals, entry.suffix);
    });
    if (progress < 1) {
      requestFrame(step);
    }
  };

  requestFrame(step);
}

/** Render the blocking daily-summary modal. */
export function renderSummaryModal() {
  // While the modal is open, render from the prepared next-state payload but
  // leave the underlying main screen on the outgoing day.
  const payload = uiState.pendingAdvanceState || uiState.state;
  const summary = payload.lastSummary;
  const overlay = document.getElementById("summaryModalOverlay");
  const body = document.getElementById("summaryModalBody");
  const title = document.getElementById("summaryModalTitle");
  if (!overlay || !body) return;
  if (!summary || !uiState.modalVisible) {
    overlay.classList.remove("active");
    uiState.summaryAnimationKey = null;
    return;
  }
  overlay.classList.add("active");
  if (title) {
    title.textContent = summary.date ? `Daily Summary - ${summary.date}` : "Daily Summary";
  }
  const animationKey = summaryAnimationKey(payload, summary);
  // Frequent top-level renders must not restart counters or reset modal scroll.
  if (uiState.summaryAnimationKey !== animationKey || !body.innerHTML) {
    uiState.summaryAnimationKey = animationKey;
    body.innerHTML = `<div class="summary-grid">${renderSummaryGrid(summary)}</div>`;
    body.scrollTop = 0;
    animateSummaryCounters(body, { duration: summaryCounterDurationMs(payload) });
  }
}

/** Render the persistent summary section and trigger counters. */
export function renderSummary() {
  const puzzle = uiState.state.lastSummary?.puzzle || uiState.state.livePuzzle;
  $("summarySection").classList.toggle("hidden", !puzzle);
  if (!puzzle) return;
  $("summaryGrid").innerHTML = `
    ${renderSubmarinePuzzle(puzzle, {
      showUnplaced: false,
      highlightNewlyPlaced: false,
    })}
  `;
}
