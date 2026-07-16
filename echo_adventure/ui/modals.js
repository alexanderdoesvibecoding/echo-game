"use strict";

import { uiState } from "./state.js";
import { $ } from "./html.js";
import { renderSubmarineImage } from "./submarineVisual.js";

const callbacks = {
  renderDecisionQueue: () => {},
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
    visual.innerHTML = renderSubmarineImage({
      idPrefix: "welcomeSubmarine",
      className: "welcome-submarine-image",
      ariaLabel: "Submarine underway",
    });
  }

  if (!blurb) return;

  const jobCount = Array.isArray(uiState.state?.jobs) ? uiState.state.jobs.length : 0;
  const jobText = jobCount ? `${jobCount} job${jobCount === 1 ? "" : "s"}` : "jobs";
  blurb.textContent = `Your mission is to finish all ${jobText} and assemble the submarine. Each day, you will make decisions that affect the outcome of your journey. Good luck!`;
}

export function closeWelcomeModal() {
  uiState.welcomeModalVisible = false;
  renderWelcomeModal();
  callbacks.renderDecisionQueue();
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
}

export function closeNewRunModal() {
  uiState.newRunModalVisible = false;
  callbacks.showNewRunError("");
  renderNewRunModal();
  callbacks.renderDecisionQueue();
}

export function renderNewRunModal() {
  const overlay = $("newRunModalOverlay");
  if (!overlay) return;
  overlay.classList.toggle("active", uiState.newRunModalVisible);
}

export function initDarkMode() {
  // Theme is intentionally local browser preference, separate from run
  // uiState.state so seed replays do not change presentation preferences.
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
