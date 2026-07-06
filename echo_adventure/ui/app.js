"use strict";

import { api } from "./api.js";
import { configureDayClock, readyToAdvance, resetDayCycle, syncDayCycleForState } from "./dayClock.js";
import { $ } from "./html.js";
import {
  closeNewRunModal,
  closeSettingsMenu,
  closeWelcomeModal,
  configureModals,
  initDarkMode,
  openNewRunModal,
  renderNewRunModal,
  renderSettingsMenu,
  renderWelcomeModal,
  toggleDarkMode,
  toggleSettingsMenu,
} from "./modals.js";
import { hideDecisionChartTooltip, renderFinal, showDecisionChartTooltip } from "./renderFinal.js";
import { renderMetrics } from "./renderMetrics.js";
import {
  closeDecisionModal,
  configureDecisionActions,
  openDecisionModal,
  renderDecisionModal,
  renderDecisions,
  renderInlineDecisions,
  selectPendingChoice,
  submitDecision,
} from "./renderDecisions.js";
import { renderSummary, renderSummaryModal } from "./renderSummary.js";
import { uiState } from "./state.js";

function showError(message) {
  const box = $("error");
  if (!message) {
    box.classList.add("hidden");
    box.textContent = "";
    return;
  }
  box.textContent = message;
  box.classList.remove("hidden");
}

function showNewRunError(message) {
  const box = $("newRunError");
  if (!box) return;
  if (!message) {
    box.classList.add("hidden");
    box.textContent = "";
    return;
  }
  box.textContent = message;
  box.classList.remove("hidden");
}

async function loadState() {
  try {
    uiState.state = await api("/api/state");
    showError("");
    render();
  } catch (error) {
    uiState.dayCycleAdvancing = false;
    showError(error.message);
  }
}

async function startNewRun() {
  try {
    uiState.state = await api("/api/new", {
      method: "POST",
      body: JSON.stringify({})
    });
    uiState.runCycleId += 1;
    resetDayCycle();
    uiState.pendingChoice = null;
    uiState.decisionModalVisible = false;
    uiState.decisionModalDismissedKey = null;
    uiState.welcomeModalVisible = true;
    uiState.newRunModalVisible = false;
    showNewRunError("");
    showError("");
    render();
  } catch (error) {
    if (uiState.newRunModalVisible) {
      showNewRunError(error.message);
    } else {
      showError(error.message);
    }
  }
}

async function choose(cardId, choiceId, renderAfter = true) {
  try {
    uiState.state = await api("/api/choice", {
      method: "POST",
      body: JSON.stringify({ cardId, choiceId })
    });
    uiState.pendingChoice = null;
    uiState.decisionModalVisible = false;
    uiState.decisionModalDismissedKey = null;
    showError("");
    if (renderAfter) {
      render();
    }
    return uiState.state;
  } catch (error) {
    showError(error.message);
    return null;
  }
}

async function prepareAdvanceDay() {
  // The button should already be disabled until all decisions are complete,
  // but this guard keeps direct console calls and stale UI state honest.
  if (!readyToAdvance()) {
    uiState.dayCycleAdvancing = false;
    document.getElementById("dailyDecisionSection")?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  try {
    const nextState = await api("/api/advance", { method: "POST", body: "{}" });
    showError("");
    uiState.pendingAdvanceState = nextState;
    if (nextState.finalReveal) {
      uiState.state = nextState;
      uiState.pendingAdvanceState = null;
      uiState.modalVisible = false;
    } else {
      uiState.modalVisible = true;
    }
    render();
  } catch (error) {
    showError(error.message);
  }
}

function commitAdvanceDay() {
  if (!uiState.pendingAdvanceState) {
    return;
  }
  uiState.state = uiState.pendingAdvanceState;
  uiState.pendingAdvanceState = null;
  uiState.modalVisible = false;
  render();
}

function render() {
  if (!uiState.state) return;
  syncDayCycleForState();
  $("dayBadge").textContent = `Day ${uiState.state.day}`;
  $("projectedText").textContent = `Projected completion: ${uiState.state.projectedCompletion}`;
  renderMainSectionVisibility();

  renderMetrics();
  renderDecisions();
  renderInlineDecisions();
  renderSummary();
  renderSummaryModal();
  renderFinal();
  renderWelcomeModal();
  renderNewRunModal();
  renderDecisionModal();
  renderSettingsMenu();
}

function renderMainSectionVisibility() {
  const gameOver = Boolean(uiState.state.gameOver);
  $("projectPositionSection").classList.toggle("hidden", gameOver);
  $("dailyDecisionSection").classList.toggle("hidden", gameOver);
}

configureDayClock({
  render,
  renderInlineDecisions,
  prepareAdvanceDay,
  showError,
});
configureDecisionActions({ choose });
configureModals({ renderDecisionModal, showNewRunError });

$("settingsMenuBtn").addEventListener("click", toggleSettingsMenu);
$("openNewRunModalBtn").addEventListener("click", openNewRunModal);
$("themeMenuBtn").addEventListener("click", toggleDarkMode);

document.addEventListener("click", (e) => {
  const welcomeOverlay = document.getElementById("welcomeModalOverlay");
  const newRunOverlay = document.getElementById("newRunModalOverlay");
  const decisionOverlay = document.getElementById("decisionModalOverlay");
  const settingsWrap = document.querySelector(".settings-wrap");
  if (settingsWrap && !settingsWrap.contains(e.target)) {
    closeSettingsMenu();
  }
  if (e.target && e.target.id === "closeWelcomeBtn") {
    closeWelcomeModal();
  }
  if (e.target && e.target.id === "closeNewRunModalBtn") {
    closeNewRunModal();
  }
  if (e.target && e.target.id === "closeDecisionModalBtn") {
    closeDecisionModal();
  }
  if (welcomeOverlay && e.target === welcomeOverlay) {
    closeWelcomeModal();
  }
  if (newRunOverlay && e.target === newRunOverlay) {
    closeNewRunModal();
  }
  if (decisionOverlay && e.target === decisionOverlay) {
    closeDecisionModal();
  }
});

Object.assign(window, {
  closeDecisionModal,
  closeNewRunModal,
  closeWelcomeModal,
  commitAdvanceDay,
  hideDecisionChartTooltip,
  openDecisionModal,
  selectPendingChoice,
  showDecisionChartTooltip,
  startNewRun,
  submitDecision,
});

initDarkMode();
uiState.welcomeModalVisible = true;
renderWelcomeModal();
loadState();
