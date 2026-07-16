import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";

import { installDom } from "./testDom.mjs";

const dom = installDom();
const { uiState } = await import("../../echo_adventure/ui/state.js");
const {
  buildDailyDecisionGroups,
  hideDecisionChartTooltip,
  renderFinal,
  showDecisionChartTooltip,
} = await import("../../echo_adventure/ui/renderFinal.js");
const {
  closeNewRunModal,
  closeWelcomeModal,
  configureModals,
  initDarkMode,
  openNewRunModal,
  renderSettingsMenu,
  renderWelcomeModal,
  toggleDarkMode,
  toggleSettingsMenu,
} = await import("../../echo_adventure/ui/modals.js");

function resetUiState() {
  Object.assign(uiState, {
    state: null,
    welcomeModalVisible: false,
    newRunModalVisible: false,
    newRunLoading: false,
    settingsMenuOpen: false,
    runCycleId: 0,
    dayCycleKey: null,
    dayCycleProgress: 0,
    dayCycleTimer: null,
    dayCycleLastTick: null,
    dayCycleAdvancing: false,
    dayDecisionThresholds: [],
    pendingAdvanceState: null,
    modalVisible: false,
    summaryAnimationKey: null,
    pendingChoice: null,
  });
}

beforeEach(() => {
  dom.reset();
  resetUiState();
  dom.element("decisionChartTooltip");
  hideDecisionChartTooltip({ force: true });
});

test("daily score groups begin at zero and aggregate all score events by day", () => {
  const groups = buildDailyDecisionGroups([
    { sequence: 1, day: 1, dateLabel: "July 1", playerDelta: 1, echoDelta: -1.5, playerChoice: "A", echoChoice: "B" },
    { sequence: 2, day: 1, dateLabel: "July 1", playerDelta: 0.5, echoDelta: 2, playerChoice: "C", echoChoice: "D" },
    { sequence: 3, day: 2, dateLabel: "July 2", playerDelta: -1, echoDelta: 1 },
  ]);

  assert.equal(groups[0].dateLabel, "Start");
  assert.equal(groups[0].playerCumulativeScore, 0);
  assert.equal(groups[1].decisions.length, 2);
  assert.equal(groups[1].playerDailyDelta, 1.5);
  assert.equal(groups[1].echoDailyDelta, 0.5);
  assert.equal(groups[2].playerCumulativeScore, 0.5);
  assert.equal(groups[2].echoCumulativeScore, 1.5);
});

test("decision chart tooltip safely renders, locks, and force-unlocks", () => {
  const tooltip = dom.element("decisionChartTooltip");
  tooltip.offsetWidth = 300;
  tooltip.offsetHeight = 200;
  const marker = dom.createElement("marker");
  marker.classList.add("chart-hover-zone");
  marker.dataset = {
    dateLabel: "July <1>",
    decisionCount: "1",
    playerChange: "+1.00",
    playerCumulative: "+1.00",
    echoChange: "+2.00",
    echoCumulative: "+2.00",
    decisions: JSON.stringify([
      { label: "Q1", playerChoice: "Route <now>", echoChoice: "Optimize", playerDelta: "+1", echoDelta: "+2", affected: "Job 1" },
    ]),
  };

  showDecisionChartTooltip({ clientX: 500, clientY: 300 }, marker);
  assert.equal(tooltip.classList.contains("active"), true);
  assert.match(tooltip.innerHTML, /July &lt;1&gt;/);
  assert.match(tooltip.innerHTML, /Route &lt;now&gt;/);
  assert.doesNotMatch(tooltip.innerHTML, /Route <now>/);
  assert.match(tooltip.innerHTML, /Click to lock this panel/);

  document.dispatchEvent("click", { target: marker, preventDefault() {}, stopPropagation() {} });
  assert.equal(tooltip.classList.contains("locked"), true);
  assert.match(tooltip.innerHTML, /Locked - click this day again to unlock/);
  hideDecisionChartTooltip();
  assert.equal(tooltip.classList.contains("active"), true);
  hideDecisionChartTooltip({ force: true });
  assert.equal(tooltip.classList.contains("active"), false);
});

test("final reveal renders comparison metrics, score chart, and escaped review notes", () => {
  for (const id of ["finalSection", "finalMetricsBar", "finalCompletionChart", "finalNotes"]) dom.element(id);
  uiState.state = {
    finalReveal: {
      player: { completion: "July 4", completionDay: 4, finalScore: 2 },
      automated: { completion: "July 3", completionDay: 3, finalScore: 4 },
      completionHistory: {
        decisionPoints: [
          { sequence: 1, day: 1, dateLabel: "July 1", playerDelta: 1, echoDelta: 2, playerChoice: "A", echoChoice: "B" },
        ],
      },
      review: { reasons: ["ECHO finished <first>."] },
    },
  };

  renderFinal();

  assert.equal(dom.element("finalSection").classList.contains("hidden"), false);
  assert.match(dom.element("finalMetricsBar").innerHTML, /Completion Day/);
  assert.match(dom.element("finalMetricsBar").innerHTML, /ECHO 3/);
  assert.match(dom.element("finalCompletionChart").innerHTML, /Your score/);
  assert.match(dom.element("finalCompletionChart").innerHTML, /ECHO score/);
  assert.equal(dom.element("finalNotes").innerHTML, "<li>ECHO finished &lt;first&gt;.</li>");
});

