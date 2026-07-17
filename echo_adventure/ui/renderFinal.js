"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml } from "./html.js";

let selectedDecisionChartDayKey = null;

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

function routeDecisionFromPoint(decisionPoint, actor, index) {
  const nested = actor === "player" ? decisionPoint.playerDecision : decisionPoint.echoDecision;
  if (!nested || typeof nested !== "object") return null;
  return {
    position: numberOrNull(nested.position) ?? index + 1,
    questionId: nested.questionId || "",
    questionTitle: nested.questionTitle || nested.questionId || "Decision",
    questionText: nested.questionText || nested.questionTitle || "",
    choice: nested.choice || "-",
    scoreDelta: formatScore(nested.scoreDelta),
    cumulativeScore: formatScore(nested.cumulativeScore),
    affectedLabel: nested.affectedLabel || "-",
    echoPreferredChoice: nested.echoPreferredChoice || "",
    alignedWithEcho: Boolean(nested.alignedWithEcho),
  };
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
    const playerCumulative = numberOrNull(decisionPoint.playerDecision?.cumulativeScore);
    const echoCumulative = numberOrNull(decisionPoint.echoDecision?.cumulativeScore);
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
      playerDecisions: [],
      echoDecisions: [],
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
    const ariaLabel = [
      `${group.dateLabel}.`,
      `${group.playerDecisionCount} of your decisions and ${group.echoDecisionCount} ECHO decisions.`,
      `Your cumulative score ${formatScore(group.playerCumulativeScore)}.`,
      `ECHO cumulative score ${formatScore(group.echoCumulativeScore)}.`,
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
      data-player-cumulative="${escapeHtml(formatScore(group.playerCumulativeScore))}"
      data-echo-cumulative="${escapeHtml(formatScore(group.echoCumulativeScore))}"
      data-player-decisions="${escapeHtml(JSON.stringify(group.playerDecisions))}"
      data-echo-decisions="${escapeHtml(JSON.stringify(group.echoDecisions))}"
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
    if (group.isBaseline) return "";
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
      <p class="chart-instructions">Hover or focus to highlight a day. Select it to review your route and ECHO's route.</p>
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
        <div class="chart-tooltip" id="decisionChartTooltip" role="dialog" aria-modal="false" aria-labelledby="decisionChartTooltipTitle"></div>
      </div>
    </div>
  `;
}

function renderFinalMetricBar(player, automated) {
  const playerCompletionDay = numberOrNull(player.completionDay);
  const echoCompletionDay = numberOrNull(automated.completionDay);
  const completionTone = playerCompletionDay === echoCompletionDay ? "warn" : "danger";
  const metricCards = [
    {
      label: "Completion date",
      playerValue: player.completion || "-",
      playerDetail: playerCompletionDay === null ? "Day -" : `Day ${playerCompletionDay}`,
      echoValue: automated.completion || "-",
      echoDetail: echoCompletionDay === null ? "Day -" : `Day ${echoCompletionDay}`,
      tone: completionTone,
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
      ${metric.playerDetail ? `<div class="final-metric-secondary">${escapeHtml(metric.playerDetail)}</div>` : ""}
      <div class="final-metric-benchmark">
        ECHO ${escapeHtml(metric.echoValue)}${metric.echoDetail ? ` <span aria-hidden="true">&middot;</span> ${escapeHtml(metric.echoDetail)}` : ""}
      </div>
    </div>
  `).join("");
}

