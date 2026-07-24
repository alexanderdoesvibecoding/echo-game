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

export function configureTutorial(overrides) {
  Object.assign(callbacks, overrides || {});
}

export function tutorialVisible() {
  return Number.isInteger(uiState.tutorialStep) && uiState.tutorialStep >= 0;
}

function currentRunKey() {
  if (!uiState.state) return null;
  return `${uiState.runCycleId}:${uiState.state.seed ?? "run"}`;
}

function tutorialEligible() {
  return Boolean(
    uiState.state
      && !uiState.state.gameOver
      && Number(uiState.state.day) === 1
  );
}

export function startTutorial() {
  const runKey = currentRunKey();
  if (!tutorialEligible() || !runKey || uiState.tutorialCompletedRunKey === runKey) {
    return false;
  }
  uiState.tutorialStep = 0;
  renderTutorial();
  notifyTutorialChange();
  return true;
}

export function resetTutorial() {
  clearTutorialHighlight();
  uiState.tutorialStep = -1;
  renderTutorial();
}

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

export function skipTutorial() {
  if (tutorialVisible()) finishTutorial();
}

function finishTutorial() {
  uiState.tutorialCompletedRunKey = currentRunKey();
  uiState.tutorialStep = -1;
  renderTutorial();
  notifyTutorialChange();
}

function notifyTutorialChange() {
  callbacks.renderDecisionQueue();
  callbacks.renderDevTools();
}

function clearTutorialHighlight() {
  for (const element of document.querySelectorAll(".tutorial-highlight")) {
    element.classList.remove("tutorial-highlight");
  }
}

export function renderTutorial() {
  const overlay = $("tutorialOverlay");
  if (!overlay) return;

  clearTutorialHighlight();
  const active = tutorialVisible() && tutorialEligible() && !uiState.welcomeModalVisible;
  overlay.classList.toggle("active", active);
  overlay.setAttribute("aria-hidden", active ? "false" : "true");
  if (!active) return;

  const step = TUTORIAL_STEPS[uiState.tutorialStep];
  const target = step ? $(step.targetId) : null;
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
  if (overlay.dataset.renderedStep !== renderedStep) {
    overlay.dataset.renderedStep = renderedStep;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    $("tutorialNextBtn").focus();
  }
}
