"use strict";

import { uiState } from "./state.js";
import { SUBMARINE_IMAGE_SRC } from "./submarineVisual.js";

const DEFAULT_DAY_CYCLE_DURATION_MS = 6000;
const TICK_MS = 180;
const TIMELINE_ACTORS = [
  { key: "player", label: "YOU:", spokenLabel: "You" },
  { key: "echo", label: "ECHO:", spokenLabel: "ECHO" },
];
const callbacks = {
  renderInlineDecisions: () => {},
  renderDecisionQueue: () => {},
  prepareAdvanceDay: () => {},
};

export function configureDayClock(overrides) {
  Object.assign(callbacks, overrides || {});
}

export function decisionProgress() {
  return uiState.state?.decisionProgress || { completed: 0, total: 0 };
}

export function readyToAdvance() {
  const progress = decisionProgress();
  return Boolean(uiState.state && !uiState.state.gameOver && progress.completed === progress.total);
}

export function instantProgressionEnabled() {
  return Boolean(uiState.state?.developer && uiState.devInstantProgression);
}

export function resetDayCycle() {
  uiState.dayCycleKey = null;
  uiState.dayCycleProgress = 0;
  uiState.dayCycleLastTick = null;
  uiState.dayCycleAdvancing = false;
  uiState.dayDecisionThresholds = [];
}

export function syncDayCycleForState() {
  if (!uiState.state || uiState.state.gameOver) {
    stopTimer();
    return;
  }
  const finalAssemblyStatus = uiState.state.finalAssembly?.status || "normal";
  const key = `${uiState.runCycleId}:${uiState.state.seed}:${uiState.state.day}:${finalAssemblyStatus}`;
  if (uiState.dayCycleKey !== key) {
    uiState.dayCycleKey = key;
    uiState.dayCycleProgress = 0;
    uiState.dayCycleLastTick = performance.now();
    uiState.dayCycleAdvancing = false;
    uiState.dayDecisionThresholds = buildThresholds(decisionProgress().total);
  }
  if (!uiState.dayCycleTimer) {
    uiState.dayCycleTimer = window.setInterval(tick, TICK_MS);
  }
  maybeAdvanceInstantly();
}

function buildThresholds(total) {
  const count = Math.max(0, Number(total) || 0);
  return Array.from({ length: count }, (_, index) => ((index + 1) / (count + 1)) * 88);
}

function stopTimer() {
  if (uiState.dayCycleTimer) window.clearInterval(uiState.dayCycleTimer);
  uiState.dayCycleTimer = null;
  uiState.dayCycleLastTick = null;
}

function tick() {
  if (!uiState.state || uiState.state.gameOver) {
    stopTimer();
    return;
  }
  const now = performance.now();
  const elapsed = now - (uiState.dayCycleLastTick ?? now);
  uiState.dayCycleLastTick = now;
  if (maybeAdvanceInstantly()) return;
  if (!cycleBlocked()) {
    uiState.dayCycleProgress = Math.min(100, uiState.dayCycleProgress + elapsed / dayDurationMs() * 100);
  }

  if (uiState.dayCycleProgress >= 100 && readyToAdvance() && !uiState.dayCycleAdvancing && !uiState.pendingAdvanceState) {
    uiState.dayCycleAdvancing = true;
    callbacks.prepareAdvanceDay();
    return;
  }
  callbacks.renderInlineDecisions();
  callbacks.renderDecisionQueue();
}

function cycleBlocked() {
  return uiState.welcomeModalVisible
    || uiState.newRunModalVisible
    || uiState.modalVisible
    || uiState.newRunLoading
    || uiState.devRequestInFlight
    || uiState.choiceRequestInFlight
    || instantProgressionEnabled()
    || nextDecisionIsDue()
    || Boolean(uiState.pendingAdvanceState);
}

function maybeAdvanceInstantly() {
  if (
    !instantProgressionEnabled()
    || uiState.welcomeModalVisible
    || uiState.newRunModalVisible
    || uiState.modalVisible
    || uiState.newRunLoading
    || uiState.devRequestInFlight
    || uiState.choiceRequestInFlight
    || uiState.advanceRequestInFlight
    || uiState.pendingAdvanceState
    || uiState.dayCycleAdvancing
    || !readyToAdvance()
  ) {
    return false;
  }
  uiState.dayCycleAdvancing = true;
  callbacks.prepareAdvanceDay();
  return true;
}

