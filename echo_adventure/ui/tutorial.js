/** First-run tutorial progression and target highlighting. */

"use strict";

import { $ } from "./html.js";
import { uiState } from "./state.js";

const TUTORIAL_CARD_GAP = 12;
const TUTORIAL_VIEWPORT_MARGIN = 12;
const TUTORIAL_STEPS = [
  {
    targetId: "summarySection",
    placement: "bottom-right",
    title: "Submarine Puzzle",
    copy: "Each blank section is an unfinished job. Finish a job to build that part of the submarine.",
  },
  {
    targetId: "decisionQueueSection",
    placement: "bottom-left",
    title: "Decision Queue",
    copy: "Production questions appear here during the day. Choose an answer for each one.",
  },
  {
    targetId: "dailyDecisionSection",
    placement: "bottom-right",
    title: "ECD Progress",
    copy: "These bars track your ECD and ECHO's ECD.",
  },
];

const callbacks = {
  renderDecisionQueue: () => {},
  renderDevTools: () => {},
};

/** Override tutorial callbacks for application wiring or tests. */
export function configureTutorial(overrides) {
  Object.assign(callbacks, overrides || {});
}

/** Report whether the tutorial overlay is currently active. */
export function tutorialVisible() {
  return Number.isInteger(uiState.tutorialStep) && uiState.tutorialStep >= 0;
}

/** Build the local-storage key that identifies the current run. */
function currentRunKey() {
  if (!uiState.state) return null;
  // runCycleId distinguishes consecutive random runs that could theoretically
  // resolve to the same seed.
  return `${uiState.runCycleId}:${uiState.state.seed ?? "run"}`;
}

/** Report whether the tutorial can start in the current UI state. */
function tutorialEligible() {
  return Boolean(
    uiState.state
      && !uiState.state.gameOver
      && Number(uiState.state.day) === 1
  );
}

/** Start or resume the tutorial when the current run is eligible. */
export function startTutorial() {
  const runKey = currentRunKey();
  if (!tutorialEligible() || !runKey || uiState.tutorialCompletedRunKey === runKey) {
    return false;
  }
  // Completion is tracked per browser run rather than globally so each new game
  // can introduce the interface again.
  uiState.tutorialStep = 0;
  renderTutorial();
  notifyTutorialChange();
  return true;
}

/** Clear tutorial state after a new run starts. */
export function resetTutorial() {
  clearTutorialHighlight();
  const overlay = $("tutorialOverlay");
  if (overlay) {
    delete overlay.dataset.renderedStep;
  }
  uiState.tutorialStep = -1;
  renderTutorial();
}

/** Move to the next tutorial step or finish the sequence. */
export function advanceTutorial() {
  if (!tutorialVisible()) return;
  if (uiState.tutorialStep < TUTORIAL_STEPS.length - 1) {
    uiState.tutorialStep += 1;
    renderTutorial();
    notifyTutorialChange();
    return;
  }
  finishTutorial();
}

/** Dismiss the tutorial immediately. */
export function skipTutorial() {
  if (tutorialVisible()) finishTutorial();
}

/** Persist completion and remove tutorial highlighting. */
function finishTutorial() {
  uiState.tutorialCompletedRunKey = currentRunKey();
  uiState.tutorialStep = -1;
  renderTutorial();
  notifyTutorialChange();
}

/** Ask the application to resynchronize timing and rendering. */
function notifyTutorialChange() {
  callbacks.renderDecisionQueue();
  callbacks.renderDevTools();
}

/** Remove the active highlight from every target. */
function clearTutorialHighlight() {
  for (const element of document.querySelectorAll(".tutorial-highlight")) {
    element.classList.remove("tutorial-highlight");
  }
}

