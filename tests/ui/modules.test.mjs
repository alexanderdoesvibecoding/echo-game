import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";

import { installDom } from "./domStub.mjs";

const dom = installDom();

const { api } = await import("../../echo_adventure/ui/api.js");
const { $, escapeHtml, fmtNum } = await import("../../echo_adventure/ui/html.js");
const { renderSubmarineImage, SUBMARINE_IMAGE_SRC } = await import("../../echo_adventure/ui/submarineVisual.js");
const { uiState } = await import("../../echo_adventure/ui/state.js");
const {
  renderSubmarinePuzzle,
  renderSummary,
  renderSummaryModal,
} = await import("../../echo_adventure/ui/renderSummary.js");
const {
  closeDecisionModal,
  openDecisionModal,
  renderDecisionModal,
  renderDecisions,
  renderInlineDecisions,
  selectPendingChoice,
} = await import("../../echo_adventure/ui/renderDecisions.js");
const { resetDayCycle, syncDayCycleForState } = await import("../../echo_adventure/ui/dayClock.js");

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
    pendingChoice: null,
    metricSnapshot: null,
    metricDeltas: {},
    metricDeltaTimer: null,
  });
}

function decisionState(overrides = {}) {
  return {
    seed: 456,
    day: 2,
    currentDate: "December 24",
    gameOver: false,
    shiftsPerDay: 3,
    dayCycleDurationMs: 1000,
    snapshot: { shift: 3 },
    decisionProgress: { completed: 0, total: 1, visibleCards: 1, openCardIds: ["CARD-1"] },
    decisions: [
      {
        id: "CARD-1",
        type: "Critical Path",
        title: "Two jobs need the same key fixture",
        description: "Route <urgent> work around a blocker.",
        context: "Job 04",
        severity: 4,
        selectedChoice: null,
        choices: [
          { id: "A", label: "Reroute now", description: "Move work to alternate capacity." },
          { id: "B", label: "Wait", description: "Hold the current queue." },
        ],
      },
    ],
    pieces: [],
    criticalPath: [],
    ...overrides,
  };
}

beforeEach(() => {
  dom.reset();
  resetUiState();
  globalThis.fetch = undefined;
});

test("api helper sends JSON headers and throws server error messages", async () => {
  const calls = [];
  globalThis.fetch = async (path, options) => {
    calls.push({ path, options });
    return {
      ok: path === "/ok",
      async json() {
        return path === "/ok" ? { route: "ok" } : { error: "bad request" };
      },
    };
  };

  assert.deepEqual(await api("/ok", { method: "POST", body: "{}" }), { route: "ok" });

  assert.equal(calls[0].path, "/ok");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers["content-type"], "application/json");

  await assert.rejects(() => api("/bad"), /bad request/);
});

test("html and submarine visual helpers escape attributes and render accessible images", () => {
  dom.element("target").textContent = "found";

  assert.equal($("target").textContent, "found");
  assert.equal(escapeHtml(`<tag attr="x">&'`), "&lt;tag attr=&quot;x&quot;&gt;&amp;&#039;");
  assert.equal(fmtNum(1234.7), "1,235");
  assert.equal(SUBMARINE_IMAGE_SRC, "/ui/assets/virginia-submarine-cutout.png");
  assert.match(
    renderSubmarineImage({ idPrefix: `sub"&`, className: "hero", ariaLabel: `Sub "&` }),
    /alt="Sub &quot;&amp;"/,
  );
  assert.match(
    renderSubmarineImage({ decorative: true }),
    /alt="" aria-hidden="true"/,
  );
});

