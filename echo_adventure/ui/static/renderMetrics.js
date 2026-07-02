"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml, fmtNum } from "./html.js";

export function renderMetrics() {
  const snap = uiState.state.snapshot;
  const totalSubjobs = snap.jobsCompleted + snap.jobsRemaining;
  const metrics = [
    ["Jobs Complete", `${snap.piecesCompleted}/${uiState.state.pieces.length}`, snap.piecesCompleted / uiState.state.pieces.length, "good", "How many top-level jobs are complete.", true, renderJobsMetricPopover()],
    ["Subjobs Complete", `${fmtNum(snap.jobsCompleted)}/${fmtNum(totalSubjobs)}`, snap.jobsCompleted / Math.max(1, totalSubjobs), "good", "Total subjobs finished out of all required work.", true, ""],
    ["Subjobs Behind Schedule", fmtNum(snap.jobsBehindSchedule), 0, snap.jobsBehindSchedule > 0 ? "warn" : "good", "Incomplete subjobs whose target completion date has already passed.", false, ""],
    ["Subjobs Late", fmtNum(snap.jobsLate), 0, snap.jobsLate > 0 ? "warn" : "good", "Completed subjobs that finished after their target completion date.", false, ""],
    ["Schedule Risk", `${Math.round(snap.scheduleRisk)}/100`, snap.scheduleRisk / 100, snap.scheduleRisk > 70 ? "danger" : snap.scheduleRisk > 40 ? "warn" : "good", "Overall probability of missing the deadline (0 = safe, 100 = critical).", true, ""]
  ];
  $("metrics").innerHTML = metrics.map(([label, value, pct, tone, tooltip, showBar, detail]) => `
    <div class="metric ${detail ? "hoverable" : ""}" ${detail ? `tabindex="0" aria-describedby="jobsMetricPopover"` : ""}>
      <div class="metric-title-row">
        <span class="subtle">${label}<span class="info-icon" data-tooltip="${escapeHtml(tooltip)}">i</span></span>
        ${detail ? `<span class="metric-hint">Details</span>` : ""}
      </div>
      <strong>${value}</strong>
      ${showBar ? `<div class="progress"><div class="bar ${tone}" style="width:${Math.max(0, Math.min(1, pct)) * 100}%"></div></div>` : ""}
      ${detail}
    </div>
  `).join("");
}

function renderJobsMetricPopover() {
  const pieces = Array.isArray(uiState.state?.pieces)
    ? [...uiState.state.pieces].sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, { numeric: true }))
    : [];
  if (!pieces.length) return "";

  return `
    <div id="jobsMetricPopover" class="metric-popover" role="tooltip">
      <h3>Jobs</h3>
      <div class="metric-popover-frame">
        <table>
          <thead>
            <tr>
              <th>Job</th>
              <th>Subjobs Complete</th>
              <th>Projected Finish</th>
              <th>Due Date</th>
            </tr>
          </thead>
          <tbody>
            ${pieces.map(piece => {
              const completed = Number(piece.completed || 0);
              const total = Number(piece.total || 0);
              return `
                <tr>
                  <td>${escapeHtml(piece.displayId || piece.id || "-")}</td>
                  <td>${completed}/${total}</td>
                  <td>${escapeHtml(piece.projectedCompletion || "-")}</td>
                  <td>${escapeHtml(piece.dueDate || "-")}</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}
