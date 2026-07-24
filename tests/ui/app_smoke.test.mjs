import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "./testDom.mjs";

const dom = installDom();
for (const id of [
  "settingsMenuBtn", "openNewRunModalBtn", "themeMenuBtn", "error", "newRunError", "dayBadge",
  "dailyDecisionSection", "game-area", "inlineDecisionBody", "decisionQueueSection", "decisionQueueBody",
  "summarySection", "summaryGrid", "summaryModalOverlay", "summaryModalBody", "summaryModalTitle",
  "finalSection", "finalMetricsBar", "finalCompletionChart", "finalNotes", "welcomeModalOverlay",
  "welcomeSubmarineVisual", "welcomeBlurb", "newRunModalOverlay", "newRunSettings", "newRunLoading",
  "tutorialOverlay", "tutorialStepLabel", "tutorialTitle", "tutorialDescription", "tutorialNextBtn",
  "closeNewRunModalBtn", "cancelNewRunBtn", "startNewRunBtn", "settingsPanel", "newRunDescription",
  "devSeedField", "newRunSeedInput", "devPanel", "devPanelToggle", "devPanelBody", "devRunSeed",
  "devRunDay", "devRunPhase", "devBusyState", "devModalNotice", "devActiveControls",
  "devGameOverControls", "devDiagnosticsRow", "devSkipDayRow", "devSkipEndRow",
  "devInstantProgression", "devShowDiagnostics", "devStrategy", "devTargetDay",
  "devSkipToDayBtn", "devSkipToEndBtn", "devNewGameBtn",
]) dom.element(id);

const initialState = {
  seed: 700,
  day: 1,
  currentDate: "July 1",
  scheduleStartDate: "July 1",
  gameOver: false,
  jobCount: 2,
  dayCycleDurationMs: 1000,
  timelines: {
    player: { progressPercent: 0, displayCompletion: "July 3", projectedCompletion: "July 3" },
    echo: { progressPercent: 0, displayCompletion: "July 2", projectedCompletion: "July 2" },
  },
  decisionProgress: { completed: 0, total: 0 },
  decisions: [],
  livePuzzle: null,
  lastSummary: null,
};
const calls = [];
let nextError = null;
let nextPayload = null;
let nextPayloads = [];
globalThis.fetch = async (path, options = {}) => {
  calls.push({ path, options });
  if (nextError) {
    const error = nextError;
    nextError = null;
    return { ok: false, async json() { return { error }; } };
  }
  return {
    ok: true,
    async json() {
      const payload = nextPayloads.length ? nextPayloads.shift() : nextPayload;
      nextPayload = null;
      return payload || { ...initialState, seed: path === "/api/new" ? 701 : 700 };
    },
  };
};

await import("../../echo_adventure/ui/app.js");
const { uiState } = await import("../../echo_adventure/ui/state.js");
const { resetDayCycle, syncDayCycleForState } = await import("../../echo_adventure/ui/dayClock.js");
await new Promise(resolve => globalThis.setTimeout(resolve, 0));

