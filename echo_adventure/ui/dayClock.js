"use strict";

import { api } from "./api.js";
import { uiState } from "./state.js";
import { escapeHtml } from "./html.js";
import { renderSubmarineImage } from "./submarineVisual.js";

const DEFAULT_DAY_CYCLE_DURATION_MS = 8000;
const DAY_CYCLE_TICK_MS = 220;
const DAY_PROGRESS_SUBMARINE_WIDTH_PX = 78;

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
  if (!uiState.state) {
    return { completed: 0, total: 0, visibleCards: 0, openCardIds: [] };
  }
  return uiState.state.decisionProgress || { completed: 0, total: 0, visibleCards: 0, openCardIds: [] };
}

export function readyToAdvance() {
  const progress = decisionProgress();
  return Boolean(uiState.state && !uiState.state.gameOver && (progress.total === 0 || progress.completed === progress.total));
}

export function resetDayCycle() {
  uiState.dayCycleKey = null;
  uiState.dayCycleProgress = 0;
  uiState.dayCycleLastTick = null;
  uiState.dayCycleAdvancing = false;
  uiState.dayCycleShiftInFlight = false;
  uiState.dayCycleCompletedShiftMarkers = new Set();
  uiState.dayDecisionThresholdKey = null;
  uiState.dayDecisionThresholds = [];
}

export function syncDayCycleForState() {
  if (!uiState.state || uiState.state.gameOver) {
    stopDayCycle();
    return;
  }

  const nextKey = `${uiState.runCycleId}:${uiState.state.day}`;
  if (uiState.dayCycleKey !== nextKey) {
    uiState.dayCycleKey = nextKey;
    uiState.dayCycleProgress = 0;
    uiState.dayCycleLastTick = null;
    uiState.dayCycleAdvancing = false;
    uiState.dayCycleShiftInFlight = false;
    uiState.dayCycleCompletedShiftMarkers = completedShiftMarkersFromState();
    uiState.dayCycleProgress = Math.max(uiState.dayCycleProgress, (completedShiftCountFromState() / shiftsPerDay()) * 100);
    uiState.dayDecisionThresholdKey = null;
    uiState.dayDecisionThresholds = [];
    uiState.decisionModalVisible = false;
    uiState.decisionModalDismissedKey = null;
  }
  syncDecisionThresholdsForState();
  ensureDayCycle();
}

function ensureDayCycle() {
  if (uiState.dayCycleTimer) return;
  uiState.dayCycleLastTick = performance.now();
  uiState.dayCycleTimer = window.setInterval(tickDayCycle, DAY_CYCLE_TICK_MS);
}

function stopDayCycle() {
  if (uiState.dayCycleTimer) {
    window.clearInterval(uiState.dayCycleTimer);
    uiState.dayCycleTimer = null;
  }
  uiState.dayCycleLastTick = null;
}

export function nextDecisionThreshold() {
  const progressState = decisionProgress();
  if (!progressState.total) return 100;
  syncDecisionThresholdsForState();
  const threshold = uiState.dayDecisionThresholds[progressState.completed];
  if (Number.isFinite(threshold)) return threshold;
  return ((progressState.completed + 1) / (progressState.total + 1)) * 100;
}

function syncDecisionThresholdsForState() {
  if (!uiState.state || uiState.state.gameOver) {
    uiState.dayDecisionThresholdKey = null;
    uiState.dayDecisionThresholds = [];
    return;
  }
  const progressState = decisionProgress();
  const cardIds = Array.isArray(uiState.state.decisions)
    ? uiState.state.decisions.map(card => card.id).join("|")
    : "";
  const nextKey = `${uiState.state.seed ?? "seedless"}:${uiState.state.day}:${progressState.total}:${cardIds}`;
  if (uiState.dayDecisionThresholdKey === nextKey) return;
  uiState.dayDecisionThresholdKey = nextKey;
  uiState.dayDecisionThresholds = buildDecisionThresholds(progressState.total, nextKey);
}

