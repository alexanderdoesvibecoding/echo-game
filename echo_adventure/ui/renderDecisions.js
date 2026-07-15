"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml } from "./html.js";
import {
  currentOpenDecisionCard,
  decisionModalBlocked,
  decisionModalKey,
  decisionProgress,
  nextDecisionIsDue,
  readyToAdvance,
  renderDayClock,
  updateDayClock,
} from "./dayClock.js";

const callbacks = { choose: async () => null };

export function configureDecisionActions(overrides) {
  Object.assign(callbacks, overrides || {});
}

export function renderDecisions() {}

export function renderInlineDecisions() {
  const body = $("inlineDecisionBody");
  if (!body || !uiState.state) return;
  const next = currentOpenDecisionCard();
  const status = readyToAdvance()
    ? "Finishing today's work"
    : uiState.decisionModalVisible || nextDecisionIsDue()
      ? "Workday paused for decision"
      : "Workday in progress";
  if (!body.querySelector("[data-day-clock]")) {
    body.innerHTML = `
      <div class="daily-overview">
        ${renderDayClock(status)}
        <button class="primary decision-open-button hidden" data-action="open-decision-modal">Open next decision</button>
      </div>
    `;
  }
  updateDayClock(body, status);
  body.querySelector(".decision-open-button")?.classList.toggle("hidden", !next);
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
  $("decisionModalBody").innerHTML = `
    <p class="decision-question-copy">${escapeHtml(card.description)}</p>
    <div class="decision-choice-list">
      ${card.choices.map(choice => {
        const selected = uiState.pendingChoice?.cardId === card.id && uiState.pendingChoice?.choiceId === choice.id;
        return `
          <button class="decision-choice ${selected ? "selected" : ""}" onclick="selectPendingChoice('${card.id}', '${choice.id}')">
            ${escapeHtml(choice.label)}
          </button>
        `;
      }).join("")}
    </div>
  `;
  $("decisionModalFooter").innerHTML = `
    <button class="primary" onclick="submitDecision()" ${uiState.pendingChoice ? "" : "disabled"}>Confirm response</button>
  `;
}
