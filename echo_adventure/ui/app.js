"use strict";

import { api } from "./api.js";
import { configureDayClock, readyToAdvance, resetDayCycle, syncDayCycleForState } from "./dayClock.js";
import { configureDevTools, initDevTools, renderDevTools } from "./devTools.js";
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
import {
  configureDecisionActions,
  renderDecisionQueue,
  renderInlineDecisions,
  selectPendingChoice,
  submitDecision,
} from "./renderDecisions.js";
import { renderSummary, renderSummaryModal } from "./renderSummary.js";
import { uiState } from "./state.js";

function showMessageBox(box, message) {
  if (!box) return;
  if (!message) {
    box.classList.add("hidden");
    box.textContent = "";
    return;
  }
  box.textContent = message;
  box.classList.remove("hidden");
}

function showError(message) {
  showMessageBox($("error"), message);
}

function showNewRunError(message) {
  showMessageBox($("newRunError"), message);
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
  if (uiState.newRunLoading) return;

  uiState.newRunLoading = true;
  showNewRunError("");
  renderNewRunModal();
  renderDevTools();

  try {
    const seedValue = $("newRunSeedInput")?.value?.trim() || null;
    const body = uiState.state?.developer ? { seed: seedValue } : {};
    uiState.state = await api("/api/new", {
      method: "POST",
      body: JSON.stringify(body)
    });
    uiState.runCycleId += 1;
    resetDayCycle();
    uiState.pendingChoice = null;
    uiState.summaryAnimationKey = null;
    uiState.welcomeModalVisible = true;
    uiState.newRunModalVisible = false;
    uiState.newRunLoading = false;
    $("inlineDecisionBody").replaceChildren();
    showNewRunError("");
    showError("");
    render();
  } catch (error) {
    uiState.newRunLoading = false;
    renderNewRunModal();
    renderDevTools();
    if (uiState.newRunModalVisible) {
      showNewRunError(error.message);
    } else {
      showError(error.message);
    }
  }
}

async function choose(cardId, choiceId) {
  try {
    uiState.state = await api("/api/choice", {
      method: "POST",
      body: JSON.stringify({ cardId, choiceId })
    });
    uiState.pendingChoice = null;
    showError("");
    render();
    return uiState.state;
  } catch (error) {
    showError(error.message);
    return null;
  }
}

async function prepareAdvanceDay() {
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
  $("dayBadge").textContent = uiState.state.currentDate || "Schedule";
  renderMainSectionVisibility();

  renderInlineDecisions();
  renderSummary();
  renderSummaryModal();
  renderFinal();
  renderWelcomeModal();
  renderNewRunModal();
  renderDecisionQueue();
  renderSettingsMenu();
  renderDevTools();
}

function renderMainSectionVisibility() {
  const gameOver = Boolean(uiState.state.gameOver);
  $("dailyDecisionSection").classList.toggle("hidden", gameOver);
  $("game-area").classList.toggle("hidden", gameOver);
}

configureDayClock({
  renderInlineDecisions,
  prepareAdvanceDay,
  renderDecisionQueue,
});
configureDecisionActions({ choose });
configureModals({ renderDecisionQueue, renderDevTools, showNewRunError });
configureDevTools({ openNewRunModal });
initDevTools();

$("settingsMenuBtn").addEventListener("click", toggleSettingsMenu);
$("openNewRunModalBtn").addEventListener("click", openNewRunModal);
$("themeMenuBtn").addEventListener("click", toggleDarkMode);

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const settingsWrap = document.querySelector(".settings-wrap");
  const welcomeOverlay = $("welcomeModalOverlay");
  const newRunOverlay = $("newRunModalOverlay");

  if (settingsWrap && target && !settingsWrap.contains(target)) {
    closeSettingsMenu();
  }
  if (welcomeOverlay && target === welcomeOverlay) {
    closeWelcomeModal();
  }
  if (newRunOverlay && target === newRunOverlay) {
    closeNewRunModal();
  }
});

Object.assign(window, {
  closeNewRunModal,
  closeWelcomeModal,
  commitAdvanceDay,
  hideDecisionChartTooltip,
  selectPendingChoice,
  showDecisionChartTooltip,
  startNewRun,
  submitDecision,
});

initDarkMode();
uiState.welcomeModalVisible = true;
renderWelcomeModal();
loadState();