/** Position the tutorial card at one configured corner of its highlighted target. */
export function positionTutorialCard(target, placement = "bottom-right") {
  const card = $("tutorialCard");
  if (!target || !card || typeof target.getBoundingClientRect !== "function") return;

  const targetRect = target.getBoundingClientRect();
  const cardRect = card.getBoundingClientRect();
  const viewportWidth = Number(globalThis.window?.innerWidth)
    || document.documentElement.clientWidth;
  const viewportHeight = Number(globalThis.window?.innerHeight)
    || document.documentElement.clientHeight;
  const cardWidth = Number(cardRect.width) || Number(card.offsetWidth) || 0;
  const cardHeight = Number(cardRect.height) || Number(card.offsetHeight) || 0;
  const targetLeft = Number(targetRect.left) || 0;
  const targetTop = Number(targetRect.top) || 0;
  const targetWidth = Number(targetRect.width) || 0;
  const targetHeight = Number(targetRect.height) || 0;
  const targetRight = Number.isFinite(targetRect.right)
    ? targetRect.right
    : targetLeft + targetWidth;
  const targetBottom = Number.isFinite(targetRect.bottom)
    ? targetRect.bottom
    : targetTop + targetHeight;

  // Each step selects a deliberate corner while shared clamping ensures that
  // edge targets never push the tutorial actions off-screen.
  const maxLeft = Math.max(
    TUTORIAL_VIEWPORT_MARGIN,
    viewportWidth - cardWidth - TUTORIAL_VIEWPORT_MARGIN,
  );
  const maxTop = Math.max(
    TUTORIAL_VIEWPORT_MARGIN,
    viewportHeight - cardHeight - TUTORIAL_VIEWPORT_MARGIN,
  );
  const alignLeft = placement.endsWith("-left");
  const placeAbove = placement.startsWith("top-");
  const preferredLeft = alignLeft ? targetLeft : targetRight - cardWidth;
  const preferredTop = placeAbove
    ? targetTop - cardHeight - TUTORIAL_CARD_GAP
    : targetBottom + TUTORIAL_CARD_GAP;
  const left = Math.min(
    maxLeft,
    Math.max(TUTORIAL_VIEWPORT_MARGIN, preferredLeft),
  );
  const top = Math.min(
    maxTop,
    Math.max(TUTORIAL_VIEWPORT_MARGIN, preferredTop),
  );

  card.dataset.placement = placement;
  card.style.left = `${Math.round(left)}px`;
  card.style.top = `${Math.round(top)}px`;
}

/** Reposition the active tutorial card after viewport or target movement. */
function repositionActiveTutorialCard() {
  if (!tutorialVisible()) return;
  const step = TUTORIAL_STEPS[uiState.tutorialStep];
  positionTutorialCard(step ? $(step.targetId) : null, step?.placement);
}

/** Render the active tutorial step and its highlighted target. */
export function renderTutorial() {
  const overlay = $("tutorialOverlay");
  if (!overlay) return;

  clearTutorialHighlight();
  // The welcome overlay owns the screen first; tutorial state may be prepared
  // but remains visually inactive until the welcome closes.
  const active = tutorialVisible() && tutorialEligible() && !uiState.welcomeModalVisible;
  overlay.classList.toggle("active", active);
  overlay.setAttribute("aria-hidden", active ? "false" : "true");
  if (!active) return;

  const step = TUTORIAL_STEPS[uiState.tutorialStep];
  const target = step ? $(step.targetId) : null;
  // Missing markup should finish gracefully rather than trapping the player in
  // a blocking tutorial overlay.
  if (!step || !target) {
    finishTutorial();
    return;
  }

  target.classList.add("tutorial-highlight");
  $("tutorialStepLabel").textContent = `${uiState.tutorialStep + 1} of ${TUTORIAL_STEPS.length}`;
  $("tutorialTitle").textContent = step.title;
  $("tutorialDescription").textContent = step.copy;
  const isFinalStep = uiState.tutorialStep === TUTORIAL_STEPS.length - 1;
  $("tutorialSkipBtn").classList.toggle("hidden", isFinalStep);
  $("tutorialNextBtn").textContent = isFinalStep
    ? "Got it"
    : "Next";

  const renderedStep = String(uiState.tutorialStep);
  // Scroll and focus only on step transitions, not on every application render.
  if (overlay.dataset.renderedStep !== renderedStep) {
    overlay.dataset.renderedStep = renderedStep;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    $("tutorialNextBtn").focus();
  }
  positionTutorialCard(target, step.placement);
}

// Fixed positioning follows the highlighted element while smooth scrolling and
// viewport changes move it beneath the tutorial overlay.
globalThis.window?.addEventListener?.("scroll", repositionActiveTutorialCard, true);
globalThis.window?.addEventListener?.("resize", repositionActiveTutorialCard);
