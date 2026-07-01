let state = null;
// Client-side modal state is intentionally local. The server remains the
// source of truth for the run, decisions, and day advancement rules.
let welcomeModalVisible = false;
let newRunModalVisible = false;
let decisionModalVisible = false;
let decisionModalDismissedKey = null;
let settingsMenuOpen = false;
let runCycleId = 0;
let dayCycleKey = null;
let dayCycleProgress = 0;
let dayCycleTimer = null;
let dayCycleLastTick = null;
let dayCycleAdvancing = false;
let dayCycleShiftInFlight = false;
let dayCycleCompletedShiftMarkers = new Set();
let dayDecisionThresholdKey = null;
let dayDecisionThresholds = [];

const DAY_CYCLE_DURATION_MS = 28000;
const DAY_CYCLE_TICK_MS = 220;

const $ = (id) => document.getElementById(id);
const fmtNum = (value) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });

async function api(path, options = {}) {
  // All API endpoints return JSON, including errors. Throwing here keeps
  // button handlers small and centralizes user-facing error display.
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function showError(message) {
  const box = $("error");
  if (!message) {
    box.classList.add("hidden");
    box.textContent = "";
    return;
  }
  box.textContent = message;
  box.classList.remove("hidden");
}

function showNewRunError(message) {
  const box = $("newRunError");
  if (!box) return;
  if (!message) {
    box.classList.add("hidden");
    box.textContent = "";
    return;
  }
  box.textContent = message;
  box.classList.remove("hidden");
}

async function loadState() {
  try {
    state = await api("/api/state");
    showError("");
    render();
  } catch (error) {
    dayCycleAdvancing = false;
    showError(error.message);
  }
}

async function startNewRun() {
  try {
    state = await api("/api/new", {
      method: "POST",
      body: JSON.stringify({})
    });
    runCycleId += 1;
    resetDayCycle();
    pendingChoice = null;
    decisionModalVisible = false;
    decisionModalDismissedKey = null;
    welcomeModalVisible = true;
    newRunModalVisible = false;
    showNewRunError("");
    showError("");
    render();
  } catch (error) {
    if (newRunModalVisible) {
      showNewRunError(error.message);
    } else {
      showError(error.message);
    }
  }
}

async function choose(cardId, choiceId, renderAfter = true) {
  try {
    state = await api("/api/choice", {
      method: "POST",
      body: JSON.stringify({ cardId, choiceId })
    });
    pendingChoice = null;
    decisionModalVisible = false;
    decisionModalDismissedKey = null;
    showError("");
    if (renderAfter) {
      render();
    }
    return state;
  } catch (error) {
    showError(error.message);
    return null;
  }
}

// Holds the server-advanced state while the player reads the daily summary.
let pendingAdvanceState = null;

async function prepareAdvanceDay() {
  // The button should already be disabled until all decisions are complete,
  // but this guard keeps direct console calls and stale UI state honest.
  if (!readyToAdvance()) {
    dayCycleAdvancing = false;
    document.getElementById("dailyDecisionSection")?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  try {
    const nextState = await api("/api/advance", { method: "POST", body: "{}" });
    showError("");
    pendingAdvanceState = nextState;
    if (nextState.finalReveal) {
      state = nextState;
      pendingAdvanceState = null;
      modalVisible = false;
    } else {
      modalVisible = true;
    }
    render();
  } catch (error) {
    showError(error.message);
  }
}

function commitAdvanceDay() {
  if (!pendingAdvanceState) {
    return;
  }
  state = pendingAdvanceState;
  pendingAdvanceState = null;
  modalVisible = false;
  render();
}

// These flags are purely presentation state. The authoritative simulation
// state always comes from the server payload in `state`.
let modalVisible = false;
let pendingChoice = null;

function render() {
  if (!state) return;
  syncDayCycleForState();
  $("dayBadge").textContent = `Day ${state.day}`;
  $("projectedText").textContent = `Projected completion: ${state.projectedCompletion}`;

  renderMetrics();
  renderDecisions();
  renderInlineDecisions();
  renderSummary();
  renderSummaryModal();
  renderFinal();
  renderWelcomeModal();
  renderNewRunModal();
  renderDecisionModal();
  renderSettingsMenu();
}

function decisionProgress() {
  if (!state) {
    return { completed: 0, total: 0, visibleCards: 0, openCardIds: [] };
  }
  return state.decisionProgress || { completed: 0, total: 0, visibleCards: 0, openCardIds: [] };
}

function readyToAdvance() {
  const progress = decisionProgress();
  return Boolean(state && !state.gameOver && (progress.total === 0 || progress.completed === progress.total));
}

function resetDayCycle() {
  dayCycleKey = null;
  dayCycleProgress = 0;
  dayCycleLastTick = null;
  dayCycleAdvancing = false;
  dayCycleShiftInFlight = false;
  dayCycleCompletedShiftMarkers = new Set();
  dayDecisionThresholdKey = null;
  dayDecisionThresholds = [];
}

function syncDayCycleForState() {
  if (!state || state.gameOver) {
    stopDayCycle();
    return;
  }

  const nextKey = `${runCycleId}:${state.day}`;
  if (dayCycleKey !== nextKey) {
    dayCycleKey = nextKey;
    dayCycleProgress = 0;
    dayCycleLastTick = null;
    dayCycleAdvancing = false;
    dayCycleShiftInFlight = false;
    dayCycleCompletedShiftMarkers = completedShiftMarkersFromState();
    dayCycleProgress = Math.max(dayCycleProgress, (completedShiftCountFromState() / shiftsPerDay()) * 100);
    dayDecisionThresholdKey = null;
    dayDecisionThresholds = [];
    decisionModalVisible = false;
    decisionModalDismissedKey = null;
  }
  syncDecisionThresholdsForState();
  ensureDayCycle();
}

function ensureDayCycle() {
  if (dayCycleTimer) return;
  dayCycleLastTick = performance.now();
  dayCycleTimer = window.setInterval(tickDayCycle, DAY_CYCLE_TICK_MS);
}

function stopDayCycle() {
  if (dayCycleTimer) {
    window.clearInterval(dayCycleTimer);
    dayCycleTimer = null;
  }
  dayCycleLastTick = null;
}

function nextDecisionThreshold() {
  const progressState = decisionProgress();
  if (!progressState.total) return 100;
  syncDecisionThresholdsForState();
  const threshold = dayDecisionThresholds[progressState.completed];
  if (Number.isFinite(threshold)) return threshold;
  return ((progressState.completed + 1) / (progressState.total + 1)) * 100;
}

function syncDecisionThresholdsForState() {
  if (!state || state.gameOver) {
    dayDecisionThresholdKey = null;
    dayDecisionThresholds = [];
    return;
  }
  const progressState = decisionProgress();
  const cardIds = Array.isArray(state.decisions)
    ? state.decisions.map(card => card.id).join("|")
    : "";
  const nextKey = `${state.seed ?? "seedless"}:${state.day}:${progressState.total}:${cardIds}`;
  if (dayDecisionThresholdKey === nextKey) return;
  dayDecisionThresholdKey = nextKey;
  dayDecisionThresholds = buildDecisionThresholds(progressState.total, nextKey);
}

function buildDecisionThresholds(total, seedText) {
  const count = Math.max(0, Math.floor(Number(total) || 0));
  if (!count) return [];
  const random = seededRandomFactory(seedText);
  if (count === 1) {
    return [randomBetween(random, 24, 76)];
  }

  const edgeBuffer = 7;
  const minimumGap = count >= 5 ? 8 : 10;
  const baseUsed = edgeBuffer * 2 + minimumGap * Math.max(0, count - 1);
  const remaining = Math.max(0, 100 - baseUsed);
  const weights = Array.from({ length: count + 1 }, () => 0.25 + random() * 1.5);
  const weightTotal = weights.reduce((sum, weight) => sum + weight, 0) || 1;
  const extras = weights.map(weight => remaining * (weight / weightTotal));
  const thresholds = [];
  let cursor = edgeBuffer + extras[0];

  for (let index = 0; index < count; index += 1) {
    if (index > 0) {
      cursor += minimumGap + extras[index];
    }
    thresholds.push(Math.max(5, Math.min(94, Number(cursor.toFixed(1)))));
  }
  return thresholds;
}

function seededRandomFactory(seedText) {
  let seed = 2166136261;
  const text = String(seedText || "decision-thresholds");
  for (let index = 0; index < text.length; index += 1) {
    seed ^= text.charCodeAt(index);
    seed = Math.imul(seed, 16777619);
  }
  seed >>>= 0;
  return () => {
    seed += 0x6D2B79F5;
    let value = seed;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function randomBetween(random, minimum, maximum) {
  return Number((minimum + random() * (maximum - minimum)).toFixed(1));
}

function nextDecisionIsDue() {
  return Boolean(currentOpenDecisionCard() && dayCycleProgress >= nextDecisionThreshold());
}

function dayCycleBlocked() {
  return !state
    || state.gameOver
    || welcomeModalVisible
    || newRunModalVisible
    || decisionModalVisible
    || dayCycleShiftInFlight
    || nextDecisionIsDue()
    || (modalVisible && pendingAdvanceState);
}

function tickDayCycle() {
  if (!state || state.gameOver) {
    stopDayCycle();
    return;
  }

  const now = performance.now();
  const lastTick = dayCycleLastTick ?? now;
  const elapsed = now - lastTick;
  dayCycleLastTick = now;

  if (!dayCycleBlocked()) {
    dayCycleProgress = Math.min(100, dayCycleProgress + (elapsed / DAY_CYCLE_DURATION_MS) * 100);
  }

  if (nextDecisionIsDue()) {
    const nextCard = currentOpenDecisionCard();
    const key = decisionModalKey(nextCard);
    if (nextCard && decisionModalDismissedKey !== key) {
      if (decisionModalVisible) {
        return;
      }
      decisionModalVisible = true;
      render();
      return;
    }
  }

  const shiftMarker = nextShiftMarkerDue();
  if (shiftMarker && !dayCycleShiftInFlight && !(modalVisible && pendingAdvanceState)) {
    advanceShift(shiftMarker);
    return;
  }

  if (dayCycleProgress >= 100 && readyToAdvance() && !dayCycleAdvancing && !dayCycleShiftInFlight && !(modalVisible && pendingAdvanceState)) {
    dayCycleAdvancing = true;
    renderInlineDecisions();
    prepareAdvanceDay();
    return;
  }

  renderInlineDecisions();
}

function dayCyclePercent() {
  return Math.max(0, Math.min(100, dayCycleProgress));
}

function shiftsPerDay() {
  return Math.max(1, Number(state?.shiftsPerDay || 3));
}

function nextShiftMarkerDue() {
  const count = shiftsPerDay();
  for (let marker = 1; marker < count; marker += 1) {
    if (!dayCycleCompletedShiftMarkers.has(marker) && dayCycleProgress >= (marker / count) * 100) {
      return marker;
    }
  }
  return null;
}

function completedShiftMarkersFromState() {
  const count = shiftsPerDay();
  const completedInDay = completedShiftCountFromState();
  const markers = new Set();
  for (let marker = 1; marker <= Math.min(completedInDay, count - 1); marker += 1) {
    markers.add(marker);
  }
  return markers;
}

function completedShiftCountFromState() {
  return Math.max(0, Number(state?.snapshot?.shift || 0) % shiftsPerDay());
}

async function advanceShift(marker) {
  dayCycleShiftInFlight = true;
  dayCycleCompletedShiftMarkers.add(marker);
  try {
    const nextState = await api("/api/shift", { method: "POST", body: "{}" });
    showError("");
    if (nextState.finalReveal) {
      state = nextState;
      pendingAdvanceState = null;
      modalVisible = false;
    } else if (nextState.shiftAdvance?.dayComplete) {
      pendingAdvanceState = nextState;
      modalVisible = true;
    } else {
      state = nextState;
    }
    render();
  } catch (error) {
    dayCycleCompletedShiftMarkers.delete(marker);
    showError(error.message);
  } finally {
    dayCycleShiftInFlight = false;
  }
}

function renderDayClock(statusText, paused = false) {
  const percent = dayCyclePercent();
  return `
    <div class="day-clock">
      <div class="day-clock-row">
        <span>${escapeHtml(statusText)}</span>
        <span>${Math.round(percent)}%</span>
      </div>
      <div class="day-progress-track" aria-label="Day progress">
        <div class="day-progress-fill ${paused ? "paused" : ""}" style="width:${percent}%"></div>
      </div>
    </div>
  `;
}

function currentOpenDecisionCard() {
  return Array.isArray(state?.decisions)
    ? state.decisions.find(card => !card.selectedChoice) || null
    : null;
}

function decisionModalKey(card) {
  return state && card ? `${state.day}:${card.id}` : "";
}

function decisionModalBlocked() {
  return !state
    || state.gameOver
    || welcomeModalVisible
    || newRunModalVisible
    || !nextDecisionIsDue()
    || (modalVisible && pendingAdvanceState);
}

function openDecisionModal() {
  const nextCard = currentOpenDecisionCard();
  if (!nextCard) return;
  if (!nextCard.choices.some(choice => choice.id === pendingChoice)) {
    pendingChoice = null;
  }
  decisionModalDismissedKey = null;
  decisionModalVisible = true;
  renderDecisionModal();
}

function closeDecisionModal() {
  const nextCard = currentOpenDecisionCard();
  if (nextCard) {
    decisionModalDismissedKey = decisionModalKey(nextCard);
  }
  decisionModalVisible = false;
  renderInlineDecisions();
  renderDecisionModal();
}

async function submitDecision(cardId) {
  if (!pendingChoice) return;
  const choiceId = pendingChoice;
  await choose(cardId, choiceId);
}

function selectPendingChoice(choiceId) {
  pendingChoice = choiceId;
  renderInlineDecisions();
  renderDecisionModal();
}

function renderWelcomeModal() {
  const overlay = document.getElementById("welcomeModalOverlay");
  if (!overlay) return;
  renderWelcomeContent();
  overlay.classList.toggle("active", welcomeModalVisible);
}

function renderWelcomeContent() {
  const blurb = $("welcomeBlurb");
  const list = $("welcomeCriticalPath");
  if (!blurb || !list) return;

  const jobCount = Array.isArray(state?.pieces) ? state.pieces.length : 0;
  const jobText = jobCount ? `${jobCount} job${jobCount === 1 ? "" : "s"}` : "jobs";
  blurb.textContent = `Your job is to get these ${jobText} done on time. Each decision you make can risk or reward other jobs.`;

  const criticalRows = Array.isArray(state?.criticalPath) ? state.criticalPath : [];
  list.innerHTML = criticalRows.length
    ? criticalRows.map(job => `
      <li>
        <strong>${escapeHtml(job.id)} - ${escapeHtml(job.impact || "Job")}</strong>
        <span>${escapeHtml(job.shop || "-")} - ${Number(job.remaining || 0)} shift${Number(job.remaining || 0) === 1 ? "" : "s"} left - slack ${escapeHtml(job.slack ?? "-")}</span>
      </li>
    `).join("")
    : `<li><strong>No critical path jobs yet</strong><span>The first schedule pass is still loading.</span></li>`;
}

function closeWelcomeModal() {
  welcomeModalVisible = false;
  renderWelcomeModal();
  renderDecisionModal();
}

function toggleSettingsMenu() {
  settingsMenuOpen = !settingsMenuOpen;
  renderSettingsMenu();
}

function closeSettingsMenu() {
  settingsMenuOpen = false;
  renderSettingsMenu();
}

function renderSettingsMenu() {
  const panel = $("settingsPanel");
  const button = $("settingsMenuBtn");
  if (!panel || !button) return;
  panel.classList.toggle("active", settingsMenuOpen);
  button.setAttribute("aria-expanded", settingsMenuOpen ? "true" : "false");
}

function openNewRunModal() {
  closeSettingsMenu();
  newRunModalVisible = true;
  showNewRunError("");
  renderNewRunModal();
  renderDecisionModal();
}

function closeNewRunModal() {
  newRunModalVisible = false;
  showNewRunError("");
  renderNewRunModal();
  renderDecisionModal();
}

function renderNewRunModal() {
  const overlay = $("newRunModalOverlay");
  if (!overlay) return;
  overlay.classList.toggle("active", newRunModalVisible);
}

function renderPastDueJobs(pastDueJobs) {
  if (!pastDueJobs || pastDueJobs.length === 0) {
    return `<p class="subtle">No past due subjobs.</p>`;
  }

  return `
    <table>
      <thead>
        <tr>
          <th>Subjob</th>
          <th>Shop</th>
          <th>Due</th>
          <th>Late</th>
          <th>Remaining</th>
        </tr>
      </thead>
      <tbody>
        ${pastDueJobs.map(job => `
          <tr>
            <td>${escapeHtml(job.id)}</td>
            <td>${escapeHtml(job.shop)}</td>
            <td>${escapeHtml(job.due)}</td>
            <td>${job.daysLate} day${job.daysLate === 1 ? "" : "s"}</td>
            <td>${job.remaining} shift${job.remaining === 1 ? "" : "s"}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderSummaryStatsTable(summary, piecesTotal) {
  return `
    <table>
      <tbody>
        <tr><td>Subjobs completed today</td><td>${summary.completedToday}</td></tr>
        <tr><td>Subjobs remaining</td><td>${summary.jobsRemaining}</td></tr>
        <tr><td>Jobs complete</td><td>${summary.piecesCompleted}/${piecesTotal}</td></tr>
        <tr><td>Subjobs behind schedule</td><td>${summary.jobsBehindSchedule}</td></tr>
        <tr><td>Subjobs late</td><td>${summary.jobsLate}</td></tr>
        <tr><td>Risk</td><td>${Math.round(summary.risk)}/100</td></tr>
        <tr><td>Projected completion</td><td>${summary.projectedCompletion}</td></tr>
      </tbody>
    </table>
  `;
}

function renderSummaryGrid(summary, piecesTotal, puzzleInstanceId) {
  const notesMarkup = (summary.notes || [])
    .map(note => `<li>${escapeHtml(note)}</li>`)
    .join("") || "<li>No notable notes recorded.</li>";
  return `
    <div class="summary-main-column">
      <div class="reveal-panel summary-puzzle-panel">
        ${renderSubmarinePuzzle(summary.puzzle, puzzleInstanceId)}
      </div>
    </div>
    <div class="summary-side-column">
      <div class="reveal-panel summary-stats-panel">
        <h3>Stats</h3>
        <div class="summary-table-scroll">${renderSummaryStatsTable(summary, piecesTotal)}</div>
      </div>
      <div class="reveal-panel summary-updates-panel">
        <h3>Updates</h3>
        <ul class="notes">${notesMarkup}</ul>
      </div>
      <div class="reveal-panel summary-past-due-panel">
        <h3>Past Due Subjobs</h3>
        <div class="summary-table-scroll">${renderPastDueJobs(summary.pastDueJobs)}</div>
      </div>
    </div>
  `;
}

function submarinePieceSlots(total) {
  if (total <= 0) return [];
  const n = (value) => Number(value).toFixed(1);
  const hullTop = (x) => 154 + Math.pow(Math.abs(x - 350) / 230, 1.75) * 19;
  const hullBottom = (x) => 286 - Math.pow(Math.abs(x - 350) / 230, 1.75) * 19;
  const wholePath = "M 70 220 C 70 138, 184 144, 365 144 C 630 144, 730 174, 730 220 C 730 266, 630 296, 365 296 C 184 296, 70 302, 70 220 Z";
  const tailSlot = () => ({
    part: "tail section",
    path: "M 126 188 L 66 166 L 84 220 L 66 274 L 126 252 L 150 220 Z",
    centerX: 106,
    centerY: 220,
    labelY: 222,
    labelSize: 10,
    details: [],
  });
  const noseSlot = () => ({
    part: "front section",
    path: "M 570 172 C 660 172 724 188 738 220 C 724 252 660 268 570 268 Z",
    centerX: 640,
    centerY: 220,
    labelY: 241,
    labelSize: 11,
    details: [`<circle class="piece-detail-fill" cx="640" cy="209" r="12"></circle>`],
  });
  const sailSlot = () => ({
    part: "sail and mast",
    path: "M 340 154 L 354 90 L 424 90 L 438 154 Z",
    centerX: 389,
    centerY: 124,
    labelY: 128,
    labelSize: 10,
    details: [
      `<path class="piece-detail" d="M 376 90 L 376 68 L 390 68 M 408 90 L 408 72"></path>`,
    ],
  });
  const bodySlot = (index, count) => {
    const startX = 130;
    const endX = 570;
    const width = (endX - startX) / count;
    const x1 = startX + index * width;
    const x2 = index === count - 1 ? endX : startX + (index + 1) * width;
    const top1 = hullTop(x1);
    const top2 = hullTop(x2);
    const bottom1 = hullBottom(x1);
    const bottom2 = hullBottom(x2);
    const curve = Math.max(18, width * 0.32);
    const path = [
      `M ${n(x1)} ${n(top1)}`,
      `C ${n(x1 + curve)} ${n(top1 - 8)} ${n(x2 - curve)} ${n(top2 - 8)} ${n(x2)} ${n(top2)}`,
      `L ${n(x2)} ${n(bottom2)}`,
      `C ${n(x2 - curve)} ${n(bottom2 + 8)} ${n(x1 + curve)} ${n(bottom1 + 8)} ${n(x1)} ${n(bottom1)}`,
      "Z",
    ].join(" ");
    const portholes = [218, 282, 456, 520]
      .filter((x) => x > x1 + 16 && x < x2 - 16)
      .map((x) => `<circle class="piece-detail-fill" cx="${x}" cy="207" r="12"></circle>`);
    let part = "middle hull";
    if (count === 1) part = "main hull";
    else if (index === 0) part = "aft hull";
    else if (index === count - 1) part = "forward hull";
    else part = `middle hull ${index}`;
    return {
      part,
      path,
      centerX: (x1 + x2) / 2,
      centerY: (top1 + top2 + bottom1 + bottom2) / 4,
      labelY: portholes.length ? 242 : 222,
      labelSize: Math.max(9, Math.min(12, width * 0.13)),
      details: portholes,
    };
  };

  if (total === 1) {
    return [{
      part: "submarine",
      path: wholePath,
      centerX: 400,
      centerY: 220,
      labelY: 222,
      labelSize: 13,
      details: [],
    }];
  }
  if (total === 2) {
    return [tailSlot(), noseSlot()];
  }
  if (total === 3) {
    return [
      bodySlot(0, 1),
      noseSlot(),
      sailSlot(),
    ];
  }

  const bodyCount = Math.max(1, total - 3);
  const slots = [tailSlot()];
  for (let index = 0; index < bodyCount; index += 1) {
    slots.push(bodySlot(index, bodyCount));
  }
  slots.push(noseSlot(), sailSlot());
  return slots.slice(0, total);
}

function loosePieceColumnCount(total) {
  if (total <= 3) return 1;
  if (total <= 8) return 4;
  return 5;
}

function loosePieceRows(total) {
  if (total <= 0) return 0;
  return Math.ceil(total / loosePieceColumnCount(total));
}

function loosePieceStageHeight(total) {
  const rows = loosePieceRows(total);
  return rows ? 550 + (rows - 1) * 170 : 500;
}

function loosePiecePosition(index, total) {
  const columns = loosePieceColumnCount(total);
  const column = index % columns;
  const row = Math.floor(index / columns);
  const laneWidth = 800 / columns;
  const angles = [-7, 5, -4, 7, -5];
  return {
    x: columns === 1 ? 400 : laneWidth * column + laneWidth / 2,
    y: 420 + row * 170,
    angle: angles[index % angles.length],
  };
}

function renderPuzzleSection(tile, slot, className, transform = "") {
  const label = escapeHtml(tile.label || tile.id || "");
  const assembled = className === "placed";
  const status = assembled
    ? `Assembled${tile.completedAt ? ` at ${tile.completedAt}` : ""}`
    : `Waiting outside${tile.due ? `; due ${tile.due}` : ""}`;
  const title = `${tile.name || tile.id}: ${slot.part}. ${status}.`;
  const transformAttr = transform ? ` transform="${transform}"` : "";
  const newlyPlaced = assembled && tile.newlyCompleted ? " newly-placed" : "";
  const labelFill = assembled ? "#ffffff" : "var(--ink)";
  return `
    <g class="puzzle-section ${className}"${transformAttr}>
      <path class="puzzle-piece ${className}${newlyPlaced}" d="${slot.path}">
        <title>${escapeHtml(title)}</title>
      </path>
      ${(slot.details || []).join("")}
      <text class="puzzle-label" x="${slot.centerX.toFixed(1)}" y="${(slot.labelY || slot.centerY).toFixed(1)}" font-size="${(slot.labelSize || 11).toFixed(1)}" fill="${labelFill}">${label}</text>
    </g>
  `;
}

function renderSubmarinePuzzle(puzzle, instanceId) {
  const tiles = Array.isArray(puzzle?.tiles) ? puzzle.tiles : [];
  if (!tiles.length) return "";

  const total = tiles.length;
  const width = 800;
  const slots = submarinePieceSlots(total);
  const unplacedItems = tiles
    .map((tile, index) => ({ tile, index, slot: slots[index] }))
    .filter((item) => !item.tile.completed);
  const height = loosePieceStageHeight(unplacedItems.length);
  const slotMarkup = slots.map((slot) => `
    <path class="puzzle-slot" d="${slot.path}">
      <title>${escapeHtml(`${slot.part} slot`)}</title>
    </path>
  `).join("");
  const placedMarkup = tiles.map((tile, index) => (
    tile.completed ? renderPuzzleSection(tile, slots[index], "placed") : ""
  )).join("");
  const unplacedMarkup = unplacedItems
    .map((item, looseIndex) => {
      const position = loosePiecePosition(looseIndex, unplacedItems.length);
      const dx = position.x - item.slot.centerX;
      const dy = position.y - item.slot.centerY;
      const transform = `translate(${dx.toFixed(1)} ${dy.toFixed(1)}) rotate(${position.angle} ${item.slot.centerX.toFixed(1)} ${item.slot.centerY.toFixed(1)})`;
      return renderPuzzleSection(item.tile, item.slot, "unplaced", transform);
    }).join("");
  const placedToday = tiles.filter(tile => tile.completed && tile.newlyCompleted);
  const placedMarkupToday = placedToday.length
    ? placedToday.map(tile => `<span class="badge">${escapeHtml(tile.label)}</span>`).join("")
    : `<span class="subtle">No jobs were placed today.</span>`;

  return `
    <div class="submarine-puzzle">
      <div class="puzzle-caption">
        <strong>Assembly</strong>
      </div>
      <div class="puzzle-stage">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Submarine puzzle showing assembled and waiting sections">
          <g aria-hidden="true">${slotMarkup}</g>
          <g>${placedMarkup}</g>
          <g>${unplacedMarkup}</g>
        </svg>
      </div>
      <div class="puzzle-added"><span>Placed today:</span>${placedMarkupToday}</div>
    </div>
  `;
}

function renderSummaryModal() {
  const payload = pendingAdvanceState || state;
  const summary = payload.lastSummary;
  const overlay = document.getElementById("summaryModalOverlay");
  const body = document.getElementById("summaryModalBody");
  if (!overlay || !body) return;
  if (!summary || !modalVisible) {
    overlay.classList.remove("active");
    return;
  }
  // The day has already been simulated on the server, but the summary modal
  // lets the player read consequences before committing that state locally.
  overlay.classList.add("active");
  body.innerHTML = `<div class="summary-grid">${renderSummaryGrid(summary, payload.pieces.length, "summary-modal")}</div>`;
  body.scrollTop = 0;
}

function renderCompletionChart(history) {
  const decisionPoints = Array.isArray(history?.decisionPoints) ? history.decisionPoints : [];
  const count = decisionPoints.length;
  if (!count) return `<div class="subtle">No decision score history recorded.</div>`;

  const width = 640;
  const height = 260;
  const pad = { left: 54, right: 18, top: 18, bottom: 42 };
  const formatImpact = (value) => {
    const number = Number(value) || 0;
    return `${number >= 0 ? "+" : ""}${number.toFixed(2)}`;
  };
  const playerImpact = decisionPoints.map(decisionPoint => Number(decisionPoint.playerDelta) || 0);
  const echoImpact = decisionPoints.map(decisionPoint => Number(decisionPoint.echoDelta) || 0);
  const rawMin = Math.min(0, ...playerImpact, ...echoImpact);
  const rawMax = Math.max(0, ...playerImpact, ...echoImpact);
  const scoreSpan = Math.max(1, rawMax - rawMin);
  const minScore = rawMin - scoreSpan * 0.15;
  const maxScore = rawMax + scoreSpan * 0.15;
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const point = (value, index) => {
    const x = count === 1 ? pad.left + plotWidth / 2 : pad.left + (index / (count - 1)) * plotWidth;
    const y = pad.top + ((maxScore - value) / (maxScore - minScore)) * plotHeight;
    return [x, y];
  };
  const pathFor = (series) => series.slice(0, count).map((value, index) => {
    const [x, y] = point(Number(value) || 0, index);
    return `${index ? "L" : "M"} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const yTicks = rawMin === rawMax
    ? [-1, 0, 1]
    : [...new Set([rawMin, 0, rawMax].map(value => Number(value.toFixed(2))))].sort((a, b) => a - b);
  const xTicks = count <= 3
    ? Array.from({ length: count }, (_, index) => index)
    : [...new Set([0, Math.floor((count - 1) / 2), count - 1])];
  const yGrid = yTicks.map(value => {
    const [, y] = point(value, 0);
    return `
      <line class="chart-grid" x1="${pad.left}" y1="${y.toFixed(1)}" x2="${(width - pad.right).toFixed(1)}" y2="${y.toFixed(1)}"></line>
      <text class="chart-label" x="${pad.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end">${formatImpact(value)}</text>
    `;
  }).join("");
  const xLabels = xTicks.map(index => {
    const [x] = point(0, index);
    const sequence = Number(decisionPoints[index]?.sequence || index + 1);
    const label = `Q${sequence}`;
    return `<text class="chart-label" x="${x.toFixed(1)}" y="${height - 12}" text-anchor="middle">${escapeHtml(label)}</text>`;
  }).join("");
  const decisionAttrs = (decisionPoint, series) => `
    tabindex="0"
    data-series="${escapeHtml(series)}"
    data-day="${escapeHtml(decisionPoint.day || "-")}"
    data-question="${escapeHtml(decisionPoint.questionTitle || decisionPoint.questionText || decisionPoint.questionId || "-")}"
    data-player-choice="${escapeHtml(decisionPoint.playerChoice || "-")}"
    data-echo-choice="${escapeHtml(decisionPoint.echoChoice || "-")}"
    data-player-impact="${escapeHtml(formatImpact(decisionPoint.playerDelta))}"
    data-echo-impact="${escapeHtml(formatImpact(decisionPoint.echoDelta))}"
    data-player-cumulative="${escapeHtml(formatImpact(decisionPoint.playerCumulativeScore))}"
    data-echo-cumulative="${escapeHtml(formatImpact(decisionPoint.echoCumulativeScore))}"
    data-affected="${escapeHtml(decisionPoint.affectedLabel || "-")}"
    onmousemove="showDecisionChartTooltip(event, this)"
    onmouseleave="hideDecisionChartTooltip()"
    onfocus="showDecisionChartTooltip(event, this)"
    onblur="hideDecisionChartTooltip()"
  `;
  const decisionMarker = (decisionPoint, series, index) => {
    const values = series === "Player" ? playerImpact : echoImpact;
    const value = Number(values[index]) || 0;
    const [x, y] = point(value, index);
    if (series === "Player") {
      return `
        <circle class="chart-dot chart-player-dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.8" fill="var(--teal)" stroke="#fff" stroke-width="1.4" ${decisionAttrs(decisionPoint, series)}></circle>
      `;
    }
    return `
      <circle class="chart-dot chart-echo-dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5.6" fill="var(--panel)" stroke="var(--violet)" stroke-width="2.2" ${decisionAttrs(decisionPoint, series)}></circle>
    `;
  };

  return `
    <div class="completion-chart">
      <div class="chart-legend">
        <span class="chart-key chart-player"><span class="chart-swatch"></span>Your impact</span>
        <span class="chart-key chart-echo"><span class="chart-swatch"></span>ECHO impact</span>
      </div>
      <div class="chart-frame">
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Line chart comparing decision score impact by question for player and ECHO">
          ${yGrid}
          <line class="chart-axis" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}"></line>
          <line class="chart-axis" x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}"></line>
          ${xLabels}
          <path d="${pathFor(playerImpact)}" fill="none" stroke="var(--teal)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
          <path d="${pathFor(echoImpact)}" fill="none" stroke="var(--violet)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
          <g>${decisionPoints.map((decisionPoint, index) => decisionMarker(decisionPoint, "Player", index)).join("")}</g>
          <g>${decisionPoints.map((decisionPoint, index) => decisionMarker(decisionPoint, "ECHO", index)).join("")}</g>
        </svg>
        <div class="chart-tooltip" id="decisionChartTooltip"></div>
      </div>
    </div>
  `;
}

function showDecisionChartTooltip(event, marker) {
  const tooltip = $("decisionChartTooltip");
  if (!tooltip || !marker) return;
  const data = marker.dataset;
  tooltip.innerHTML = `
    <strong>${escapeHtml(data.series || "Decision")} point</strong>
    <div>Day ${escapeHtml(data.day || "-")}</div>
    <div>Question: ${escapeHtml(data.question || "-")}</div>
    <div>Player picked: ${escapeHtml(data.playerChoice || "-")}</div>
    <div>ECHO picked: ${escapeHtml(data.echoChoice || "-")}</div>
    <div>Player impact: ${escapeHtml(data.playerImpact || "+0.00")} (${escapeHtml(data.playerCumulative || "+0.00")} cumulative)</div>
    <div>ECHO impact: ${escapeHtml(data.echoImpact || "+0.00")} (${escapeHtml(data.echoCumulative || "+0.00")} cumulative)</div>
    <div>Job/Subjob: ${escapeHtml(data.affected || "-")}</div>
  `;
  tooltip.classList.add("active");
  positionDecisionChartTooltip(event, marker, tooltip);
}

function positionDecisionChartTooltip(event, marker, tooltip) {
  const frame = tooltip.parentElement;
  if (!frame) return;
  const frameRect = frame.getBoundingClientRect();
  const markerRect = marker.getBoundingClientRect();
  const clientX = Number.isFinite(event?.clientX) && event.clientX > 0
    ? event.clientX
    : markerRect.left + markerRect.width / 2;
  const clientY = Number.isFinite(event?.clientY) && event.clientY > 0
    ? event.clientY
    : markerRect.top;
  const tooltipWidth = tooltip.offsetWidth || 260;
  const tooltipHeight = tooltip.offsetHeight || 120;
  let left = clientX - frameRect.left + 12;
  let top = clientY - frameRect.top - tooltipHeight - 10;

  if (left + tooltipWidth > frameRect.width) {
    left = Math.max(8, frameRect.width - tooltipWidth - 8);
  }
  if (top < 8) {
    top = clientY - frameRect.top + 14;
  }

  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function hideDecisionChartTooltip() {
  const tooltip = $("decisionChartTooltip");
  if (!tooltip) return;
  tooltip.classList.remove("active");
}

function renderMetrics() {
  const snap = state.snapshot;
  const totalSubjobs = snap.jobsCompleted + snap.jobsRemaining;
  const metrics = [
    ["Jobs Complete", `${snap.piecesCompleted}/${state.pieces.length}`, snap.piecesCompleted / state.pieces.length, "good", "How many top-level jobs are complete.", true, renderJobsMetricPopover()],
    ["Subjobs Complete", `${fmtNum(snap.jobsCompleted)}/${fmtNum(totalSubjobs)}`, snap.jobsCompleted / Math.max(1, totalSubjobs), "good", "Total subjobs finished out of all required work.", true, ""],
    ["Subjobs Behind Schedule", fmtNum(snap.jobsBehindSchedule), 0, snap.jobsBehindSchedule > 0 ? "warn" : "good", "Incomplete subjobs whose target completion date has already passed.", false, ""],
    ["Subjobs Late", fmtNum(snap.jobsLate), 0, snap.jobsLate > 0 ? "warn" : "good", "Completed subjobs that finished after their target completion date.", false, ""],
    ["Schedule Risk", `${Math.round(snap.scheduleRisk)}/100`, snap.scheduleRisk / 100, snap.scheduleRisk > 70 ? "danger" : snap.scheduleRisk > 40 ? "warn" : "good", "Overall probability of missing the deadline (0 = safe, 100 = critical).", true, ""]
  ];
  $("metrics").innerHTML = metrics.map(([label, value, pct, tone, tooltip, showBar, detail]) => `
    <div class="metric ${detail ? "hoverable" : ""}" ${detail ? `tabindex="0" aria-describedby="jobsMetricPopover"` : ""}>
      <div class="metric-title-row">
        <span class="subtle">${label}<span class="info-icon" data-tooltip="${escapeHtml(tooltip)}">i</span></span>
        ${detail ? `<span class="metric-hint">Details</span>` : ""}
      </div>
      <strong>${value}</strong>
      ${showBar ? `<div class="progress"><div class="bar ${tone}" style="width:${Math.max(0, Math.min(1, pct)) * 100}%"></div></div>` : ""}
      ${detail}
    </div>
  `).join("");
}

function renderJobsMetricPopover() {
  const pieces = Array.isArray(state?.pieces)
    ? [...state.pieces].sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, { numeric: true }))
    : [];
  if (!pieces.length) return "";

  return `
    <div id="jobsMetricPopover" class="metric-popover" role="tooltip">
      <h3>Jobs</h3>
      <div class="metric-popover-frame">
        <table>
          <thead>
            <tr>
              <th>Job</th>
              <th>Subjobs Complete</th>
              <th>Projected Finish</th>
              <th>Due Date</th>
            </tr>
          </thead>
          <tbody>
            ${pieces.map(piece => {
              const completed = Number(piece.completed || 0);
              const total = Number(piece.total || 0);
              return `
                <tr>
                  <td>${escapeHtml(piece.displayId || piece.id || "-")}</td>
                  <td>${completed}/${total}</td>
                  <td>${escapeHtml(piece.projectedCompletion || "-")}</td>
                  <td>${escapeHtml(piece.dueDate || "-")}</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderDecisions() {
  const advanceBtn = $("advanceBtn");
  if (advanceBtn) advanceBtn.disabled = state.gameOver || !readyToAdvance();
}

function renderInlineDecisions() {
  const body = $("inlineDecisionBody");
  if (!body) return;

  if (modalVisible && pendingAdvanceState) {
    body.innerHTML = "";
    return;
  }

  if (!state || state.gameOver) {
    body.innerHTML = `
      <div class="reveal-panel">
        <h3>Campaign decisions are complete.</h3>
        <div class="subtle">Review the final operational comparison at the top of the page.</div>
      </div>
    `;
    return;
  }

  const progressState = decisionProgress();
  const nextCard = currentOpenDecisionCard();

  if (nextCard) {
    if (!nextCard.choices.some(choice => choice.id === pendingChoice)) {
      pendingChoice = null;
    }
    const decisionDue = nextDecisionIsDue();
    const title = decisionDue ? "Decision Event" : "Day In Motion";
    const badge = decisionDue ? `<span class="badge warn">Paused</span>` : `<span class="badge info">Rolling</span>`;
    const status = decisionDue
      ? "Paused for decision"
      : "Day progress";
    const detail = decisionDue
      ? `${escapeHtml(nextCard.title)}`
      : "Work is moving through the day.";
    body.innerHTML = `
      <div class="reveal-panel decision-status-panel">
        <div class="decision-title">
          <div>
            <h3>${title}</h3>
            <div class="subtle">${detail}</div>
          </div>
          ${badge}
        </div>
        ${renderDayClock(status, decisionDue)}
        ${decisionDue ? `
          <div class="inline-decision-actions">
            <button class="primary" onclick="openDecisionModal()">Respond</button>
          </div>
        ` : ""}
      </div>
    `;
    return;
  }

  const ending = dayCycleProgress >= 100 || dayCycleAdvancing;
  const status = ending ? "Preparing daily summary" : "Finishing today's work";
  body.innerHTML = `
    <div class="reveal-panel decision-status-panel">
      <div class="decision-title">
        <div>
          <h3>${ending ? "Day Complete" : "Day In Motion"}</h3>
          <div class="subtle">${progressState.total ? "All scheduled decisions are answered." : "No campaign decisions are scheduled today."}</div>
        </div>
        <span class="badge good">${ending ? "Complete" : "Rolling"}</span>
      </div>
      ${renderDayClock(status, ending)}
    </div>
  `;
}

function renderDecisionModal() {
  const overlay = $("decisionModalOverlay");
  const title = $("decisionModalTitle");
  const meta = $("decisionModalMeta");
  const body = $("decisionModalBody");
  const footer = $("decisionModalFooter");
  if (!overlay || !title || !meta || !body || !footer) return;

  const nextCard = currentOpenDecisionCard();
  const decisionDue = nextDecisionIsDue();
  if (!nextCard || !decisionDue || decisionModalBlocked()) {
    overlay.classList.remove("active");
    decisionModalVisible = false;
    if (!nextCard) {
      decisionModalVisible = false;
      decisionModalDismissedKey = null;
    }
    return;
  }

  if (!nextCard.choices.some(choice => choice.id === pendingChoice)) {
    pendingChoice = null;
  }

  const cardKey = decisionModalKey(nextCard);
  if (!decisionModalVisible && decisionModalDismissedKey !== cardKey) {
    decisionModalVisible = true;
  }

  if (!decisionModalVisible) {
    overlay.classList.remove("active");
    return;
  }

  title.textContent = "Daily Decision";
  meta.textContent = `Day ${state.day}`;
  body.innerHTML = `
    <div class="decision-prompt">
      <div class="decision-title">
        <div>
          <h2>${escapeHtml(nextCard.title)}</h2>
          <div class="subtle">${escapeHtml(nextCard.type)} | ${escapeHtml(decisionUrgencyLabel(nextCard.severity))}</div>
        </div>
        <span class="badge warn">Open</span>
      </div>
      <p>${escapeHtml(nextCard.description)}</p>
    </div>
    <div class="decision-choices decision-modal-choices">
      ${nextCard.choices.map(choice => `
        <button class="choice ${pendingChoice === choice.id ? "selected" : ""}" onclick="selectPendingChoice('${choice.id}')">
          <strong>${escapeHtml(choice.label)}</strong>
          <small>${escapeHtml(choice.description)}</small>
        </button>
      `).join("")}
    </div>
  `;
  footer.innerHTML = `
    <button ${!pendingChoice ? "disabled" : ""} class="primary" onclick="submitDecision('${nextCard.id}')">Submit</button>
  `;
  overlay.classList.add("active");
}

function renderSummary() {
  const summary = state.lastSummary;
  $("summarySection").classList.toggle("hidden", !summary);
  if (!summary) return;
  $("summaryGrid").innerHTML = renderSummaryGrid(summary, state.pieces.length, "summary-panel");
}

function renderFinal() {
  const final = state.finalReveal;
  if (!final) {
    $("finalSection").classList.add("hidden");
    return;
  }

  $("finalSection").classList.remove("hidden");

  const p = final.player;
  const a = final.automated;
  const review = final.review || {};

  $("finalCompletionChart").innerHTML = renderCompletionChart(final.completionHistory);

  $("finalTable").innerHTML = `
    <thead>
      <tr>
        <th>Metric</th>
        <th>Your Schedule</th>
        <th>ECHO Benchmark</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Final score</td>
        <td>${Number(p.finalScore || 0).toFixed(2)}</td>
        <td>${Number(a.finalScore || 0).toFixed(2)}</td>
      </tr>
      <tr>
        <td>Strategic path signature</td>
        <td>${Number(p.decisionPathDifferentiator || 0).toFixed(2)}</td>
        <td>${Number(a.decisionPathDifferentiator || 0).toFixed(2)}</td>
      </tr>
      <tr>
        <td>Deadline met</td>
        <td>${p.deadlineMet ? "Yes" : "No"}</td>
        <td>${a.deadlineMet ? "Yes" : "No"}</td>
      </tr>
      <tr>
        <td>Completion</td>
        <td>${escapeHtml(p.completion || "Not complete")}</td>
        <td>${escapeHtml(a.completion || "Not complete")}</td>
      </tr>
      <tr>
        <td>Jobs complete</td>
        <td>${p.piecesCompleted}</td>
        <td>${a.piecesCompleted}</td>
      </tr>
      <tr>
        <td>Subjobs completed</td>
        <td>${p.jobsCompleted}</td>
        <td>${a.jobsCompleted}</td>
      </tr>
      <tr>
        <td>Subjobs behind schedule</td>
        <td>${p.jobsBehindSchedule}</td>
        <td>${a.jobsBehindSchedule}</td>
      </tr>
      <tr>
        <td>Subjobs late</td>
        <td>${p.jobsLate}</td>
        <td>${a.jobsLate}</td>
      </tr>
      <tr>
        <td>Risk</td>
        <td>${Math.round(p.scheduleRisk)}/100</td>
        <td>${Math.round(a.scheduleRisk)}/100</td>
      </tr>
    </tbody>
  `;

  $("finalNotes").innerHTML = (review.reasons || final.explanation || [])
    .map(note => `<li>${escapeHtml(note)}</li>`)
    .join("") || "<li>No final review notes recorded.</li>";

  $("decisionAuditTable").innerHTML = `
    <thead>
      <tr>
        <th>Day</th>
        <th>Decision</th>
        <th>Your choice</th>
        <th>ECHO choice</th>
        <th>Matched</th>
      </tr>
    </thead>
    <tbody>
      ${(final.decisionAudit || []).map(row => `
        <tr>
          <td>${row.day}</td>
          <td>${escapeHtml(row.card)}</td>
          <td>${escapeHtml(row.playerChoice || "-")}</td>
          <td>${escapeHtml(row.echoChoice || "-")}</td>
          <td>${row.matched ? "Yes" : "No"}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

function decisionUrgencyLabel(severity) {
  if (severity >= 5) return "Severe urgency";
  if (severity >= 4) return "High urgency";
  if (severity >= 3) return "Elevated urgency";
  if (severity >= 2) return "Moderate urgency";
  return "Low urgency";
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
}

$("settingsMenuBtn").addEventListener("click", toggleSettingsMenu);
$("openNewRunModalBtn").addEventListener("click", openNewRunModal);
document.addEventListener("click", (e) => {
  const welcomeOverlay = document.getElementById("welcomeModalOverlay");
  const newRunOverlay = document.getElementById("newRunModalOverlay");
  const decisionOverlay = document.getElementById("decisionModalOverlay");
  const settingsWrap = document.querySelector(".settings-wrap");
  if (settingsWrap && !settingsWrap.contains(e.target)) {
    closeSettingsMenu();
  }
  if (e.target && e.target.id === "closeWelcomeBtn") {
    closeWelcomeModal();
  }
  if (e.target && e.target.id === "closeNewRunModalBtn") {
    closeNewRunModal();
  }
  if (e.target && e.target.id === "closeDecisionModalBtn") {
    closeDecisionModal();
  }
  if (welcomeOverlay && e.target === welcomeOverlay) {
    closeWelcomeModal();
  }
  if (newRunOverlay && e.target === newRunOverlay) {
    closeNewRunModal();
  }
  if (decisionOverlay && e.target === decisionOverlay) {
    closeDecisionModal();
  }
});

function initDarkMode() {
  // Theme is intentionally local browser preference, separate from run
  // state so seed replays do not change presentation preferences.
  const saved = localStorage.getItem("theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
  updateThemeButton(saved);
}

function updateThemeButton(theme) {
  const btn = $("themeMenuBtn");
  if (btn) btn.textContent = theme === "dark" ? "Light Mode" : "Dark Mode";
}

function toggleDarkMode() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
  updateThemeButton(next);
}

$("themeMenuBtn").addEventListener("click", toggleDarkMode);

initDarkMode();
welcomeModalVisible = true;
renderWelcomeModal();
loadState();
