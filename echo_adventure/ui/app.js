/** Browser entry point and top-level UI orchestration for a game run. */

"use strict";

import { api } from "./api.js";
import {
  configureDayClock,
  instantProgressionEnabled,
  readyToAdvance,
  resetDayCycle,
  syncDayCycleForState,
} from "./dayClock.js";
import { configureDevTools, initDevTools, renderDevTools } from "./devTools.js";
import { $ } from "./html.js";
import {
  closeNewRunModal,
  closeSettingsMenu,
  closeWelcomeModal,
  configureModals,
  initDarkMode,
  initNewRunModal,
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
import {
  advanceTutorial,
  configureTutorial,
  renderTutorial,
  resetTutorial,
  startTutorial,
  skipTutorial,
} from "./tutorial.js";

/** Show or hide a message element based on the supplied text. */
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

/** Display a top-level gameplay error. */
function showError(message) {
  showMessageBox($("error"), message);
}

/** Display an error inside the new-run modal. */
function showNewRunError(message) {
  showMessageBox($("newRunError"), message);
}

/** Fetch the initial session state and synchronize the browser UI. */
async function loadState() {
  try {
    // Initial state is fetched before starting the tutorial so eligibility uses
    // real session data rather than an empty shell.
    uiState.state = await api("/api/state");
    showError("");
    render();
    if (!uiState.welcomeModalVisible) {
      startTutorial();
    }
  } catch (error) {
    uiState.dayCycleAdvancing = false;
    showError(error.message);
  }
}

/** Request a seeded or random replacement run and reset local UI state. */
async function startNewRun() {
  if (uiState.newRunLoading) return;

  // Seed selection exists only in developer mode; standard runs always ask the
  // server for fresh entropy.
  const developerMode = Boolean(uiState.state?.developer);
  const seededRun = developerMode && uiState.devSeededRun;
  const seedValue = $("newRunSeedInput")?.value?.trim() || "";
  if (seededRun && !/^[+-]?\d+$/.test(seedValue)) {
    showNewRunError("Enter a valid integer seed before starting a seeded run.");
    $("newRunSeedInput")?.focus();
    return;
  }

  uiState.newRunLoading = true;
  showNewRunError("");
  renderNewRunModal();
  renderDevTools();

  try {
    const body = seededRun ? { seed: seedValue } : {};
    uiState.state = await api("/api/new", {
      method: "POST",
      body: JSON.stringify(body)
    });
    // Incrementing the run identity forces timers and animations to treat day 1
    // as new even if the replacement run happens to reuse a seed.
    uiState.runCycleId += 1;
    resetDayCycle();
    uiState.pendingChoice = null;
    uiState.summaryAnimationKey = null;
    resetTutorial();
    uiState.welcomeModalVisible = true;
    uiState.newRunModalVisible = false;
    uiState.newRunLoading = false;
    uiState.devSeededRun = false;
    if ($("newRunSeedInput") && uiState.state?.seed != null) {
      $("newRunSeedInput").value = String(uiState.state.seed);
    }
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

/** Submit one decision and merge the returned session payload. */
async function choose(cardId, choiceId) {
  // Disable duplicate submissions until the authoritative server response
  // replaces the local state.
  if (uiState.choiceRequestInFlight) return null;
  uiState.choiceRequestInFlight = true;
  renderDecisionQueue();
  let result = null;
  try {
    uiState.state = await api("/api/choice", {
      method: "POST",
      body: JSON.stringify({ cardId, choiceId })
    });
    uiState.pendingChoice = null;
    showError("");
    result = uiState.state;
  } catch (error) {
    showError(error.message);
  } finally {
    uiState.choiceRequestInFlight = false;
    render();
  }
  return result;
}

/** Request the next day while retaining the outgoing summary state. */
async function prepareAdvanceDay() {
  if (uiState.advanceRequestInFlight) return;
  if (!readyToAdvance()) {
    uiState.dayCycleAdvancing = false;
    document.getElementById("dailyDecisionSection")?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  uiState.advanceRequestInFlight = true;
  try {
    const nextState = await api("/api/advance", { method: "POST", body: "{}" });
    showError("");
    // Normal play retains the outgoing payload beneath a summary modal. Terminal
    // and instant modes promote the next state immediately.
    if (nextState.finalReveal || instantProgressionEnabled()) {
      uiState.state = nextState;
      uiState.pendingAdvanceState = null;
      uiState.modalVisible = false;
    } else {
      uiState.pendingAdvanceState = nextState;
      uiState.modalVisible = true;
    }
    uiState.advanceRequestInFlight = false;
    render();
  } catch (error) {
    uiState.dayCycleAdvancing = false;
    showError(error.message);
  } finally {
    uiState.advanceRequestInFlight = false;
  }
}

/** Run a developer automation request and reset transient UI state. */
async function runDeveloperSkip({ strategy, targetDay }) {
  try {
    const nextState = await api("/api/dev/skip", {
      method: "POST",
      body: JSON.stringify({ strategy, targetDay }),
    });
    uiState.state = nextState;
    // Automation may cross many UI phases, so discard every transient browser
    // cursor before rendering the returned authoritative snapshot.
    uiState.pendingChoice = null;
    uiState.pendingAdvanceState = null;
    uiState.modalVisible = false;
    uiState.summaryAnimationKey = null;
    uiState.dayCycleAdvancing = false;
    uiState.choiceRequestInFlight = false;
    uiState.advanceRequestInFlight = false;
    resetDayCycle();
    showError("");
    render();
  } catch (error) {
    showError(error.message);
  }
}

/** Promote a prepared next-day payload after summary animation completes. */
function commitAdvanceDay() {
  if (!uiState.pendingAdvanceState) {
    return;
  }
  uiState.state = uiState.pendingAdvanceState;
  uiState.pendingAdvanceState = null;
  uiState.modalVisible = false;
  render();
}

/** Render every UI region from the current shared state. */
function render() {
  if (!uiState.state) return;
  // Synchronize timing first because later renderers derive due/blocked state
  // from the day-cycle cursor.
  syncDayCycleForState();
  $("dayBadge").textContent = uiState.state.currentDate || "Schedule";
  renderMainSectionVisibility();

  renderInlineDecisions();
  renderSummary();
  renderSummaryModal();
  renderFinal();
  renderWelcomeModal();
  renderTutorial();
  renderNewRunModal();
  renderDecisionQueue();
  renderSettingsMenu();
  renderDevTools();
}

/** Toggle primary game sections for active and terminal phases. */
function renderMainSectionVisibility() {
  const gameOver = Boolean(uiState.state.gameOver);
  $("dailyDecisionSection").classList.toggle("hidden", gameOver);
  $("game-area").classList.toggle("hidden", gameOver);
}

/** Resynchronize the day clock after a developer timing change. */
function handleInstantProgressionChanged(enabled) {
  if (!enabled) resetDayCycle();
  render();
}

// Inject cross-module callbacks once to avoid import cycles between renderers
// and the top-level mutation functions.
configureDayClock({
  renderInlineDecisions,
  prepareAdvanceDay,
  renderDecisionQueue,
});
configureDecisionActions({ choose });
configureModals({ renderDecisionQueue, renderDevTools, showNewRunError });
configureTutorial({ renderDecisionQueue, renderDevTools });
configureDevTools({
  diagnosticsChanged: renderDecisionQueue,
  instantProgressionChanged: handleInstantProgressionChanged,
  openNewRunModal,
  skipToDay: runDeveloperSkip,
  skipToEnd: runDeveloperSkip,
});
initDevTools();
initNewRunModal();

$("settingsMenuBtn").addEventListener("click", toggleSettingsMenu);
$("openNewRunModalBtn").addEventListener("click", openNewRunModal);
$("themeMenuBtn").addEventListener("click", toggleDarkMode);

// A single document listener handles click-away behavior for all overlays.
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

// Inline HTML handlers call this deliberately small public action surface.
Object.assign(window, {
  advanceTutorial,
  closeNewRunModal,
  closeWelcomeModal,
  commitAdvanceDay,
  hideDecisionChartTooltip,
  selectPendingChoice,
  showDecisionChartTooltip,
  skipTutorial,
  startNewRun,
  submitDecision,
});

// Paint local preferences and the welcome shell immediately; loadState replaces
// only data-dependent regions when the initial request completes.
initDarkMode();
uiState.welcomeModalVisible = true;
renderWelcomeModal();
loadState();
