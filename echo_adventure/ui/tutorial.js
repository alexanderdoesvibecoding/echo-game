/** First-run tutorial progression and target highlighting. */

"use strict";

import { $ } from "./html.js";
import { uiState } from "./state.js";

const TUTORIAL_STEPS = [
  {
    targetId: "summarySection",
    title: "Submarine Puzzle",
    copy: "Each blank section is an unfinished job. Finish a job to build that part of the submarine.",
  },
  {
    targetId: "decisionQueueSection",
    title: "Decision Queue",
    copy: "Production questions appear here during the day. Choose an answer for each one.",
  },
  {
    targetId: "dailyDecisionSection",
    title: "ECD Progress",
    copy: "These bars track your ECD and ECHO's ECD. An earlier date is better.",
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
  $("tutorialNextBtn").textContent = uiState.tutorialStep === TUTORIAL_STEPS.length - 1
    ? "Got it"
    : "Next";

  const renderedStep = String(uiState.tutorialStep);
  // Scroll and focus only on step transitions, not on every application render.
  if (overlay.dataset.renderedStep !== renderedStep) {
    overlay.dataset.renderedStep = renderedStep;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    $("tutorialNextBtn").focus();
  }
}
