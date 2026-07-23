import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";

import { installDom } from "./testDom.mjs";

const dom = installDom();
const { uiState } = await import("../../echo_adventure/ui/state.js");
const {
  animateSummaryCounters,
  renderSubmarinePuzzle,
  renderSummary,
  renderSummaryModal,
} = await import("../../echo_adventure/ui/renderSummary.js");
const {
  configureDecisionActions,
  renderDecisionQueue,
  renderInlineDecisions,
  selectPendingChoice,
  submitDecision,
} = await import("../../echo_adventure/ui/renderDecisions.js");
const {
  configureDayClock,
  currentOpenDecisionCard,
  dayCyclePercent,
  decisionInteractionBlocked,
  nextDecisionIsDue,
  readyToAdvance,
  renderDayClock,
  resetDayCycle,
  syncDayCycleForState,
  updateDayClock,
} = await import("../../echo_adventure/ui/dayClock.js");

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

function statePayload(overrides = {}) {
  return {
    seed: 123,
    day: 1,
    currentDate: "July 1",
    scheduleStartDate: "July 1",
    gameOver: false,
    jobCount: 2,
    dayCycleDurationMs: 1000,
    dailySummaryCounterDurationMs: 50,
    timelines: {
      player: { progressPercent: 25, displayCompletion: "July 4", projectedCompletion: "July 4", completion: null },
      echo: { progressPercent: 50, displayCompletion: "July 3", projectedCompletion: "July 3", completion: null },
    },
    decisionProgress: { completed: 0, total: 1 },
    decisions: [
      {
        id: "CARD-1",
        title: "Recover <time>",
        description: "Remove one day from Job 1.",
        choices: [
          { id: "choice-1", label: "Accelerate", icon: "accelerate" },
          { id: "choice-2", label: "Wait", icon: "wait" },
        ],
      },
    ],
    ...overrides,
  };
}

const puzzle = {
  tiles: [
    { label: "Job 1", name: "Job <One>", completed: true, newlyCompleted: true, completedAt: "July 1" },
    { label: "Job 2", name: "Job Two", completed: false, newlyCompleted: false },
  ],
};

beforeEach(() => {
  dom.reset();
  resetUiState();
});

test("submarine puzzle renders assembled, waiting, and accessible image slices", () => {
  const markup = renderSubmarinePuzzle(puzzle, { showCaption: true });

  assert.match(markup, /puzzle-image-slice placed newly-placed/);
  assert.match(markup, /puzzle-image-placeholder/);
  assert.match(markup, /puzzle-loose-row/);
  assert.match(markup, /virginia-submarine-cutout\.png/);
  assert.match(markup, /Job &lt;One&gt;/);
  assert.doesNotMatch(markup, /\stitle=/);
});


test("submarine puzzle handles empty data and assembled-only animation options", () => {
  assert.equal(renderSubmarinePuzzle(null), "");
  assert.equal(renderSubmarinePuzzle({ tiles: [] }), "");

  const markup = renderSubmarinePuzzle(puzzle, {
    showUnplaced: false,
    showCaption: false,
    highlightNewlyPlaced: false,
    animateNewlyPlaced: true,
  });

  assert.match(markup, /aria-label="Submarine puzzle showing assembled image sections"/);
  assert.doesNotMatch(markup, /puzzle-caption/);
  assert.doesNotMatch(markup, /puzzle-loose-row/);
  assert.doesNotMatch(markup, /newly-placed/);
  assert.doesNotMatch(markup, /move-into-place/);
});


test("waiting puzzle sections use a deterministic scrambled order", () => {
  const waitingPuzzle = {
    tiles: [
      { label: "Job 1", name: "One", completed: false },
      { label: "Job 2", name: "Two", completed: false },
      { label: "Job 3", name: "Three", completed: false },
      { label: "Job 4", name: "Four", completed: false },
    ],
  };

  const first = renderSubmarinePuzzle(waitingPuzzle);
  const second = renderSubmarinePuzzle(waitingPuzzle);

  assert.equal(first, second);
  assert.equal((first.match(/puzzle-image-slice unplaced/g) || []).length, 4);
  assert.match(first, /--slice-count:4/);
});

