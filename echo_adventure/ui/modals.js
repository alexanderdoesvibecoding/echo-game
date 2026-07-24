"use strict";

import { uiState } from "./state.js";
import { $ } from "./html.js";
import { SUBMARINE_IMAGE_SRC } from "./submarineVisual.js";
import { startTutorial } from "./tutorial.js";

const callbacks = {
  renderDecisionQueue: () => {},
  renderDevTools: null,
  showNewRunError: () => {},
};

export function configureModals(overrides) {
  Object.assign(callbacks, overrides || {});
}

export function renderWelcomeModal() {
  const overlay = document.getElementById("welcomeModalOverlay");
  if (!overlay) return;
  renderWelcomeContent();
  overlay.classList.toggle("active", uiState.welcomeModalVisible);
}

function renderWelcomeContent() {
  const visual = $("welcomeSubmarineVisual");
  const blurb = $("welcomeBlurb");

  if (visual) {
    visual.innerHTML = `<img src="${SUBMARINE_IMAGE_SRC}" alt="Submarine underway" draggable="false">`;
  }

  if (!blurb) return;

  const jobCount = Number(uiState.state?.jobCount) || 0;
  const jobText = jobCount ? `${jobCount} job${jobCount === 1 ? "" : "s"}` : "jobs";
  blurb.innerHTML = `
    <p>Finish all ${jobText} to assemble the submarine.</p>
    <p>ECHO is an AI planner answering the same production questions.</p>
    <p>The progress bars track your estimated completion date (ECD) and ECHO's as you compete.</p>
  `;
}

export function closeWelcomeModal() {
  uiState.welcomeModalVisible = false;
  renderWelcomeModal();
  startTutorial();
  callbacks.renderDecisionQueue();
  callbacks.renderDevTools?.();
}

export function toggleSettingsMenu() {
  uiState.settingsMenuOpen = !uiState.settingsMenuOpen;
  renderSettingsMenu();
}

export function closeSettingsMenu() {
  uiState.settingsMenuOpen = false;
  renderSettingsMenu();
}

export function renderSettingsMenu() {
  const panel = $("settingsPanel");
  const button = $("settingsMenuBtn");
  if (!panel || !button) return;
  panel.classList.toggle("active", uiState.settingsMenuOpen);
  button.setAttribute("aria-expanded", uiState.settingsMenuOpen ? "true" : "false");
}

export function openNewRunModal() {
  closeSettingsMenu();
  uiState.newRunModalVisible = true;
  callbacks.showNewRunError("");
  renderNewRunModal();
  callbacks.renderDecisionQueue();
  callbacks.renderDevTools?.();
}

export function closeNewRunModal() {
  if (uiState.newRunLoading) return;
  uiState.newRunModalVisible = false;
  callbacks.showNewRunError("");
  renderNewRunModal();
  callbacks.renderDecisionQueue();
  callbacks.renderDevTools?.();
}

export function renderNewRunModal() {
  const overlay = $("newRunModalOverlay");
  if (!overlay) return;
  const developerMode = Boolean(uiState.state?.developer);
  overlay.classList.toggle("active", uiState.newRunModalVisible);
  overlay.setAttribute("aria-busy", uiState.newRunLoading ? "true" : "false");

  $("newRunSettings")?.classList.toggle("hidden", uiState.newRunLoading);
  $("newRunLoading")?.classList.toggle("hidden", !uiState.newRunLoading);
  $("devSeedField")?.classList.toggle("hidden", !developerMode);
  if ($("newRunDescription")) {
    $("newRunDescription").textContent = developerMode
      ? "Start a fresh run with a random seed or enter an exact seed."
      : "Start a fresh standard run with a newly generated seed.";
  }

  for (const id of ["closeNewRunModalBtn", "cancelNewRunBtn", "startNewRunBtn"]) {
    const button = $(id);
    if (button) button.disabled = uiState.newRunLoading;
  }
  if ($("newRunSeedInput")) $("newRunSeedInput").disabled = uiState.newRunLoading;
}

export function initDarkMode() {
  const saved = localStorage.getItem("theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
  updateThemeButton(saved);
}

function updateThemeButton(theme) {
  const btn = $("themeMenuBtn");
  if (btn) btn.textContent = theme === "dark" ? "Light Mode" : "Dark Mode";
}

export function toggleDarkMode() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
  updateThemeButton(next);
}
