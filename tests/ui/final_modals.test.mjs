import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";

import { installDom } from "./testDom.mjs";

const dom = installDom();
const { uiState } = await import("../../echo_adventure/ui/state.js");
const {
  configureDevTools,
  initDevTools,
  renderDevTools,
} = await import("../../echo_adventure/ui/devTools.js");
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
    devPanelCollapsed: false,
    devInstantProgression: false,
    devShowDiagnostics: false,
    devStrategy: "echo",
    devRequestInFlight: false,
  });
}

beforeEach(() => {
  dom.reset();
  resetUiState();
  dom.element("decisionChartTooltip");
  hideDecisionChartTooltip();
});

test("daily score groups begin at neutral score and aggregate all score events by day", () => {
  const groups = buildDailyDecisionGroups([
    {
      day: 1,
      dateLabel: "July 1",
      playerDecision: { scoreDelta: 1, cumulativeScore: 1, choice: "A" },
      echoDecision: { scoreDelta: -1.5, cumulativeScore: -1.5, choice: "B" },
    },
    {
      day: 1,
      dateLabel: "July 1",
      playerDecision: { scoreDelta: 0.5, cumulativeScore: 1.5, choice: "C" },
      echoDecision: { scoreDelta: 2, cumulativeScore: 0.5, choice: "D" },
    },
    {
      day: 2,
      dateLabel: "July 2",
      playerDecision: { scoreDelta: -1, cumulativeScore: 0.5 },
      echoDecision: { scoreDelta: 1, cumulativeScore: 1.5 },
    },
  ]);

  assert.equal(groups[0].dateLabel, "Start");
  assert.equal(groups[0].playerCumulativeScore, 50);
  assert.equal(groups[1].playerDecisionCount, 2);
  assert.equal(groups[1].playerDailyDelta, 1.5);
  assert.equal(groups[1].echoDailyDelta, 0.5);
  assert.equal(groups[2].playerCumulativeScore, 50.5);
  assert.equal(groups[2].echoCumulativeScore, 51.5);
});