test("renderSummary renders live and modal submarine puzzle state", () => {
  dom.element("summarySection");
  dom.element("summaryGrid");
  dom.element("summaryModalOverlay");
  dom.element("summaryModalBody");
  const puzzle = {
    tiles: [
      {
        id: "PIECE-01",
        label: "Job 01",
        name: "Job 01 - Aster",
        completed: true,
        newlyCompleted: true,
        completedAt: "December 24",
        due: "December 25",
      },
      {
        id: "PIECE-02",
        label: "Job 02",
        name: "Job 02 - Beacon",
        completed: false,
        newlyCompleted: false,
        due: "December 26",
      },
    ],
  };

  const puzzleMarkup = renderSubmarinePuzzle(puzzle, "unit-puzzle");

  assert.match(puzzleMarkup, /puzzle-image-slice placed newly-placed/);
  assert.match(puzzleMarkup, /puzzle-image-placeholder/);
  assert.match(puzzleMarkup, /puzzle-loose-row/);
  assert.match(puzzleMarkup, /Placed today:/);
  assert.match(puzzleMarkup, /virginia-submarine-cutout\.png/);

  uiState.state = {
    livePuzzle: puzzle,
    pieces: puzzle.tiles,
    lastSummary: null,
  };

  renderSummary();

  assert.equal(dom.element("summarySection").classList.contains("hidden"), false);
  assert.match(dom.element("summaryGrid").innerHTML, /live-submarine-panel/);

  uiState.modalVisible = true;
  uiState.pendingAdvanceState = {
    pieces: puzzle.tiles,
    lastSummary: {
      completedToday: 1,
      jobsRemaining: 3,
      piecesCompleted: 1,
      jobsBehindSchedule: 1,
      jobsLate: 0,
      risk: 42,
      projectedCompletion: "December 27",
      notes: ["Completed <one> subjob."],
      puzzle,
    },
  };

  renderSummaryModal();

  assert.equal(dom.element("summaryModalOverlay").classList.contains("active"), true);
  assert.match(dom.element("summaryModalBody").innerHTML, /Subjobs Today/);
  assert.match(dom.element("summaryModalBody").innerHTML, /Completed &lt;one&gt; subjob\./);
});

test("renderDecisions controls inline state, modal selection, and dismissal", () => {
  dom.element("advanceBtn");
  dom.element("inlineDecisionBody");
  dom.element("decisionModalOverlay");
  dom.element("decisionModalTitle");
  dom.element("decisionModalMeta");
  dom.element("decisionModalBody");
  dom.element("decisionModalFooter");
  uiState.runCycleId = 2;
  uiState.state = decisionState();
  resetDayCycle();
  syncDayCycleForState();

  renderDecisions();

  assert.equal(dom.element("advanceBtn").disabled, true);

  renderInlineDecisions();

  assert.match(dom.element("inlineDecisionBody").innerHTML, /Schedule In Motion/);
  assert.doesNotMatch(dom.element("inlineDecisionBody").innerHTML, /Respond/);

  uiState.dayCycleProgress = 100;

  renderInlineDecisions();

  assert.match(dom.element("inlineDecisionBody").innerHTML, /Decision Event/);
  assert.match(dom.element("inlineDecisionBody").innerHTML, /Respond/);

  openDecisionModal();

  assert.equal(uiState.decisionModalVisible, true);
  assert.equal(dom.element("decisionModalOverlay").classList.contains("active"), true);
  assert.match(dom.element("decisionModalTitle").innerHTML, /Two jobs need the same key fixture/);
  assert.equal(dom.element("decisionModalTitle").getAttribute("aria-label"), "Two jobs need the same key fixture");
  assert.match(dom.element("decisionModalTitle").innerHTML, /decision-icon-svg/);
  assert.equal(dom.element("decisionModalMeta").textContent, "Impact: Job 04");
  assert.match(dom.element("decisionModalBody").innerHTML, /Reroute now/);
  assert.match(dom.element("decisionModalBody").innerHTML, /choice-icon/);
  assert.doesNotMatch(dom.element("decisionModalBody").innerHTML, /Route &lt;urgent&gt; work/);
  assert.doesNotMatch(dom.element("decisionModalBody").innerHTML, /Affected area:/);
  assert.doesNotMatch(dom.element("decisionModalBody").innerHTML, /Elevated urgency/);
  assert.doesNotMatch(dom.element("decisionModalBody").innerHTML, /Open/);
  assert.match(dom.element("decisionModalFooter").innerHTML, /disabled/);

  selectPendingChoice("A");

  assert.equal(uiState.pendingChoice, "A");
  assert.match(dom.element("decisionModalBody").innerHTML, /aria-checked="true"/);
  assert.match(dom.element("decisionModalFooter").innerHTML, /Confirm decision/);
  assert.doesNotMatch(dom.element("decisionModalFooter").innerHTML, /disabled/);

  closeDecisionModal();

  assert.equal(uiState.decisionModalVisible, false);
  assert.equal(uiState.decisionModalDismissedKey, "2:CARD-1");

  uiState.state.decisionProgress = { completed: 1, total: 1, visibleCards: 1, openCardIds: [] };
  uiState.state.decisions[0].selectedChoice = "A";

  renderDecisions();

  assert.equal(dom.element("advanceBtn").disabled, false);

  renderDecisionModal();

  assert.equal(uiState.decisionModalDismissedKey, null);
});
