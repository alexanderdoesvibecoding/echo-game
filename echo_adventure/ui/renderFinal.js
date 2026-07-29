/** Final comparison charts, route review, and interactive tooltips. */

"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml } from "./html.js";

let selectedDecisionChartDayKey = null;

const SCORE_BASELINE = 50;
const METRIC_TOOLTIP_GAP = 14;
const METRIC_TOOLTIP_MARGIN = 12;

/** Format a score consistently while allowing caller-specific fallbacks. */
const formatScore = (value, options = {}) => {
  const number = Number(value) || 0;
  const signed = options.signed !== false;
  return `${signed && number >= 0 ? "+" : ""}${number.toFixed(2)}`;
};

/** Convert finite numeric input while preserving invalid values as null. */
function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

/** Render and position guidance for a final comparison metric. */
export function positionFinalMetricTooltip(event, metric, anchor = metric) {
  const tooltip = metric?.querySelector(".final-metric-tooltip");
  if (!tooltip) return;

  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1024;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 768;
  const tooltipWidth = tooltip.offsetWidth || 160;
  const tooltipHeight = tooltip.offsetHeight || 34;
  const hasPointerCoordinates = Number.isFinite(event?.clientX) && Number.isFinite(event?.clientY);
  let left;
  let top;

  // Pointer interactions anchor beside the cursor; keyboard focus anchors to
  // the info trigger so guidance remains accessible without activating the card.
  if (hasPointerCoordinates) {
    left = event.clientX + METRIC_TOOLTIP_GAP;
    top = event.clientY + METRIC_TOOLTIP_GAP;
    if (left + tooltipWidth > viewportWidth - METRIC_TOOLTIP_MARGIN) {
      left = event.clientX - tooltipWidth - METRIC_TOOLTIP_GAP;
    }
    if (top + tooltipHeight > viewportHeight - METRIC_TOOLTIP_MARGIN) {
      top = event.clientY - tooltipHeight - METRIC_TOOLTIP_GAP;
    }
  } else {
    const anchorRect = anchor.getBoundingClientRect();
    const anchorBottom = Number.isFinite(anchorRect.bottom)
      ? anchorRect.bottom
      : anchorRect.top + anchorRect.height;
    left = anchorRect.left + (anchorRect.width - tooltipWidth) / 2;
    top = anchorBottom + 8;
    if (top + tooltipHeight > viewportHeight - METRIC_TOOLTIP_MARGIN) {
      top = anchorRect.top - tooltipHeight - 8;
    }
  }

  // Final clamping handles tiny viewports where neither preferred side fits.
  const maxLeft = Math.max(
    METRIC_TOOLTIP_MARGIN,
    viewportWidth - tooltipWidth - METRIC_TOOLTIP_MARGIN,
  );
  const maxTop = Math.max(
    METRIC_TOOLTIP_MARGIN,
    viewportHeight - tooltipHeight - METRIC_TOOLTIP_MARGIN,
  );
  tooltip.style.left = `${Math.min(maxLeft, Math.max(METRIC_TOOLTIP_MARGIN, left))}px`;
  tooltip.style.top = `${Math.min(maxTop, Math.max(METRIC_TOOLTIP_MARGIN, top))}px`;
}

/** Round a score to the precision used by final charts. */
function roundScore(value) {
  return Math.round((Number(value) || 0) * 100) / 100;
}

/** Split a display date into month and day components. */
function dateLabelParts(label) {
  const safeLabel = String(label || "").trim();
  const match = safeLabel.match(/^(.+?)\s+(\d{1,2})$/);
  if (!match) return { month: safeLabel || "Day", day: "" };
  return { month: match[1], day: match[2] };
}

