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
  "closeNewRunModalBtn", "cancelNewRunBtn", "startNewRunBtn", "settingsPanel",
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
      return { ...initialState, seed: path === "/api/new" ? 701 : 700 };
    },
  };
};

await import("../../echo_adventure/ui/app.js");
const { uiState } = await import("../../echo_adventure/ui/state.js");
await new Promise(resolve => globalThis.setTimeout(resolve, 0));

test("app bootstrap loads state, renders the shell, and exposes working global actions", async () => {
  assert.equal(calls[0].path, "/api/state");
  assert.equal(dom.element("dayBadge").textContent, "July 1");
  assert.equal(dom.element("welcomeModalOverlay").classList.contains("active"), true);
  assert.match(dom.element("welcomeBlurb").textContent, /all 2 jobs/);
  assert.match(dom.element("inlineDecisionBody").innerHTML, /data-timeline-actor="player"/);
  assert.equal(typeof window.startNewRun, "function");
  assert.equal(typeof window.submitDecision, "function");

  await window.startNewRun();

  assert.equal(calls.at(-1).path, "/api/new");
  assert.equal(calls.at(-1).options.method, "POST");
  assert.equal(dom.element("error").classList.contains("hidden"), true);
  assert.equal(dom.element("dayBadge").textContent, "July 1");

  uiState.newRunModalVisible = true;
  nextError = "new run failed";
  await window.startNewRun();
  assert.equal(dom.element("newRunError").textContent, "new run failed");
  assert.equal(dom.element("newRunError").classList.contains("hidden"), false);

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
});
