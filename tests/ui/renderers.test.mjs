import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";

import { installDom } from "./domStub.mjs";

const dom = installDom();

const { uiState } = await import("../../echo_adventure/ui/state.js");
const { renderMetrics } = await import("../../echo_adventure/ui/renderMetrics.js");
const {
  decisionModalBlocked,
  nextDecisionIsDue,
  nextDecisionThreshold,
  readyToAdvance,
  renderDayClock,
  resetDayCycle,
  syncDayCycleForState,
} = await import("../../echo_adventure/ui/dayClock.js");
const {
  buildDailyDecisionGroups,
  hideDecisionChartTooltip,
  showDecisionChartTooltip,
} = await import("../../echo_adventure/ui/renderFinal.js");
const {
  closeNewRunModal,
  initDarkMode,
  openNewRunModal,
  renderSettingsMenu,
  toggleDarkMode,
  toggleSettingsMenu,
} = await import("../../echo_adventure/ui/modals.js");

function resetUiState() {
  Object.assign(uiState, {
    state: null,
    welcomeModalVisible: false,
    newRunModalVisible: false,
    decisionModalVisible: false,
    decisionModalDismissedKey: null,
    settingsMenuOpen: false,
    runCycleId: 0,
    dayCycleKey: null,
    dayCycleProgress: 0,
    dayCycleTimer: null,
    dayCycleLastTick: null,
    dayCycleAdvancing: false,
    dayCycleShiftInFlight: false,
    dayCycleCompletedShiftMarkers: new Set(),
    dayDecisionThresholdKey: null,
    dayDecisionThresholds: [],
    pendingAdvanceState: null,
    modalVisible: false,
    summaryAnimationKey: null,
    pendingChoice: null,
    metricSnapshot: null,
    metricDeltas: {},
    metricDeltaTimer: null,
  });
}

function statePayload(overrides = {}) {
  return {
    seed: 123,
    day: 1,
    currentDate: "December 23",
    gameOver: false,
    shiftsPerDay: 3,
    dayCycleDurationMs: 1000,
    snapshot: {
      shift: 0,
      jobsCompleted: 2,
      jobsRemaining: 4,
      piecesCompleted: 1,
      jobsBehindSchedule: 0,
      jobsLate: 0,
      scheduleRisk: 25,
    },
    pieces: [
      {
        id: "PIECE-01",
        displayId: "Job 01",
        completed: 1,
        total: 2,
        projectedCompletion: "December 24",
        dueDate: "December 25",
      },
      {
        id: "PIECE-02",
        displayId: "Job 02",
        completed: 0,
        total: 2,
        projectedCompletion: "December 26",
        dueDate: "December 27",
      },
    ],
    pastDueJobs: [],
    decisionProgress: { completed: 0, total: 0, visibleCards: 0, openCardIds: [] },
    decisions: [],
    criticalPath: [],
    ...overrides,
  };
}

beforeEach(() => {
  dom.reset();
  resetUiState();
  dom.element("decisionChartTooltip");
  hideDecisionChartTooltip({ force: true });
});

test("renderMetrics renders popovers and live deltas from runtime state", () => {
  dom.element("metrics");
  uiState.runCycleId = 1;
  uiState.state = statePayload();

  dom.setNow(1000);
  renderMetrics();

  assert.match(dom.element("metrics").innerHTML, /id="jobsMetricPopover"/);
  assert.match(dom.element("metrics").innerHTML, /id="subjobsBehindSchedulePopover"/);
  assert.doesNotMatch(dom.element("metrics").innerHTML, /metric-live-delta/);

  uiState.state = statePayload({
    snapshot: {
      ...uiState.state.snapshot,
      shift: 1,
      jobsCompleted: 3,
      jobsRemaining: 3,
      piecesCompleted: 2,
    },
  });

  dom.setNow(1200);
  renderMetrics();

  assert.match(dom.element("metrics").innerHTML, /metric-live-delta/);
  assert.match(dom.element("metrics").innerHTML, /\+1/);
  assert.match(dom.element("metrics").innerHTML, /2\/2/);

  dom.setNow(5000);
  renderMetrics();

  assert.doesNotMatch(dom.element("metrics").innerHTML, /metric-live-delta/);
});

