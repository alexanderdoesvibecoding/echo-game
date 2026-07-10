"use strict";

import { uiState } from "./state.js";
import { escapeHtml, $ } from "./html.js";
import {
  currentOpenDecisionCard,
  decisionModalBlocked,
  decisionModalKey,
  decisionProgress,
  nextDecisionIsDue,
  readyToAdvance,
  renderDayClock,
} from "./dayClock.js";

const callbacks = {
  choose: async () => null,
};

export function configureDecisionActions(overrides) {
  Object.assign(callbacks, overrides || {});
}

const DECISION_ICON_CATALOG = {
  weather: {
    label: "Weather risk",
    tone: "blue",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-fill" d="M21 33a10 10 0 0 1 18-6 8 8 0 0 1 12 7c0 5-4 9-9 9H22a8 8 0 0 1-1-16z"></path>
        <path class="icon-line" d="M22 47l-3 6M33 47l-3 6M44 47l-3 6"></path>
      </svg>
    `,
  },
  power: {
    label: "Facility outage",
    tone: "violet",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-fill" d="M25 9h15l-6 18h13L25 55l5-21H18z"></path>
        <path class="icon-line" d="M42 14l5-5M47 21h8M39 8l2-6"></path>
      </svg>
    `,
  },
  crew: {
    label: "Crew pressure",
    tone: "amber",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <circle class="icon-fill" cx="23" cy="24" r="7"></circle>
        <circle class="icon-fill" cx="42" cy="25" r="6"></circle>
        <path class="icon-line" d="M12 50c2-9 8-14 18-14s16 5 20 14M36 43c2-4 6-6 12-6 5 0 9 3 11 8"></path>
      </svg>
    `,
  },
  machine: {
    label: "Machine down",
    tone: "red",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <rect class="icon-fill" x="15" y="28" width="34" height="19" rx="4"></rect>
        <path class="icon-line" d="M21 28v-8h22v8M22 47v7M42 47v7M27 36h10"></path>
        <circle class="icon-alert-fill" cx="45" cy="18" r="8"></circle>
      </svg>
    `,
  },
  tooling: {
    label: "Tooling issue",
    tone: "red",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-fill" d="M18 45l20-20 8 8-20 20H18z"></path>
        <path class="icon-line" d="M39 24l7-7 5 5-7 7M17 20l8 8M25 20l-8 8M47 43l5 5M52 43l-5 5"></path>
      </svg>
    `,
  },
  material: {
    label: "Material problem",
    tone: "amber",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-fill" d="M15 25l17-9 17 9v20L32 55 15 45z"></path>
        <path class="icon-line" d="M15 25l17 10 17-10M32 35v20M24 20l17 10"></path>
        <path class="icon-alert" d="M49 13v13M49 33v1"></path>
      </svg>
    `,
  },
  logistics: {
    label: "Logistics backlog",
    tone: "amber",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-fill" d="M12 35h33v11H12zM45 38h7l5 5v3H45z"></path>
        <circle class="icon-line-fill" cx="22" cy="49" r="4"></circle>
        <circle class="icon-line-fill" cx="49" cy="49" r="4"></circle>
        <path class="icon-line" d="M15 24h27M19 18h19M23 12h11"></path>
      </svg>
    `,
  },
  quality: {
    label: "Quality rework",
    tone: "green",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <rect class="icon-fill" x="17" y="12" width="30" height="40" rx="5"></rect>
        <path class="icon-line" d="M24 24h17M24 34h10M25 44l5 5 11-14"></path>
        <path class="icon-alert" d="M48 15l5-5M51 23h8"></path>
      </svg>
    `,
  },
  priority: {
    label: "Priority change",
    tone: "red",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-fill" d="M21 12h24l-6 10 6 10H21z"></path>
        <path class="icon-line" d="M21 12v42M28 44h14M35 50h7M18 54h28"></path>
      </svg>
    `,
  },
  inspection: {
    label: "Inspection delay",
    tone: "blue",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <circle class="icon-fill" cx="28" cy="26" r="14"></circle>
        <path class="icon-line" d="M39 37l13 13M23 24h10M23 31h7"></path>
        <path class="icon-alert" d="M48 12v12M48 31v1"></path>
      </svg>
    `,
  },
  engineering: {
    label: "Engineering hold",
    tone: "violet",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-fill" d="M17 14h30v36H17z"></path>
        <path class="icon-line" d="M23 24h18M23 32h10M38 43v-7a6 6 0 0 1 12 0v7M35 43h18v10H35z"></path>
      </svg>
    `,
  },
  urgent: {
    label: "Urgent work",
    tone: "red",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-fill" d="M24 12h16v16h12v14H40v12H24V42H12V28h12z"></path>
        <path class="icon-line" d="M46 12l6-5M50 22h9M39 8l1-7"></path>
      </svg>
    `,
  },
  bottleneck: {
    label: "Bottleneck overload",
    tone: "amber",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-fill" d="M15 13h34L37 30v20l-10 5V30z"></path>
        <path class="icon-line" d="M13 22h18M13 30h14M13 38h11M40 40h12M40 47h9"></path>
      </svg>
    `,
  },
  critical: {
    label: "Critical path",
    tone: "red",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-line" d="M12 43c10-24 25 4 40-20"></path>
        <circle class="icon-fill" cx="14" cy="43" r="6"></circle>
        <circle class="icon-fill" cx="32" cy="33" r="6"></circle>
        <circle class="icon-alert-fill" cx="51" cy="23" r="7"></circle>
        <path class="icon-alert" d="M51 18v7M51 30v1"></path>
      </svg>
    `,
  },
  idle: {
    label: "Idle capacity",
    tone: "blue",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <rect class="icon-fill" x="15" y="28" width="34" height="16" rx="4"></rect>
        <path class="icon-line" d="M23 44v7M41 44v7M23 20h18M29 14h12M35 8h6"></path>
        <circle class="icon-alert-fill" cx="50" cy="18" r="4"></circle>
      </svg>
    `,
  },
  routing: {
    label: "Alternate routing",
    tone: "green",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-line" d="M14 47h10c17 0 16-28 31-28M14 17h11c9 0 12 9 17 16"></path>
        <path class="icon-fill" d="M52 13l8 6-8 6zM52 39l8 6-8 6z"></path>
        <circle class="icon-fill" cx="14" cy="47" r="5"></circle>
      </svg>
    `,
  },
  queue: {
    label: "Queue congestion",
    tone: "amber",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <rect class="icon-fill" x="14" y="16" width="36" height="8" rx="3"></rect>
        <rect class="icon-fill" x="14" y="29" width="30" height="8" rx="3"></rect>
        <rect class="icon-fill" x="14" y="42" width="22" height="8" rx="3"></rect>
        <path class="icon-alert" d="M51 29v14M51 50v1"></path>
      </svg>
    `,
  },
  readiness: {
    label: "Completion readiness",
    tone: "green",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-fill" d="M16 38c0-12 15-16 31-8 7 4 7 12 0 16-16 8-31 4-31-8z"></path>
        <path class="icon-line" d="M24 38l5 5 11-14M46 34h5M46 42h5"></path>
      </svg>
    `,
  },
  strategy: {
    label: "Strategic priority",
    tone: "violet",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <circle class="icon-line-fill" cx="32" cy="32" r="18"></circle>
        <circle class="icon-bg" cx="32" cy="32" r="10"></circle>
        <circle class="icon-fill" cx="32" cy="32" r="4"></circle>
        <path class="icon-line" d="M32 8v8M32 48v8M8 32h8M48 32h8"></path>
      </svg>
    `,
  },
  unexpected: {
    label: "Unexpected job",
    tone: "red",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <rect class="icon-fill" x="16" y="18" width="28" height="34" rx="5"></rect>
        <path class="icon-line" d="M23 28h14M23 37h10M47 12v12M41 18h12"></path>
      </svg>
    `,
  },
  echo: {
    label: "ECHO recommendation",
    tone: "teal",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <circle class="icon-line-fill" cx="32" cy="32" r="8"></circle>
        <path class="icon-line" d="M18 32a14 14 0 0 1 28 0M10 32a22 22 0 0 1 44 0M32 40v12"></path>
        <path class="icon-fill" d="M28 52h8l-4 6z"></path>
      </svg>
    `,
  },
  default: {
    label: "Decision",
    tone: "teal",
    svg: `
      <svg class="decision-icon-svg" viewBox="0 0 64 64" aria-hidden="true">
        <circle class="icon-bg" cx="32" cy="32" r="29"></circle>
        <path class="icon-fill" d="M18 15h28v34H18z"></path>
        <path class="icon-line" d="M25 25h14M25 33h10M25 41h16"></path>
      </svg>
    `,
  },
};

const CHOICE_ICON_CATALOG = {
  protect: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z"></path><path d="M8 12l3 3 5-6"></path></svg>`,
  route: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 18h4c8 0 7-12 14-12"></path><path d="M18 3l4 3-4 3"></path><path d="M4 6h4c4 0 5 4 7 7"></path></svg>`,
  wrench: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4a6 6 0 0 0 6 6L9 21l-6-6 11-11z"></path></svg>`,
  queue: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 6h14M5 12h11M5 18h8"></path></svg>`,
  split: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h5c5 0 5-6 11-6"></path><path d="M16 3l4 3-4 3"></path><path d="M9 12c5 0 5 6 11 6"></path><path d="M16 15l4 3-4 3"></path></svg>`,
  calendar: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="2"></rect><path d="M8 3v4M16 3v4M4 10h16M8 14h4"></path></svg>`,
  defer: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6h12M6 11h9M6 16h5"></path><path d="M16 14l3 3-3 3"></path></svg>`,
  bolt: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 2L4 14h7l-1 8 10-13h-7z"></path></svg>`,
  echo: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"></circle><path d="M6 12a6 6 0 0 1 12 0M3 12a9 9 0 0 1 18 0"></path></svg>`,
  flag: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 21V4h12l-3 5 3 5H6"></path></svg>`,
  backlog: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v14H4z"></path><path d="M4 14h5l2 3h2l2-3h5"></path></svg>`,
  wait: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"></circle><path d="M12 7v5l4 2"></path></svg>`,
  note: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4h12v16H6z"></path><path d="M9 9h6M9 13h6M9 17h3"></path></svg>`,
};

function decisionIconForCard(card) {
  const text = `${card?.type || ""} ${card?.title || ""} ${card?.description || ""}`.toLowerCase();
  let key = "default";
  if (text.includes("echo")) key = "echo";
  else if (text.includes("weather") || text.includes("rain") || text.includes("storm")) key = "weather";
  else if (text.includes("facility") || text.includes("outage")) key = "power";
  else if (text.includes("crew")) key = "crew";
  else if (text.includes("tooling") || text.includes("tool")) key = "tooling";
  else if (text.includes("machine") || text.includes("workcenter down") || text.includes("equipment")) key = "machine";
  else if (text.includes("logistics") || text.includes("backlog")) key = "logistics";
  else if (text.includes("material") || text.includes("supplier")) key = "material";
  else if (text.includes("quality") || text.includes("rework")) key = "quality";
  else if (text.includes("priority") || text.includes("handoff")) key = "priority";
  else if (text.includes("inspection") || text.includes("certification") || text.includes("audit")) key = "inspection";
  else if (text.includes("engineering")) key = "engineering";
  else if (text.includes("urgent")) key = "urgent";
  else if (text.includes("unexpected") || text.includes("new job")) key = "unexpected";
  else if (text.includes("bottleneck")) key = "bottleneck";
  else if (text.includes("critical path") || text.includes("at risk")) key = "critical";
  else if (text.includes("idle")) key = "idle";
  else if (text.includes("routing") || text.includes("route")) key = "routing";
  else if (text.includes("queue") || text.includes("congestion")) key = "queue";
  else if (text.includes("completion")) key = "readiness";
  else if (text.includes("strategic")) key = "strategy";
  return DECISION_ICON_CATALOG[key] || DECISION_ICON_CATALOG.default;
}

function renderDecisionIcon(card, size = "medium") {
  const icon = decisionIconForCard(card);
  return `
    <div class="decision-icon decision-icon-${size} tone-${icon.tone}" role="img" aria-label="${escapeHtml(icon.label)}" title="${escapeHtml(icon.label)}">
      ${icon.svg}
    </div>
  `;
}

function choiceIconKey(choice) {
  const text = `${choice?.label || ""} ${choice?.description || ""}`.toLowerCase();
  if (text.includes("echo")) return "echo";
  if (text.includes("protect") || text.includes("hold a slot")) return "protect";
  if (text.includes("reroute") || text.includes("route") || text.includes("around")) return "route";
  if (text.includes("fix") || text.includes("shorten") || text.includes("expedite")) return "wrench";
  if (text.includes("queue") || text.includes("resequence") || text.includes("change")) return "queue";
  if (text.includes("split")) return "split";
  if (text.includes("due date") || text.includes("dates first")) return "calendar";
  if (text.includes("push") || text.includes("defer") || text.includes("back")) return "defer";
  if (text.includes("preempt") || text.includes("bump") || text.includes("interrupt")) return "bolt";
  if (text.includes("front") || text.includes("prioritize") || text.includes("pull")) return "flag";
  if (text.includes("backlog") || text.includes("back of queue")) return "backlog";
  if (text.includes("wait") || text.includes("ride") || text.includes("keep") || text.includes("hold")) return "wait";
  return "note";
}

function renderChoiceIcon(choice) {
  const key = choiceIconKey(choice);
  const svg = CHOICE_ICON_CATALOG[key] || CHOICE_ICON_CATALOG.note;
  return `<span class="choice-icon" aria-hidden="true">${svg}</span>`;
}

export function openDecisionModal() {
  const nextCard = currentOpenDecisionCard();
  if (!nextCard) return;
  if (!nextCard.choices.some(choice => choice.id === uiState.pendingChoice)) {
    uiState.pendingChoice = null;
  }
  uiState.decisionModalDismissedKey = null;
  uiState.decisionModalVisible = true;
  renderDecisionModal();
}

export function closeDecisionModal() {
  const nextCard = currentOpenDecisionCard();
  if (nextCard) {
    uiState.decisionModalDismissedKey = decisionModalKey(nextCard);
  }
  uiState.decisionModalVisible = false;
  renderInlineDecisions();
  renderDecisionModal();
}

export async function submitDecision(cardId) {
  if (!uiState.pendingChoice) return;
  const choiceId = uiState.pendingChoice;
  await callbacks.choose(cardId, choiceId);
}

export function selectPendingChoice(choiceId) {
  uiState.pendingChoice = choiceId;
  renderInlineDecisions();
  renderDecisionModal();
}

export function renderDecisions() {
  const advanceBtn = $("advanceBtn");
  if (advanceBtn) advanceBtn.disabled = uiState.state.gameOver || !readyToAdvance();
}

export function renderInlineDecisions() {
  const body = $("inlineDecisionBody");
  if (!body) return;

  if (uiState.modalVisible && uiState.pendingAdvanceState) {
    body.innerHTML = "";
    return;
  }

  if (!uiState.state || uiState.state.gameOver) {
    body.innerHTML = `
      <div class="reveal-panel">
        <h3>Campaign decisions are complete.</h3>
        <div class="subtle">Review the final operational comparison at the top of the page.</div>
      </div>
    `;
    return;
  }

  const progressState = decisionProgress();
  const nextCard = currentOpenDecisionCard();

  if (nextCard) {
    if (!nextCard.choices.some(choice => choice.id === uiState.pendingChoice)) {
      uiState.pendingChoice = null;
    }
    const decisionDue = nextDecisionIsDue();
    const title = decisionDue ? "Decision Event" : "Schedule In Motion";
    const badge = decisionDue ? `<span class="badge warn">Paused</span>` : `<span class="badge info">Rolling</span>`;
    const status = decisionDue
      ? "Paused for decision"
      : "Workday Progress";
    const detail = decisionDue
      ? `${escapeHtml(nextCard.title)}`
      : "Work is moving through the schedule.";
    body.innerHTML = `
      <div class="reveal-panel decision-status-panel">
        <div class="decision-title">
          <div>
            <h3>${title}</h3>
            <div class="subtle">${detail}</div>
          </div>
          ${badge}
        </div>
        ${renderDayClock(status, decisionDue)}
        ${decisionDue ? `
          <div class="inline-decision-actions">
            <button type="button" class="primary" data-action="open-decision-modal">Respond</button>
          </div>
        ` : ""}
      </div>
    `;
    return;
  }

  const ending = uiState.dayCycleProgress >= 100 || uiState.dayCycleAdvancing;
  body.innerHTML = `
    <div class="reveal-panel decision-status-panel">
      <div class="decision-title">
        <div>
          <h3>${ending ? "Workday Complete" : "Schedule In Motion"}</h3>
          <div class="subtle">Work is moving through the schedule.</div>
        </div>
        <span class="badge good">${ending ? "Complete" : "Rolling"}</span>
      </div>
      ${renderDayClock("Workday Progress", ending)}
    </div>
  `;
}

export function renderDecisionModal() {
  const overlay = $("decisionModalOverlay");
  const title = $("decisionModalTitle");
  const meta = $("decisionModalMeta");
  const body = $("decisionModalBody");
  const footer = $("decisionModalFooter");
  if (!overlay || !title || !meta || !body || !footer) return;

  const nextCard = currentOpenDecisionCard();
  const decisionDue = nextDecisionIsDue();
  if (!nextCard || !decisionDue || decisionModalBlocked()) {
    overlay.classList.remove("active");
    uiState.decisionModalVisible = false;
    if (!nextCard) {
      uiState.decisionModalVisible = false;
      uiState.decisionModalDismissedKey = null;
    }
    return;
  }

  if (!nextCard.choices.some(choice => choice.id === uiState.pendingChoice)) {
    uiState.pendingChoice = null;
  }

  const cardKey = decisionModalKey(nextCard);
  if (!uiState.decisionModalVisible && uiState.decisionModalDismissedKey !== cardKey) {
    uiState.decisionModalVisible = true;
  }

  if (!uiState.decisionModalVisible) {
    overlay.classList.remove("active");
    return;
  }

  title.textContent = "Decision Event";
  meta.textContent = uiState.state.currentDate || "";
  body.innerHTML = `
    <div class="decision-prompt">
      <div class="decision-title decision-title-with-icon decision-prompt-head">
        ${renderDecisionIcon(nextCard, "large")}
        <div class="decision-title-copy">
          <h2>${escapeHtml(nextCard.title)}</h2>
          <div class="subtle">${escapeHtml(nextCard.type)} | ${escapeHtml(decisionUrgencyLabel(nextCard.severity))}</div>
        </div>
        <span class="badge warn">Open</span>
      </div>
      <p>${escapeHtml(nextCard.description)}</p>
      ${nextCard.context ? `<div class="subtle">Affected area: ${escapeHtml(nextCard.context)}</div>` : ""}
    </div>
    <div class="decision-choices decision-modal-choices">
      ${nextCard.choices.map(choice => `
        <button class="choice ${uiState.pendingChoice === choice.id ? "selected" : ""}" onclick="selectPendingChoice('${choice.id}')">
          <span class="choice-content">
            ${renderChoiceIcon(choice)}
            <span>
              <strong>${escapeHtml(choice.label)}</strong>
              <small>${escapeHtml(choice.description)}</small>
            </span>
          </span>
        </button>
      `).join("")}
    </div>
  `;
  footer.innerHTML = `
    <button ${!uiState.pendingChoice ? "disabled" : ""} class="primary" onclick="submitDecision('${nextCard.id}')">Submit</button>
  `;
  overlay.classList.add("active");
}

function decisionUrgencyLabel(severity) {
  if (severity >= 5) return "Severe urgency";
  if (severity >= 4) return "High urgency";
  if (severity >= 3) return "Elevated urgency";
  if (severity >= 2) return "Moderate urgency";
  return "Low urgency";
}
