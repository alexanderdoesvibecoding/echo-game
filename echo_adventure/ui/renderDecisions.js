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

const CHOICE_ICONS = {
  echo: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="2.5"></circle><path d="M7.8 12a4.2 4.2 0 0 1 8.4 0M4.3 12a7.7 7.7 0 0 1 15.4 0M12 14.5V21"></path></svg>`,
  wait: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="13" r="8"></circle><path d="M12 9v4l3 2M9 3h6"></path></svg>`,
  merge: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h3c3 0 3 7 7 7h6M4 18h3c3 0 3-5 7-5M17 10l3 3-3 3"></path></svg>`,
  route: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="18" r="2.5"></circle><circle cx="18" cy="6" r="2.5"></circle><path d="M7.5 18h2c5.5 0 1.5-12 6-12"></path></svg>`,
  protect: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6zM8.5 12l2.2 2.2 4.8-5"></path></svg>`,
  repair: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 5a5 5 0 0 0 5 5L9 20l-5-5L14 5zM6 15l3 3"></path></svg>`,
  inspect: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="M15.5 15.5L21 21M8 10.5l1.7 1.7 3.5-4"></path></svg>`,
  accelerate: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 2L5 13h6l-1 9 9-13h-6z"></path></svg>`,
  release: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4v16M5 12h12M14 8l4 4-4 4"></path></svg>`,
  stop: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="3"></rect><path d="M9 9h6v6H9z"></path></svg>`,
  exchange: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8h15M16 5l3 3-3 3M20 16H5M8 13l-3 3 3 3"></path></svg>`,
  branch: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h5c4 0 4-6 9-6M10 12c4 0 4 6 9 6M16 3l3 3-3 3M16 15l3 3-3 3"></path></svg>`,
  people: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3"></circle><circle cx="17" cy="9" r="2.5"></circle><path d="M3.5 20c.5-4 2.3-6 5.5-6s5 2 5.5 6M14 15c3.5-.7 5.7 1 6.5 4"></path></svg>`,
  document: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h9l4 4v14H6zM15 3v5h4M9 12h7M9 16h5"></path></svg>`,
  material: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8l8-4 8 4v9l-8 4-8-4zM4 8l8 4 8-4M12 12v9"></path></svg>`,
  discard: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"></path></svg>`,
  search: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="M15.5 15.5L21 21M8 10.5h5"></path></svg>`,
  adjust: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 17h16M9 4v6M15 14v6"></path></svg>`,
  gauge: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 17a8 8 0 0 1 16 0M12 17l4-6M7 20h10"></path><circle cx="12" cy="17" r="1"></circle></svg>`,
  study: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="3" width="14" height="18" rx="2"></rect><path d="M8 16v-3M12 16V9M16 16v-5M8 6h8"></path></svg>`,
  calibrate: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle><path d="M12 2v4M12 18v4M2 12h4M18 12h4"></path></svg>`,
  inventory: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="8" height="6" rx="1"></rect><rect x="13" y="5" width="8" height="6" rx="1"></rect><rect x="8" y="13" width="8" height="6" rx="1"></rect><path d="M6 8h2M16 8h2M11 16h2"></path></svg>`,
  printer: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 8V3h10v5M7 17H4V9h16v8h-3M7 14h10v7H7z"></path><circle cx="17" cy="11" r="1"></circle></svg>`,
  quality: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="10" r="7"></circle><path d="M8.5 10l2.2 2.2 4.8-5M8 16l-1 5 5-2 5 2-1-5"></path></svg>`,
  tool: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4v7a6 6 0 0 0 12 0V4M6 8h5M13 8h5M12 17v4"></path></svg>`,
  calendar: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="2"></rect><path d="M8 3v4M16 3v4M4 10h16M8 14h3M13 14h3"></path></svg>`,
  monitor: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="13" rx="2"></rect><path d="M6 11h3l2-4 3 7 2-3h2M9 21h6M12 17v4"></path></svg>`,
  flag: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 21V4h12l-3 5 3 5H6"></path></svg>`,
  idea: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 15a7 7 0 1 1 8 0c-1 1-1 2-1 3H9c0-1 0-2-1-3M9 21h6"></path></svg>`,
};

function renderChoiceIcon(iconKey) {
  const icon = CHOICE_ICONS[iconKey] || CHOICE_ICONS.adjust;
  return `<span class="choice-icon" aria-hidden="true">${icon}</span>`;
}

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
              ${renderChoiceIcon(choice.icon)}
              <span class="decision-choice-label">${escapeHtml(choice.label)}</span>
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
