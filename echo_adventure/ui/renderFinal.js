"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml } from "./html.js";

function finalMetric(label, player, echo) {
  return `
    <div class="metric final-metric">
      <span class="subtle metric-label">${escapeHtml(label)}</span>
      <strong>${escapeHtml(player)}</strong>
      <div class="final-metric-benchmark">ECHO ${escapeHtml(echo)}</div>
    </div>
  `;
}

function renderHistory(history) {
  if (!history?.length) return `<p class="subtle">No completion history recorded.</p>`;
  return `
    <div class="completion-history-table">
      <table>
        <thead><tr><th>Day</th><th>You</th><th>ECHO</th></tr></thead>
        <tbody>${history.map(point => `
          <tr><td>${escapeHtml(point.label)}</td><td>${point.player}/20 jobs</td><td>${point.automated}/20 jobs</td></tr>
        `).join("")}</tbody>
      </table>
    </div>
  `;
}

export function showDecisionChartTooltip() {}
export function hideDecisionChartTooltip() {}

export function renderFinal() {
  const final = uiState.state?.finalReveal;
  if (!final) {
    $("finalSection").classList.add("hidden");
    return;
  }
  $("finalSection").classList.remove("hidden");
  const player = final.player;
  const echo = final.automated;
  $("finalMetricsBar").innerHTML = [
    finalMetric("Completion", player.completion || "-", echo.completion || "-"),
    finalMetric("Completion Day", String(player.completionDay || "-"), String(echo.completionDay || "-")),
    finalMetric("Decision Score", String(player.finalScore), String(echo.finalScore)),
    finalMetric("Jobs Complete", `${player.jobsCompleted}/20`, `${echo.jobsCompleted}/20`),
  ].join("");
  $("finalCompletionChart").innerHTML = renderHistory(final.completionHistory);
  const review = final.review || {};
  $("finalNotes").innerHTML = [review.headline, ...(review.reasons || [])]
    .filter(Boolean)
    .map(note => `<li>${escapeHtml(note)}</li>`)
    .join("");
}
