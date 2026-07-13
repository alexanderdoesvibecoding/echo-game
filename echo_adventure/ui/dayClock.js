"use strict";

import { uiState } from "./state.js";
import { escapeHtml } from "./html.js";

const DEFAULT_DAY_CYCLE_DURATION_MS = 8000;
const TICK_MS = 180;
const callbacks = {
  render: () => {},
  renderInlineDecisions: () => {},
  prepareAdvanceDay: () => {},
  showError: () => {},
};

export function configureDayClock(overrides) {
  Object.assign(callbacks, overrides || {});
}

export function decisionProgress() {
  return uiState.state?.decisionProgress || { completed: 0, total: 0, openCardIds: [] };
}

export function readyToAdvance() {
  const progress = decisionProgress();
  return Boolean(uiState.state && !uiState.state.gameOver && progress.completed === progress.total);
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
  const key = `${uiState.runCycleId}:${uiState.state.seed}:${uiState.state.day}`;
  if (uiState.dayCycleKey !== key) {
    uiState.dayCycleKey = key;
    uiState.dayCycleProgress = 0;
    uiState.dayCycleLastTick = performance.now();
    uiState.dayCycleAdvancing = false;
    uiState.dayDecisionThresholds = buildThresholds(decisionProgress().total);
    uiState.decisionModalVisible = false;
    uiState.decisionModalDismissedKey = null;
  }
  if (!uiState.dayCycleTimer) {
    uiState.dayCycleTimer = window.setInterval(tick, TICK_MS);
  }
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
  if (!cycleBlocked()) {
    uiState.dayCycleProgress = Math.min(100, uiState.dayCycleProgress + elapsed / dayDurationMs() * 100);
  }
  if (nextDecisionIsDue()) {
    const card = currentOpenDecisionCard();
    const key = decisionModalKey(card);
    if (card && uiState.decisionModalDismissedKey !== key && !uiState.decisionModalVisible) {
      uiState.decisionModalVisible = true;
      callbacks.render();
      return;
    }
  }
  if (uiState.dayCycleProgress >= 100 && readyToAdvance() && !uiState.dayCycleAdvancing && !uiState.pendingAdvanceState) {
    uiState.dayCycleAdvancing = true;
    callbacks.prepareAdvanceDay();
    return;
  }
  callbacks.renderInlineDecisions();
}

function cycleBlocked() {
  return uiState.welcomeModalVisible
    || uiState.newRunModalVisible
    || uiState.decisionModalVisible
    || nextDecisionIsDue()
    || Boolean(uiState.pendingAdvanceState);
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
  return Boolean(currentOpenDecisionCard() && dayCyclePercent() >= threshold);
}

export function currentOpenDecisionCard() {
  return uiState.state?.decisions?.find(card => !card.selectedChoice) || null;
}

export function decisionModalKey(card) {
  return card ? `${uiState.state?.day}:${card.id}` : "";
}

export function decisionModalBlocked() {
  return !uiState.state || uiState.state.gameOver || uiState.welcomeModalVisible || uiState.newRunModalVisible;
}

export function renderDayClock(statusText, paused = false) {
  const percent = dayCyclePercent();
  return `
    <div class="day-clock">
      <div class="day-clock-row"><span>${escapeHtml(statusText)}</span><span>${Math.round(percent)}%</span></div>
      <div class="day-progress-track" aria-label="Day progress, ${Math.round(percent)} percent">
        <div class="day-progress-fill ${paused ? "paused" : ""}" style="width:${percent}%"></div>
      </div>
    </div>
  `;
}