test("decision chart tooltip safely renders, locks, and closes", () => {
  const tooltip = dom.element("decisionChartTooltip");
  tooltip.offsetWidth = 300;
  tooltip.offsetHeight = 200;
  const marker = dom.createElement("marker");
  marker.classList.add("chart-hover-zone");
  marker.dataset = {
    dateLabel: "July <1>",
    dayKey: "1",
    playerDecisionCount: "6",
    echoDecisionCount: "0",
    playerChange: "+1.00",
    playerCumulative: "+1.00",
    echoChange: "+2.00",
    echoCumulative: "+2.00",
    playerDecisions: JSON.stringify([
      {
        position: 1, questionTitle: "Route", choice: "Route <now>", scoreDelta: "+1.00", affectedLabel: "Job 1",
        echoPreferredChoice: "Route <now>", alignedWithEcho: true, echoSituationMatches: true, echoEventMatches: true,
        echoPreferenceState: "same-context-same-choice",
      },
      {
        position: 2, questionTitle: "Materials", choice: "Hold", scoreDelta: "+0.00", affectedLabel: "Job 2",
        echoPreferredChoice: "Release", alignedWithEcho: false, echoSituationMatches: true, echoEventMatches: true,
        echoPreferenceState: "same-context-different-choice",
      },
      {
        position: 3, questionTitle: "Staffing", choice: "Reassign", scoreDelta: "+0.50", affectedLabel: "Job 3",
        echoPreferredChoice: "Reassign", alignedWithEcho: true, echoSituationMatches: false, echoEventMatches: true,
        echoPreferenceState: "same-event-different-context-same-choice",
      },
      {
        position: 4, questionTitle: "Inspection", choice: "Continue", scoreDelta: "-0.50", affectedLabel: "Job 4",
        echoPreferredChoice: "Pause", alignedWithEcho: false, echoSituationMatches: false, echoEventMatches: true,
        echoPreferenceState: "same-event-different-context-different-choice",
        followUpSource: { day: 1, title: "Earlier inspection", choice: "Pause work" },
      },
      {
        position: 5, questionTitle: "Routing", choice: "Reassign", scoreDelta: "+0.50", affectedLabel: "Job 3",
        echoPreferredChoice: "Reassign", alignedWithEcho: true, echoSituationMatches: false, echoEventMatches: false,
        echoPreferenceState: "different-events-same-choice",
      },
      {
        position: 6, questionTitle: "Quality", choice: "Continue", scoreDelta: "-0.50", affectedLabel: "Job 4",
        echoPreferredChoice: "Pause", alignedWithEcho: false, echoSituationMatches: false, echoEventMatches: false,
        echoPreferenceState: "different-events-different-choice",
      },
    ]),
    echoDecisions: "[]",
  };

  showDecisionChartTooltip({ preventDefault() {}, stopPropagation() {} }, marker);
  assert.equal(tooltip.classList.contains("active"), true);
  assert.equal(tooltip.classList.contains("locked"), true);
  assert.match(tooltip.innerHTML, /July &lt;1&gt;/);
  assert.match(tooltip.innerHTML, /Route &lt;now&gt;/);
  assert.doesNotMatch(tooltip.innerHTML, /Route <now>/);
  assert.match(tooltip.innerHTML, /Same context · preference matched/);
  assert.match(tooltip.innerHTML, /Same context · different response/);
  assert.match(tooltip.innerHTML, /Shared event · preference matched/);
  assert.match(tooltip.innerHTML, /Shared event · different response/);
  assert.match(tooltip.innerHTML, /Different events · preference matched/);
  assert.match(tooltip.innerHTML, /Different events · different response/);
  assert.match(tooltip.innerHTML, /Follow-up to Day 1: Earlier inspection · Pause work/);
  assert.match(tooltip.innerHTML, /data-preference-state="same-context-different-choice"/);
  assert.match(tooltip.innerHTML, /data-preference-state="different-events-different-choice"/);
  assert.doesNotMatch(tooltip.innerHTML, /resulting completion date first, then the overall route score/);
  assert.doesNotMatch(tooltip.innerHTML, /correct|incorrect/i);
  hideDecisionChartTooltip();
  assert.equal(tooltip.classList.contains("active"), false);
});

test("final reveal renders comparison metrics, score chart, and escaped review notes", () => {
  for (const id of ["finalSection", "finalMetricsBar", "finalCompletionChart", "finalNotes"]) dom.element(id);
  uiState.state = {
    finalReveal: {
      player: { completion: "July 4", completionDay: 4, finalScore: 2, unfinishedJobDays: 48 },
      automated: { completion: "July 3", completionDay: 3, finalScore: 4, unfinishedJobDays: 42 },
      completionHistory: {
        decisionPoints: [
          {
            day: 1,
            dateLabel: "July 1",
            playerDecision: { scoreDelta: 1, cumulativeScore: 1, choice: "A" },
            echoDecision: { scoreDelta: 2, cumulativeScore: 2, choice: "B" },
          },
        ],
      },
      review: { reasons: ["ECHO finished <first>."] },
    },
  };

  renderFinal();

  assert.equal(dom.element("finalSection").classList.contains("hidden"), false);
  assert.match(dom.element("finalMetricsBar").innerHTML, /Completion Date/);
  assert.match(dom.element("finalMetricsBar").innerHTML, /<strong>July 4<\/strong>/);
  assert.match(dom.element("finalMetricsBar").innerHTML, /ECHO: July 3/);
  assert.match(dom.element("finalMetricsBar").innerHTML, /Cumulative Unfinished Work/);
  assert.match(dom.element("finalMetricsBar").innerHTML, /48 job-days/);
  assert.match(dom.element("finalMetricsBar").innerHTML, /ECHO 42 job-days/);
  assert.equal((dom.element("finalMetricsBar").innerHTML.match(/final-metric-[a-z]+ final-metric-hoverable/g) || []).length, 3);
  assert.match(dom.element("finalMetricsBar").innerHTML, /Earlier is better\./);
  assert.match(dom.element("finalMetricsBar").innerHTML, /Higher is better\./);
  assert.match(dom.element("finalMetricsBar").innerHTML, /Lower is better\./);
  assert.match(dom.element("finalMetricsBar").innerHTML, /aria-describedby="finalCompletionDateTooltip"/);
  assert.match(dom.element("finalMetricsBar").innerHTML, /aria-describedby="finalDecisionScoreTooltip"/);
  assert.match(dom.element("finalMetricsBar").innerHTML, /aria-describedby="finalUnfinishedWorkTooltip"/);
  assert.doesNotMatch(dom.element("finalMetricsBar").innerHTML, /Day [34]/);
  assert.match(dom.element("finalCompletionChart").innerHTML, /Your score/);
  assert.match(dom.element("finalCompletionChart").innerHTML, /ECHO score/);
  assert.equal(dom.element("finalNotes").innerHTML, "<li>ECHO finished &lt;first&gt;.</li>");
});

