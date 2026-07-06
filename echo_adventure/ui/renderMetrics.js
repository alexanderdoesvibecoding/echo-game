"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml, fmtNum } from "./html.js";

export function renderMetrics() {
  const snap = uiState.state.snapshot;
  const totalSubjobs = snap.jobsCompleted + snap.jobsRemaining;
  const jobsCompletedToday = Math.max(0, Number(snap.jobsCompletedToday || 0));
  const jobsCompletedTodayDelta = renderTodayDelta(jobsCompletedToday);
  const metrics = [
    ["Jobs Complete", `${snap.piecesCompleted}/${uiState.state.pieces.length}`, snap.piecesCompleted / uiState.state.pieces.length, "good", "How many top-level jobs are complete.", true, renderJobsMetricPopover(), "jobsMetricPopover"],
    ["Subjobs Complete", `${fmtNum(snap.jobsCompleted)}/${fmtNum(totalSubjobs)}`, snap.jobsCompleted / Math.max(1, totalSubjobs), "good", "Total subjobs finished out of all required work.", true, "", jobsCompletedToday],
    ["Subjobs Behind Schedule", fmtNum(snap.jobsBehindSchedule), 0, snap.jobsBehindSchedule > 0 ? "warn" : "good", "Incomplete subjobs whose target completion date has already passed.", false,  renderSubjobsBehindSchedulePopover(), "subjobsBehindSchedulePopover"],
    ["Subjobs Late", fmtNum(snap.jobsLate), 0, snap.jobsLate > 0 ? "warn" : "good", "Completed subjobs that finished after their target completion date.", false, ""],
    ["Schedule Risk", `${Math.round(snap.scheduleRisk)}/100`, snap.scheduleRisk / 100, snap.scheduleRisk > 70 ? "danger" : snap.scheduleRisk > 40 ? "warn" : "good", "Overall probability of missing the deadline (0 = safe, 100 = critical).", true, "",""]
  ];
  $("metrics").innerHTML = metrics.map(([label, value, pct, tone, tooltip, showBar, detail]) => `
    <div class="metric ${detail ? "hoverable" : ""}" ${detail ? `tabindex="0" aria-describedby="jobsMetricPopover"` : ""}>
      <div class="metric-title-row">
        <span class="subtle metric-label">${label}<span class="info-icon" data-tooltip="${escapeHtml(tooltip)}">i</span></span>
        ${detail ? `<span class="metric-hint">Details</span>` : ""}
      </div>
      <strong>${value}</strong>
      ${showBar ? `<div class="progress"><div class="bar ${tone}" style="width:${Math.max(0, Math.min(1, pct)) * 100}%"></div></div>` : ""}
      ${detail}
    </div>
  `).join("");
}

function renderTodayDelta(count) {
  if (!count) return "";
  return `<span class="metric-live-delta" aria-label="${fmtNum(count)} subjobs completed today">+${fmtNum(count)}</span>`;
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

function renderSubjobsBehindSchedulePopover() {
  const pastDueJobs = Array.isArray(uiState.state?.pastDueJobs) ? uiState.state.pastDueJobs : [];
  const body = pastDueJobs.length ? `
    <table>
      <thead>
        <tr>
          <th>Subjob</th>
          <th>Job</th>
          <th>Shop</th>
          <th>Due Date</th>
          <th>Late</th>
          <th>Remaining</th>
        </tr>
      </thead>
      <tbody>
        ${pastDueJobs.map(job => `
          <tr>
            <td>${escapeHtml(job.id)}</td>
            <td>${escapeHtml(job.piece || "-")}</td>
            <td>${escapeHtml(job.shop || "-")}</td>
            <td>${escapeHtml(job.due || "-")}</td>
            <td>${fmtNum(job.daysLate)} day${Number(job.daysLate) === 1 ? "" : "s"}</td>
            <td>${fmtNum(job.remaining)} shift${Number(job.remaining) === 1 ? "" : "s"}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  ` : `<p class="subtle metric-empty">No subjobs are currently behind schedule.</p>`;

  return `
    <div id="subjobsBehindSchedulePopover" class="metric-popover" role="tooltip">
      <h3>Behind Schedule</h3>
      <div class="metric-popover-frame">
        ${body}
      </div>
    </div>
  `;
}
