"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml } from "./html.js";

function renderDecisionScoreChart(history) {
  const decisionPoints = Array.isArray(history?.decisionPoints) ? history.decisionPoints : [];
  const count = decisionPoints.length;
  if (!count) return `<div class="subtle">No decision score history recorded.</div>`;

  const width = 640;
  const height = 260;
  const pad = { left: 54, right: 18, top: 18, bottom: 42 };
  const formatScore = (value) => {
    const number = Number(value) || 0;
    return `${number >= 0 ? "+" : ""}${number.toFixed(2)}`;
  };
  const playerScore = decisionPoints.map(decisionPoint => Number(decisionPoint.playerCumulativeScore) || 0);
  const echoScore = decisionPoints.map(decisionPoint => Number(decisionPoint.echoCumulativeScore) || 0);
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
  const xTicks = count <= 3
    ? Array.from({ length: count }, (_, index) => index)
    : [...new Set([0, Math.floor((count - 1) / 2), count - 1])];
  const yGrid = yTicks.map(value => {
    const [, y] = point(value, 0);
    return `
      <line class="chart-grid" x1="${pad.left}" y1="${y.toFixed(1)}" x2="${(width - pad.right).toFixed(1)}" y2="${y.toFixed(1)}"></line>
      <text class="chart-label" x="${pad.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end">${formatScore(value)}</text>
    `;
  }).join("");
  const xLabels = xTicks.map(index => {
    const [x] = point(0, index);
    const sequence = Number(decisionPoints[index]?.sequence || index + 1);
    const label = `Q${sequence}`;
    return `<text class="chart-label" x="${x.toFixed(1)}" y="${height - 12}" text-anchor="middle">${escapeHtml(label)}</text>`;
  }).join("");
  const decisionAttrs = (decisionPoint, series) => {
    const sequence = Number(decisionPoint.sequence || 0) || 0;
    const label = decisionPoint.label || (sequence ? `Q${sequence}` : "Question");
    const questionTitle = decisionPoint.questionTitle || decisionPoint.questionId || "-";
    const questionText = decisionPoint.questionText || questionTitle;
    const playerChoice = decisionPoint.playerChoice || "-";
    const correctAnswer = decisionPoint.echoChoice || "-";
    const score = series === "Player" ? decisionPoint.playerCumulativeScore : decisionPoint.echoCumulativeScore;
    const change = series === "Player" ? decisionPoint.playerDelta : decisionPoint.echoDelta;
    const ariaLabel = `${label}: ${questionTitle}. Your answer: ${playerChoice}. Correct answer: ${correctAnswer}.`;
    return `
      tabindex="0"
      aria-label="${escapeHtml(ariaLabel)}"
      data-series="${escapeHtml(series)}"
      data-label="${escapeHtml(label)}"
      data-day="${escapeHtml(decisionPoint.day || "-")}"
      data-question-title="${escapeHtml(questionTitle)}"
      data-question-text="${escapeHtml(questionText)}"
      data-player-choice="${escapeHtml(playerChoice)}"
      data-correct-answer="${escapeHtml(correctAnswer)}"
      data-score="${escapeHtml(formatScore(score))}"
      data-change="${escapeHtml(formatScore(change))}"
      data-player-change="${escapeHtml(formatScore(decisionPoint.playerDelta))}"
      data-echo-change="${escapeHtml(formatScore(decisionPoint.echoDelta))}"
      data-player-cumulative="${escapeHtml(formatScore(decisionPoint.playerCumulativeScore))}"
      data-echo-cumulative="${escapeHtml(formatScore(decisionPoint.echoCumulativeScore))}"
      data-affected="${escapeHtml(decisionPoint.affectedLabel || "-")}"
      onmousemove="showDecisionChartTooltip(event, this)"
      onmouseleave="hideDecisionChartTooltip()"
      onfocus="showDecisionChartTooltip(event, this)"
      onblur="hideDecisionChartTooltip()"
    `;
  };
  const decisionMarker = (decisionPoint, series, index) => {
    const values = series === "Player" ? playerScore : echoScore;
    const value = Number(values[index]) || 0;
    const [x, y] = point(value, index);
    if (series === "Player") {
      return `
        <circle class="chart-dot chart-player-dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.8" fill="var(--teal)" stroke="var(--panel)" stroke-width="1.4" ${decisionAttrs(decisionPoint, series)}></circle>
      `;
    }
    return `
      <circle class="chart-dot chart-echo-dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5.6" fill="var(--panel)" stroke="var(--violet)" stroke-width="2.2" ${decisionAttrs(decisionPoint, series)}></circle>
    `;
  };

  return `
    <div class="completion-chart">
      <div class="chart-legend">
        <span class="chart-key chart-player"><span class="chart-swatch"></span>Your score</span>
        <span class="chart-key chart-echo"><span class="chart-swatch"></span>ECHO score</span>
      </div>
      <div class="chart-frame">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Line chart comparing cumulative decision score by question for player and ECHO">
          ${yGrid}
          <line class="chart-axis" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}"></line>
          <line class="chart-axis" x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}"></line>
          ${xLabels}
          <path d="${pathFor(playerScore)}" fill="none" stroke="var(--teal)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
          <path d="${pathFor(echoScore)}" fill="none" stroke="var(--violet)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="8 6"></path>
          <g>${decisionPoints.map((decisionPoint, index) => decisionMarker(decisionPoint, "Player", index)).join("")}</g>
          <g>${decisionPoints.map((decisionPoint, index) => decisionMarker(decisionPoint, "ECHO", index)).join("")}</g>
        </svg>
        <div class="chart-tooltip" id="decisionChartTooltip"></div>
      </div>
    </div>
  `;
}