test("welcome, settings, new-run, and developer controls reflect browser-local state", () => {
  for (const id of [
    "welcomeModalOverlay", "welcomeSubmarineVisual", "welcomeBlurb", "settingsPanel", "settingsMenuBtn",
    "newRunModalOverlay", "newRunSettings", "newRunLoading", "closeNewRunModalBtn", "cancelNewRunBtn",
    "startNewRunBtn", "themeMenuBtn", "newRunDescription", "devSeedField", "newRunSeedInput",
    "devPanel", "devPanelToggle", "devPanelBody", "devRunSeed", "devRunDay", "devRunPhase",
    "devBusyState", "devModalNotice", "devActiveControls", "devGameOverControls",
    "devDiagnosticsRow", "devSkipDayRow", "devSkipEndRow", "devInstantProgression",
    "devShowDiagnostics", "devStrategy", "devTargetDay", "devSkipToDayBtn",
    "devSkipToEndBtn", "devNewGameBtn",
  ]) dom.element(id);
  let queueRenders = 0;
  let lastError = "unset";
  let devNewGameRequests = 0;
  configureModals({
    renderDecisionQueue: () => { queueRenders += 1; },
    renderDevTools,
    showNewRunError: value => { lastError = value; },
  });
  configureDevTools({
    openNewRunModal: () => { devNewGameRequests += 1; },
  });
  initDevTools();
  uiState.state = {
    seed: 700,
    day: 1,
    jobCount: 3,
    gameOver: false,
    decisions: [{ id: "CARD-1" }],
    developer: {
      generation: {},
      runState: { inDecisionWeb: true, canSkipToEnd: true, canSkipToDay: true },
    },
  };
  uiState.welcomeModalVisible = true;

  renderWelcomeModal();
  assert.equal(dom.element("welcomeModalOverlay").classList.contains("active"), true);
  assert.match(dom.element("welcomeSubmarineVisual").innerHTML, /Submarine underway/);
  assert.match(dom.element("welcomeBlurb").textContent, /all 3 jobs/);
  renderDevTools();
  assert.equal(dom.element("devPanel").classList.contains("hidden"), false);
  assert.equal(dom.element("devActiveControls").classList.contains("hidden"), true);
  assert.equal(dom.element("devModalNotice").classList.contains("hidden"), false);
  closeWelcomeModal();
  assert.equal(uiState.welcomeModalVisible, false);

  assert.equal(dom.element("devActiveControls").classList.contains("hidden"), false);
  assert.equal(dom.element("devSkipDayRow").classList.contains("hidden"), false);
  assert.equal(dom.element("devDiagnosticsRow").classList.contains("hidden"), false);
  assert.equal(dom.element("devSkipToDayBtn").disabled, true);
  assert.equal(dom.element("devSkipToEndBtn").disabled, true);
  assert.equal(dom.element("devRunPhase").textContent, "Preplanned run");

  dom.element("devPanelToggle").listeners.get("click")[0]();
  assert.equal(uiState.devPanelCollapsed, true);
  assert.equal(dom.element("devPanelBody").classList.contains("hidden"), true);
  dom.element("devInstantProgression").listeners.get("change")[0]({ target: { checked: true } });
  dom.element("devShowDiagnostics").listeners.get("change")[0]({ target: { checked: true } });
  dom.element("devStrategy").listeners.get("change")[0]({ target: { value: "worst" } });
  assert.equal(uiState.devInstantProgression, true);
  assert.equal(uiState.devShowDiagnostics, true);
  assert.equal(uiState.devStrategy, "worst");

  toggleSettingsMenu();
  assert.equal(dom.element("settingsPanel").classList.contains("active"), true);
  assert.equal(dom.element("settingsMenuBtn").getAttribute("aria-expanded"), "true");
  openNewRunModal();
  assert.equal(uiState.settingsMenuOpen, false);
  assert.equal(uiState.newRunModalVisible, true);
  assert.equal(lastError, "");
  assert.equal(dom.element("newRunModalOverlay").classList.contains("active"), true);
  assert.equal(dom.element("devSeedField").classList.contains("hidden"), false);
  assert.match(dom.element("newRunDescription").textContent, /exact seed/);
  assert.equal(dom.element("devActiveControls").classList.contains("hidden"), true);
  closeNewRunModal();
  assert.equal(uiState.newRunModalVisible, false);

  uiState.state = {
    ...uiState.state,
    finalAssembly: { active: true },
    decisions: [{ id: "FINAL-1" }],
    developer: {
      generation: {},
      runState: { inDecisionWeb: false, canSkipToEnd: true, canSkipToDay: false },
    },
  };
  renderDevTools();
  assert.equal(dom.element("devRunPhase").textContent, "Final assembly");
  assert.equal(dom.element("devSkipDayRow").classList.contains("hidden"), true);
  assert.equal(dom.element("devSkipEndRow").classList.contains("hidden"), false);

  uiState.state = {
    ...uiState.state,
    gameOver: true,
    decisions: [],
    finalAssembly: null,
    developer: {
      generation: {},
      runState: { inDecisionWeb: false, canSkipToEnd: false, canSkipToDay: false },
    },
  };
  renderDevTools();
  assert.equal(dom.element("devActiveControls").classList.contains("hidden"), true);
  assert.equal(dom.element("devGameOverControls").classList.contains("hidden"), false);
  assert.equal(dom.element("devRunPhase").textContent, "Game over");
  dom.element("devNewGameBtn").listeners.get("click")[0]();
  assert.equal(devNewGameRequests, 1);

  uiState.newRunLoading = true;
  renderDevTools();
  assert.equal(dom.element("devBusyState").classList.contains("hidden"), false);
  assert.match(dom.element("devBusyState").textContent, /Generating/);
  assert.ok(queueRenders >= 3);
});

test("new-run loading locks dismissal and theme preference persists", () => {
  for (const id of [
    "newRunModalOverlay", "newRunSettings", "newRunLoading", "closeNewRunModalBtn", "cancelNewRunBtn",
    "startNewRunBtn", "settingsPanel", "settingsMenuBtn", "themeMenuBtn", "devSeedField",
    "newRunSeedInput", "newRunDescription",
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
    playerDecisionCount: "0",
    echoDecisionCount: "0",
    playerDecisions: "not-json",
    echoDecisions: "not-json",
  };
  showDecisionChartTooltip({ preventDefault() {}, stopPropagation() {} }, marker);
  assert.match(dom.element("decisionChartTooltip").innerHTML, /You had no decisions on this day/);
  assert.equal(dom.element("decisionChartTooltip").classList.contains("active"), true);
});

test("new-run loading exposes busy state and disables every modal action", () => {
  for (const id of [
    "newRunModalOverlay", "newRunSettings", "newRunLoading", "closeNewRunModalBtn",
    "cancelNewRunBtn", "startNewRunBtn", "devSeedField", "newRunSeedInput",
    "newRunDescription",
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
  assert.equal(dom.element("newRunSeedInput").disabled, true);
});
