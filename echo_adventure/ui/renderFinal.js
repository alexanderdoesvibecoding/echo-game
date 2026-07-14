"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml } from "./html.js";

let lockedDecisionChartMarker = null;

const formatScore = (value) => {
  const number = Number(value) || 0;
  return `${number >= 0 ? "+" : ""}${number.toFixed(2)}`;
};

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function roundScore(value) {
  return Math.round((Number(value) || 0) * 100) / 100;
}

function dateLabelParts(label) {
  const safeLabel = String(label || "").trim();
  const match = safeLabel.match(/^(.+?)\s+(\d{1,2})$/);
  if (!match) return { month: safeLabel || "Day", day: "" };
  return { month: match[1], day: match[2] };
}

export function buildDailyDecisionGroups(decisionPoints) {
  const groups = [];
  const groupsByKey = new Map();
  let previousPlayerCumulative = 0;
  let previousEchoCumulative = 0;

  decisionPoints.forEach((decisionPoint, index) => {
    const day = numberOrNull(decisionPoint.day) ?? index + 1;
    const dateLabel = decisionPoint.dateLabel || `Day ${day}`;
    const key = `${day}|${dateLabel}`;
    const playerCumulative = numberOrNull(decisionPoint.playerCumulativeScore);
    const echoCumulative = numberOrNull(decisionPoint.echoCumulativeScore);
    const playerDelta = numberOrNull(decisionPoint.playerDelta)
      ?? (playerCumulative !== null ? playerCumulative - previousPlayerCumulative : 0);
    const echoDelta = numberOrNull(decisionPoint.echoDelta)
      ?? (echoCumulative !== null ? echoCumulative - previousEchoCumulative : 0);
    const sequence = numberOrNull(decisionPoint.sequence) ?? index + 1;
    let group = groupsByKey.get(key);

    if (!group) {
      group = {
        day,
        dateLabel,
        decisions: [],
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
    if (decisionPoint.playerQuestionId || decisionPoint.playerScoreEvent) group.playerDecisionCount += 1;
    if (decisionPoint.echoQuestionId || decisionPoint.echoScoreEvent) group.echoDecisionCount += 1;
    group.decisions.push({
      sequence,
      label: decisionPoint.label || `Q${sequence}`,
      playerChoice: decisionPoint.playerChoice || "-",
      echoChoice: decisionPoint.echoChoice || "-",
      playerDelta: formatScore(playerDelta),
      echoDelta: formatScore(echoDelta),
      affected: decisionPoint.affectedLabel || "-",
      playerEventKind: decisionPoint.playerEventKind || "decision",
      echoEventKind: decisionPoint.echoEventKind || "decision",
    });

    previousPlayerCumulative = playerCumulative !== null
      ? playerCumulative
      : previousPlayerCumulative + playerDelta;
    previousEchoCumulative = echoCumulative !== null
      ? echoCumulative
      : previousEchoCumulative + echoDelta;
  });

  let playerRunning = 0;
  let echoRunning = 0;
  groups.forEach((group) => {
    group.playerDailyDelta = roundScore(group.playerDailyDelta);
    group.echoDailyDelta = roundScore(group.echoDailyDelta);
    playerRunning = roundScore(playerRunning + group.playerDailyDelta);
    echoRunning = roundScore(echoRunning + group.echoDailyDelta);
    group.playerCumulativeScore = playerRunning;
    group.echoCumulativeScore = echoRunning;
  });

  return [
    {
      day: 0,
      dateLabel: "Start",
      decisions: [],
      playerDailyDelta: 0,
      echoDailyDelta: 0,
      playerCumulativeScore: 0,
      echoCumulativeScore: 0,
      playerDecisionCount: 0,
      echoDecisionCount: 0,
      isBaseline: true,
    },
    ...groups,
  ];
}

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
  const rawMin = Math.min(0, ...playerScore, ...echoScore);
  const rawMax = Math.max(0, ...playerScore, ...echoScore);
  const scoreSpan = Math.max(1, rawMax - rawMin);
  const minScore = rawMin - scoreSpan * 0.15;
  const maxScore = rawMax + scoreSpan * 0.15;
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const point = (value, index) => {
    const x = count === 1 ? pad.left + plotWidth / 2 : pad.left + (index / (count - 1)) * plotWidth;
    const y = pad.top + ((maxScore - value) / (maxScore - minScore)) * plotHeight;
    return [x, y];
  };
  const pathFor = (series) => series.slice(0, count).map((value, index) => {
    const [x, y] = point(Number(value) || 0, index);
    return `${index ? "L" : "M"} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const yTicks = rawMin === rawMax
    ? [-1, 0, 1]
    : [...new Set([rawMin, 0, rawMax].map(value => Number(value.toFixed(2))))].sort((a, b) => a - b);
  const yGrid = yTicks.map(value => {
    const [, y] = point(value, 0);
    return `
      <line class="chart-grid" x1="${pad.left}" y1="${y.toFixed(1)}" x2="${(width - pad.right).toFixed(1)}" y2="${y.toFixed(1)}"></line>
      <text class="chart-label" x="${pad.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end">${formatScore(value)}</text>
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
  const dayAttrs = (group) => {
    const decisionCount = group.decisions.length;
    const decisionWord = decisionCount === 1 ? "score event" : "score events";
    const ariaLabel = [
      `${group.dateLabel}: ${decisionCount} ${decisionWord}.`,
      `Your cumulative score ${formatScore(group.playerCumulativeScore)}.`,
      `ECHO cumulative score ${formatScore(group.echoCumulativeScore)}.`,
    ].join(" ");
    return `
      tabindex="0"
      aria-label="${escapeHtml(ariaLabel)}"
      data-label="${escapeHtml(group.dateLabel)}"
      data-day="${escapeHtml(group.day)}"
      data-date-label="${escapeHtml(group.dateLabel)}"
      data-decision-count="${escapeHtml(decisionCount)}"
      data-player-change="${escapeHtml(formatScore(group.playerDailyDelta))}"
      data-echo-change="${escapeHtml(formatScore(group.echoDailyDelta))}"
      data-player-cumulative="${escapeHtml(formatScore(group.playerCumulativeScore))}"
      data-echo-cumulative="${escapeHtml(formatScore(group.echoCumulativeScore))}"
      data-decisions="${escapeHtml(JSON.stringify(group.decisions))}"
      onmousemove="showDecisionChartTooltip(event, this)"
      onfocus="showDecisionChartTooltip(event, this)"
      onblur="hideDecisionChartTooltip()"
    `;
  };
  const decisionMarker = (series, index) => {
    const group = dailyGroups[index];
    if (series === "Player" && group.playerDecisionCount === 0) return "";
    if (series === "ECHO" && group.echoDecisionCount === 0) return "";
    const values = series === "Player" ? playerScore : echoScore;
    const value = Number(values[index]) || 0;
    const [x, y] = point(value, index);
    if (series === "Player") {
      return `
        <circle class="chart-dot chart-player-dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.8" fill="var(--teal)" stroke="var(--panel)" stroke-width="1.4"></circle>
      `;
    }
    return `
      <circle class="chart-dot chart-echo-dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5.6" fill="var(--panel)" stroke="var(--violet)" stroke-width="2.2"></circle>
    `;
  };
  const dayHoverZone = (group, index) => {
    const [x] = point(0, index);
    const step = count === 1 ? plotWidth : plotWidth / (count - 1);
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
      <div class="chart-frame">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Line chart comparing cumulative score by day for player and ECHO">
          ${yGrid}
          <line class="chart-axis" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}"></line>
          <line class="chart-axis" x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}"></line>
          ${xLabels}
          <path d="${pathFor(playerScore)}" fill="none" stroke="var(--teal)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
          <path d="${pathFor(echoScore)}" fill="none" stroke="var(--violet)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="8 6"></path>
          <g>${dailyGroups.map((group, index) => decisionMarker("Player", index)).join("")}</g>
          <g>${dailyGroups.map((group, index) => decisionMarker("ECHO", index)).join("")}</g>
          <g>${dailyGroups.map((group, index) => dayHoverZone(group, index)).join("")}</g>
        </svg>
        <div class="chart-tooltip" id="decisionChartTooltip"></div>
      </div>
    </div>
  `;
}

function renderFinalMetricBar(player, automated) {
  const metricCards = [
    {
      label: "Completion",
      playerValue: player.completion || "-",
      echoValue: automated.completion || "-",
      tone: "good",
    },
    {
      label: "Completion Day",
      playerValue: String(player.completionDay || "-"),
      echoValue: String(automated.completionDay || "-"),
      tone: Number(player.completionDay || Infinity) <= Number(automated.completionDay || Infinity) ? "good" : "warn",
    },
    {
      label: "Decision Score",
      playerValue: Number(player.finalScore || 0).toFixed(2),
      echoValue: Number(automated.finalScore || 0).toFixed(2),
      tone: Number(player.finalScore || 0) >= Number(automated.finalScore || 0) ? "good" : "warn",
    },
  ];

  return metricCards.map(metric => `
    <div class="metric final-metric final-metric-${metric.tone}">
      <div class="metric-title-row">
        <span class="subtle metric-label">${escapeHtml(metric.label)}</span>
      </div>
      <div class="metric-value-row final-metric-value-row">
        <strong>${escapeHtml(metric.playerValue)}</strong>
      </div>
      <div class="final-metric-benchmark">ECHO ${escapeHtml(metric.echoValue)}</div>
    </div>
  `).join("");
}

function isLockedMarker(marker) {
  return Boolean(lockedDecisionChartMarker && lockedDecisionChartMarker === marker);
}

export function showDecisionChartTooltip(event, marker, options = {}) {
  const tooltip = $("decisionChartTooltip");
  if (!tooltip || !marker) return;
  const locked = isLockedMarker(marker);
  if (lockedDecisionChartMarker && !locked && !options.lock) return;
  const data = marker.dataset;
  let decisions = [];
  try {
    const parsed = JSON.parse(data.decisions || "[]");
    decisions = Array.isArray(parsed) ? parsed : [];
  } catch {
    decisions = [];
  }
  const decisionMarkup = decisions.map((decision, index) => {
    const playerCompletion = decision.playerEventKind === "completion";
    const echoCompletion = decision.echoEventKind === "completion";
    return `
      <section class="chart-tooltip-decision">
        <div class="chart-tooltip-decision-title">
          <span>${escapeHtml(decision.label || `Decision ${index + 1}`)}</span>
          <span>${escapeHtml(decision.affected || "-")}</span>
        </div>
        <dl class="chart-tooltip-fields">
          <div class="chart-tooltip-field">
            <dt>${playerCompletion ? "Your payoff:" : "Your answer:"}</dt>
            <dd>${escapeHtml(decision.playerChoice || "-")}</dd>
          </div>
          <div class="chart-tooltip-field">
            <dt>${echoCompletion ? "ECHO payoff" : "ECHO chose"}</dt>
            <dd>${escapeHtml(decision.echoChoice || "-")}</dd>
          </div>
          <div class="chart-tooltip-field">
            <dt>Your score change</dt>
            <dd>${escapeHtml(decision.playerDelta || "+0.00")}</dd>
          </div>
          <div class="chart-tooltip-field">
            <dt>ECHO score change</dt>
            <dd>${escapeHtml(decision.echoDelta || "+0.00")}</dd>
          </div>
          <div class="chart-tooltip-field">
            <dt>Job</dt>
            <dd>${escapeHtml(decision.affected || "-")}</dd>
          </div>
        </dl>
      </section>
    `;
  }).join("") || `<div class="subtle">No decisions recorded for this day.</div>`;
  tooltip.innerHTML = `
    <div class="chart-tooltip-title">
      <strong>${escapeHtml(data.dateLabel || data.label || "Day")} score</strong>
      <span>${escapeHtml(data.decisionCount || "0")} score events</span>
    </div>
    <div class="chart-tooltip-hint">${locked ? "Locked - click this day again to unlock" : "Click to lock this panel"}</div>
    <div class="chart-tooltip-summary">
      <div><span>Your day</span><strong>${escapeHtml(data.playerChange || "+0.00")}</strong></div>
      <div><span>Your cumulative</span><strong>${escapeHtml(data.playerCumulative || "+0.00")}</strong></div>
      <div><span>ECHO day</span><strong>${escapeHtml(data.echoChange || "+0.00")}</strong></div>
      <div><span>ECHO cumulative</span><strong>${escapeHtml(data.echoCumulative || "+0.00")}</strong></div>
    </div>
    <div class="chart-tooltip-decision-list">${decisionMarkup}</div>
  `;
  tooltip.classList.add("active");
  tooltip.classList.toggle("locked", locked || Boolean(options.lock));
  if (locked && !options.lock) return;
  positionDecisionChartTooltip(event, marker, tooltip);
}

function positionDecisionChartTooltip(event, marker, tooltip) {
  const markerRect = marker.getBoundingClientRect();
  const clientX = Number.isFinite(event?.clientX) && event.clientX > 0
    ? event.clientX
    : markerRect.left + markerRect.width / 2;
  const clientY = Number.isFinite(event?.clientY) && event.clientY > 0
    ? event.clientY
    : markerRect.top;
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1024;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 768;
  const tooltipWidth = tooltip.offsetWidth || Math.min(560, viewportWidth - 48);
  const tooltipHeight = tooltip.offsetHeight || 320;
  let left = clientX + 16;
  let top = clientY - tooltipHeight - 12;

  if (left + tooltipWidth > viewportWidth - 16) {
    left = Math.max(16, viewportWidth - tooltipWidth - 16);
  }
  if (top < 16) {
    top = Math.min(viewportHeight - tooltipHeight - 16, clientY + 18);
  }
  top = Math.max(16, top);

  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

export function hideDecisionChartTooltip(options = {}) {
  const tooltip = $("decisionChartTooltip");
  if (!tooltip) return;
  if (lockedDecisionChartMarker && !options.force) return;
  if (options.force) {
    lockedDecisionChartMarker = null;
  }
  tooltip.classList.remove("active");
  tooltip.classList.remove("locked");
}

function toggleDecisionChartTooltipLock(event, marker) {
  if (!marker) return;
  event?.preventDefault();
  event?.stopPropagation();
  if (isLockedMarker(marker)) {
    hideDecisionChartTooltip({ force: true });
    return;
  }
  lockedDecisionChartMarker = marker;
  showDecisionChartTooltip(event, marker, { lock: true });
}

document.addEventListener("mousemove", (event) => {
  if (lockedDecisionChartMarker) return;
  const target = event.target instanceof Element ? event.target : null;
  if (target?.closest(".chart-hover-zone")) return;
  if (target?.closest(".chart-tooltip")) return;
  hideDecisionChartTooltip();
});

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const marker = target?.closest(".chart-hover-zone");
  if (marker) {
    toggleDecisionChartTooltipLock(event, marker);
    return;
  }
  if (lockedDecisionChartMarker && !target?.closest(".chart-tooltip")) {
    hideDecisionChartTooltip({ force: true });
  }
});

document.addEventListener("keydown", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const marker = target?.closest(".chart-hover-zone");
  if (marker && (event.key === "Enter" || event.key === " ")) {
    toggleDecisionChartTooltipLock(event, marker);
    return;
  }
  if (event.key === "Escape" && lockedDecisionChartMarker) {
    hideDecisionChartTooltip({ force: true });
  }
});

export function renderFinal() {
  const final = uiState.state.finalReveal;
  if (!final) {
    $("finalSection").classList.add("hidden");
    return;
  }

  $("finalSection").classList.remove("hidden");

  const p = final.player;
  const a = final.automated;
  const review = final.review || {};

  $("finalMetricsBar").innerHTML = renderFinalMetricBar(p, a);
  $("finalCompletionChart").innerHTML = renderDecisionScoreChart(final.completionHistory);

  $("finalNotes").innerHTML = (review.reasons || final.explanation || [])
    .map(note => `<li>${escapeHtml(note)}</li>`)
    .join("") || "<li>No final review notes recorded.</li>";
}