test("dayClock builds deterministic thresholds and blocks decisions while modals are open", () => {
  uiState.runCycleId = 7;
  uiState.state = statePayload({
    decisionProgress: { completed: 0, total: 2, visibleCards: 2, openCardIds: ["CARD-1", "CARD-2"] },
    decisions: [
      { id: "CARD-1", selectedChoice: null },
      { id: "CARD-2", selectedChoice: null },
    ],
  });
  resetDayCycle();

  syncDayCycleForState();

  assert.equal(uiState.dayDecisionThresholds.length, 2);
  assert.equal(uiState.decisionModalVisible, false);
  assert.equal(uiState.decisionModalDismissedKey, null);
  assert.ok(nextDecisionThreshold() > 5);
  assert.ok(nextDecisionThreshold() < 94);
  assert.equal(readyToAdvance(), false);

  uiState.dayCycleProgress = nextDecisionThreshold();

  assert.equal(nextDecisionIsDue(), true);
  assert.equal(decisionModalBlocked(), false);

  uiState.welcomeModalVisible = true;
  assert.equal(decisionModalBlocked(), true);

  uiState.welcomeModalVisible = false;
  uiState.newRunModalVisible = true;
  assert.equal(decisionModalBlocked(), true);

  uiState.newRunModalVisible = false;
  uiState.state.decisionProgress = { completed: 2, total: 2, visibleCards: 2, openCardIds: [] };
  uiState.state.decisions = [
    { id: "CARD-1", selectedChoice: "A" },
    { id: "CARD-2", selectedChoice: "B" },
  ];

  assert.equal(readyToAdvance(), true);
  assert.match(renderDayClock("Paused for decision", true), /day-progress-fill paused/);
  uiState.dayCycleProgress = 100;
  assert.match(renderDayClock("Complete"), /day-progress-submarine" style="left:calc\(100% - 78px\)"/);
});

test("renderFinal decision chart tooltip locks and force-unlocks at runtime", () => {
  const tooltip = dom.element("decisionChartTooltip");
  tooltip.offsetWidth = 360;
  tooltip.offsetHeight = 240;
  const marker = dom.createElement("marker");
  marker.classList.add("chart-hover-zone");
  marker.dataset = {
    dateLabel: "December 24",
    label: "December 24",
    decisionCount: "1",
    playerChange: "+1.00",
    playerCumulative: "+2.00",
    echoChange: "+0.50",
    echoCumulative: "+1.50",
    decisions: JSON.stringify([
      {
        label: "Q1",
        questionTitle: "Route work",
        questionText: "Route work around a blocker?",
        playerChoice: "Reroute",
        echoChoice: "Expedite",
        playerDelta: "+1.00",
        echoDelta: "+0.50",
        affected: "JOB-01-001",
      },
    ]),
  };

  showDecisionChartTooltip({ clientX: 500, clientY: 320 }, marker);

  assert.equal(tooltip.classList.contains("active"), true);
  assert.equal(tooltip.classList.contains("locked"), false);
  assert.match(tooltip.innerHTML, /Click to lock this panel/);
  assert.match(tooltip.innerHTML, /Your answer:/);
  assert.match(tooltip.innerHTML, /ECHO chose/);
  assert.doesNotMatch(tooltip.innerHTML, /<dt>Question<\/dt>/);
  assert.doesNotMatch(tooltip.innerHTML, /Route work around a blocker/);

  document.dispatchEvent("click", {
    target: marker,
    preventDefault() {},
    stopPropagation() {},
  });

  assert.equal(tooltip.classList.contains("locked"), true);
  assert.match(tooltip.innerHTML, /Locked - click this day again to unlock/);

  hideDecisionChartTooltip();

  assert.equal(tooltip.classList.contains("active"), true);

  hideDecisionChartTooltip({ force: true });

  assert.equal(tooltip.classList.contains("active"), false);
  assert.equal(tooltip.classList.contains("locked"), false);
});

test("final score groups start both competitors at zero and preserve delayed payoffs", () => {
  const groups = buildDailyDecisionGroups([
    {
      sequence: 1,
      day: 1,
      dateLabel: "July 1",
      playerQuestionId: "PLAYER-1",
      echoQuestionId: "ECHO-1",
      playerDelta: 1,
      echoDelta: -1.5,
      playerCumulativeScore: 1,
      echoCumulativeScore: -1.5,
    },
    {
      sequence: 2,
      day: 2,
      dateLabel: "July 2",
      playerQuestionId: "PLAYER-2",
      echoQuestionId: "ECHO-2",
      playerDelta: 0.25,
      echoDelta: 3,
      playerCumulativeScore: 1.25,
      echoCumulativeScore: 1.5,
    },
  ]);

  assert.equal(groups[0].dateLabel, "Start");
  assert.equal(groups[0].playerCumulativeScore, 0);
  assert.equal(groups[0].echoCumulativeScore, 0);
  assert.equal(groups[1].echoCumulativeScore, -1.5);
  assert.equal(groups[2].echoCumulativeScore, 1.5);
});

test("modals and theme controls mutate browser-local UI state", () => {
  dom.element("settingsPanel");
  dom.element("settingsMenuBtn");
  dom.element("newRunModalOverlay");
  dom.element("themeMenuBtn");
  uiState.state = statePayload();
  localStorage.setItem("theme", "dark");

  initDarkMode();

  assert.equal(document.documentElement.getAttribute("data-theme"), "dark");
  assert.equal(dom.element("themeMenuBtn").textContent, "Light Mode");

  toggleSettingsMenu();

  assert.equal(uiState.settingsMenuOpen, true);
  assert.equal(dom.element("settingsPanel").classList.contains("active"), true);
  assert.equal(dom.element("settingsMenuBtn").getAttribute("aria-expanded"), "true");

  openNewRunModal();

  assert.equal(uiState.settingsMenuOpen, false);
  assert.equal(uiState.newRunModalVisible, true);
  assert.equal(dom.element("newRunModalOverlay").classList.contains("active"), true);

  closeNewRunModal();

  assert.equal(uiState.newRunModalVisible, false);
  assert.equal(dom.element("newRunModalOverlay").classList.contains("active"), false);

  toggleDarkMode();

  assert.equal(document.documentElement.getAttribute("data-theme"), "light");
  assert.equal(localStorage.getItem("theme"), "light");

  renderSettingsMenu();

  assert.equal(dom.element("settingsMenuBtn").getAttribute("aria-expanded"), "false");
});