test("app bootstrap loads state, renders the shell, and exposes working global actions", async () => {
  assert.equal(calls[0].path, "/api/state");
  assert.equal(dom.element("dayBadge").textContent, "July 1");
  assert.equal(dom.element("welcomeModalOverlay").classList.contains("active"), true);
  assert.match(dom.element("welcomeBlurb").innerHTML, /Finish all 2 jobs/);
  assert.match(dom.element("welcomeBlurb").innerHTML, /AI planner/);
  assert.match(dom.element("welcomeBlurb").innerHTML, /estimated completion date \(ECD\)/);
  assert.doesNotMatch(dom.element("welcomeBlurb").innerHTML, /always win|designed to beat/i);
  assert.match(dom.element("inlineDecisionBody").innerHTML, /data-timeline-actor="player"/);
  assert.equal(dom.element("devPanel").classList.contains("hidden"), true);
  assert.equal(typeof window.advanceTutorial, "function");
  assert.equal(typeof window.skipTutorial, "function");
  assert.equal(typeof window.startNewRun, "function");
  assert.equal(typeof window.submitDecision, "function");

  await window.startNewRun();

  assert.equal(calls.at(-1).path, "/api/new");
  assert.equal(calls.at(-1).options.method, "POST");
  assert.equal(dom.element("error").classList.contains("hidden"), true);
  assert.equal(dom.element("dayBadge").textContent, "July 1");

  uiState.state = {
    ...initialState,
    developer: {
      generation: {},
      runState: { inDecisionWeb: true, canSkipToEnd: true, canSkipToDay: true },
    },
  };
  dom.element("newRunSeedInput").value = "12345";
  nextPayload = { ...uiState.state, seed: 12345 };
  await window.startNewRun();
  assert.deepEqual(JSON.parse(calls.at(-1).options.body), { seed: "12345" });
  assert.equal(uiState.state.seed, 12345);
  assert.equal(dom.element("devPanel").classList.contains("hidden"), false);
  const callsBeforeDiagnosticsToggle = calls.length;
  dom.element("devShowDiagnostics").listeners.get("change")[0]({
    target: { checked: true },
  });
  assert.equal(uiState.devShowDiagnostics, true);
  assert.equal(calls.length, callsBeforeDiagnosticsToggle);

  uiState.welcomeModalVisible = false;
  uiState.pendingChoice = { cardId: "STALE", choiceId: "choice-1" };
  uiState.pendingAdvanceState = { ...uiState.state, day: 2 };
  uiState.modalVisible = true;
  uiState.summaryAnimationKey = "stale-summary";
  uiState.dayCycleProgress = 75;
  nextPayload = {
    ...uiState.state,
    day: 5,
    currentDate: "July 5",
    gameOver: true,
    decisions: [],
    developer: {
      generation: {},
      runState: { inDecisionWeb: false, canSkipToEnd: false, canSkipToDay: false },
    },
    finalReveal: {
      player: { completion: "July 5", completionDay: 5, finalScore: 50, unfinishedJobDays: 20 },
      automated: { completion: "July 4", completionDay: 4, finalScore: 60, unfinishedJobDays: 18 },
      completionHistory: { decisionPoints: [] },
      review: { outcome: "behind", reasons: ["ECHO finished first."] },
    },
  };
  await dom.element("devSkipToEndBtn").listeners.get("click")[0]();
  assert.equal(calls.at(-1).path, "/api/dev/skip");
  assert.deepEqual(JSON.parse(calls.at(-1).options.body), {
    strategy: "echo",
    targetDay: null,
  });
  assert.equal(uiState.state.day, 5);
  assert.equal(uiState.pendingChoice, null);
  assert.equal(uiState.pendingAdvanceState, null);
  assert.equal(uiState.modalVisible, false);
  assert.equal(uiState.summaryAnimationKey, null);
  assert.equal(uiState.dayCycleProgress, 0);
  assert.equal(uiState.devRequestInFlight, false);

  uiState.newRunModalVisible = true;
  nextError = "new run failed";
  await window.startNewRun();
  assert.equal(dom.element("newRunError").textContent, "new run failed");
  assert.equal(dom.element("newRunError").classList.contains("hidden"), false);

  uiState.newRunModalVisible = false;
  nextError = "background new run failed";
  await window.startNewRun();
  assert.equal(dom.element("error").textContent, "background new run failed");
  const callsBeforeLoadingGuard = calls.length;
  uiState.newRunLoading = true;
  await window.startNewRun();
  assert.equal(calls.length, callsBeforeLoadingGuard);
  uiState.newRunLoading = false;

  uiState.state = {
    ...initialState,
    decisionProgress: { completed: 0, total: 1 },
    decisions: [{
      id: "CARD-1",
      title: "Decision",
      description: "Choose",
      choices: [{ id: "choice-1", label: "Choose", icon: "adjust" }],
    }],
  };
  uiState.pendingChoice = { cardId: "CARD-1", choiceId: "choice-1" };
  nextError = "choice failed";
  await window.submitDecision();
  assert.equal(dom.element("error").textContent, "choice failed");
  assert.equal(dom.element("error").classList.contains("hidden"), false);

  uiState.welcomeModalVisible = false;
  uiState.newRunModalVisible = false;
  uiState.modalVisible = false;
  uiState.pendingAdvanceState = null;
  uiState.choiceRequestInFlight = false;
  uiState.advanceRequestInFlight = false;
  uiState.devInstantProgression = false;
  uiState.state = {
    ...initialState,
    decisionProgress: { completed: 0, total: 2 },
    decisions: [{
      id: "CARD-INSTANT-1",
      title: "First instant decision",
      description: "Choose immediately",
      choices: [{ id: "choice-1", label: "First", icon: "adjust" }],
    }],
    developer: {
      generation: {},
      runState: { inDecisionWeb: true, canSkipToEnd: true, canSkipToDay: true },
    },
  };
  resetDayCycle();
  dom.element("devInstantProgression").listeners.get("change")[0]({
    target: { checked: true },
  });
  assert.equal(uiState.devInstantProgression, true);
  assert.match(dom.element("decisionQueueBody").innerHTML, /First instant decision/);

  nextPayloads = [{
    ...uiState.state,
    decisionProgress: { completed: 1, total: 2 },
    decisions: [{
      id: "CARD-INSTANT-2",
      title: "Second instant decision",
      description: "Choose on the same day",
      choices: [{ id: "choice-2", label: "Second", icon: "adjust" }],
    }],
  }];
  uiState.pendingChoice = { cardId: "CARD-INSTANT-1", choiceId: "choice-1" };
  const firstInstantSubmit = window.submitDecision();
  const duplicateInstantSubmit = window.submitDecision();
  await Promise.all([firstInstantSubmit, duplicateInstantSubmit]);
  assert.match(dom.element("decisionQueueBody").innerHTML, /Second instant decision/);
  assert.equal(
    calls.filter(call => call.path === "/api/choice" && call.options.body?.includes("CARD-INSTANT-1")).length,
    1,
  );

  nextPayloads = [
    {
      ...uiState.state,
      decisionProgress: { completed: 2, total: 2 },
      decisions: [],
    },
    {
      ...uiState.state,
      day: 2,
      currentDate: "July 2",
      decisionProgress: { completed: 0, total: 1 },
      decisions: [{
        id: "CARD-DAY-2",
        title: "Next day decision",
        description: "Already visible",
        choices: [{ id: "choice-3", label: "Continue", icon: "adjust" }],
      }],
    },
  ];
  uiState.pendingChoice = { cardId: "CARD-INSTANT-2", choiceId: "choice-2" };
  await window.submitDecision();
  await new Promise(resolve => globalThis.setTimeout(resolve, 0));
  assert.equal(calls.at(-1).path, "/api/advance");
  assert.equal(uiState.state.day, 2);
  assert.equal(uiState.pendingAdvanceState, null);
  assert.equal(uiState.modalVisible, false);
  assert.match(dom.element("decisionQueueBody").innerHTML, /Next day decision/);

  uiState.dayCycleProgress = 75;
  dom.element("devInstantProgression").listeners.get("change")[0]({
    target: { checked: false },
  });
  assert.equal(uiState.devInstantProgression, false);
  assert.equal(uiState.dayCycleProgress, 0);
  assert.doesNotMatch(dom.element("decisionQueueBody").innerHTML, /Next day decision/);

  uiState.welcomeModalVisible = false;
  uiState.newRunModalVisible = false;
  uiState.pendingChoice = null;
  uiState.state = {
    ...initialState,
    dayCycleDurationMs: 1,
    finalAssembly: { active: true, status: "locked", jobName: "Final job" },
  };
  uiState.dayCycleKey = null;
  uiState.dayCycleProgress = 0;
  uiState.dayCycleLastTick = null;
  uiState.dayCycleAdvancing = false;
  uiState.pendingAdvanceState = null;
  uiState.modalVisible = false;
  nextPayload = {
    ...uiState.state,
    day: 2,
    currentDate: "July 2",
  };
  syncDayCycleForState();
  dom.setNow(2);
  dom.runInterval(uiState.dayCycleTimer);
  await new Promise(resolve => globalThis.setTimeout(resolve, 0));
  assert.equal(calls.at(-1).path, "/api/advance");
  assert.equal(uiState.state.day, 1);
  assert.equal(uiState.pendingAdvanceState.day, 2);
  assert.equal(uiState.modalVisible, true);
  window.commitAdvanceDay();
  assert.equal(uiState.state.day, 2);
  assert.equal(uiState.pendingAdvanceState, null);
  assert.equal(uiState.modalVisible, false);

  uiState.pendingAdvanceState = {
    ...initialState,
    gameOver: true,
    currentDate: "July 9",
    finalReveal: {
      player: { completion: "July 9", completionDay: 9, finalScore: 2, unfinishedJobDays: 48 },
      automated: { completion: "July 8", completionDay: 8, finalScore: 3, unfinishedJobDays: 42 },
      completionHistory: { decisionPoints: [] },
      review: { reasons: ["ECHO finished first."] },
    },
  };
  window.commitAdvanceDay();
  assert.equal(dom.element("dailyDecisionSection").classList.contains("hidden"), true);
  assert.equal(dom.element("game-area").classList.contains("hidden"), true);
  assert.equal(dom.element("finalSection").classList.contains("hidden"), false);
  assert.equal(dom.element("dayBadge").textContent, "July 9");

  const completedState = uiState.state;
  window.commitAdvanceDay();
  assert.equal(uiState.state, completedState);

  uiState.state = {
    ...initialState,
    dayCycleDurationMs: 1,
  };
  uiState.welcomeModalVisible = false;
  uiState.newRunModalVisible = false;
  uiState.modalVisible = false;
  uiState.pendingAdvanceState = null;
  uiState.advanceRequestInFlight = false;
  nextError = "advance failed";
  resetDayCycle();
  syncDayCycleForState();
  dom.setNow(20);
  dom.runInterval(uiState.dayCycleTimer);
  await new Promise(resolve => globalThis.setTimeout(resolve, 0));
  assert.equal(dom.element("error").textContent, "advance failed");
  assert.equal(uiState.dayCycleAdvancing, false);
});


test("document clicks close settings and dismissible overlays", () => {
  const settingsWrap = dom.element("settingsWrap");
  settingsWrap.classList.add("settings-wrap");
  const outside = dom.element("outside");
  uiState.settingsMenuOpen = true;
  uiState.welcomeModalVisible = true;
  uiState.newRunModalVisible = true;
  uiState.newRunLoading = false;

  dom.dispatchDocument("click", { target: outside });
  assert.equal(uiState.settingsMenuOpen, false);

  dom.dispatchDocument("click", { target: dom.element("welcomeModalOverlay") });
  assert.equal(uiState.welcomeModalVisible, false);

  dom.dispatchDocument("click", { target: dom.element("newRunModalOverlay") });
  assert.equal(uiState.newRunModalVisible, false);
});