/** Normalize one actor's decision from a shared comparison point. */
function routeDecisionFromPoint(decisionPoint, actor, index) {
  const nested = actor === "player" ? decisionPoint.playerDecision : decisionPoint.echoDecision;
  if (!nested || typeof nested !== "object") return null;
  // Normalize optional server fields here so downstream tooltip rendering can
  // use one stable actor-decision shape.
  return {
    position: numberOrNull(nested.position) ?? index + 1,
    questionId: nested.questionId || "",
    questionTitle: nested.questionTitle || nested.questionId || "Decision",
    questionText: nested.questionText || nested.questionTitle || "",
    choice: nested.choice || "-",
    scoreDelta: formatScore(nested.scoreDelta),
    cumulativeScore: formatScore(nested.cumulativeScore, { signed: false }),
    affectedLabel: nested.affectedLabel || "-",
    eventScope: nested.eventScope || "route-specific",
    echoPreferredChoice: nested.echoPreferredChoice || "",
    alignedWithEcho: Boolean(nested.alignedWithEcho),
    echoSituationMatches: Boolean(nested.echoSituationMatches),
    echoEventMatches: Boolean(nested.echoEventMatches),
    echoComparisonState: nested.echoComparisonState || "",
    echoPreferenceState: nested.echoPreferenceState || "",
    echoPreferenceBasis: nested.echoPreferenceBasis || "",
  };
}

/** Aggregate route score changes into continuous daily chart groups. */
export function buildDailyDecisionGroups(decisionPoints) {
  const groups = [];
  const groupsByKey = new Map();
  let previousPlayerCumulative = SCORE_BASELINE;
  let previousEchoCumulative = SCORE_BASELINE;

  // Input contains one point per decision slot. Group them by calendar day while
  // independently carrying each actor's cumulative score through missing slots.
  decisionPoints.forEach((decisionPoint, index) => {
    const day = numberOrNull(decisionPoint.day) ?? index + 1;
    const dateLabel = decisionPoint.dateLabel || `Day ${day}`;
    const key = `${day}|${dateLabel}`;
    const playerCumulative = numberOrNull(decisionPoint.playerDecision?.cumulativeScore);
    const echoCumulative = numberOrNull(decisionPoint.echoDecision?.cumulativeScore);
    // Older/minimal payloads may omit deltas; derive them from cumulative values
    // without treating a real zero as missing.
    const playerDelta = numberOrNull(decisionPoint.playerDecision?.scoreDelta)
      ?? (playerCumulative !== null ? playerCumulative - previousPlayerCumulative : 0);
    const echoDelta = numberOrNull(decisionPoint.echoDecision?.scoreDelta)
      ?? (echoCumulative !== null ? echoCumulative - previousEchoCumulative : 0);
    let group = groupsByKey.get(key);

    if (!group) {
      group = {
        day,
        dateLabel,
        playerDecisions: [],
        echoDecisions: [],
        playerDailyDelta: 0,
        echoDailyDelta: 0,
        playerDecisionCount: 0,
        echoDecisionCount: 0,
      };
      groupsByKey.set(key, group);
      groups.push(group);
    }

    group.playerDailyDelta += playerDelta;
    group.echoDailyDelta += echoDelta;
    const playerDecision = routeDecisionFromPoint(decisionPoint, "player", index);
    const echoDecision = routeDecisionFromPoint(decisionPoint, "echo", index);
    if (playerDecision) group.playerDecisions.push(playerDecision);
    if (echoDecision) group.echoDecisions.push(echoDecision);
    group.playerDecisionCount = group.playerDecisions.length;
    group.echoDecisionCount = group.echoDecisions.length;
    previousPlayerCumulative = playerCumulative !== null
      ? playerCumulative
      : previousPlayerCumulative + playerDelta;
    previousEchoCumulative = echoCumulative !== null
      ? echoCumulative
      : previousEchoCumulative + echoDelta;
  });

  // Rebuild cumulative series from daily deltas so rounding is consistent at the
  // exact granularity the chart displays.
  let playerRunning = SCORE_BASELINE;
  let echoRunning = SCORE_BASELINE;
  groups.forEach((group) => {
    group.playerDailyDelta = roundScore(group.playerDailyDelta);
    group.echoDailyDelta = roundScore(group.echoDailyDelta);
    playerRunning = roundScore(playerRunning + group.playerDailyDelta);
    echoRunning = roundScore(echoRunning + group.echoDailyDelta);
    group.playerCumulativeScore = playerRunning;
    group.echoCumulativeScore = echoRunning;
  });

  // A neutral baseline gives both paths a visible common origin before day one.
  return [
    {
      day: 0,
      dateLabel: "Start",
      playerDecisions: [],
      echoDecisions: [],
      playerDailyDelta: 0,
      echoDailyDelta: 0,
      playerCumulativeScore: SCORE_BASELINE,
      echoCumulativeScore: SCORE_BASELINE,
      playerDecisionCount: 0,
      echoDecisionCount: 0,
      isBaseline: true,
    },
    ...groups,
  ];
}