test("summary renders the live assembly and current daily metrics", () => {
  dom.element("summarySection");
  dom.element("summaryGrid");
  dom.element("summaryModalOverlay");
  dom.element("summaryModalBody");
  dom.element("summaryModalTitle");
  uiState.state = statePayload({ livePuzzle: puzzle, lastSummary: null });

  renderSummary();
  assert.equal(dom.element("summarySection").classList.contains("hidden"), false);
  assert.match(dom.element("summaryGrid").innerHTML, /submarine-puzzle/);
  assert.doesNotMatch(dom.element("summaryGrid").innerHTML, /puzzle-loose-row/);

  uiState.modalVisible = true;
  uiState.pendingAdvanceState = statePayload({
    lastSummary: {
      date: "July 1",
      completedToday: 1,
      previousJobsComplete: 1,
      jobsComplete: 2,
      previousJobsRemaining: 2,
      jobsRemaining: 1,
      previousTotalRemainingDays: 5,
      totalRemainingDays: 2,
      remainingJobs: [
        { name: "Job <Two>", remainingDays: 2 },
      ],
      projectedCompletion: "July 3",
      notes: ["Completed <one> job."],
      puzzle,
    },
  });

  renderSummaryModal();
  const body = dom.element("summaryModalBody").innerHTML;
  assert.equal(dom.element("summaryModalOverlay").classList.contains("active"), true);
  assert.equal(dom.element("summaryModalTitle").textContent, "Daily Summary - July 1");
  assert.match(body, /Jobs Complete/);
  assert.match(body, /Jobs Complete[\s\S]*data-summary-count-from="1"/);
  assert.match(body, /Remaining Job-Days/);
  assert.match(body, /summary-metric-hoverable/);
  assert.match(body, /Hover or focus for the per-job breakdown/);
  assert.match(body, /Job &lt;Two&gt;/);
  assert.match(body, /2 days/);
  assert.match(body, /data-summary-count-from="2"/);
  assert.match(body, /Completed &lt;one&gt; job\./);
  assert.doesNotMatch(body, /Subjobs/);
});

test("summary counters support integers, ratios, and descending values", () => {
  const integer = { dataset: { summaryCountFrom: "0", summaryCountTo: "7", summaryCountDecimals: "0", summaryCountSuffix: "" }, textContent: "" };
  const ratio = { dataset: { summaryCountFrom: "5", summaryCountTo: "3", summaryCountDecimals: "0", summaryCountSuffix: "/6" }, textContent: "" };
  const container = {
    querySelectorAll(selector) {
      assert.equal(selector, "[data-summary-count-to]");
      return [integer, ratio];
    },
  };

  animateSummaryCounters(container, { duration: 0 });
  assert.equal(integer.textContent, "7");
  assert.equal(ratio.textContent, "3/6");
});


test("summary counters ignore invalid entries and modal resets when hidden", () => {
  const invalid = {
    dataset: {
      summaryCountFrom: "not-a-number",
      summaryCountTo: "7",
      summaryCountDecimals: "0",
      summaryCountSuffix: "",
    },
    textContent: "unchanged",
  };
  animateSummaryCounters({
    querySelectorAll() {
      return [invalid];
    },
  }, { duration: 25 });
  assert.equal(invalid.textContent, "unchanged");

  const overlay = dom.element("summaryModalOverlay");
  dom.element("summaryModalBody");
  overlay.classList.add("active");
  uiState.state = statePayload({ lastSummary: null });
  uiState.modalVisible = true;
  uiState.summaryAnimationKey = "old-summary";

  renderSummaryModal();

  assert.equal(overlay.classList.contains("active"), false);
  assert.equal(uiState.summaryAnimationKey, null);
});


test("summary counters animate through intermediate and final values", () => {
  const counter = {
    dataset: {
      summaryCountFrom: "0",
      summaryCountTo: "10",
      summaryCountDecimals: "1",
      summaryCountSuffix: "/10",
    },
    textContent: "",
  };
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
  const timestamps = [25, 100];
  globalThis.requestAnimationFrame = callback => callback(timestamps.shift());
  try {
    animateSummaryCounters({
      querySelectorAll() {
        return [counter];
      },
    }, { duration: 100 });
  } finally {
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
  }

  assert.equal(counter.textContent, "10.0/10");
  assert.equal(timestamps.length, 0);
});

