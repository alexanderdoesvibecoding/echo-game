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
const {
  advanceTutorial,
  configureTutorial,
  renderTutorial,
  skipTutorial,
} = await import("../../echo_adventure/ui/tutorial.js");

function resetUiState() {
  Object.assign(uiState, {
    state: null,
    welcomeModalVisible: false,
    tutorialStep: -1,
    tutorialCompletedRunKey: null,
    newRunModalVisible: false,
    newRunLoading: false,
    settingsMenuOpen: false,
    runCycleId: 0,
    dayCycleKey: null,
    dayCycleProgress: 0,
    dayCycleTimer: null,
    dayCycleLastTick: null,
    dayCycleAdvancing: false,
    advanceRequestInFlight: false,
    dayDecisionThresholds: [],
    pendingAdvanceState: null,
    modalVisible: false,
    summaryAnimationKey: null,
    pendingChoice: null,
    choiceRequestInFlight: false,
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


test("daily score groups derive missing deltas and normalize sparse decisions", () => {
  const groups = buildDailyDecisionGroups([
    {
      day: "not-a-day",
      playerDecision: {
        cumulativeScore: 55,
        questionId: "PLAYER-1",
        questionText: "Different detail",
      },
      echoDecision: null,
    },
    {
      day: 2,
      dateLabel: "",
      playerDecision: null,
      echoDecision: {
        cumulativeScore: 47.5,
        questionTitle: "ECHO decision",
      },
    },
  ]);

  assert.equal(groups[1].day, 1);
  assert.equal(groups[1].dateLabel, "Day 1");
  assert.equal(groups[1].playerDailyDelta, 5);
  assert.equal(groups[1].echoDailyDelta, 0);
  assert.equal(groups[1].playerDecisions[0].questionTitle, "PLAYER-1");
  assert.equal(groups[1].playerDecisions[0].choice, "-");
  assert.equal(groups[1].echoDecisionCount, 0);
  assert.equal(groups[2].dateLabel, "Day 2");
  assert.equal(groups[2].playerDecisionCount, 0);
  assert.equal(groups[2].echoDailyDelta, -2.5);
  assert.equal(groups[2].echoDecisions[0].position, 2);
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


test("decision chart document handlers support mouse, keyboard, escape, and outside close", () => {
  const tooltip = dom.element("decisionChartTooltip");
  const marker = dom.element("interactive-marker");
  marker.classList.add("chart-hover-zone");
  marker.getBoundingClientRect = () => ({
    left: 1000,
    top: 10,
    bottom: 20,
    width: 10,
    height: 10,
  });
  marker.dataset = {
    dayKey: "2",
    dateLabel: "July 2",
    playerDecisionCount: "1",
    echoDecisionCount: "0",
    playerDecisions: JSON.stringify([{
      questionTitle: "Fallback preference",
      choice: "Continue",
      echoPreferredChoice: "Continue",
      alignedWithEcho: true,
      echoSituationMatches: false,
      echoEventMatches: true,
    }]),
    echoDecisions: "[]",
  };
  const event = {
    target: marker,
    preventDefault() {},
    stopPropagation() {},
  };

  dom.dispatchDocument("click", event);
  assert.equal(tooltip.classList.contains("active"), true);
  assert.equal(marker.getAttribute("aria-expanded"), "true");
  assert.match(tooltip.innerHTML, /Shared event · preference matched/);
  assert.equal(tooltip.style.left, "448px");
  assert.equal(tooltip.style.top, "38px");

  dom.dispatchDocument("click", {
    target: dom.element("outside-chart"),
    preventDefault() {},
    stopPropagation() {},
  });
  assert.equal(tooltip.classList.contains("active"), false);

  dom.dispatchDocument("keydown", { ...event, key: "Enter" });
  assert.equal(tooltip.classList.contains("active"), true);
  const closeButton = dom.element("chart-close");
  closeButton.dataset.chartTooltipClose = "";
  dom.dispatchDocument("click", {
    target: closeButton,
    preventDefault() {},
    stopPropagation() {},
  });
  assert.equal(tooltip.classList.contains("active"), false);
  assert.equal(marker.focused, true);

  dom.dispatchDocument("keydown", { ...event, key: " " });
  assert.equal(tooltip.classList.contains("active"), true);
  dom.dispatchDocument("keydown", { ...event, target: dom.element("key-target"), key: "Escape" });
  assert.equal(tooltip.classList.contains("active"), false);
  assert.equal(marker.focused, true);
});

test("final reveal renders comparison metrics, score chart, and escaped review notes", () => {
  for (const id of ["finalSection", "finalMetricsBar", "finalCompletionChart", "finalNotesTitle", "finalNotes"]) dom.element(id);
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
      review: {
        outcome: "behind",
        reasons: [
          "ECHO finished <first>.",
          "Second driver.",
          "Third driver.",
          "Fourth driver.",
          "Fifth driver.",
          "Sixth driver should not render.",
        ],
      },
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
  assert.equal(dom.element("finalNotesTitle").textContent, "Where It Went Wrong");
  assert.equal((dom.element("finalNotes").innerHTML.match(/<li>/g) || []).length, 5);
  assert.match(dom.element("finalNotes").innerHTML, /ECHO finished &lt;first&gt;\./);
  assert.doesNotMatch(dom.element("finalNotes").innerHTML, /Sixth driver/);

  uiState.state.finalReveal.review.outcome = "tied";
  renderFinal();
  assert.equal(dom.element("finalNotesTitle").textContent, "Why It Was a Tie");
});

test("welcome, settings, new-run, and developer controls reflect browser-local state", () => {
  for (const id of [
    "welcomeModalOverlay", "welcomeSubmarineVisual", "welcomeBlurb", "settingsPanel", "settingsMenuBtn",
    "tutorialOverlay", "tutorialStepLabel", "tutorialTitle", "tutorialDescription", "tutorialNextBtn",
    "summarySection", "decisionQueueSection", "dailyDecisionSection",
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
  configureTutorial({
    renderDecisionQueue: () => { queueRenders += 1; },
    renderDevTools,
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
  assert.match(dom.element("welcomeBlurb").innerHTML, /Finish all 3 jobs/);
  assert.match(dom.element("welcomeBlurb").innerHTML, /AI planner/);
  assert.match(dom.element("welcomeBlurb").innerHTML, /estimated completion date \(ECD\)/);
  assert.doesNotMatch(dom.element("welcomeBlurb").innerHTML, /always win|designed to beat/i);
  renderDevTools();
  assert.equal(dom.element("devPanel").classList.contains("hidden"), false);
  assert.equal(dom.element("devActiveControls").classList.contains("hidden"), true);
  assert.equal(dom.element("devModalNotice").classList.contains("hidden"), false);
  closeWelcomeModal();
  assert.equal(uiState.welcomeModalVisible, false);
  assert.equal(uiState.tutorialStep, 0);
  assert.equal(dom.element("tutorialOverlay").classList.contains("active"), true);
  assert.equal(dom.element("tutorialTitle").textContent, "Submarine Puzzle");
  assert.match(dom.element("tutorialDescription").textContent, /blank section is an unfinished job/);
  assert.equal(dom.element("summarySection").classList.contains("tutorial-highlight"), true);

  advanceTutorial();
  assert.equal(uiState.tutorialStep, 1);
  assert.equal(dom.element("tutorialTitle").textContent, "Decision Queue");
  assert.match(dom.element("tutorialDescription").textContent, /questions appear here/);
  assert.equal(dom.element("decisionQueueSection").classList.contains("tutorial-highlight"), true);

  advanceTutorial();
  assert.equal(uiState.tutorialStep, 2);
  assert.equal(dom.element("tutorialTitle").textContent, "ECD Progress");
  assert.match(dom.element("tutorialDescription").textContent, /your ECD and ECHO's ECD/);
  assert.equal(dom.element("tutorialNextBtn").textContent, "Got it");
  assert.equal(dom.element("dailyDecisionSection").classList.contains("tutorial-highlight"), true);

  advanceTutorial();
  assert.equal(uiState.tutorialStep, -1);
  assert.equal(uiState.tutorialCompletedRunKey, "0:700");
  assert.equal(dom.element("tutorialOverlay").classList.contains("active"), false);
  assert.equal(dom.element("dailyDecisionSection").classList.contains("tutorial-highlight"), false);

  assert.equal(dom.element("devActiveControls").classList.contains("hidden"), false);
  assert.equal(dom.element("devSkipDayRow").classList.contains("hidden"), false);
  assert.equal(dom.element("devDiagnosticsRow").classList.contains("hidden"), false);
  assert.equal(dom.element("devSkipToDayBtn").disabled, true);
  assert.equal(dom.element("devSkipToEndBtn").disabled, true);
  assert.equal(dom.element("devRunPhase").textContent, "Preplanned run");

  uiState.tutorialStep = 0;
  renderTutorial();
  skipTutorial();
  assert.equal(uiState.tutorialStep, -1);

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


test("final reveal supplies safe defaults when history and review notes are absent", () => {
  for (const id of [
    "finalSection", "finalOutcomeHeadline", "finalMetricsBar", "finalCompletionChart",
    "finalNotesTitle", "finalNotes",
  ]) dom.element(id);
  uiState.state = {
    finalReveal: {
      player: {
        completion: null,
        completionDay: null,
        finalScore: 0,
        unfinishedJobDays: 0,
      },
      automated: {
        completion: null,
        completionDay: null,
        finalScore: 0,
        unfinishedJobDays: 0,
      },
      completionHistory: null,
    },
  };

  renderFinal();

  assert.equal(
    dom.element("finalOutcomeHeadline").textContent,
    "Final player and ECHO results",
  );
  assert.match(dom.element("finalOutcomeHeadline").className, /final-outcome-behind/);
  assert.match(dom.element("finalMetricsBar").innerHTML, /final-metric-warn/);
  assert.match(dom.element("finalMetricsBar").innerHTML, /final-metric-good/);
  assert.match(
    dom.element("finalCompletionChart").innerHTML,
    /No decision score history recorded/,
  );
  assert.equal(
    dom.element("finalNotes").innerHTML,
    "<li>No final review notes recorded.</li>",
  );
});


test("developer skip controls filter days and serialize asynchronous requests", async () => {
  for (const id of [
    "devPanel", "devPanelToggle", "devPanelBody", "devRunSeed", "devRunDay",
    "devRunPhase", "devBusyState", "devModalNotice", "devActiveControls",
    "devGameOverControls", "devDiagnosticsRow", "devSkipDayRow", "devSkipEndRow",
    "devInstantProgression", "devShowDiagnostics", "devStrategy", "devTargetDay",
    "devSkipToDayBtn", "devSkipToEndBtn", "devNewGameBtn",
  ]) dom.element(id);
  const requests = [];
  let releaseRequest;
  const pendingRequest = new Promise(resolve => {
    releaseRequest = resolve;
  });
  configureDevTools({
    skipToDay: async payload => {
      requests.push(["day", payload]);
      await pendingRequest;
    },
    skipToEnd: async payload => {
      requests.push(["end", payload]);
    },
  });
  initDevTools();
  uiState.state = {
    seed: 701,
    day: 2,
    gameOver: false,
    decisions: [],
    developer: {
      runState: {
        inDecisionWeb: true,
        canSkipToDay: true,
        canSkipToEnd: true,
        reachableDaysByStrategy: {
          echo: [1, 3, "4", 5],
          worst: [4, 6],
        },
      },
    },
  };

  renderDevTools();

  assert.match(dom.element("devTargetDay").innerHTML, /Day 3/);
  assert.match(dom.element("devTargetDay").innerHTML, /Day 5/);
  assert.doesNotMatch(dom.element("devTargetDay").innerHTML, /Day 1/);
  assert.doesNotMatch(dom.element("devTargetDay").innerHTML, /Day 4/);
  assert.equal(dom.element("devTargetDay").value, "3");
  assert.equal(dom.element("devSkipToDayBtn").disabled, false);
  assert.equal(dom.element("devSkipToEndBtn").disabled, false);

  dom.element("devStrategy").listeners.get("change")[0]({
    target: { value: "worst" },
  });
  assert.equal(uiState.devStrategy, "worst");
  assert.match(dom.element("devTargetDay").innerHTML, /Day 4/);
  assert.match(dom.element("devTargetDay").innerHTML, /Day 6/);
  assert.doesNotMatch(dom.element("devTargetDay").innerHTML, /Day 3/);

  dom.element("devTargetDay").value = "6";
  dom.element("devSkipToDayBtn").listeners.get("click")[0]();
  dom.element("devSkipToEndBtn").listeners.get("click")[0]();
  assert.equal(uiState.devRequestInFlight, true);
  assert.equal(dom.element("devSkipToDayBtn").disabled, true);
  assert.deepEqual(requests, [["day", { strategy: "worst", targetDay: 6 }]]);

  releaseRequest();
  await pendingRequest;
  await new Promise(resolve => globalThis.setTimeout(resolve, 0));
  assert.equal(uiState.devRequestInFlight, false);

  dom.element("devSkipToEndBtn").listeners.get("click")[0]();
  await new Promise(resolve => globalThis.setTimeout(resolve, 0));
  assert.deepEqual(requests.at(-1), [
    "end",
    { strategy: "worst", targetDay: null },
  ]);
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