function buildDecisionThresholds(total, seedText) {
  const count = Math.max(0, Math.floor(Number(total) || 0));
  if (!count) return [];
  const random = seededRandomFactory(seedText);
  if (count === 1) {
    return [randomBetween(random, 24, 76)];
  }

  const edgeBuffer = 7;
  const minimumGap = count >= 5 ? 8 : 10;
  const baseUsed = edgeBuffer * 2 + minimumGap * Math.max(0, count - 1);
  const remaining = Math.max(0, 100 - baseUsed);
  const weights = Array.from({ length: count + 1 }, () => 0.25 + random() * 1.5);
  const weightTotal = weights.reduce((sum, weight) => sum + weight, 0) || 1;
  const extras = weights.map(weight => remaining * (weight / weightTotal));
  const thresholds = [];
  let cursor = edgeBuffer + extras[0];

  for (let index = 0; index < count; index += 1) {
    if (index > 0) {
      cursor += minimumGap + extras[index];
    }
    thresholds.push(Math.max(5, Math.min(94, Number(cursor.toFixed(1)))));
  }
  return thresholds;
}

function seededRandomFactory(seedText) {
  let seed = 2166136261;
  const text = String(seedText || "decision-thresholds");
  for (let index = 0; index < text.length; index += 1) {
    seed ^= text.charCodeAt(index);
    seed = Math.imul(seed, 16777619);
  }
  seed >>>= 0;
  return () => {
    seed += 0x6D2B79F5;
    let value = seed;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function randomBetween(random, minimum, maximum) {
  return Number((minimum + random() * (maximum - minimum)).toFixed(1));
}

export function nextDecisionIsDue() {
  return Boolean(currentOpenDecisionCard() && uiState.dayCycleProgress >= nextDecisionThreshold());
}

function dayCycleBlocked() {
  return !uiState.state
    || uiState.state.gameOver
    || uiState.welcomeModalVisible
    || uiState.newRunModalVisible
    || uiState.decisionModalVisible
    || uiState.dayCycleShiftInFlight
    || nextDecisionIsDue()
    || (uiState.modalVisible && uiState.pendingAdvanceState);
}

function tickDayCycle() {
  if (!uiState.state || uiState.state.gameOver) {
    stopDayCycle();
    return;
  }

  const now = performance.now();
  const lastTick = uiState.dayCycleLastTick ?? now;
  const elapsed = now - lastTick;
  uiState.dayCycleLastTick = now;

  if (!dayCycleBlocked()) {
    uiState.dayCycleProgress = Math.min(100, uiState.dayCycleProgress + (elapsed / dayCycleDurationMs()) * 100);
  }

  if (nextDecisionIsDue()) {
    const nextCard = currentOpenDecisionCard();
    const key = decisionModalKey(nextCard);
    if (nextCard && uiState.decisionModalDismissedKey !== key) {
      if (uiState.decisionModalVisible) {
        return;
      }
      uiState.decisionModalVisible = true;
      callbacks.render();
      return;
    }
  }

  const shiftMarker = nextShiftMarkerDue();
  if (shiftMarker && !uiState.dayCycleShiftInFlight && !(uiState.modalVisible && uiState.pendingAdvanceState)) {
    advanceShift(shiftMarker);
    return;
  }

  if (uiState.dayCycleProgress >= 100 && readyToAdvance() && !uiState.dayCycleAdvancing && !uiState.dayCycleShiftInFlight && !(uiState.modalVisible && uiState.pendingAdvanceState)) {
    uiState.dayCycleAdvancing = true;
    callbacks.renderInlineDecisions();
    callbacks.prepareAdvanceDay();
    return;
  }

  callbacks.renderInlineDecisions();
}

export function dayCyclePercent() {
  return Math.max(0, Math.min(100, uiState.dayCycleProgress));
}

function shiftsPerDay() {
  return Math.max(1, Number(uiState.state?.shiftsPerDay || 3));
}

function dayCycleDurationMs() {
  const configured = Number(uiState.state?.dayCycleDurationMs ?? DEFAULT_DAY_CYCLE_DURATION_MS);
  return Number.isFinite(configured) ? Math.max(1, configured) : DEFAULT_DAY_CYCLE_DURATION_MS;
}

function nextShiftMarkerDue() {
  const count = shiftsPerDay();
  for (let marker = 1; marker < count; marker += 1) {
    if (!uiState.dayCycleCompletedShiftMarkers.has(marker) && uiState.dayCycleProgress >= (marker / count) * 100) {
      return marker;
    }
  }
  return null;
}

function completedShiftMarkersFromState() {
  const count = shiftsPerDay();
  const completedInDay = completedShiftCountFromState();
  const markers = new Set();
  for (let marker = 1; marker <= Math.min(completedInDay, count - 1); marker += 1) {
    markers.add(marker);
  }
  return markers;
}

function completedShiftCountFromState() {
  return Math.max(0, Number(uiState.state?.snapshot?.shift || 0) % shiftsPerDay());
}

async function advanceShift(marker) {
  uiState.dayCycleShiftInFlight = true;
  uiState.dayCycleCompletedShiftMarkers.add(marker);
  try {
    const nextState = await api("/api/shift", { method: "POST", body: "{}" });
    callbacks.showError("");
    if (nextState.finalReveal) {
      uiState.state = nextState;
      uiState.pendingAdvanceState = null;
      uiState.modalVisible = false;
    } else if (nextState.shiftAdvance?.dayComplete) {
      uiState.pendingAdvanceState = nextState;
      uiState.modalVisible = true;
    } else {
      uiState.state = nextState;
    }
    callbacks.render();
  } catch (error) {
    uiState.dayCycleCompletedShiftMarkers.delete(marker);
    callbacks.showError(error.message);
  } finally {
    uiState.dayCycleShiftInFlight = false;
  }
}

export function renderDayClock(statusText, paused = false) {
  const percent = dayCyclePercent();
  const markerPercent = Number(percent.toFixed(2));
  const submarineOffset = Number(((markerPercent / 100) * DAY_PROGRESS_SUBMARINE_WIDTH_PX).toFixed(2));
  const gradientWidth = dayProgressGradientWidth(percent);
  return `
    <div class="day-clock">
      <div class="day-clock-row">
        <span>${escapeHtml(statusText)}</span>
        <span>${Math.round(percent)}%</span>
      </div>
      <div class="day-progress-track" aria-label="Workday progress, ${Math.round(percent)} percent">
        <div class="day-progress-fill ${paused ? "paused" : ""}" style="width:${percent}%; --day-progress-gradient-width:${gradientWidth}"></div>
        <div class="day-progress-submarine" style="left:calc(${markerPercent}% - ${submarineOffset}px)">
          ${renderSubmarineImage({
            idPrefix: "dayProgressSubmarine",
            className: "day-progress-submarine-image",
            decorative: true,
          })}
        </div>
      </div>
    </div>
  `;
}

function dayProgressGradientWidth(percent) {
  if (percent <= 0) return "100%";
  const safePercent = Math.max(1, Math.min(100, Number(percent) || 0));
  return `${Number((10000 / safePercent).toFixed(2))}%`;
}

export function currentOpenDecisionCard() {
  return Array.isArray(uiState.state?.decisions)
    ? uiState.state.decisions.find(card => !card.selectedChoice) || null
    : null;
}

export function decisionModalKey(card) {
  return uiState.state && card ? `${uiState.state.day}:${card.id}` : "";
}

export function decisionModalBlocked() {
  return !uiState.state
    || uiState.state.gameOver
    || uiState.welcomeModalVisible
    || uiState.newRunModalVisible
    || !nextDecisionIsDue()
    || (uiState.modalVisible && uiState.pendingAdvanceState);
}
