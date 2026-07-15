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

const CHOICE_ICONS = {
  echo: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="2.5"></circle><path d="M7.8 12a4.2 4.2 0 0 1 8.4 0M4.3 12a7.7 7.7 0 0 1 15.4 0M12 14.5V21"></path></svg>`,
  wait: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="13" r="8"></circle><path d="M12 9v4l3 2M9 3h6"></path></svg>`,
  merge: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h3c3 0 3 6 7 6h6M4 18h3c3 0 3-6 7-6M17 9l3 3-3 3"></path></svg>`,
  route: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 18h4c7 0 6-12 12-12M4 6h4c4 0 5 4 7 7M17 3l3 3-3 3"></path></svg>`,
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
};

function choiceIconKey(choice) {
  const text = `${choice?.label || ""} ${choice?.description || ""}`.toLowerCase();
  if (/echo|advice|reshuffle/.test(text)) return "echo";
  if (/\bnest|combine|batch as one|matching work|whole family/.test(text)) return "merge";
  if (/\bwait|postpone|clock out|hold until|hold completions|wait it out/.test(text)) return "wait";
  if (/scrap|retire|tear down|strip and redo|do not reuse|clear old|empty containers/.test(text)) return "discard";
  if (/reinspect|inspect|validate|verify|check|audit|review|reconcile|cycle count|measured criteria|witness/.test(text)) return "inspect";
  if (/repair|service|recalibrat|rebuild|rework|correct|clean|reset|patch|fix|resticker|change the bath|shim/.test(text)) return "repair";
  if (/reroute|route|move|divert|send|swap|switch|reassign|work around|another area|another prep/.test(text)) return "route";
  if (/borrow|replacement|substitute|relief|another shop|sister sample/.test(text)) return "exchange";
  if (/split|separate|independent|only the unaffected|parallel work/.test(text)) return "branch";
  if (/train|pair|staff|operator|worker|lead/.test(text)) return "people";
  if (/archive|file|save|handwrite|cached cop|document|manual fallback/.test(text)) return "document";
  if (/material|stock|parts from|consume|fixture|rack|cart|container/.test(text)) return "material";
  if (/search|chase|find/.test(text)) return "search";
  if (/stop|freeze|isolate|quarantin|close the whole|keep.*quarantined/.test(text)) return "stop";
  if (/release|reopen|resume|restart|continue|let them go|return to normal/.test(text)) return "release";
  if (/critical|protect|reserve|ration|due work|low-risk|safe moves|keep it local/.test(text)) return "protect";
  if (/pull.*forward|expedite|shortcut|force|run.*immediately|open a second lane|preheat|off-peak/.test(text)) return "accelerate";
  return "adjust";
}

function renderChoiceIcon(choice) {
  const icon = CHOICE_ICONS[choiceIconKey(choice)] || CHOICE_ICONS.adjust;
  return `<span class="choice-icon" aria-hidden="true">${icon}</span>`;
}

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
    : "Workday in progress";
  body.innerHTML = `
    <div class="daily-overview">
      ${renderDayClock(status, Boolean(next))}
      ${next ? `<button class="primary decision-open-button" data-action="open-decision-modal">Open next decision</button>` : ""}
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
  $("decisionModalBody").innerHTML = `
    <p class="decision-question-copy">${escapeHtml(card.description)}</p>
    <div class="decision-choice-list">
      ${card.choices.map(choice => {
        const selected = uiState.pendingChoice?.cardId === card.id && uiState.pendingChoice?.choiceId === choice.id;
        return `
          <button class="decision-choice ${selected ? "selected" : ""}" onclick="selectPendingChoice('${card.id}', '${choice.id}')">
            ${renderChoiceIcon(choice)}
            <span class="decision-choice-label">${escapeHtml(choice.label)}</span>
          </button>
        `;
      }).join("")}
    </div>
  `;
  $("decisionModalFooter").innerHTML = `
    <button class="primary" onclick="submitDecision()" ${uiState.pendingChoice ? "" : "disabled"}>Confirm response</button>
  `;
}