test("day clock creates deterministic decision thresholds and blocks at the right states", () => {
  uiState.runCycleId = 2;
  uiState.state = statePayload({
    decisionProgress: { completed: 0, total: 2 },
  });
  resetDayCycle();
  syncDayCycleForState();

  assert.deepEqual(uiState.dayDecisionThresholds, [88 / 3, 176 / 3]);
  assert.equal(currentOpenDecisionCard().id, "CARD-1");
  assert.equal(nextDecisionIsDue(), false);
  assert.equal(readyToAdvance(), false);
  uiState.dayCycleProgress = uiState.dayDecisionThresholds[0];
  assert.equal(nextDecisionIsDue(), true);
  assert.equal(dayCyclePercent(), uiState.dayDecisionThresholds[0]);
  assert.equal(decisionInteractionBlocked(), false);
  uiState.welcomeModalVisible = true;
  assert.equal(decisionInteractionBlocked(), true);
  uiState.welcomeModalVisible = false;
  uiState.state.decisionProgress.completed = 2;
  assert.equal(readyToAdvance(), true);

  uiState.state = statePayload({
    developer: {
      generation: {},
      runState: { inDecisionWeb: true, canSkipToEnd: true, canSkipToDay: true },
    },
  });
  uiState.devInstantProgression = true;
  uiState.dayCycleProgress = 0;
  assert.equal(nextDecisionIsDue(), true);
  uiState.devRequestInFlight = true;
  assert.equal(decisionInteractionBlocked(), true);
});

test("day clock markup and timeline updates expose both player and ECHO progress", () => {
  uiState.state = statePayload();
  const markup = renderDayClock();
  assert.match(markup, /data-timeline-actor="player"/);
  assert.match(markup, /data-timeline-actor="echo"/);

  const root = dom.createElement("root");
  const clock = dom.createElement("clock");
  root.setQuery("[data-day-clock]", clock);
  for (const actor of ["player", "echo"]) {
    const row = dom.createElement(actor);
    const submarine = dom.createElement(`${actor}-submarine`);
    const fill = dom.createElement(`${actor}-fill`);
    const start = dom.createElement(`${actor}-start`);
    const end = dom.createElement(`${actor}-end`);
    row.setQuery(".timeline-submarine", submarine);
    row.setQuery(".completion-timeline-fill", fill);
    row.setQuery("[data-timeline-start]", start);
    row.setQuery("[data-timeline-end]", end);
    clock.setQuery(`[data-timeline-actor="${actor}"]`, row);
  }

  updateDayClock(root);
  const playerRow = clock.querySelector('[data-timeline-actor="player"]');
  assert.equal(playerRow.getAttribute("aria-valuenow"), "25");
  assert.equal(playerRow.querySelector(".timeline-submarine").style.left, "25%");
  assert.equal(playerRow.querySelector(".completion-timeline-fill").style.width, "25%");
  assert.match(playerRow.getAttribute("aria-valuetext"), /Projected completion: July 4/);
});


test("timeline clamps invalid progress and updates an existing completion label", () => {
  uiState.state = statePayload({
    currentDate: "",
    timelines: {
      player: {
        progressPercent: 140,
        displayCompletion: "July 4",
        projectedCompletion: "July 5",
        completion: "July 4",
      },
      echo: {
        progressPercent: "invalid",
        displayCompletion: "",
        projectedCompletion: "",
        completion: null,
      },
    },
  });
  const root = dom.createElement("root");
  const clock = dom.createElement("clock");
  root.setQuery("[data-day-clock]", clock);
  for (const actor of ["player", "echo"]) {
    const row = dom.createElement(actor);
    row.setQuery(".timeline-submarine", dom.createElement(`${actor}-submarine`));
    row.setQuery(".completion-timeline-fill", dom.createElement(`${actor}-fill`));
    row.setQuery("[data-timeline-start]", dom.createElement(`${actor}-start`));
    row.setQuery("[data-timeline-end]", dom.createElement(`${actor}-end`));
    clock.setQuery(`[data-timeline-actor="${actor}"]`, row);
  }

  updateDayClock(root);

  const playerRow = clock.querySelector('[data-timeline-actor="player"]');
  const echoRow = clock.querySelector('[data-timeline-actor="echo"]');
  assert.equal(playerRow.getAttribute("aria-valuenow"), "100");
  assert.match(playerRow.getAttribute("aria-valuetext"), /Actual completion: July 4/);
  assert.equal(echoRow.getAttribute("aria-valuenow"), "0");
  assert.match(echoRow.getAttribute("aria-valuetext"), /July 1 to July 1/);

  uiState.state.timelines.player.displayCompletion = "July 6";
  updateDayClock(root);
  assert.equal(
    playerRow.querySelector("[data-timeline-end]").textContent,
    "July 6",
  );
  assert.equal(
    playerRow.querySelector("[data-timeline-end]").classList.contains("is-updating"),
    false,
  );
});