/** Render the player's and ECHO's cumulative decision-score chart. */
function renderDecisionScoreChart(history) {
  const decisionPoints = Array.isArray(history?.decisionPoints) ? history.decisionPoints : [];
  if (!decisionPoints.length) return `<div class="subtle">No decision score history recorded.</div>`;
  const dailyGroups = buildDailyDecisionGroups(decisionPoints);
  const count = dailyGroups.length;

  const width = 760;
  const height = 320;
  const pad = { left: 58, right: 58, top: 18, bottom: 68 };
  const playerScore = dailyGroups.map(group => Number(group.playerCumulativeScore) || 0);
  const echoScore = dailyGroups.map(group => Number(group.echoCumulativeScore) || 0);
  const minScore = 0;
  const maxScore = 100;
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  /** Convert one score/index pair into SVG plot coordinates. */
  const point = (value, index) => {
    const x = count === 1 ? pad.left + plotWidth / 2 : pad.left + (index / (count - 1)) * plotWidth;
    const y = pad.top + ((maxScore - value) / (maxScore - minScore)) * plotHeight;
    return [x, y];
  };
  /** Build an SVG path command sequence for one score series. */
  const pathFor = (series) => series.slice(0, count).map((value, index) => {
    const [x, y] = point(Number(value) || 0, index);
    return `${index ? "L" : "M"} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const yTicks = [0, 50, 100];
  const yGrid = yTicks.map(value => {
    const [, y] = point(value, 0);
    return `
      <line class="chart-grid" x1="${pad.left}" y1="${y.toFixed(1)}" x2="${(width - pad.right).toFixed(1)}" y2="${y.toFixed(1)}"></line>
      <text class="chart-label" x="${pad.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end">${formatScore(value, { signed: false })}</text>
    `;
  }).join("");
  const xLabels = dailyGroups.map((group, index) => {
    const [x] = point(0, index);
    const label = dateLabelParts(group.dateLabel);
    const monthY = height - 34;
    const dayY = height - 19;
    return `
      <text class="chart-label chart-day-label" text-anchor="middle">
        <tspan x="${x.toFixed(1)}" y="${monthY}">${escapeHtml(label.month)}</tspan>
        ${label.day ? `<tspan x="${x.toFixed(1)}" y="${dayY}">${escapeHtml(label.day)}</tspan>` : ""}
      </text>
    `;
  }).join("");
  /** Serialize one day's accessible metadata onto its interaction target. */
  const dayAttrs = (group) => {
    const ariaLabel = [
      `${group.dateLabel}.`,
      `${group.playerDecisionCount} of your decisions and ${group.echoDecisionCount} ECHO decisions.`,
      `Your cumulative score ${formatScore(group.playerCumulativeScore, { signed: false })}.`,
      `ECHO cumulative score ${formatScore(group.echoCumulativeScore, { signed: false })}.`,
      "Select to review both routes.",
    ].join(" ");
    return `
      tabindex="0"
      role="button"
      aria-controls="decisionChartTooltip"
      aria-expanded="false"
      aria-label="${escapeHtml(ariaLabel)}"
      data-label="${escapeHtml(group.dateLabel)}"
      data-day-key="${escapeHtml(String(group.day))}"
      data-day="${escapeHtml(group.day)}"
      data-date-label="${escapeHtml(group.dateLabel)}"
      data-player-decision-count="${escapeHtml(group.playerDecisionCount)}"
      data-echo-decision-count="${escapeHtml(group.echoDecisionCount)}"
      data-player-change="${escapeHtml(formatScore(group.playerDailyDelta))}"
      data-echo-change="${escapeHtml(formatScore(group.echoDailyDelta))}"
      data-player-cumulative="${escapeHtml(formatScore(group.playerCumulativeScore, { signed: false }))}"
      data-echo-cumulative="${escapeHtml(formatScore(group.echoCumulativeScore, { signed: false }))}"
      data-player-decisions="${escapeHtml(JSON.stringify(group.playerDecisions))}"
      data-echo-decisions="${escapeHtml(JSON.stringify(group.echoDecisions))}"
    `;
  };
  /** Render a visible score marker when the actor had a decision that day. */
  const scoreMarker = (series, index) => {
    const group = dailyGroups[index];
    if (group.isBaseline) return "";
    const decisionCount = series === "Player"
      ? group.playerDecisionCount
      : group.echoDecisionCount;
    const hasDecision = decisionCount > 0;
    // Player days remain selectable even with no questions so completion-only
    // days can still open a route review; empty ECHO dots would add no signal.
    if (series === "ECHO" && !hasDecision) return "";
    const values = series === "Player" ? playerScore : echoScore;
    const value = Number(values[index]) || 0;
    const [x, y] = point(value, index);
    if (series === "Player") {
      return `
        <circle
          class="chart-dot chart-player-dot"
          cx="${x.toFixed(1)}"
          cy="${y.toFixed(1)}"
          r="4.8"
          fill="var(--teal)"
          stroke="var(--panel)"
          stroke-width="1.4"
        ></circle>
      `;
    }
    return `
      <circle
        class="chart-dot chart-echo-dot"
        cx="${x.toFixed(1)}"
        cy="${y.toFixed(1)}"
        r="5.6"
        fill="var(--panel)"
        stroke="var(--violet)"
        stroke-width="2.2"
      ></circle>
    `;
  };
  /** Render a full-height transparent interaction target for one day. */
  const dayHoverZone = (group, index) => {
    if (group.isBaseline) return "";
    const [x] = point(0, index);
    const step = count === 1 ? plotWidth : plotWidth / (count - 1);
    // Split the plot halfway between adjacent markers to avoid interaction gaps.
    const x1 = count === 1 ? pad.left : Math.max(pad.left, x - step / 2);
    const x2 = count === 1 ? width - pad.right : Math.min(width - pad.right, x + step / 2);
    return `
      <rect
        class="chart-hover-zone"
        x="${x1.toFixed(1)}"
        y="${pad.top}"
        width="${Math.max(1, x2 - x1).toFixed(1)}"
        height="${plotHeight.toFixed(1)}"
        ${dayAttrs(group)}
      ></rect>
    `;
  };

  return `
    <div class="completion-chart">
      <div class="chart-legend">
        <span class="chart-key chart-player"><span class="chart-swatch"></span>Your score</span>
        <span class="chart-key chart-echo"><span class="chart-swatch"></span>ECHO score</span>
      </div>
      <p class="chart-instructions">Hover or focus to highlight a day. Select it to review your route and ECHO's route.</p>
      <div class="chart-frame">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Line chart comparing cumulative score by day for player and ECHO">
          ${yGrid}
          <line class="chart-axis" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}"></line>
          <line class="chart-axis" x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}"></line>
          ${xLabels}
          <path d="${pathFor(playerScore)}" fill="none" stroke="var(--teal)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
          <path d="${pathFor(echoScore)}" fill="none" stroke="var(--violet)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="8 6"></path>
          <g>${dailyGroups.map((group, index) => scoreMarker("Player", index)).join("")}</g>
          <g>${dailyGroups.map((group, index) => scoreMarker("ECHO", index)).join("")}</g>
          <g>${dailyGroups.map((group, index) => dayHoverZone(group, index)).join("")}</g>
        </svg>
        <div class="chart-tooltip" id="decisionChartTooltip" role="dialog" aria-modal="false" aria-labelledby="decisionChartTooltipTitle"></div>
      </div>
    </div>
  `;
}

/** Render the terminal completion and score comparison bars. */
function renderFinalMetricBar(player, automated) {
  const playerCompletionDay = numberOrNull(player.completionDay);
  const echoCompletionDay = numberOrNull(automated.completionDay);
  // A divergent route cannot beat ECHO; equal dates still warn because lower
  // solver tie-breaks may decide the outcome.
  const completionTone = playerCompletionDay === echoCompletionDay ? "warn" : "danger";
  const metricCards = [
    {
      label: "Completion Date",
      playerValue: player.completion || "-",
      echoValue: automated.completion || "-",
      echoLabel: "ECHO:",
      tone: completionTone,
      guidance: "Completion Date is when all jobs are finished. Earlier is better, and this is the first result used when comparing your route with ECHO.",
      tooltipId: "finalCompletionDateTooltip",
    },
    {
      label: "Decision Score",
      playerValue: Number(player.finalScore || 0).toFixed(2),
      echoValue: Number(automated.finalScore || 0).toFixed(2),
      tone: Number(player.finalScore || 0) >= Number(automated.finalScore || 0) ? "good" : "warn",
      guidance: "Decision Score is a general estimate of how well your choices reduced the remaining workload. Choices that save time raise the score, while choices that add time lower it.",
      tooltipId: "finalDecisionScoreTooltip",
    },
    {
      label: "Cumulative Workload",
      playerValue: `${Number(player.unfinishedJobDays || 0)} job-days`,
      echoValue: `${Number(automated.unfinishedJobDays || 0)} job-days`,
      tone: Number(player.unfinishedJobDays || 0) <= Number(automated.unfinishedJobDays || 0) ? "good" : "warn",
      guidance: "Cumulative Workload adds the remaining job-days after daily decisions to a running total. Carrying more unfinished work for longer raises the total. Lower is better.",
      tooltipId: "finalUnfinishedWorkTooltip",
    },
  ];

  return metricCards.map(metric => `
    <div
      class="metric final-metric final-metric-${metric.tone}"
    >
      <div class="metric-title-row">
        <span class="subtle metric-label final-metric-label">
          ${escapeHtml(metric.label)}
          <button
            type="button"
            class="final-metric-info"
            aria-label="About ${escapeHtml(metric.label)}"
            aria-describedby="${escapeHtml(metric.tooltipId)}"
          >i</button>
          <span class="final-metric-tooltip" id="${escapeHtml(metric.tooltipId)}" role="tooltip">
            ${escapeHtml(metric.guidance)}
          </span>
        </span>
      </div>
      <div class="metric-value-row final-metric-value-row">
        <strong>${escapeHtml(metric.playerValue)}</strong>
      </div>
      <div class="final-metric-benchmark">
        ${escapeHtml(metric.echoLabel || "ECHO")} ${escapeHtml(metric.echoValue)}
      </div>
    </div>
  `).join("");
}

/** Normalize optional route-decision arrays. */
function parseDecisionList(value) {
  // JSON is stored in escaped data attributes; malformed legacy markup should
  // degrade to an empty route rather than breaking tooltip interaction.
  try {
    const parsed = JSON.parse(value || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** Classify a route decision relative to ECHO's preferred choice. */
function preferencePresentation(decision) {
  const state = decision.echoPreferenceState || [
    decision.echoSituationMatches
      ? "same-context"
      : decision.echoEventMatches
        ? "same-event-different-context"
        : "different-events",
    decision.alignedWithEcho ? "same-choice" : "different-choice",
  ].join("-");
  // The six combinations distinguish event identity, job context, and response
  // alignment without implying ECHO saw the player's exact situation.
  const presentations = {
    "same-context-same-choice": {
      badge: "Same context",
      label: "Same event and job · ECHO preferred your response",
    },
    "same-context-different-choice": {
      badge: "Same context",
      label: "Same event and job · ECHO preferred another response",
    },
    "same-event-different-context-same-choice": {
      badge: "Shared event",
      label: "Same event, different routes · ECHO preferred your response",
    },
    "same-event-different-context-different-choice": {
      badge: "Shared event",
      label: "Same event, different routes · ECHO preferred another response",
    },
    "different-events-same-choice": {
      badge: "Different events",
      label: "Different events · ECHO preferred your response",
    },
    "different-events-different-choice": {
      badge: "Different events",
      label: "Different events · ECHO preferred another response",
    },
  };
  return { state, ...(presentations[state] || presentations["different-events-different-choice"]) };
}

/** Render one decision and its applied schedule effects. */
function renderRouteDecision(decision, actor) {
  const title = decision.questionTitle || "Decision";
  const detail = decision.questionText && decision.questionText !== title
    ? `<p class="chart-decision-context">${escapeHtml(decision.questionText)}</p>`
    : "";
  const presentation = preferencePresentation(decision);
  const comparisonBadge = actor === "player" && decision.echoPreferredChoice
    ? `<span class="chart-shared-badge">${escapeHtml(presentation.badge)}</span>`
    : "";
  const preference = actor === "player" && decision.echoPreferredChoice
    ? `
      <div class="chart-echo-preference ${decision.alignedWithEcho ? "is-aligned" : ""}" data-preference-state="${escapeHtml(presentation.state)}">
        <span>${escapeHtml(presentation.label)}</span>
        <strong>${escapeHtml(decision.echoPreferredChoice)}</strong>
      </div>
    `
    : "";
  return `
    <article class="chart-route-decision">
      <div class="chart-route-decision-title">
        <strong>Decision ${escapeHtml(decision.position || "-")}: ${escapeHtml(title)}</strong>
        ${comparisonBadge}
      </div>
      ${detail}
      <dl class="chart-tooltip-fields">
        <div class="chart-tooltip-field">
          <dt>${actor === "player" ? "Your choice" : "ECHO chose"}</dt>
          <dd>${escapeHtml(decision.choice || "-")}</dd>
        </div>
        <div class="chart-tooltip-field">
          <dt>Score change</dt>
          <dd>${escapeHtml(decision.scoreDelta || "+0.00")}</dd>
        </div>
        <div class="chart-tooltip-field chart-tooltip-field-wide">
          <dt>Affected work</dt>
          <dd>${escapeHtml(decision.affectedLabel || "-")}</dd>
        </div>
      </dl>
      ${preference}
    </article>
  `;
}

/** Render one actor's complete decision route. */
function renderRouteSection(actor, decisions) {
  const label = actor === "player" ? "Your actual route" : "ECHO's actual route";
  const emptyText = actor === "player"
    ? "You answered no questions on this day."
    : "ECHO answered no questions on this day.";
  const decisionWord = decisions.length === 1 ? "decision" : "decisions";
  return `
    <section class="chart-route chart-route-${actor}">
      <div class="chart-route-title">
        <h4><span class="chart-route-swatch" aria-hidden="true"></span>${label}</h4>
        <span>${decisions.length} ${decisionWord}</span>
      </div>
      <div class="chart-route-decisions">
        ${decisions.map(decision => renderRouteDecision(decision, actor)).join("") || `<p class="subtle">${emptyText}</p>`}
      </div>
    </section>
  `;
}

/** Synchronize selected chart markers across both actor rows. */
function updateSelectedDayMarker(dayKey) {
  document.querySelectorAll(".chart-hover-zone").forEach((marker) => {
    const selected = Boolean(dayKey && marker.dataset.dayKey === dayKey);
    marker.classList.toggle("is-selected", selected);
    marker.setAttribute("aria-expanded", selected ? "true" : "false");
  });
}

/** Find the chart marker associated with a day key. */
function findDecisionChartMarker(dayKey) {
  return [...document.querySelectorAll(".chart-hover-zone")]
    .find(marker => marker.dataset.dayKey === dayKey) || null;
}

/** Open and populate the interactive day-level decision tooltip. */
export function showDecisionChartTooltip(event, marker) {
  const tooltip = $("decisionChartTooltip");
  if (!tooltip || !marker) return;
  event?.preventDefault();
  event?.stopPropagation();
  const data = marker.dataset;
  const playerDecisions = parseDecisionList(data.playerDecisions);
  const echoDecisions = parseDecisionList(data.echoDecisions);
  const dateLabel = data.dateLabel || data.label || "Day";
  // Store selection outside the DOM so rerenders and keyboard focus restoration
  // can address the same semantic day.
  selectedDecisionChartDayKey = data.dayKey || data.day || dateLabel;
  updateSelectedDayMarker(selectedDecisionChartDayKey);
  tooltip.innerHTML = `
    <div class="chart-tooltip-title">
      <div>
        <strong id="decisionChartTooltipTitle">${escapeHtml(dateLabel)} score review</strong>
        <span>${escapeHtml(data.playerDecisionCount || "0")} of your decisions · ${escapeHtml(data.echoDecisionCount || "0")} ECHO decisions</span>
      </div>
      <button class="chart-tooltip-close" type="button" data-chart-tooltip-close aria-label="Close ${escapeHtml(dateLabel)} score review">&times;</button>
    </div>
    <div class="chart-tooltip-summary">
      <div><span>Your day</span><strong>${escapeHtml(data.playerChange || "+0.00")}</strong></div>
      <div><span>Your cumulative</span><strong>${escapeHtml(data.playerCumulative || "+0.00")}</strong></div>
      <div><span>ECHO day</span><strong>${escapeHtml(data.echoChange || "+0.00")}</strong></div>
      <div><span>ECHO cumulative</span><strong>${escapeHtml(data.echoCumulative || "+0.00")}</strong></div>
    </div>
    <div class="chart-route-grid">
      ${renderRouteSection("player", playerDecisions)}
      ${renderRouteSection("echo", echoDecisions)}
    </div>
  `;
  tooltip.classList.add("active", "locked");
  positionDecisionChartTooltip(marker, tooltip);
}

/** Keep the decision tooltip inside the viewport. */
function positionDecisionChartTooltip(marker, tooltip) {
  const markerRect = marker.getBoundingClientRect();
  const anchorX = markerRect.left + markerRect.width / 2;
  const anchorY = markerRect.top;
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1024;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 768;
  const tooltipWidth = tooltip.offsetWidth || Math.min(560, viewportWidth - 48);
  const tooltipHeight = tooltip.offsetHeight || 320;
  let left = anchorX + 16;
  let top = anchorY - tooltipHeight - 12;

  // Prefer above/right of the marker, then flip and clamp inside the viewport.
  if (left + tooltipWidth > viewportWidth - 16) {
    left = Math.max(16, viewportWidth - tooltipWidth - 16);
  }
  if (top < 16) {
    top = Math.min(viewportHeight - tooltipHeight - 16, markerRect.bottom + 18);
  }
  top = Math.max(16, top);

  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

/** Close the decision tooltip unless its lock state forbids it. */
export function hideDecisionChartTooltip(options = {}) {
  const tooltip = $("decisionChartTooltip");
  const marker = selectedDecisionChartDayKey
    ? findDecisionChartMarker(selectedDecisionChartDayKey)
    : null;
  selectedDecisionChartDayKey = null;
  updateSelectedDayMarker(null);
  if (!tooltip) return;
  tooltip.classList.remove("active");
  tooltip.classList.remove("locked");
  if (options.restoreFocus && marker && typeof marker.focus === "function") marker.focus();
}

// Delegated listeners support chart markup that is replaced on each final render.
document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (target?.closest("[data-chart-tooltip-close]")) {
    event.preventDefault();
    event.stopPropagation();
    hideDecisionChartTooltip({ restoreFocus: true });
    return;
  }
  const marker = target?.closest(".chart-hover-zone");
  if (marker) {
    showDecisionChartTooltip(event, marker);
    return;
  }
  if (selectedDecisionChartDayKey && !target?.closest(".chart-tooltip")) {
    hideDecisionChartTooltip();
  }
});

// Keyboard activation mirrors click behavior and restores focus on Escape.
document.addEventListener("keydown", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const marker = target?.closest(".chart-hover-zone");
  if (marker && (event.key === "Enter" || event.key === " ")) {
    showDecisionChartTooltip(event, marker);
    return;
  }
  if (event.key === "Escape" && selectedDecisionChartDayKey) {
    event.preventDefault();
    hideDecisionChartTooltip({ restoreFocus: true });
  }
});

// Only the info trigger positions metric guidance; hovering or focusing the
// surrounding comparison card must remain inert.
document.addEventListener("pointermove", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const trigger = target?.closest(".final-metric-info");
  const metric = trigger?.closest(".final-metric");
  if (metric) positionFinalMetricTooltip(event, metric, trigger);
});

document.addEventListener("focusin", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const trigger = target?.closest(".final-metric-info");
  const metric = trigger?.closest(".final-metric");
  if (metric) positionFinalMetricTooltip(null, metric, trigger);
});

/** Render or hide the complete final comparison view. */
export function renderFinal() {
  const final = uiState.state.finalReveal;
  if (!final) {
    hideDecisionChartTooltip();
    $("finalSection").classList.add("hidden");
    return;
  }

  // Final markup replacement invalidates old marker references and selection.
  hideDecisionChartTooltip();
  $("finalSection").classList.remove("hidden");

  const p = final.player;
  const a = final.automated;
  const review = final.review || {};

  const outcomeHeadline = $("finalOutcomeHeadline");
  outcomeHeadline.textContent = review.headline || "Final player and ECHO results";
  outcomeHeadline.className = `final-outcome-headline final-outcome-${review.outcome || "behind"}`;
  $("finalNotesTitle").textContent = review.outcome === "tied"
    ? "Why It Was a Tie"
    : "Where It Went Wrong";
  $("finalMetricsBar").innerHTML = renderFinalMetricBar(p, a);
  $("finalCompletionChart").innerHTML = renderDecisionScoreChart(final.completionHistory);

  // Escape every backend-authored explanation before rendering it as a list.
  $("finalNotes").innerHTML = (review.reasons || final.explanation || [])
    .slice(0, 5)
    .map(note => `<li>${escapeHtml(note)}</li>`)
    .join("") || "<li>No final review notes recorded.</li>";
}