function parseDecisionList(value) {
  try {
    const parsed = JSON.parse(value || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function renderRouteDecision(decision, actor, sharedQuestionIds) {
  const title = decision.questionTitle || "Decision";
  const detail = decision.questionText && decision.questionText !== title
    ? `<p class="chart-decision-context">${escapeHtml(decision.questionText)}</p>`
    : "";
  const sharedBadge = decision.questionId && sharedQuestionIds.has(decision.questionId)
    ? `<span class="chart-shared-badge">Shared situation</span>`
    : "";
  const preference = actor === "player" && decision.echoPreferredChoice
    ? `
      <div class="chart-echo-preference ${decision.alignedWithEcho ? "is-aligned" : ""}">
        <span>ECHO's preferred response to your situation</span>
        <strong>${escapeHtml(decision.echoPreferredChoice)}</strong>
        <small>${decision.alignedWithEcho ? "You matched this response." : "This is not ECHO's actual-route decision."}</small>
      </div>
    `
    : "";
  return `
    <article class="chart-route-decision">
      <div class="chart-route-decision-title">
        <strong>Decision ${escapeHtml(decision.position || "-")}: ${escapeHtml(title)}</strong>
        ${sharedBadge}
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

function renderRouteSection(actor, decisions, sharedQuestionIds) {
  const label = actor === "player" ? "Your actual route" : "ECHO's actual route";
  const emptyText = actor === "player"
    ? "You had no decisions on this day."
    : "ECHO had no decisions on this day.";
  const decisionWord = decisions.length === 1 ? "decision" : "decisions";
  return `
    <section class="chart-route chart-route-${actor}">
      <div class="chart-route-title">
        <h4><span class="chart-route-swatch" aria-hidden="true"></span>${label}</h4>
        <span>${decisions.length} ${decisionWord}</span>
      </div>
      <div class="chart-route-decisions">
        ${decisions.map(decision => renderRouteDecision(decision, actor, sharedQuestionIds)).join("") || `<p class="subtle">${emptyText}</p>`}
      </div>
    </section>
  `;
}

function updateSelectedDayMarker(dayKey) {
  document.querySelectorAll(".chart-hover-zone").forEach((marker) => {
    const selected = Boolean(dayKey && marker.dataset.dayKey === dayKey);
    marker.classList.toggle("is-selected", selected);
    marker.setAttribute("aria-expanded", selected ? "true" : "false");
  });
}

function findDecisionChartMarker(dayKey) {
  return [...document.querySelectorAll(".chart-hover-zone")]
    .find(marker => marker.dataset.dayKey === dayKey) || null;
}

export function showDecisionChartTooltip(event, marker) {
  const tooltip = $("decisionChartTooltip");
  if (!tooltip || !marker) return;
  event?.preventDefault();
  event?.stopPropagation();
  const data = marker.dataset;
  const playerDecisions = parseDecisionList(data.playerDecisions);
  const echoDecisions = parseDecisionList(data.echoDecisions);
  const playerQuestionIds = new Set(playerDecisions.map(decision => decision.questionId).filter(Boolean));
  const sharedQuestionIds = new Set(
    echoDecisions.map(decision => decision.questionId).filter(questionId => playerQuestionIds.has(questionId)),
  );
  const dateLabel = data.dateLabel || data.label || "Day";
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
      ${renderRouteSection("player", playerDecisions, sharedQuestionIds)}
      ${renderRouteSection("echo", echoDecisions, sharedQuestionIds)}
    </div>
  `;
  tooltip.classList.add("active", "locked");
  positionDecisionChartTooltip(marker, tooltip);
}

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

export function renderFinal() {
  const final = uiState.state.finalReveal;
  if (!final) {
    hideDecisionChartTooltip();
    $("finalSection").classList.add("hidden");
    return;
  }

  hideDecisionChartTooltip();
  $("finalSection").classList.remove("hidden");

  const p = final.player;
  const a = final.automated;
  const review = final.review || {};

  const outcomeHeadline = $("finalOutcomeHeadline");
  outcomeHeadline.textContent = review.headline || "Final player and ECHO results";
  outcomeHeadline.className = `final-outcome-headline final-outcome-${review.outcome || "behind"}`;
  $("finalMetricsBar").innerHTML = renderFinalMetricBar(p, a);
  $("finalCompletionChart").innerHTML = renderDecisionScoreChart(final.completionHistory);

  $("finalNotes").innerHTML = (review.reasons || final.explanation || [])
    .map(note => `<li>${escapeHtml(note)}</li>`)
    .join("") || "<li>No final review notes recorded.</li>";
}