export function showDecisionChartTooltip(event, marker) {
  const tooltip = $("decisionChartTooltip");
  if (!tooltip || !marker) return;
  const data = marker.dataset;
  const questionDetail = data.questionText && data.questionText !== data.questionTitle
    ? `<div>${escapeHtml(data.questionText)}</div>`
    : "";
  tooltip.innerHTML = `
    <strong>${escapeHtml(data.label || "Question")} decision</strong>
    <div>Day ${escapeHtml(data.day || "-")}</div>
    <div>Question: ${escapeHtml(data.questionTitle || "-")}</div>
    ${questionDetail}
    <div>Your answer: ${escapeHtml(data.playerChoice || "-")}</div>
    <div>Correct answer (ECHO): ${escapeHtml(data.correctAnswer || "-")}</div>
    <div>Your score: ${escapeHtml(data.playerCumulative || "+0.00")} (${escapeHtml(data.playerChange || "+0.00")} this question)</div>
    <div>ECHO score: ${escapeHtml(data.echoCumulative || "+0.00")} (${escapeHtml(data.echoChange || "+0.00")} this question)</div>
    <div>Job/Subjob: ${escapeHtml(data.affected || "-")}</div>
  `;
  tooltip.classList.add("active");
  positionDecisionChartTooltip(event, marker, tooltip);
}

function positionDecisionChartTooltip(event, marker, tooltip) {
  const frame = tooltip.parentElement;
  if (!frame) return;
  const frameRect = frame.getBoundingClientRect();
  const markerRect = marker.getBoundingClientRect();
  const clientX = Number.isFinite(event?.clientX) && event.clientX > 0
    ? event.clientX
    : markerRect.left + markerRect.width / 2;
  const clientY = Number.isFinite(event?.clientY) && event.clientY > 0
    ? event.clientY
    : markerRect.top;
  const tooltipWidth = tooltip.offsetWidth || 260;
  const tooltipHeight = tooltip.offsetHeight || 120;
  let left = clientX - frameRect.left + 12;
  let top = clientY - frameRect.top - tooltipHeight - 10;

  if (left + tooltipWidth > frameRect.width) {
    left = Math.max(8, frameRect.width - tooltipWidth - 8);
  }
  if (top < 8) {
    top = clientY - frameRect.top + 14;
  }

  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

export function hideDecisionChartTooltip() {
  const tooltip = $("decisionChartTooltip");
  if (!tooltip) return;
  tooltip.classList.remove("active");
}

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

  $("finalCompletionChart").innerHTML = renderDecisionScoreChart(final.completionHistory);

  $("finalTable").innerHTML = `
    <thead>
      <tr>
        <th>Metric</th>
        <th>Your Schedule</th>
        <th>ECHO Benchmark</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Final decision score</td>
        <td>${Number(p.finalScore || 0).toFixed(2)}</td>
        <td>${Number(a.finalScore || 0).toFixed(2)}</td>
      </tr>
      <tr>
        <td>Deadline met</td>
        <td>${p.deadlineMet ? "Yes" : "No"}</td>
        <td>${a.deadlineMet ? "Yes" : "No"}</td>
      </tr>
      <tr>
        <td>Completion</td>
        <td>${escapeHtml(p.completion || "Not complete")}</td>
        <td>${escapeHtml(a.completion || "Not complete")}</td>
      </tr>
      <tr>
        <td>Jobs complete</td>
        <td>${p.piecesCompleted}</td>
        <td>${a.piecesCompleted}</td>
      </tr>
      <tr>
        <td>Subjobs completed</td>
        <td>${p.jobsCompleted}</td>
        <td>${a.jobsCompleted}</td>
      </tr>
      <tr>
        <td>Subjobs behind schedule</td>
        <td>${p.jobsBehindSchedule}</td>
        <td>${a.jobsBehindSchedule}</td>
      </tr>
      <tr>
        <td>Subjobs late</td>
        <td>${p.jobsLate}</td>
        <td>${a.jobsLate}</td>
      </tr>
      <tr>
        <td>Risk</td>
        <td>${Math.round(p.scheduleRisk)}/100</td>
        <td>${Math.round(a.scheduleRisk)}/100</td>
      </tr>
    </tbody>
  `;

  $("finalNotes").innerHTML = (review.reasons || final.explanation || [])
    .map(note => `<li>${escapeHtml(note)}</li>`)
    .join("") || "<li>No final review notes recorded.</li>";
}
