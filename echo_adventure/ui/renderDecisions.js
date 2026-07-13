"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml } from "./html.js";
import {
  currentOpenDecisionCard,
  decisionModalBlocked,
  decisionModalKey,
  decisionProgress,
  readyToAdvance,
  renderDayClock,
} from "./dayClock.js";

const callbacks = { choose: async () => null };

export function configureDecisionActions(overrides) {
  Object.assign(callbacks, overrides || {});
}

export function renderDecisions() {}

export function renderInlineDecisions() {
  const body = $("inlineDecisionBody");
  if (!body || !uiState.state) return;
  const snap = uiState.state.snapshot;
  const progress = decisionProgress();
  const next = currentOpenDecisionCard();
  const status = readyToAdvance()
    ? "All questions answered — finishing today's work"
    : `${progress.completed} of ${progress.total} questions answered`;
  const jobRows = uiState.state.jobs.map(job => `
    <div class="job-day-card ${job.completed ? "complete" : ""}">
      <div><strong>${escapeHtml(job.label)}</strong><span>${escapeHtml(job.name.split(" - ").slice(1).join(" - "))}</span></div>
      <div class="job-days-value">${job.completed ? "Complete" : `${job.remainingDays} day${job.remainingDays === 1 ? "" : "s"}`}</div>
      <div class="progress"><div class="bar good" style="width:${Math.max(0, Math.min(1, Number(job.progress) || 0)) * 100}%"></div></div>
    </div>
  `).join("");
  const decisions = uiState.state.decisions.map((card, index) => `
    <div class="decision-queue-item ${card.selectedChoice ? "complete" : ""}">
      <span>${index + 1}</span>
      <div><strong>${escapeHtml(card.title)}</strong><small>${card.selectedChoice ? "Answered" : "Waiting"}</small></div>
    </div>
  `).join("");
  body.innerHTML = `
    <div class="daily-overview">
      <div class="summary-metrics-bar jobs-only-metrics">
        <div class="metric"><span class="subtle">Jobs Complete</span><strong>${snap.jobsCompleted}/${uiState.state.jobCount}</strong></div>
        <div class="metric"><span class="subtle">Jobs Remaining</span><strong>${snap.jobsRemaining}</strong></div>
        <div class="metric"><span class="subtle">Remaining Job-Days</span><strong>${snap.totalRemainingDays}</strong></div>
        <div class="metric"><span class="subtle">Projected Finish</span><strong>${escapeHtml(snap.projectedCompletion)}</strong></div>
      </div>
      ${renderDayClock(status, Boolean(next))}
      <div class="decision-queue">${decisions}</div>
      ${next ? `<button class="primary decision-open-button" data-action="open-decision-modal">Open next question</button>` : ""}
      <div class="job-day-grid">${jobRows}</div>
    </div>
  `;
}

export function openDecisionModal() {
  if (decisionModalBlocked() || !currentOpenDecisionCard()) return;
  uiState.decisionModalVisible = true;
  uiState.decisionModalDismissedKey = null;
  uiState.pendingChoice = null;
  renderDecisionModal();
}

export function closeDecisionModal() {
  const card = currentOpenDecisionCard();
  uiState.decisionModalVisible = false;
  uiState.decisionModalDismissedKey = decisionModalKey(card);
  uiState.pendingChoice = null;
  renderDecisionModal();
}

export function selectPendingChoice(cardId, choiceId) {
  uiState.pendingChoice = { cardId, choiceId };
  renderDecisionModal();
}

export async function submitDecision() {
  const pending = uiState.pendingChoice;
  if (!pending) return;
  await callbacks.choose(pending.cardId, pending.choiceId);
}

export function renderDecisionModal() {
  const overlay = $("decisionModalOverlay");
  const card = currentOpenDecisionCard();
  if (!overlay || !card || !uiState.decisionModalVisible || decisionModalBlocked()) {
    overlay?.classList.remove("active");
    return;
  }
  overlay.classList.add("active");
  $("decisionModalTitle").textContent = card.title;
  $("decisionModalMeta").textContent = `${card.type} · ${card.context}`;
  $("decisionModalBody").innerHTML = `
    <p class="decision-question-copy">${escapeHtml(card.description)}</p>
    <div class="decision-choice-list">
      ${card.choices.map(choice => {
        const selected = uiState.pendingChoice?.cardId === card.id && uiState.pendingChoice?.choiceId === choice.id;
        return `
          <button class="decision-choice ${selected ? "selected" : ""}" onclick="selectPendingChoice('${card.id}', '${choice.id}')">
            <strong>${escapeHtml(choice.label)}</strong>
            <span>${escapeHtml(choice.description)}</span>
          </button>
        `;
      }).join("")}
    </div>
  `;
  $("decisionModalFooter").innerHTML = `
    <button onclick="closeDecisionModal()">Review board</button>
    <button class="primary" onclick="submitDecision()" ${uiState.pendingChoice ? "" : "disabled"}>Confirm response</button>
  `;
}