test("decision queue reveals due choices, tracks selection, and submits the selected pair", async () => {
  const section = dom.element("decisionQueueSection");
  const body = dom.element("decisionQueueBody");
  const queueProgress = dom.createElement("queue-progress");
  section.setQuery("[data-queue-day-progress]", queueProgress);
  uiState.state = statePayload();
  uiState.state.decisions[0].followUpSource = {
    day: 1,
    title: "Earlier <decision>",
    choice: "Pause <work>",
  };
  uiState.dayDecisionThresholds = [20];
  uiState.dayCycleProgress = 20;
  const calls = [];
  configureDecisionActions({ choose: async (...args) => calls.push(args) });

  renderDecisionQueue();
  assert.match(body.innerHTML, /Recover &lt;time&gt;/);
  assert.match(body.innerHTML, /Follow-up to Day 1: Earlier &lt;decision&gt; · Pause &lt;work&gt;/);
  assert.match(body.innerHTML, /choice-icon/);
  assert.match(body.innerHTML, /Confirm response/);
  assert.match(body.innerHTML, /disabled/);
  assert.equal(section.classList.contains("is-empty"), false);
  assert.equal(queueProgress.getAttribute("aria-valuenow"), "20");
  assert.equal(queueProgress.getAttribute("aria-valuetext"), "Day 20 percent complete; waiting for a decision.");
  assert.equal(queueProgress.style.getPropertyValue("--day-cycle-progress"), "20%");

  selectPendingChoice("CARD-1", "choice-1");
  assert.deepEqual(uiState.pendingChoice, { cardId: "CARD-1", choiceId: "choice-1" });
  assert.match(body.innerHTML, /decision-choice selected/);
  assert.doesNotMatch(body.innerHTML, /Confirm response[\s\S]*disabled/);
  await submitDecision();
  assert.deepEqual(calls, [["CARD-1", "choice-1"]]);

  uiState.state = statePayload({
    decisionProgress: { completed: 0, total: 0 },
    decisions: [],
  });
  uiState.dayCycleProgress = 100;
  renderDecisionQueue();
  assert.equal(queueProgress.style.getPropertyValue("--day-cycle-progress"), "100%");

  uiState.state = statePayload({
    day: 2,
    currentDate: "July 2",
    decisionProgress: { completed: 0, total: 0 },
    decisions: [],
  });
  uiState.dayCycleProgress = 0;
  renderDecisionQueue();
  assert.equal(queueProgress.style.getPropertyValue("--day-cycle-progress"), "0%");

  uiState.dayCycleProgress = 10;
  renderDecisionQueue();
  assert.equal(queueProgress.style.getPropertyValue("--day-cycle-progress"), "10%");
  assert.match(body.innerHTML, /No decision currently requires your attention/);

  uiState.state = statePayload({
    decisionProgress: { completed: 0, total: 0 },
    decisions: [],
    finalAssembly: { active: true, status: "locked", jobName: "Pressure Hull <Final>" },
  });
  renderDecisionQueue();
  assert.match(body.innerHTML, /Final assembly is locked/);
  assert.match(body.innerHTML, /Pressure Hull &lt;Final&gt;/);
  assert.match(body.innerHTML, /remains a normal job/);

  uiState.state = statePayload({
    decisionProgress: { completed: 0, total: 0 },
    decisions: [],
    finalAssembly: { active: true, status: "planning", jobName: "Sonar <Final>" },
  });
  renderDecisionQueue();
  assert.match(body.innerHTML, /Final Assembly Lock-In is ready/);
  assert.match(body.innerHTML, /Sonar &lt;Final&gt;/);
});

