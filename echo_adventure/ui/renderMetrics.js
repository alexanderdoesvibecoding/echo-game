"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml, fmtNum } from "./html.js";

const METRIC_DELTA_DISPLAY_MS = 2200;

export function renderMetrics() {
  const snap = uiState.state.snapshot;
  const totalSubjobs = snap.jobsCompleted + snap.jobsRemaining;
  const deltas = syncMetricDeltas(snap);
  scheduleMetricDeltaCleanup();
  const metrics = [
    {
      label: "Jobs Complete",
      value: `${snap.piecesCompleted}/${uiState.state.pieces.length}`,
      pct: snap.piecesCompleted / uiState.state.pieces.length,
      tone: "good",
      tooltip: "How many top-level jobs are complete.",
      showBar: true,
      detail: renderJobsMetricPopover(),
      detailId: "jobsMetricPopover",
      delta: deltas.jobs,
      deltaUnit: "top-level job",
    },
    {
      label: "Subjobs Complete",
      value: `${fmtNum(snap.jobsCompleted)}/${fmtNum(totalSubjobs)}`,
      pct: snap.jobsCompleted / Math.max(1, totalSubjobs),
      tone: "good",
      tooltip: "Total subjobs finished out of all required work.",
      showBar: true,
      delta: deltas.subjobs,
      deltaUnit: "subjob",
    },
    {
      label: "Subjobs Behind Schedule",
      value: fmtNum(snap.jobsBehindSchedule),
      pct: 0,
      tone: snap.jobsBehindSchedule > 0 ? "warn" : "good",
      tooltip: "Incomplete subjobs whose target completion date has already passed.",
      showBar: false,
      detail: renderSubjobsBehindSchedulePopover(),
      detailId: "subjobsBehindSchedulePopover",
    },
    {
      label: "Subjobs Late",
      value: fmtNum(snap.jobsLate),
      pct: 0,
      tone: snap.jobsLate > 0 ? "warn" : "good",
      tooltip: "Completed subjobs that finished after their target completion date.",
      showBar: false,
    },
    {
      label: "Schedule Risk",
      value: `${Math.round(snap.scheduleRisk)}/100`,
      pct: snap.scheduleRisk / 100,
      tone: snap.scheduleRisk > 70 ? "danger" : snap.scheduleRisk > 40 ? "warn" : "good",
      tooltip: "Overall probability of missing the deadline (0 = safe, 100 = critical).",
      showBar: true,
    },
  ];
  $("metrics").innerHTML = metrics.map((metric) => {
    const detail = metric.detail || "";
    const detailAttrs = detail
      ? `tabindex="0"${metric.detailId ? ` aria-describedby="${escapeHtml(metric.detailId)}"` : ""}`
      : "";
    return `
    <div class="metric ${detail ? "hoverable" : ""} ${metric.delta ? "has-live-delta" : ""}" ${detailAttrs}>
      <div class="metric-title-row">
        <span class="subtle metric-label">${metric.label}<span class="info-icon" data-tooltip="${escapeHtml(metric.tooltip)}">i</span></span>
        ${detail ? `<span class="metric-hint">Details</span>` : ""}
      </div>
      <div class="metric-value-row">
        <strong>${metric.value}</strong>
        ${renderShiftDelta(metric.delta, metric.deltaUnit)}
      </div>
      ${metric.showBar ? `<div class="progress"><div class="bar ${metric.tone}" style="width:${Math.max(0, Math.min(1, metric.pct)) * 100}%"></div></div>` : ""}
      ${detail}
    </div>
  `;
  }).join("");
}

function renderShiftDelta(count, unitName) {
  if (!count) return "";
  const unit = Number(count) === 1 ? unitName : `${unitName}s`;
  return `<span class="metric-live-delta" aria-live="polite" aria-label="${fmtNum(count)} ${unit} completed this shift">+${fmtNum(count)}</span>`;
}

function syncMetricDeltas(snap) {
  const now = nowMs();
  pruneMetricDeltas(now);

  const current = {
    runCycleId: uiState.runCycleId,
    seed: uiState.state?.seed ?? "",
    shift: Math.max(0, Number(snap.shift || 0)),
    jobsCompleted: Math.max(0, Number(snap.jobsCompleted || 0)),
    piecesCompleted: Math.max(0, Number(snap.piecesCompleted || 0)),
  };
  const previous = uiState.metricSnapshot;
  const sameRun = Boolean(previous && previous.runCycleId === current.runCycleId && previous.seed === current.seed);

  if (!sameRun) {
    uiState.metricDeltas = {};
  } else if (current.shift > previous.shift) {
    setMetricDelta("subjobs", current.jobsCompleted - previous.jobsCompleted, now);
    setMetricDelta("jobs", current.piecesCompleted - previous.piecesCompleted, now);
  }

  uiState.metricSnapshot = current;
  return activeMetricDeltas(now);
}

function setMetricDelta(key, count, now) {
  const safeCount = Math.max(0, Number(count || 0));
  if (!safeCount) {
    delete uiState.metricDeltas[key];
    return;
  }
  uiState.metricDeltas[key] = {
    count: safeCount,
    expiresAt: now + METRIC_DELTA_DISPLAY_MS,
  };
}

function activeMetricDeltas(now) {
  pruneMetricDeltas(now);
  return Object.fromEntries(
    Object.entries(uiState.metricDeltas || {}).map(([key, delta]) => [key, delta.count])
  );
}

function pruneMetricDeltas(now) {
  for (const [key, delta] of Object.entries(uiState.metricDeltas || {})) {
    if (!delta || Number(delta.expiresAt || 0) <= now) {
      delete uiState.metricDeltas[key];
    }
  }
}

function scheduleMetricDeltaCleanup() {
  if (typeof window === "undefined") return;
  const expiries = Object.values(uiState.metricDeltas || {})
    .map((delta) => Number(delta?.expiresAt || 0))
    .filter((expiresAt) => expiresAt > 0);

  if (uiState.metricDeltaTimer) {
    window.clearTimeout(uiState.metricDeltaTimer);
    uiState.metricDeltaTimer = null;
  }
  if (!expiries.length) return;

  const delay = Math.max(0, Math.min(...expiries) - nowMs() + 30);
  uiState.metricDeltaTimer = window.setTimeout(() => {
    uiState.metricDeltaTimer = null;
    if (uiState.state) {
      renderMetrics();
    }
  }, delay);
}

function nowMs() {
  return typeof performance !== "undefined" && typeof performance.now === "function"
    ? performance.now()
    : Date.now();
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
