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
    dayDecisionThresholds: [],
    pendingAdvanceState: null,
    modalVisible: false,
    summaryAnimationKey: null,
    pendingChoice: null,
  });
}

function statePayload(overrides = {}) {
  return {
    seed: 123,
    day: 1,
    currentDate: "July 1",
    scheduleStartDate: "July 1",
    gameOver: false,
    dayCycleDurationMs: 1000,
    dailySummaryCounterDurationMs: 50,
    snapshot: { jobsCompleted: 0, jobsRemaining: 2, totalRemainingDays: 5 },
    timelines: {
      player: { progressPercent: 25, displayCompletion: "July 4", projectedCompletion: "July 4", completion: null },
      echo: { progressPercent: 50, displayCompletion: "July 3", projectedCompletion: "July 3", completion: null },
    },
    decisionProgress: { completed: 0, total: 1, visibleCards: 1, openCardIds: ["CARD-1"] },
    decisions: [
      {
        id: "CARD-1",
        type: "Opportunity",
        title: "Recover <time>",
        description: "Remove one day from Job 1.",
        context: "Job 1",
        selectedChoice: null,
        choices: [
          { id: "choice-1", label: "Accelerate", description: "Remove one day.", icon: "accelerate" },
          { id: "choice-2", label: "Wait", description: "No change.", icon: "wait" },
        ],
      },
    ],
    ...overrides,
  };
}

const puzzle = {
  tiles: [
    { id: "JOB-01", label: "Job 1", name: "Job <One>", completed: true, newlyCompleted: true, completedAt: "July 1" },
    { id: "JOB-02", label: "Job 2", name: "Job Two", completed: false, newlyCompleted: false, remainingDays: 2 },
  ],
};

beforeEach(() => {
  dom.reset();
  resetUiState();
});

test("submarine puzzle renders assembled, waiting, and accessible image slices", () => {
  const markup = renderSubmarinePuzzle(puzzle, "unit", { showCaption: true, showPlacedToday: true });

  assert.match(markup, /puzzle-image-slice placed newly-placed/);
  assert.match(markup, /puzzle-image-placeholder/);
  assert.match(markup, /puzzle-loose-row/);
  assert.match(markup, /Placed today:/);
  assert.match(markup, /virginia-submarine-cutout\.png/);
  assert.match(markup, /Job &lt;One&gt;/);
  assert.doesNotMatch(markup, /\stitle=/);
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
      day: 1,
      date: "July 1",
      completedToday: 1,
      jobsRemaining: 1,
      jobsComplete: 1,
      previousTotalRemainingDays: 5,
      totalRemainingDays: 2,
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
  assert.match(body, /Remaining Job-Days/);
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

test("day clock creates deterministic decision thresholds and blocks at the right states", () => {
  uiState.runCycleId = 2;
  uiState.state = statePayload({
    decisionProgress: { completed: 0, total: 2, visibleCards: 1, openCardIds: ["CARD-1"] },
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

test("decision queue reveals due choices, tracks selection, and submits the selected pair", async () => {
  const section = dom.element("decisionQueueSection");
  const body = dom.element("decisionQueueBody");
  const queueClock = dom.createElement("queue-clock");
  section.setQuery("[data-queue-day-clock]", queueClock);
  uiState.state = statePayload();
  uiState.dayDecisionThresholds = [20];
  uiState.dayCycleProgress = 20;
  const calls = [];
  configureDecisionActions({ choose: async (...args) => calls.push(args) });

  renderDecisionQueue();
  assert.match(body.innerHTML, /Recover &lt;time&gt;/);
  assert.match(body.innerHTML, /choice-icon/);
  assert.match(body.innerHTML, /Confirm response/);
  assert.match(body.innerHTML, /disabled/);
  assert.equal(section.classList.contains("is-empty"), false);
  assert.equal(queueClock.getAttribute("aria-valuenow"), "20");

  selectPendingChoice("CARD-1", "choice-1");
  assert.deepEqual(uiState.pendingChoice, { cardId: "CARD-1", choiceId: "choice-1" });
  assert.match(body.innerHTML, /decision-choice selected/);
  assert.doesNotMatch(body.innerHTML, /Confirm response[\s\S]*disabled/);
  await submitDecision();
  assert.deepEqual(calls, [["CARD-1", "choice-1"]]);
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
    decisionProgress: { completed: 0, total: 0, visibleCards: 0, openCardIds: [] },
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
});

test("automatic clock pauses at a due decision and while overlays are active", () => {
  let inlineRenders = 0;
  let queueRenders = 0;
  configureDayClock({
    prepareAdvanceDay() {},
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
});

test("summary and decision queue hide or idle safely when content is unavailable", () => {
  dom.element("summarySection");
  dom.element("summaryGrid");
  dom.element("decisionQueueSection");
  dom.element("decisionQueueBody");
  uiState.state = statePayload({
    livePuzzle: null,
    lastSummary: null,
    decisionProgress: { completed: 0, total: 0, visibleCards: 0, openCardIds: [] },
    decisions: [],
  });

  renderSummary();
  renderDecisionQueue();

  assert.equal(dom.element("summarySection").classList.contains("hidden"), true);
  assert.equal(dom.element("decisionQueueSection").classList.contains("is-empty"), true);
  assert.match(dom.element("decisionQueueBody").innerHTML, /No decision currently requires your attention/);
});
