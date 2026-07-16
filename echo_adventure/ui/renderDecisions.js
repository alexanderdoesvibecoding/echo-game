"use strict";

import { uiState } from "./state.js";
import { $, escapeHtml } from "./html.js";
import {
  currentOpenDecisionCard,
  decisionInteractionBlocked,
  decisionProgress,
  nextDecisionIsDue,
  renderDayClock,
  updateDayClock,
} from "./dayClock.js";

const callbacks = { choose: async () => null };

export function configureDecisionActions(overrides) {
  Object.assign(callbacks, overrides || {});
}

export function renderInlineDecisions() {
  const body = $("inlineDecisionBody");
  if (!body || !uiState.state) return;

  if (!body.querySelector("[data-day-clock]")) {
    body.innerHTML = `
      <div class="daily-overview">
        ${renderDayClock()}
      </div>
    `;
  }

  updateDayClock(body);
}

export function selectPendingChoice(cardId, choiceId) {
  uiState.pendingChoice = { cardId, choiceId };
  renderDecisionQueue();
  const selectedButton = Array.from(document.querySelectorAll("#decisionQueueBody [data-choice-id]"))
    .find(button => button.dataset.choiceId === choiceId);
  selectedButton?.focus();
}

export async function submitDecision() {
  const pending = uiState.pendingChoice;
  if (!pending) return;
  await callbacks.choose(pending.cardId, pending.choiceId);
}

export function renderDecisionQueue() {
  const section = $("decisionQueueSection");
  const body = $("decisionQueueBody");
  if (!section || !body || !uiState.state) return;

  const progress = decisionProgress();
  const blocked = decisionInteractionBlocked();
  const due = nextDecisionIsDue();
  const card = due && !blocked ? currentOpenDecisionCard() : null;
  const pendingChoiceId = card && uiState.pendingChoice?.cardId === card.id
    ? uiState.pendingChoice.choiceId
    : "";
  const mode = card ? "active" : blocked ? "blocked" : "idle";
  const renderKey = JSON.stringify([
    uiState.runCycleId,
    uiState.state.seed,
    uiState.state.day,
    mode,
    progress.completed,
    progress.total,
    card?.id || "",
    pendingChoiceId,
  ]);

  section.classList.toggle("is-empty", !card);
  if (body.dataset.renderKey === renderKey) return;
  body.dataset.renderKey = renderKey;

  if (!card) {
    body.innerHTML = `<div class="decision-queue-empty">No decision currently requires your attention.</div>`;

    return;
  }

  body.innerHTML = `
    <article class="decision-queue-card">
      <div>
        <h3>${escapeHtml(card.title)}</h3>
        <p class="decision-question-copy">${escapeHtml(card.description)}</p>
      </div>

      <div class="decision-choice-list">
        ${card.choices.map(choice => {
          const selected =
            uiState.pendingChoice?.cardId === card.id &&
            uiState.pendingChoice?.choiceId === choice.id;

          return `
            <button
              class="decision-choice ${selected ? "selected" : ""}"
              data-choice-id="${escapeHtml(choice.id)}"
              onclick="selectPendingChoice('${card.id}', '${choice.id}')"
            >
              ${escapeHtml(choice.label)}
            </button>
          `;
        }).join("")}
      </div>

      <div class="decision-queue-actions">
        <button
          class="primary"
          onclick="submitDecision()"
          ${uiState.pendingChoice ? "" : "disabled"}
        >
          Confirm response
        </button>
      </div>
    </article>
  `;
}