function dayDurationMs() {
  const configured = Number(uiState.state?.dayCycleDurationMs ?? DEFAULT_DAY_CYCLE_DURATION_MS);
  return Number.isFinite(configured) ? Math.max(1, configured) : DEFAULT_DAY_CYCLE_DURATION_MS;
}

export function dayCyclePercent() {
  return Math.max(0, Math.min(100, uiState.dayCycleProgress));
}

export function nextDecisionIsDue() {
  const progress = decisionProgress();
  const threshold = uiState.dayDecisionThresholds[progress.completed] ?? 100;
  return Boolean(
    currentOpenDecisionCard()
      && (instantProgressionEnabled() || dayCyclePercent() >= threshold)
  );
}

export function currentOpenDecisionCard() {
  return uiState.state?.decisions?.[0] || null;
}

export function decisionInteractionBlocked() {
  return !uiState.state
    || uiState.state.gameOver
    || uiState.welcomeModalVisible
    || uiState.newRunModalVisible
    || uiState.modalVisible
    || uiState.newRunLoading
    || uiState.devRequestInFlight
    || uiState.choiceRequestInFlight;
}

export function renderDayClock() {
  return `
    <div class="day-clock" data-day-clock>
      <div class="completion-timelines" role="group" aria-label="Estimated completion timelines">
        ${TIMELINE_ACTORS.map(renderTimelineRow).join("")}
      </div>
    </div>
  `;
}

export function updateDayClock(root) {
  const clock = root?.querySelector?.("[data-day-clock]");
  if (!clock || !uiState.state) return;
  for (const actor of TIMELINE_ACTORS) {
    updateTimelineRow(clock, actor);
  }
}

function renderTimelineRow(actor) {
  return `
    <div class="completion-timeline" data-timeline-actor="${actor.key}" role="progressbar" aria-labelledby="timeline-${actor.key}-label" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
      <div class="timeline-actor-label" id="timeline-${actor.key}-label">${actor.label}</div>
      <div class="timeline-plot">
        <div class="timeline-course" style="--timeline-submarine-mask:url('${SUBMARINE_IMAGE_SRC}')">
          <span class="timeline-submarine" aria-hidden="true"></span>
          <div class="completion-timeline-track" aria-hidden="true">
            <div class="completion-timeline-fill"></div>
          </div>
          <div class="timeline-dates">
            <span data-timeline-start></span>
            <span class="timeline-end-date" data-timeline-end></span>
          </div>
        </div>
      </div>
    </div>
  `;
}

function updateTimelineRow(clock, actor) {
  const row = clock.querySelector(`[data-timeline-actor="${actor.key}"]`);
  if (!row) return;
  const timeline = uiState.state.timelines?.[actor.key] || {};
  const progressValue = Number(timeline.progressPercent);
  const progress = Number.isFinite(progressValue)
    ? Math.max(0, Math.min(100, progressValue))
    : 0;
  const startDate = uiState.state.scheduleStartDate || "July 1";
  const endDate = timeline.displayCompletion || timeline.projectedCompletion || startDate;
  const projectedDate = timeline.projectedCompletion || endDate;
  const currentDate = uiState.state.currentDate || startDate;
  const actualCompletion = timeline.completion
    ? ` Actual completion: ${timeline.completion}.`
    : "";

  const progressPosition = `${progress}%`;
  const submarine = row.querySelector(".timeline-submarine");
  const fill = row.querySelector(".completion-timeline-fill");
  if (submarine) submarine.style.left = progressPosition;
  if (fill) fill.style.width = progressPosition;
  row.setAttribute("aria-valuenow", String(Math.round(progress)));
  row.setAttribute(
    "aria-valuetext",
    `${actor.spokenLabel}: ${startDate} to ${endDate}. Current story date: ${currentDate}. Projected completion: ${projectedDate}.${actualCompletion}`
  );
  setDateLabel(row.querySelector("[data-timeline-start]"), startDate, false);
  setDateLabel(row.querySelector("[data-timeline-end]"), endDate, true);
}

function setDateLabel(element, value, animateChange) {
  if (!element || element.textContent === value) return;
  const hasPreviousValue = Boolean(element.textContent);
  element.textContent = value;
  if (!animateChange || !hasPreviousValue) return;
  element.classList.remove("is-updating");
  void element.offsetWidth;
  element.classList.add("is-updating");
  window.setTimeout(() => element.classList.remove("is-updating"), 450);
}