test("inline decision area contains the shared player and ECHO clock", () => {
  dom.element("inlineDecisionBody");
  uiState.state = statePayload();

  renderInlineDecisions();

  assert.match(dom.element("inlineDecisionBody").innerHTML, /daily-overview/);
  assert.match(dom.element("inlineDecisionBody").innerHTML, /data-timeline-actor="echo"/);
});

test("automatic clock advances at 100 percent and stops cleanly at game over", () => {
  let prepareCalls = 0;
  let inlineRenders = 0;
  let queueRenders = 0;
  configureDayClock({
    prepareAdvanceDay: () => { prepareCalls += 1; },
    renderInlineDecisions: () => { inlineRenders += 1; },
    renderDecisionQueue: () => { queueRenders += 1; },
  });
  uiState.state = statePayload({
    dayCycleDurationMs: 1000,
    decisionProgress: { completed: 0, total: 0 },
    decisions: [],
  });
  dom.setNow(0);
  syncDayCycleForState();
  const timer = uiState.dayCycleTimer;

  dom.setNow(1000);
  dom.runInterval(timer);

  assert.equal(uiState.dayCycleProgress, 100);
  assert.equal(uiState.dayCycleAdvancing, true);
  assert.equal(prepareCalls, 1);
  assert.equal(inlineRenders, 0);
  assert.equal(queueRenders, 0);

  uiState.state.gameOver = true;
  dom.runInterval(timer);
  assert.equal(uiState.dayCycleTimer, null);

  uiState.state = statePayload({
    developer: {
      generation: {},
      runState: { inDecisionWeb: true, canSkipToEnd: true, canSkipToDay: true },
    },
    decisionProgress: { completed: 0, total: 0 },
    decisions: [],
  });
  uiState.devInstantProgression = true;
  resetDayCycle();
  syncDayCycleForState();
  assert.equal(prepareCalls, 2);
  assert.equal(uiState.dayCycleProgress, 0);
});

test("automatic clock pauses at a due decision and while overlays are active", () => {
  let prepareCalls = 0;
  let inlineRenders = 0;
  let queueRenders = 0;
  configureDayClock({
    prepareAdvanceDay: () => { prepareCalls += 1; },
    renderInlineDecisions: () => { inlineRenders += 1; },
    renderDecisionQueue: () => { queueRenders += 1; },
  });
  uiState.state = statePayload();
  dom.setNow(0);
  syncDayCycleForState();
  const timer = uiState.dayCycleTimer;
  uiState.dayCycleProgress = uiState.dayDecisionThresholds[0];

  dom.setNow(500);
  dom.runInterval(timer);
  assert.equal(uiState.dayCycleProgress, uiState.dayDecisionThresholds[0]);
  assert.equal(inlineRenders, 1);
  assert.equal(queueRenders, 1);

  uiState.state.decisions = [];
  uiState.welcomeModalVisible = true;
  dom.setNow(900);
  dom.runInterval(timer);
  assert.equal(uiState.dayCycleProgress, uiState.dayDecisionThresholds[0]);

  uiState.state = statePayload({
    developer: {
      generation: {},
      runState: { inDecisionWeb: true, canSkipToEnd: true, canSkipToDay: true },
    },
    decisionProgress: { completed: 0, total: 0 },
    decisions: [],
  });
  uiState.devInstantProgression = true;
  uiState.devRequestInFlight = true;
  resetDayCycle();
  syncDayCycleForState();
  const instantTimer = uiState.dayCycleTimer;
  uiState.welcomeModalVisible = false;
  dom.runInterval(instantTimer);
  assert.equal(prepareCalls, 0);
  uiState.devRequestInFlight = false;
  dom.runInterval(instantTimer);
  assert.equal(prepareCalls, 1);
});

test("summary and decision queue hide or idle safely when content is unavailable", () => {
  dom.element("summarySection");
  dom.element("summaryGrid");
  dom.element("decisionQueueSection");
  dom.element("decisionQueueBody");
  uiState.state = statePayload({
    livePuzzle: null,
    lastSummary: null,
    decisionProgress: { completed: 0, total: 0 },
    decisions: [],
  });

  renderSummary();
  renderDecisionQueue();

  assert.equal(dom.element("summarySection").classList.contains("hidden"), true);
  assert.equal(dom.element("decisionQueueSection").classList.contains("is-empty"), true);
  assert.match(dom.element("decisionQueueBody").innerHTML, /No decision currently requires your attention/);
});
