"use strict";

import { $ } from "./html.js";
import { uiState } from "./state.js";

const callbacks = {
  diagnosticsChanged: () => {},
  instantProgressionChanged: () => {},
  openNewRunModal: () => {},
  skipToDay: null,
  skipToEnd: null,
};

export function configureDevTools(overrides) {
  Object.assign(callbacks, overrides || {});
}

export function initDevTools() {
  $("devPanelToggle")?.addEventListener("click", () => {
    uiState.devPanelCollapsed = !uiState.devPanelCollapsed;
    renderDevTools();
  });
  $("devInstantProgression")?.addEventListener("change", event => {
    uiState.devInstantProgression = Boolean(event.target.checked);
    callbacks.instantProgressionChanged(uiState.devInstantProgression);
  });
  $("devShowDiagnostics")?.addEventListener("change", event => {
    uiState.devShowDiagnostics = Boolean(event.target.checked);
    callbacks.diagnosticsChanged(uiState.devShowDiagnostics);
    renderDevTools();
  });
  $("devStrategy")?.addEventListener("change", event => {
    uiState.devStrategy = event.target.value || "echo";
    renderDevTools();
  });
  $("devNewGameBtn")?.addEventListener("click", () => callbacks.openNewRunModal());
  $("devSkipToDayBtn")?.addEventListener("click", () => {
    const targetDay = Number($("devTargetDay")?.value);
    if (Number.isInteger(targetDay) && targetDay > 0) {
      runDeveloperRequest(callbacks.skipToDay, targetDay);
    }
  });
  $("devSkipToEndBtn")?.addEventListener("click", () => {
    runDeveloperRequest(callbacks.skipToEnd, null);
  });
}

export function renderDevTools() {
  const panel = $("devPanel");
  const developer = uiState.state?.developer;
  if (!panel) return;

  const visible = Boolean(developer);
  panel.classList.toggle("hidden", !visible);
  panel.setAttribute("aria-hidden", visible ? "false" : "true");
  if (!visible) return;

  const runState = developer.runState || {};
  const gameOver = Boolean(uiState.state.gameOver);
  const inDecisionWeb = Boolean(runState.inDecisionWeb);
  const hasDecision = Boolean(uiState.state.decisions?.length);
  const modalOpen = Boolean(
    uiState.welcomeModalVisible
      || uiState.newRunModalVisible
      || uiState.modalVisible
  );
  const busy = Boolean(uiState.newRunLoading || uiState.devRequestInFlight);
  const controlsAvailable = !gameOver && !modalOpen;

  $("devPanelBody")?.classList.toggle("hidden", uiState.devPanelCollapsed);
  $("devPanelToggle")?.setAttribute(
    "aria-expanded",
    uiState.devPanelCollapsed ? "false" : "true",
  );
  if ($("devPanelToggle")) {
    $("devPanelToggle").textContent = uiState.devPanelCollapsed ? "Expand" : "Collapse";
  }

  setText("devRunSeed", String(uiState.state.seed ?? "unknown"));
  setText("devRunDay", String(uiState.state.day ?? "—"));
  setText("devRunPhase", phaseLabel(gameOver, inDecisionWeb));

  $("devBusyState")?.classList.toggle("hidden", !busy);
  setText(
    "devBusyState",
    uiState.newRunLoading ? "Generating new game…" : "Developer action running…",
  );
  $("devModalNotice")?.classList.toggle("hidden", !modalOpen || busy);
  $("devActiveControls")?.classList.toggle("hidden", !controlsAvailable);
  $("devGameOverControls")?.classList.toggle("hidden", !gameOver || modalOpen);
  $("devDiagnosticsRow")?.classList.toggle("hidden", !hasDecision);
  $("devSkipDayRow")?.classList.toggle(
    "hidden",
    !inDecisionWeb || !runState.canSkipToDay,
  );
  $("devSkipEndRow")?.classList.toggle("hidden", !runState.canSkipToEnd);

  setChecked("devInstantProgression", uiState.devInstantProgression);
  setChecked("devShowDiagnostics", uiState.devShowDiagnostics);
  if ($("devStrategy")) $("devStrategy").value = uiState.devStrategy;

  const reachableDays = Array.isArray(runState.reachableDays)
    ? runState.reachableDays.filter(day => Number.isInteger(day) && day > uiState.state.day)
    : [];
  renderTargetDays(reachableDays);

  for (const id of [
    "devInstantProgression",
    "devShowDiagnostics",
    "devStrategy",
  ]) {
    if ($(id)) $(id).disabled = busy;
  }
  if ($("devSkipToDayBtn")) {
    $("devSkipToDayBtn").disabled = busy || !callbacks.skipToDay || reachableDays.length === 0;
  }
  if ($("devSkipToEndBtn")) {
    $("devSkipToEndBtn").disabled = busy || !callbacks.skipToEnd;
  }
  if ($("devTargetDay")) {
    $("devTargetDay").disabled = busy || reachableDays.length === 0;
  }
  if ($("devNewGameBtn")) $("devNewGameBtn").disabled = busy;
}

async function runDeveloperRequest(callback, targetDay) {
  if (!callback || uiState.devRequestInFlight || uiState.newRunLoading) return;
  uiState.devRequestInFlight = true;
  renderDevTools();
  try {
    await callback({ strategy: uiState.devStrategy, targetDay });
  } finally {
    uiState.devRequestInFlight = false;
    renderDevTools();
  }
}

function phaseLabel(gameOver, inDecisionWeb) {
  if (gameOver) return "Game over";
  if (uiState.state.finalAssembly?.active) return "Final assembly";
  return inDecisionWeb ? "Preplanned run" : "Extended play";
}

function renderTargetDays(days) {
  const select = $("devTargetDay");
  if (!select) return;
  if (!days.length) {
    select.innerHTML = '<option value="">No reachable days</option>';
    select.value = "";
    return;
  }
  select.innerHTML = days
    .map(day => `<option value="${day}">Day ${day}</option>`)
    .join("");
  select.value = String(days[0]);
}

function setText(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

function setChecked(id, value) {
  const element = $(id);
  if (element) element.checked = Boolean(value);
}