test("welcome, settings, and new-run controls reflect browser-local state", () => {
  for (const id of [
    "welcomeModalOverlay", "welcomeSubmarineVisual", "welcomeBlurb", "settingsPanel", "settingsMenuBtn",
    "newRunModalOverlay", "newRunSettings", "newRunLoading", "closeNewRunModalBtn", "cancelNewRunBtn",
    "startNewRunBtn", "themeMenuBtn",
  ]) dom.element(id);
  let queueRenders = 0;
  let lastError = "unset";
  configureModals({
    renderDecisionQueue: () => { queueRenders += 1; },
    showNewRunError: value => { lastError = value; },
  });
  uiState.state = { jobs: [{}, {}, {}] };
  uiState.welcomeModalVisible = true;

  renderWelcomeModal();
  assert.equal(dom.element("welcomeModalOverlay").classList.contains("active"), true);
  assert.match(dom.element("welcomeSubmarineVisual").innerHTML, /Submarine underway/);
  assert.match(dom.element("welcomeBlurb").textContent, /all 3 jobs/);
  closeWelcomeModal();
  assert.equal(uiState.welcomeModalVisible, false);

  toggleSettingsMenu();
  assert.equal(dom.element("settingsPanel").classList.contains("active"), true);
  assert.equal(dom.element("settingsMenuBtn").getAttribute("aria-expanded"), "true");
  openNewRunModal();
  assert.equal(uiState.settingsMenuOpen, false);
  assert.equal(uiState.newRunModalVisible, true);
  assert.equal(lastError, "");
  assert.equal(dom.element("newRunModalOverlay").classList.contains("active"), true);
  closeNewRunModal();
  assert.equal(uiState.newRunModalVisible, false);
  assert.ok(queueRenders >= 3);
});

test("new-run loading locks dismissal and theme preference persists", () => {
  for (const id of [
    "newRunModalOverlay", "newRunSettings", "newRunLoading", "closeNewRunModalBtn", "cancelNewRunBtn",
    "startNewRunBtn", "settingsPanel", "settingsMenuBtn", "themeMenuBtn",
  ]) dom.element(id);
  configureModals({ renderDecisionQueue() {}, showNewRunError() {} });
  uiState.newRunModalVisible = true;
  uiState.newRunLoading = true;
  closeNewRunModal();
  assert.equal(uiState.newRunModalVisible, true);

  localStorage.setItem("theme", "dark");
  initDarkMode();
  assert.equal(document.documentElement.getAttribute("data-theme"), "dark");
  assert.equal(dom.element("themeMenuBtn").textContent, "Light Mode");
  toggleDarkMode();
  assert.equal(document.documentElement.getAttribute("data-theme"), "light");
  assert.equal(localStorage.getItem("theme"), "light");
  renderSettingsMenu();
  assert.equal(dom.element("settingsMenuBtn").getAttribute("aria-expanded"), "false");
});

test("final view hides without a reveal and tooltip tolerates invalid event data", () => {
  dom.element("finalSection");
  uiState.state = { finalReveal: null };
  renderFinal();
  assert.equal(dom.element("finalSection").classList.contains("hidden"), true);

  const marker = dom.createElement("bad-marker");
  marker.dataset = {
    dateLabel: "July 3",
    decisionCount: "0",
    decisions: "not-json",
  };
  showDecisionChartTooltip({ clientX: 10, clientY: 10 }, marker);
  assert.match(dom.element("decisionChartTooltip").innerHTML, /No decisions recorded for this day/);
  assert.equal(dom.element("decisionChartTooltip").classList.contains("active"), true);
});

test("new-run loading exposes busy state and disables every modal action", () => {
  for (const id of [
    "newRunModalOverlay", "newRunSettings", "newRunLoading", "closeNewRunModalBtn",
    "cancelNewRunBtn", "startNewRunBtn",
  ]) dom.element(id);
  uiState.newRunModalVisible = true;
  uiState.newRunLoading = true;

  openNewRunModal();

  assert.equal(dom.element("newRunModalOverlay").getAttribute("aria-busy"), "true");
  assert.equal(dom.element("newRunSettings").classList.contains("hidden"), true);
  assert.equal(dom.element("newRunLoading").classList.contains("hidden"), false);
  assert.equal(dom.element("closeNewRunModalBtn").disabled, true);
  assert.equal(dom.element("cancelNewRunBtn").disabled, true);
  assert.equal(dom.element("startNewRunBtn").disabled, true);
});
