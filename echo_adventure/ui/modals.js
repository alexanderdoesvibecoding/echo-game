/** Welcome, settings, new-run, and theme modal state management. */

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

/** Override modal callbacks for application wiring or tests. */
export function configureModals(overrides) {
  Object.assign(callbacks, overrides || {});
}

/** Show or hide the welcome overlay and refresh its content. */
export function renderWelcomeModal() {
  const overlay = document.getElementById("welcomeModalOverlay");
  if (!overlay) return;
  renderWelcomeContent();
  overlay.classList.toggle("active", uiState.welcomeModalVisible);
}

/** Render run-specific welcome copy and puzzle artwork. */
function renderWelcomeContent() {
  const visual = $("welcomeSubmarineVisual");
  const blurb = $("welcomeBlurb");

  if (visual) {
    visual.innerHTML = `<img src="${SUBMARINE_IMAGE_SRC}" alt="Submarine underway" draggable="false">`;
  }

  if (!blurb) return;

  // The shell can render before initial state arrives, so copy has a generic
  // fallback rather than flashing an invalid zero-job run.
  const jobCount = Number(uiState.state?.jobCount) || 0;
  const jobText = jobCount ? `${jobCount} job${jobCount === 1 ? "" : "s"}` : "jobs";
  blurb.innerHTML = `
    <p>Finish all ${jobText} to assemble the submarine.</p>
    <p>Your goal is to complete all jobs before ECHO, the AI planner does.</p>
  `;
}

/** Dismiss the welcome overlay unless new-run loading locks it. */
export function closeWelcomeModal() {
  // Tutorial timing begins only after the welcome explanation is dismissed.
  uiState.welcomeModalVisible = false;
  renderWelcomeModal();
  startTutorial();
  callbacks.renderDecisionQueue();
  callbacks.renderDevTools?.();
}

/** Toggle the settings menu and update its accessibility state. */
export function toggleSettingsMenu() {
  uiState.settingsMenuOpen = !uiState.settingsMenuOpen;
  renderSettingsMenu();
}

/** Close the settings menu and update its accessibility state. */
export function closeSettingsMenu() {
  uiState.settingsMenuOpen = false;
  renderSettingsMenu();
}

/** Synchronize settings menu visibility with browser state. */
export function renderSettingsMenu() {
  const panel = $("settingsPanel");
  const button = $("settingsMenuBtn");
  if (!panel || !button) return;
  panel.classList.toggle("active", uiState.settingsMenuOpen);
  button.setAttribute("aria-expanded", uiState.settingsMenuOpen ? "true" : "false");
}

/** Bind new-run modal events exactly once. */
export function initNewRunModal() {
  $("newRunSeededToggle")?.addEventListener("change", event => {
    uiState.devSeededRun = Boolean(event.target.checked);
    renderNewRunModal();
  });
  /** Opt into seeded mode when the user interacts directly with the seed field. */
  // Interacting directly with the seed field opts into seeded mode, avoiding a
  // second required toggle while still keeping random mode the default.
  const enableSeededRun = () => {
    if (
      !uiState.state?.developer
      || uiState.newRunLoading
      || uiState.devSeededRun
    ) {
      return;
    }
    uiState.devSeededRun = true;
    renderNewRunModal();
  };
  $("newRunSeedInput")?.addEventListener("focus", enableSeededRun);
  $("newRunSeedInput")?.addEventListener("click", enableSeededRun);
  $("newRunSeedInput")?.addEventListener("input", enableSeededRun);
}

/** Populate and display the new-run form. */
export function openNewRunModal() {
  closeSettingsMenu();
  const developerMode = Boolean(uiState.state?.developer);
  // Every open starts in random mode even though developer mode pre-fills the
  // current seed as a convenient replay reference.
  uiState.devSeededRun = false;
  if ($("newRunSeedInput")) {
    $("newRunSeedInput").value = (
      developerMode && uiState.state?.seed != null
        ? String(uiState.state.seed)
        : ""
    );
  }
  uiState.newRunModalVisible = true;
  callbacks.showNewRunError("");
  renderNewRunModal();
  callbacks.renderDecisionQueue();
  callbacks.renderDevTools?.();
}

/** Dismiss the new-run modal when no request is in flight. */
export function closeNewRunModal() {
  if (uiState.newRunLoading) return;
  uiState.newRunModalVisible = false;
  callbacks.showNewRunError("");
  renderNewRunModal();
  callbacks.renderDecisionQueue();
  callbacks.renderDevTools?.();
}

/** Render new-run form, loading, and disabled states. */
export function renderNewRunModal() {
  const overlay = $("newRunModalOverlay");
  if (!overlay) return;
  const developerMode = Boolean(uiState.state?.developer);
  overlay.classList.toggle("active", uiState.newRunModalVisible);
  overlay.setAttribute("aria-busy", uiState.newRunLoading ? "true" : "false");

  // Loading swaps form content for a locked status panel; all dismissal buttons
  // are also disabled below to protect the in-flight replacement.
  $("newRunSettings")?.classList.toggle("hidden", uiState.newRunLoading);
  $("newRunLoading")?.classList.toggle("hidden", !uiState.newRunLoading);
  $("devSeedField")?.classList.toggle("hidden", !developerMode);
  $("devSeedField")?.classList.toggle(
    "seeded-run-active",
    developerMode && uiState.devSeededRun,
  );
  if ($("newRunSeededToggle")) {
    $("newRunSeededToggle").checked = developerMode && uiState.devSeededRun;
  }
  if ($("newRunSeedHint")) {
    $("newRunSeedHint").textContent = uiState.devSeededRun
      ? "This exact seed will be used for the new run."
      : "This seed is visible for reference but is ignored unless Seeded run is enabled.";
  }
  if ($("newRunDescription")) {
    $("newRunDescription").textContent = developerMode
      ? "Start a fresh game with newly generated jobs and decisions using a random seed, or enter an exact seed to replay a specific setup; your current run will be replaced."
      : "Start a fresh game with newly generated jobs and decisions, replacing your current run.";
  }

  for (const id of ["closeNewRunModalBtn", "cancelNewRunBtn", "startNewRunBtn"]) {
    const button = $(id);
    if (button) button.disabled = uiState.newRunLoading;
  }
  if ($("newRunSeedInput")) $("newRunSeedInput").disabled = uiState.newRunLoading;
  if ($("newRunSeededToggle")) {
    $("newRunSeededToggle").disabled = uiState.newRunLoading;
  }
}

/** Restore the saved theme preference. */
export function initDarkMode() {
  // Theme is a browser-local presentation preference and never enters game state.
  const saved = localStorage.getItem("theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
  updateThemeButton(saved);
}

/** Update the theme button label for the active theme. */
function updateThemeButton(theme) {
  const btn = $("themeMenuBtn");
  if (btn) btn.textContent = theme === "dark" ? "Light Mode" : "Dark Mode";
}

/** Toggle and persist the browser theme preference. */
export function toggleDarkMode() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
  updateThemeButton(next);
}
