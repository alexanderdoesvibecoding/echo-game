"""HTML template for the local browser UI."""

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Shipyard Scheduler Choose Your Own Adventure Game</title>
  <style>
    :root {
      --bg: #f6f7f4;
      --panel: #ffffff;
      --ink: #202524;
      --muted: #66706d;
      --line: #d9ded8;
      --teal: #167c78;
      --teal-dark: #0d5552;
      --amber: #b7791f;
      --red: #b33a3a;
      --green: #2f7d46;
      --violet: #6c5aa7;
      --shadow: 0 14px 32px rgba(32, 37, 36, 0.08);
    }

    html[data-theme="dark"] {
      --bg: #0f1419;
      --panel: #1a202a;
      --ink: #f0f3f5;
      --muted: #a5b0b8;
      --line: #3a4352;
      --shadow: 0 14px 32px rgba(0, 0, 0, 0.4);
    }

    html[data-theme="dark"] header {
      background: rgba(15, 20, 25, 0.95);
    }

    html[data-theme="dark"] h1,
    html[data-theme="dark"] h2,
    html[data-theme="dark"] h3 {
      color: #ffffff;
    }

    html[data-theme="dark"] input,
    html[data-theme="dark"] select,
    html[data-theme="dark"] button {
      background: #1a202a;
      color: #f0f3f5;
      border-color: #3a4352;
    }

    html[data-theme="dark"] button.primary {
      background: #167c78;
      color: #ffffff;
      border-color: #167c78;
    }

    html[data-theme="dark"] button.primary:hover {
      background: #0d5552;
      border-color: #0d5552;
    }

    html[data-theme="dark"] button:disabled {
      opacity: 0.48;
    }

    html[data-theme="dark"] option {
      background: #1a202a;
      color: #f0f3f5;
    }

    html[data-theme="dark"] .badge {
      background: #2a3543;
      color: #a5b0b8;
    }

    html[data-theme="dark"] .badge.good {
      background: #1a3a2a;
      color: #5dd99f;
    }

    html[data-theme="dark"] .badge.warn {
      background: #3a2a1a;
      color: #f0ad4e;
    }

    html[data-theme="dark"] .badge.danger {
      background: #3a1a1a;
      color: #ff6b6b;
    }

    html[data-theme="dark"] .badge.info {
      background: #1a2a3a;
      color: #5dd9e0;
    }

    html[data-theme="dark"] .badge.progress {
      background: #2b2548;
      color: #c8bcff;
    }

    html[data-theme="dark"] table,
    html[data-theme="dark"] th,
    html[data-theme="dark"] td {
      border-color: #3a4352;
    }

    html[data-theme="dark"] th {
      background: #1a202a;
      color: #a5b0b8;
    }

    html[data-theme="dark"] .section-head {
      background: #252d38;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .decision {
      background: #1a202a;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .decision.done {
      border-color: #2a5a3a;
      background: #1a2f1f;
    }

    html[data-theme="dark"] .decision-head {
      border-color: #3a4352;
    }

    html[data-theme="dark"] .choice {
      background: #252d38;
      border-color: #3a4352;
      color: #f0f3f5;
    }

    html[data-theme="dark"] .choice.selected {
      background: #2a5a3a;
      border-color: #5dd99f;
    }

    html[data-theme="dark"] .modal {
      background: #1a202a;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .reveal-panel {
      background: #1a202a;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .error {
      background: #2a1a1a;
      border-color: #5a3a3a;
      color: #ff9999;
    }

    html[data-theme="dark"] .metric {
      background: #252d38;
      border-color: #3a4352;
      color: #f0f3f5;
    }

    html[data-theme="dark"] .settings-panel {
      background: #1a202a;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .modal-error {
      background: #2a1a1a;
      border-color: #5a3a3a;
      color: #ff9999;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.4;
    }

    header {
      position: sticky;
      top: 0;
      z-index: 20;
      background: rgba(246, 247, 244, 0.94);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(12px);
    }

    .topbar {
      display: grid;
      grid-template-columns: auto minmax(240px, 1fr) auto;
      gap: 18px;
      align-items: center;
      padding: 16px 22px;
      position: relative;
    }

    h1, h2, h3 { margin: 0; letter-spacing: 0; }
    h1 { font-size: 20px; font-weight: 760; }
    h2 { font-size: 15px; font-weight: 760; }
    h3 { font-size: 13px; font-weight: 760; color: var(--muted); text-transform: uppercase; }
    .subtle { color: var(--muted); }
    .controls { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; align-items: center; }
    .settings-wrap { position: relative; }
    .settings-button {
      width: 38px;
      padding: 0;
      display: inline-flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 4px;
    }
    .settings-button span {
      width: 18px;
      height: 2px;
      border-radius: 999px;
      background: currentColor;
    }
    .settings-panel {
      position: absolute;
      top: calc(100% + 8px);
      left: 0;
      z-index: 40;
      display: none;
      width: 220px;
      padding: 8px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .settings-panel.active { display: grid; gap: 8px; }
    .settings-panel button {
      width: 100%;
      justify-content: flex-start;
      text-align: left;
    }
    .settings-form {
      display: grid;
      gap: 12px;
    }
    .settings-form label {
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .settings-form select {
      width: 100%;
      min-width: 0;
    }
    .modal-error {
      padding: 9px 10px;
      border: 1px solid #e4b3b3;
      border-radius: 8px;
      background: #fff2f2;
      color: #8d2525;
      font-weight: 700;
    }
    input, select, button {
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }
    input { width: 132px; padding: 0 10px; }
    select { min-width: 210px; padding: 0 8px; }
    button {
      padding: 0 12px;
      cursor: pointer;
      font-weight: 650;
    }
    button.primary { background: var(--teal); color: #fff; border-color: var(--teal); }
    button.primary:hover { background: var(--teal-dark); }
    button:disabled { opacity: 0.48; cursor: not-allowed; }

    main {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 16px;
      padding: 16px 22px 28px;
      max-width: 1600px;
      margin: 0 auto;
    }

    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    section { overflow: visible; }
    .section-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 13px 15px;
      border-bottom: 1px solid var(--line);
      background: #fbfcf9;
    }

    .grid { display: grid; gap: 16px; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 10px;
      padding: 14px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 11px;
      background: #fff;
      min-height: 74px;
    }
    .metric strong {
      display: block;
      font-size: 22px;
      line-height: 1.1;
      margin-top: 6px;
    }

    .progress {
      width: 100%;
      height: 8px;
      border-radius: 99px;
      background: #e6ebe6;
      overflow: hidden;
      margin-top: 8px;
    }
    .bar { height: 100%; background: var(--teal); width: 0; }
    .bar.warn { background: var(--amber); }
    .bar.danger { background: var(--red); }
    .bar.good { background: var(--green); }
    .bar.info { background: var(--teal); }
    .bar.muted { background: var(--line); }

    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 13px;
    }
    th, td {
      padding: 8px 7px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
      background: #fbfcf9;
    }
    tr:last-child td { border-bottom: none; }
    .table-wrap { max-height: 520px; overflow: auto; border: 1px solid var(--line); border-radius: 8px; }

    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 7px;
      border-radius: 999px;
      background: #eef2ee;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .badge.good { background: #e7f3eb; color: var(--green); }
    .badge.warn { background: #fbf0da; color: var(--amber); }
    .badge.danger { background: #f8e4e4; color: var(--red); }
    .badge.info { background: #e7f1f1; color: var(--teal-dark); }
    .badge.progress { background: #ece8f8; color: var(--violet); }

    .link-button {
      appearance: none;
      border: none;
      background: none;
      color: var(--teal-dark);
      text-decoration: underline;
      cursor: pointer;
      padding: 0;
      font: inherit;
    }
    .link-button:hover {
      color: var(--primary);
    }

    .decision {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }
    .decision.done { border-color: #b8d8c2; background: #fbfffc; }
    .decision-head { padding: 11px; border-bottom: 1px solid var(--line); }
    .decision-title { display: flex; justify-content: space-between; gap: 10px; align-items: start; }
    .choice {
      display: block;
      width: calc(100% - 20px);
      height: auto;
      min-height: 44px;
      margin: 8px 10px;
      padding: 9px;
      text-align: left;
      border-radius: 6px;
    }
    .choice.selected { border-color: var(--green); background: #eef8f0; }
    .choice small { display: block; color: var(--muted); margin-top: 3px; }
    .inline-decisions {
      display: grid;
      gap: 12px;
      padding: 14px;
    }
    .inline-decisions .decision {
      max-width: 820px;
    }
    .inline-decision-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
      padding: 2px 10px 10px;
    }
    .mode-choices {
      display: grid;
      gap: 8px;
    }
    .mode-choices .choice {
      width: 100%;
      margin: 0;
    }
    .decision-modal {
      max-width: 680px;
    }
    .modal-titlebar {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 12px;
    }
    .icon-button {
      width: 34px;
      padding: 0;
      font-size: 20px;
      line-height: 1;
    }

    .split {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 12px;
      padding: 14px;
    }
    .reveal-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }
    .completion-chart {
      display: grid;
      gap: 10px;
    }
    .chart-frame {
      width: 100%;
      overflow: hidden;
    }
    .chart-frame svg {
      display: block;
      width: 100%;
      height: auto;
    }
    .chart-axis,
    .chart-grid {
      stroke: var(--line);
      stroke-width: 1;
    }
    .chart-label {
      fill: var(--muted);
      font-size: 12px;
    }
    .chart-legend {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .chart-key {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .chart-swatch {
      width: 18px;
      height: 3px;
      border-radius: 999px;
      background: currentColor;
    }
    .chart-player { color: var(--teal); }
    .chart-echo { color: var(--violet); }
    .notes {
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
    }
    .status-line {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      margin-top: 6px;
    }
    .hidden { display: none !important; }
    .error {
      margin: 0 22px;
      padding: 10px 12px;
      border: 1px solid #e4b3b3;
      background: #fff2f2;
      color: #8d2525;
      border-radius: 8px;
    }

    @media (max-width: 1120px) {
      main { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: repeat(3, minmax(120px, 1fr)); }
    }
    @media (max-width: 680px) {
      .topbar { grid-template-columns: auto 1fr; }
      .controls { grid-column: 1 / -1; }
      .controls { justify-content: flex-start; }
      main { padding: 12px; }
      .metrics, .split { grid-template-columns: 1fr; }
      table { min-width: 720px; }
    }
    /* Modal overlay for end-of-day summary */
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(16,20,18,0.45);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 60;
      padding: 24px;
    }
    .modal-overlay.active { display: flex; }
    .modal {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 18px;
      max-width: 820px;
      width: 100%;
      box-shadow: 0 30px 60px rgba(8,10,9,0.4);
    }
    .modal .modal-body { max-height: 60vh; overflow: auto; margin-bottom: 12px; }
    .modal .modal-footer { display:flex; justify-content:flex-end; gap:8px; }
    .modal h3 { margin-top: 0; }
    .welcome-copy {
      display: grid;
      gap: 10px;
      margin: 8px 0 4px;
      color: var(--muted);
    }
    .welcome-copy p {
      margin: 0;
    }
    .welcome-copy ul {
      margin: 0;
      padding-left: 20px;
    }
    .welcome-copy li {
      margin: 6px 0;
    }
    .rework-flag {
      display: inline-block;
      width: 8px;
      height: 8px;
      margin-left: 6px;
      border-radius: 50%;
      background: var(--red);
      box-shadow: 0 0 0 2px rgba(179, 58, 58, 0.14);
      vertical-align: middle;
    }
    .info-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-style: italic;
      color: var(--muted);
      cursor: help;
      font-size: 11px;
      font-weight: bold;
      margin-left: 4px;
      position: relative;
      z-index: 10;
      width: 16px;
      height: 16px;
      border: 1.5px solid var(--ink);
      border-radius: 50%;
    }
    .info-icon:hover::after {
      content: attr(data-tooltip);
      position: absolute;
      bottom: 125%;
      left: 50%;
      transform: translateX(-50%);
      background: var(--panel);
      color: var(--ink);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 12px;
      font-size: 13px;
      font-style: normal;
      font-weight: 600;
      opacity: 1;
      white-space: nowrap;
      z-index: 100000;
      box-shadow: 0 10px 24px rgba(0, 0, 0, 0.24);
    }
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div class="settings-wrap">
        <button id="settingsMenuBtn" class="settings-button" title="Settings" aria-label="Settings menu" aria-expanded="false">
          <span></span>
          <span></span>
          <span></span>
        </button>
        <div id="settingsPanel" class="settings-panel">
          <button id="openNewRunModalBtn">New Game</button>
          <button id="themeMenuBtn">Light/Dark Mode</button>
        </div>
      </div>
      <div>
        <h1>Shipyard Scheduler Choose Your Own Adventure Game</h1>
        <div class="status-line">
          <span class="badge" id="dayBadge">Day</span>
          <span class="badge warn" id="decisionProgress">0/0 Daily Questions Complete</span>
        </div>
      </div>
      <div class="controls">
        <button id="decisionBtn">Daily Decisions</button>
        <button id="advanceBtn" class="primary" disabled>End Day</button>
      </div>
    </div>
    <div id="error" class="error hidden"></div>
  </header>

  <main>
    <div class="grid">
      <section id="finalSection" class="hidden">
        <div class="section-head">
          <div>
            <h2>Final Operational Comparison</h2>
            <div class="subtle">The silent benchmark is revealed only after the run ends.</div>
          </div>
        </div>
        <div class="split">
          <div class="reveal-panel"><h3>Subjobs Complete Over Time</h3><div id="finalCompletionChart"></div></div>
          <div class="reveal-panel"><h3>Metric Comparison</h3><table id="finalTable"></table></div>
          <div class="reveal-panel"><h3>Outcome Drivers</h3><ul class="notes" id="finalNotes"></ul></div>
          <div class="reveal-panel"><h3>Decision Audit</h3><table id="decisionAuditTable"></table></div>
        </div>
      </section>

      <section>
        <div class="section-head">
          <div>
            <h2>Project Position</h2>
            <div class="subtle" id="projectedText">Projected completion</div>
          </div>
        </div>
        <div class="metrics" id="metrics"></div>
      </section>

      <section id="dailyDecisionSection">
        <div class="section-head">
          <div>
            <h2>Daily Decisions</h2>
            <div class="subtle" id="inlineDecisionSubtitle"></div>
          </div>
        </div>
        <div class="inline-decisions" id="inlineDecisionBody"></div>
      </section>

      <section id="summarySection" class="hidden">
        <div class="section-head"><h2>End-of-Day Summary</h2></div>
        <div class="split">
          <div class="reveal-panel" id="summaryMetrics"></div>
          <div class="reveal-panel"><h3>Updates</h3><ul class="notes" id="summaryNotes"></ul></div>
        </div>
      </section>

    </div>

  </main>

  <div id="welcomeModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="welcomeModalTitle">
    <div class="modal">
      <h1 id="welcomeModalTitle">Welcome</h1>
      <div class="welcome-copy">
        <p>You are managing a manufacturing schedule under disruption. Each day, answer the daily decision prompts and choose how the yard should respond.</p>
        <p>Your goal is to complete every job before <span id="welcomeDeadline">the deadline</span> while balancing cost, reschedules, and schedule risk.</p>
        <ul>
          <li>Use daily decisions to resequence, reroute, expedite, or protect critical work.</li>
          <li>End the day to see the consequences of your choices and move the schedule forward.</li>
        </ul>
      </div>
      <div class="modal-footer">
        <button id="closeWelcomeBtn" class="primary" onclick="closeWelcomeModal()">Start</button>
      </div>
    </div>
  </div>

  <div id="decisionModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="decisionModalTitle">
    <div class="modal decision-modal">
      <div class="modal-titlebar">
        <div>
          <h1 id="decisionModalTitle">Daily Decisions</h1>
          <div class="subtle" id="decisionModalSubtitle"></div>
        </div>
        <button id="closeDecisionBtn" class="icon-button" title="Dismiss decisions" onclick="dismissDecisionModal()">×</button>
      </div>
      <div class="modal-body" id="decisionModalBody"></div>
      <div class="modal-footer" id="decisionModalFooter"></div>
    </div>
  </div>

  <div id="newRunModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="newRunModalTitle">
    <div class="modal">
      <div class="modal-titlebar">
        <div>
          <h1 id="newRunModalTitle">New Game</h1>
          <div class="subtle">Choose a preset.</div>
        </div>
        <button id="closeNewRunModalBtn" class="icon-button" title="Close new run settings" onclick="closeNewRunModal()">×</button>
      </div>
      <div class="modal-body">
        <div class="settings-form">
          <div class="mode-choices">
            <button id="normalModeBtn" class="choice" type="button" onclick="selectRunMode('normal')">
              <strong>Normal</strong>
              <small>Full project run with the standard schedule length, job count, and disruption mix.</small>
            </button>
            <button id="demoModeBtn" class="choice" type="button" onclick="selectRunMode('demo')">
              <strong>Demo</strong>
              <small>Short five-day run with fewer jobs and faster pacing.</small>
            </button>
          </div>
          <div id="newRunError" class="modal-error hidden"></div>
        </div>
      </div>
      <div class="modal-footer">
        <button onclick="closeNewRunModal()">Cancel</button>
        <button class="primary" onclick="startNewRun()">Start Game</button>
      </div>
    </div>
  </div>

  <script>
    let state = null;
    // Client-side modal state is intentionally local. The server remains the
    // source of truth for the run, decisions, and day advancement rules.
    let welcomeModalVisible = false;
    let decisionModalVisible = false;
    let newRunModalVisible = false;
    let settingsMenuOpen = false;
    let selectedRunMode = "normal";
    let finalModalDismissed = false;
    let dismissedDecisionKey = null;

    const $ = (id) => document.getElementById(id);
    const fmtPct = (value) => `${Math.round((value || 0) * 100)}%`;
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
        showError(error.message);
      }
    }

    async function startNewRun() {
      try {
        state = await api("/api/new", {
          method: "POST",
          body: JSON.stringify({ mode: selectedRunMode })
        });
        pendingChoice = null;
        dismissedDecisionKey = null;
        decisionModalVisible = false;
        welcomeModalVisible = true;
        newRunModalVisible = false;
        finalModalDismissed = false;
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

    async function choose(cardId, choiceId) {
      try {
        state = await api("/api/choice", {
          method: "POST",
          body: JSON.stringify({ cardId, choiceId })
        });
        pendingChoice = null;
        dismissedDecisionKey = null;
        decisionModalVisible = false;
        showError("");
        render();
      } catch (error) {
        showError(error.message);
      }
    }

    // Holds the server-advanced state while the player reads the daily summary.
    let pendingAdvanceState = null;

    async function prepareAdvanceDay() {
      // The button should already be disabled until all decisions are complete,
      // but this guard keeps direct console calls and stale UI state honest.
      if (!readyToAdvance()) {
        openDecisionModal();
        return;
      }
      try {
        const nextState = await api("/api/advance", { method: "POST", body: "{}" });
        showError("");
        pendingAdvanceState = nextState;
        if (nextState.finalReveal) {
          state = nextState;
          pendingAdvanceState = null;
          finalModalVisible = false;
          finalModalDismissed = true;
          modalVisible = false;
        } else {
          modalVisible = true;
          finalModalVisible = false;
        }
        decisionModalVisible = false;
        pieceModalVisible = false;
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
    let finalModalVisible = false;
    let pieceModalVisible = false;
    let activePieceId = null;
    let pendingChoice = null;

    function openPieceModal(pieceId) {
      activePieceId = pieceId;
      modalVisible = false;
      finalModalVisible = false;
      decisionModalVisible = false;
      pieceModalVisible = true;
      render();
    }

    function closePieceModal() {
      pieceModalVisible = false;
      render();
    }

    function closeFinalModal() {
      finalModalVisible = false;
      finalModalDismissed = true;
      render();
    }

    function render() {
      if (!state) return;
      $("dayBadge").textContent = `Day ${state.day}`;
      $("welcomeDeadline").textContent = state.deadlineLabel;
      $("projectedText").textContent = `Projected completion: ${state.overview.projectedCompletion}`;

      renderMetrics();
      renderDecisions();
      renderInlineDecisions();
      renderSummary();
      renderSummaryModal();
      renderFinal();
      renderPieceModal();
      renderWelcomeModal();
      renderNewRunModal();
      renderSettingsMenu();
      maybeAutoOpenDecisionModal();
      renderDecisionModal();
      renderFinalModal();
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

    function decisionPromptKey() {
      if (!state) return "";
      const nextCard = state.decisions.find(card => !card.selectedChoice);
      // A dismissed decision modal should stay dismissed only until the next
      // unresolved card appears or the day's completion state changes.
      const progress = decisionProgress();
      return `${state.day}:${progress.completed}:${progress.visibleCards}:${nextCard ? nextCard.id : "complete"}`;
    }

    function maybeAutoOpenDecisionModal() {
      // Daily decisions are rendered inline in the main page.
      return;
    }

    function openDecisionModal() {
      if (!state || state.gameOver) return;
      decisionModalVisible = false;
      document.getElementById("dailyDecisionSection")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function dismissDecisionModal() {
      dismissedDecisionKey = decisionPromptKey();
      decisionModalVisible = false;
      renderDecisionModal();
    }

    function submitDecision(cardId) {
      if (!pendingChoice) return;
      choose(cardId, pendingChoice);
    }

    function selectPendingChoice(choiceId) {
      pendingChoice = choiceId;
      renderInlineDecisions();
      renderDecisionModal();
    }

    function renderWelcomeModal() {
      const overlay = document.getElementById("welcomeModalOverlay");
      if (!overlay) return;
      overlay.classList.toggle("active", welcomeModalVisible);
    }

    function closeWelcomeModal() {
      welcomeModalVisible = false;
      renderWelcomeModal();
      maybeAutoOpenDecisionModal();
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
      selectedRunMode = state ? state.mode || "normal" : "normal";
      renderNewRunModal();
    }

    function closeNewRunModal() {
      newRunModalVisible = false;
      showNewRunError("");
      renderNewRunModal();
    }

    function renderNewRunModal() {
      const overlay = $("newRunModalOverlay");
      if (!overlay) return;
      overlay.classList.toggle("active", newRunModalVisible);
      ["normal", "demo"].forEach(mode => {
        const button = $(`${mode}ModeBtn`);
        if (!button) return;
        const selected = selectedRunMode === mode;
        button.classList.toggle("selected", selected);
        button.setAttribute("aria-pressed", selected ? "true" : "false");
      });
    }

    function selectRunMode(mode) {
      selectedRunMode = mode === "demo" ? "demo" : "normal";
      showNewRunError("");
      renderNewRunModal();
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
              <th>Job</th>
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
                <td>${escapeHtml(job.piece)}</td>
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

    function renderSummaryModal() {
      const payload = pendingAdvanceState || state;
      const summary = payload.lastSummary;
      const overlay = document.getElementById("summaryModalOverlay");
      const body = document.getElementById("summaryModalBody");
      const notes = document.getElementById("summaryModalNotes");
      if (!overlay || !body || !notes) return;
      if (!summary || !modalVisible) {
        overlay.classList.remove("active");
        return;
      }
      // The day has already been simulated on the server, but the summary modal
      // lets the player read consequences before committing that state locally.
      overlay.classList.add("active");
      body.innerHTML = `
        <table>
          <tbody>
            <tr><td>Subjobs completed today</td><td>${summary.completedToday}</td></tr>
            <tr><td>Subjobs remaining</td><td>${summary.jobsRemaining}</td></tr>
            <tr><td>Jobs complete</td><td>${summary.piecesCompleted}/${state.pieces.length}</td></tr>
            <tr><td>Subjobs late</td><td>${summary.jobsLate}</td></tr>
            <tr><td>Cost</td><td>${fmtNum(summary.cost)}</td></tr>
            <tr><td>Risk</td><td>${Math.round(summary.risk)}/100</td></tr>
            <tr><td>Projected completion</td><td>${summary.projectedCompletion}</td></tr>
          </tbody>
        </table>

        <h3>Past Due Subjobs</h3>
        ${renderPastDueJobs(summary.pastDueJobs)}
      `;
      body.scrollTop = 0;
      notes.innerHTML = (summary.notes || []).map(note => `<li>${escapeHtml(note)}</li>`).join("") || "<li>No notable notes recorded.</li>";
    }

    function renderFinalModal() {
      const final = state.finalReveal;
      const overlay = document.getElementById("finalModalOverlay");
      const body = document.getElementById("finalModalBody");
      const notes = document.getElementById("finalModalNotes");
      if (!overlay || !body || !notes) return;
      if (!final || !finalModalVisible) {
        overlay.classList.remove("active");
        return;
      }
      overlay.classList.add("active");
      const p = final.player;
      const a = final.automated;
      const review = final.review || {};
      body.innerHTML = `
        <div class="callout">
          <strong>${escapeHtml(review.headline || "Final review")}</strong>
        </div>
        <table>
          <tbody>
            <tr><td>Deadline met</td><td>${p.deadlineMet ? "Yes" : "No"}</td><td>${a.deadlineMet ? "Yes" : "No"}</td></tr>
            <tr><td>Project completed</td><td>${p.finalItemCompleted ? "Yes" : "No"}</td><td>${a.finalItemCompleted ? "Yes" : "No"}</td></tr>
            <tr><td>Completion</td><td>${p.completion || "Not complete"}</td><td>${a.completion || "Not complete"}</td></tr>
            <tr><td>Jobs complete</td><td>${p.piecesCompleted}</td><td>${a.piecesCompleted}</td></tr>
            <tr><td>Subjobs completed</td><td>${p.jobsCompleted}</td><td>${a.jobsCompleted}</td></tr>
            <tr><td>Subjobs late</td><td>${p.jobsLate}</td><td>${a.jobsLate}</td></tr>
            <tr><td>Idle time</td><td>${p.idleTime}</td><td>${a.idleTime}</td></tr>
            <tr><td>Reschedules</td><td>${p.reschedules}</td><td>${a.reschedules}</td></tr>
            <tr><td>Cost</td><td>${fmtNum(p.cost)}</td><td>${fmtNum(a.cost)}</td></tr>
            <tr><td>Schedule risk</td><td>${Math.round(p.scheduleRisk)}</td><td>${Math.round(a.scheduleRisk)}</td></tr>
          </tbody>
        </table>
        <h3>Subjobs Complete Over Time</h3>
        ${renderCompletionChart(final.completionHistory)}
      `;
      body.scrollTop = 0;
      notes.innerHTML = (review.reasons || final.explanation || [])
        .map(note => `<li>${escapeHtml(note)}</li>`)
        .join("") || "<li>No final review notes recorded.</li>";
      const audit = document.getElementById("finalModalAudit");
      const auditRows = (final.decisionAudit || []).slice(0, 12).map(row => `
        <tr>
          <td>Day ${row.day}</td>
          <td>${escapeHtml(row.playerChoice)}</td>
          <td>${escapeHtml(row.echoChoice)}</td>
          <td>${row.matched ? "Matched" : "Different"}</td>
        </tr>
      `).join("");
      if (audit) audit.innerHTML = `
        <h3>Decision Audit</h3>
        <table>
          <thead><tr><th>Day</th><th>Player</th><th>ECHO</th><th>Result</th></tr></thead>
          <tbody>${auditRows || `<tr><td colspan="4">No decisions recorded</td></tr>`}</tbody>
        </table>
      `;
    }

    function renderCompletionChart(history) {
      const days = Array.isArray(history?.days) ? history.days : [];
      const player = Array.isArray(history?.player) ? history.player : [];
      const echo = Array.isArray(history?.automated) ? history.automated : [];
      const count = Math.min(days.length, player.length, echo.length);
      if (!count) return `<div class="subtle">No completion history recorded.</div>`;

      const width = 640;
      const height = 260;
      const pad = { left: 44, right: 18, top: 18, bottom: 36 };
      const maxCompleted = Math.max(1, Number(history?.total) || 0, ...player, ...echo);
      const maxIndex = Math.max(1, count - 1);
      const plotWidth = width - pad.left - pad.right;
      const plotHeight = height - pad.top - pad.bottom;
      const point = (value, index) => {
        const x = pad.left + (index / maxIndex) * plotWidth;
        const y = pad.top + (1 - Math.max(0, Math.min(maxCompleted, value)) / maxCompleted) * plotHeight;
        return [x, y];
      };
      const pathFor = (series) => series.slice(0, count).map((value, index) => {
        const [x, y] = point(Number(value) || 0, index);
        return `${index ? "L" : "M"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      }).join(" ");
      const yTicks = [...new Set([0, Math.round(maxCompleted / 2), maxCompleted])];
      const xTicks = [...new Set([0, Math.floor(maxIndex / 2), maxIndex])];
      const yGrid = yTicks.map(value => {
        const [, y] = point(value, 0);
        return `
          <line class="chart-grid" x1="${pad.left}" y1="${y.toFixed(1)}" x2="${(width - pad.right).toFixed(1)}" y2="${y.toFixed(1)}"></line>
          <text class="chart-label" x="${pad.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end">${value}</text>
        `;
      }).join("");
      const xLabels = xTicks.map(index => {
        const [x] = point(0, index);
        const day = days[index] ?? index;
        const label = day === 0 ? "Start" : `Day ${day}`;
        return `<text class="chart-label" x="${x.toFixed(1)}" y="${height - 10}" text-anchor="middle">${escapeHtml(label)}</text>`;
      }).join("");
      const [playerX, playerY] = point(Number(player[count - 1]) || 0, count - 1);
      const [echoX, echoY] = point(Number(echo[count - 1]) || 0, count - 1);

      return `
        <div class="completion-chart">
          <div class="chart-legend">
            <span class="chart-key chart-player"><span class="chart-swatch"></span>Your schedule</span>
            <span class="chart-key chart-echo"><span class="chart-swatch"></span>ECHO benchmark</span>
          </div>
          <div class="chart-frame">
            <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Line chart comparing cumulative subjobs completed by player and ECHO">
              ${yGrid}
              <line class="chart-axis" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}"></line>
              <line class="chart-axis" x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}"></line>
              ${xLabels}
              <path d="${pathFor(player)}" fill="none" stroke="var(--teal)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
              <path d="${pathFor(echo)}" fill="none" stroke="var(--violet)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
              <circle cx="${playerX.toFixed(1)}" cy="${playerY.toFixed(1)}" r="4" fill="var(--teal)"></circle>
              <circle cx="${echoX.toFixed(1)}" cy="${echoY.toFixed(1)}" r="4" fill="var(--violet)"></circle>
            </svg>
          </div>
        </div>
      `;
    }

    function renderPieceModal() {
      const overlay = document.getElementById("pieceModalOverlay");
      const body = document.getElementById("pieceModalBody");
      if (!overlay || !body) return;
      const piece = state.pieces.find(item => item.id === activePieceId);
      if (!piece || !pieceModalVisible) {
        overlay.classList.remove("active");
        return;
      }
      overlay.classList.add("active");
      const blockedCount = piece.jobs.filter(job => job.blocked).length;
      const criticalCount = piece.jobs.filter(job => job.critical).length;
      body.innerHTML = `
        <div style="margin-bottom: 16px;">
          <h3>${escapeHtml(piece.name)}</h3>
          <p class="subtle">${escapeHtml(piece.displayId || piece.id)}</p>
          <table>
            <tbody>
              <tr><td>Status</td><td>${escapeHtml(pieceStatusLabel(piece.status))}</td></tr>
              <tr><td>Progress</td><td>${fmtPct(piece.progress)}</td></tr>
              <tr><td>Subjobs complete</td><td>${piece.completed}/${piece.total}</td></tr>
              <tr><td>Subjobs blocked</td><td>${blockedCount}</td></tr>
              <tr><td>Critical subjobs</td><td>${criticalCount}</td></tr>
              <tr><td>Due date</td><td>${escapeHtml(piece.dueDate)}</td></tr>
              <tr><td>Risk</td><td>${Math.round(piece.risk)}</td></tr>
            </tbody>
          </table>
        </div>
        <h4>Subjobs</h4>
        <table>
          <thead>
            <tr>
              <th>Subjob</th>
              <th>Status</th>
              <th>Shop</th>
              <th>Workcenter</th>
              <th>Capability</th>
              <th>Remaining</th>
              <th>Due</th>
              <th>Blocked</th>
            </tr>
          </thead>
          <tbody>
            ${piece.jobs.map(job => `
              <tr>
                <td>${jobLabel(job.id, job.rework)}</td>
                <td>${escapeHtml(job.status)}</td>
                <td>${escapeHtml(job.shop)}</td>
                <td>${escapeHtml(job.workcenter)}</td>
                <td>${escapeHtml(job.capability)}</td>
                <td>${escapeHtml(job.remaining)}</td>
                <td>${escapeHtml(job.due)}</td>
                <td>${job.blocked ? "Yes" : ""}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
      body.scrollTop = 0;
    }

    function renderMetrics() {
      const snap = state.snapshot;
      const metrics = [
        ["Jobs Complete", `${snap.piecesCompleted}/${state.pieces.length}`, snap.piecesCompleted / state.pieces.length, "good", "How many top-level jobs are complete."],
        ["Subjobs Complete", fmtNum(snap.jobsCompleted), snap.jobsCompleted / Math.max(1, snap.jobsCompleted + snap.jobsRemaining), "good", "Total subjobs finished out of all required work."],
        ["Subjobs Late", fmtNum(snap.jobsLate), Math.min(1, snap.jobsLate / 20), snap.jobsLate > 0 ? "warn" : "good", "Number of subjobs that have missed their target completion date."],
        ["Cost", fmtNum(snap.cost), Math.min(1, snap.cost / 28000), "warn", "Total additional costs from rescheduling, expediting, and resolving issues."],
        ["Schedule Risk", `${Math.round(snap.scheduleRisk)}/100`, snap.scheduleRisk / 100, snap.scheduleRisk > 70 ? "danger" : snap.scheduleRisk > 40 ? "warn" : "good", "Overall probability of missing the deadline (0 = safe, 100 = critical)."]
      ];
      $("metrics").innerHTML = metrics.map(([label, value, pct, tone, tooltip]) => `
        <div class="metric">
          <span class="subtle">${label}<span class="info-icon" data-tooltip="${escapeHtml(tooltip)}">i</span></span>
          <strong>${value}</strong>
          <div class="progress"><div class="bar ${tone}" style="width:${Math.max(0, Math.min(1, pct)) * 100}%"></div></div>
        </div>
      `).join("");
    }

    function renderDecisions() {
      const progressState = decisionProgress();
      const chosenCount = progressState.completed;
      const totalCount = progressState.total;
      const remainingCount = Math.max(0, totalCount - chosenCount);
      const openCount = (progressState.openCardIds || []).length;
      const progress = $("decisionProgress");
      const decisionBtn = $("decisionBtn");
      const advanceBtn = $("advanceBtn");

      if (state.gameOver) {
        progress.textContent = "Run complete";
        progress.className = "badge good";
        decisionBtn.disabled = true;
        advanceBtn.disabled = true;
        return;
      }

      progress.textContent = `${chosenCount}/${totalCount} Daily Questions Complete`;
      progress.className = `badge ${remainingCount ? "warn" : "good"}`;
      decisionBtn.disabled = false;
      decisionBtn.textContent = openCount ? `Daily Decisions (${openCount})` : "Daily Decisions";
      advanceBtn.disabled = !readyToAdvance();
    }

    function renderInlineDecisions() {
      const subtitle = $("inlineDecisionSubtitle");
      const body = $("inlineDecisionBody");
      if (!subtitle || !body) return;

      if (!state || state.gameOver) {
        subtitle.textContent = "Run complete";
        body.innerHTML = `
          <div class="reveal-panel">
            <h3>Daily decisions are complete.</h3>
            <div class="subtle">Review the final operational comparison at the top of the page.</div>
          </div>
        `;
        return;
      }

      const progressState = decisionProgress();
      subtitle.textContent = `${progressState.completed}/${progressState.total} daily questions complete`;
      const nextCard = state.decisions.find(card => !card.selectedChoice);

      if (nextCard) {
        if (!nextCard.choices.some(choice => choice.id === pendingChoice)) {
          pendingChoice = null;
        }
        body.innerHTML = `
          <div class="decision">
            <div class="decision-head">
              <div class="decision-title">
                <div>
                  <h2>${escapeHtml(nextCard.title)}</h2>
                  <div class="subtle">${escapeHtml(nextCard.type)} | ${escapeHtml(decisionUrgencyLabel(nextCard.severity))}</div>
                </div>
                <span class="badge warn">Open</span>
              </div>
              <p>${escapeHtml(nextCard.description)}</p>
            </div>
            ${nextCard.choices.map(choice => `
              <button class="choice ${pendingChoice === choice.id ? "selected" : ""}" onclick="selectPendingChoice('${choice.id}')">
                <strong>${escapeHtml(choice.label)}</strong>
                <small>${escapeHtml(choice.description)}</small>
              </button>
            `).join("")}
            <div class="inline-decision-actions">
              <button ${!pendingChoice ? "disabled" : ""} class="primary" onclick="submitDecision('${nextCard.id}')">Submit</button>
            </div>
          </div>
        `;
        return;
      }

      const choices = (state.appliedChoices || []).map(note => `<li>${escapeHtml(note)}</li>`).join("");
      body.innerHTML = `
        <div class="reveal-panel">
          <h3>All choices made for today.</h3>
          <div class="subtle">End the day to process the schedule and reveal the daily consequences.</div>
          ${choices ? `<ul class="notes">${choices}</ul>` : ""}
          <div class="inline-decision-actions">
            <button class="primary" onclick="prepareAdvanceDay()">End Day</button>
          </div>
        </div>
      `;
    }

    function renderDecisionModal() {
      const overlay = $("decisionModalOverlay");
      const subtitle = $("decisionModalSubtitle");
      const body = $("decisionModalBody");
      const footer = $("decisionModalFooter");
      if (!overlay || !subtitle || !body || !footer) return;

      if (!state || !decisionModalVisible || state.gameOver) {
        overlay.classList.remove("active");
        return;
      }

      const progressState = decisionProgress();
      const nextCard = state.decisions.find(card => !card.selectedChoice);
      overlay.classList.add("active");
      subtitle.textContent = `${progressState.completed}/${progressState.total} daily questions complete`;

      if (nextCard) {
        // Only one open card is shown at a time. Submitting it asks the server
        // for the updated state, which may expose the next required card.
        body.innerHTML = `
          <div class="decision">
            <div class="decision-head">
              <div class="decision-title">
                <div>
                  <h2>${escapeHtml(nextCard.title)}</h2>
                  <div class="subtle">${escapeHtml(nextCard.type)} | ${escapeHtml(decisionUrgencyLabel(nextCard.severity))}</div>
                </div>
                <span class="badge warn">Open</span>
              </div>
              <p>${escapeHtml(nextCard.description)}</p>
            </div>
            ${nextCard.choices.map(choice => `
              <button class="choice ${pendingChoice === choice.id ? "selected" : ""}" onclick="pendingChoice='${choice.id}';renderDecisionModal()">
                <strong>${escapeHtml(choice.label)}</strong>
                <small>${escapeHtml(choice.description)}</small>
              </button>
            `).join("")}
          </div>
        `;
        footer.innerHTML = `
          <button onclick="dismissDecisionModal()">Close</button>
          <button ${!pendingChoice ? "disabled" : ""} class="primary" onclick="submitDecision('${nextCard.id}')">Submit</button>
        `;
        return;
      }

      body.innerHTML = `
        <div class="reveal-panel">
          <h3>All choices made for today.</h3>
          <div class="subtle">End the day to process the schedule and reveal the daily consequences.</div>
        </div>
      `;
      footer.innerHTML = `
        <button onclick="dismissDecisionModal()">Close</button>
        <button class="primary" onclick="prepareAdvanceDay()">End Day</button>
      `;
    }

    function renderSummary() {
      const summary = state.lastSummary;
      $("summarySection").classList.toggle("hidden", !summary);
      if (!summary) return;
      $("summaryMetrics").innerHTML = `
        <h3>Day Result</h3>
        <table>
          <tbody>
            <tr><td>Subjobs completed today</td><td>${summary.completedToday}</td></tr>
            <tr><td>Subjobs remaining</td><td>${summary.jobsRemaining}</td></tr>
            <tr><td>Jobs complete</td><td>${summary.piecesCompleted}/${state.pieces.length}</td></tr>
            <tr><td>Subjobs late</td><td>${summary.jobsLate}</td></tr>
            <tr><td>Cost</td><td>${fmtNum(summary.cost)}</td></tr>
            <tr><td>Risk</td><td>${Math.round(summary.risk)}/100</td></tr>
            <tr><td>Projected completion</td><td>${summary.projectedCompletion}</td></tr>
          </tbody>
        </table>

        <h3>Past Due Subjobs</h3>
        ${renderPastDueJobs(summary.pastDueJobs)}
      `;
      $("summaryNotes").innerHTML = (summary.notes || []).map(note => `<li>${escapeHtml(note)}</li>`).join("") || "<li>No notable notes recorded.</li>";
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
            <td>Subjobs late</td>
            <td>${p.jobsLate}</td>
            <td>${a.jobsLate}</td>
          </tr>
          <tr>
            <td>Cost</td>
            <td>${fmtNum(p.cost)}</td>
            <td>${fmtNum(a.cost)}</td>
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
              <td>${row.aligned ? "Yes" : "No"}</td>
            </tr>
          `).join("")}
        </tbody>
      `;
    }

    function table(el, headers, rows) {
      el.innerHTML = `
        <thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead>
        <tbody>${rows.length ? rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${headers.length}">No rows</td></tr>`}</tbody>
      `;
    }

    function progressCell(value, status = "") {
      const tone = status === "Complete" ? "good" : status === "Not Started" ? "muted" : status === "Blocked" || status === "At Risk" ? "warn" : "info";
      return `<div>${fmtPct(value)}</div><div class="progress"><div class="bar ${tone}" style="width:${Math.max(0, Math.min(1, value)) * 100}%"></div></div>`;
    }

    function badge(value, tone) {
      return `<span class="badge ${tone || ""}">${escapeHtml(String(value))}</span>`;
    }

    function pieceStatusLabel(status) {
      return status;
    }

    function pieceStatusTone(status) {
      if (status === "Complete") return "good";
      if (status === "In Progress") return "progress";
      if (status === "At Risk" || status === "Blocked") return "warn";
      return "info";
    }

    function decisionUrgencyLabel(severity) {
      if (severity >= 5) return "Severe urgency";
      if (severity >= 4) return "High urgency";
      if (severity >= 3) return "Elevated urgency";
      if (severity >= 2) return "Moderate urgency";
      return "Low urgency";
    }

    function jobLabel(value, hasRework) {
      const label = escapeHtml(String(value || "-"));
      if (!hasRework || label === "-") return label;
      // Rework is a visual flag, not a separate table column, so dense boards
      // can still be scanned without widening every job table.
      return `${label}<span class="rework-flag" title="Rework required or completed" aria-label="Rework"></span>`;
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
    }

    $("settingsMenuBtn").addEventListener("click", toggleSettingsMenu);
    $("openNewRunModalBtn").addEventListener("click", openNewRunModal);
    $("decisionBtn").addEventListener("click", openDecisionModal);
    $("advanceBtn").addEventListener("click", prepareAdvanceDay);
    document.addEventListener("click", (e) => {
      const finalOverlay = document.getElementById("finalModalOverlay");
      const pieceOverlay = document.getElementById("pieceModalOverlay");
      const welcomeOverlay = document.getElementById("welcomeModalOverlay");
      const decisionOverlay = document.getElementById("decisionModalOverlay");
      const newRunOverlay = document.getElementById("newRunModalOverlay");
      const settingsWrap = document.querySelector(".settings-wrap");
      if (settingsWrap && !settingsWrap.contains(e.target)) {
        closeSettingsMenu();
      }
      if (e.target && e.target.id === "closeWelcomeBtn") {
        closeWelcomeModal();
      }
      if (e.target && e.target.id === "closeDecisionBtn") {
        dismissDecisionModal();
      }
      if (e.target && e.target.id === "closeNewRunModalBtn") {
        closeNewRunModal();
      }
      if (e.target && e.target.id === "closeModalBtn") {
        if (pendingAdvanceState) {
          commitAdvanceDay();
        }
      }
      if (e.target && e.target.id === "closeFinalBtn") {
        closeFinalModal();
      }
      if (e.target && e.target.id === "closePieceModalBtn") {
        pieceModalVisible = false;
        render();
      }
      if (finalOverlay && e.target === finalOverlay) {
        closeFinalModal();
      }
      if (pieceOverlay && e.target === pieceOverlay) {
        pieceModalVisible = false;
        render();
      }
      if (welcomeOverlay && e.target === welcomeOverlay) {
        closeWelcomeModal();
      }
      if (decisionOverlay && e.target === decisionOverlay) {
        dismissDecisionModal();
      }
      if (newRunOverlay && e.target === newRunOverlay) {
        closeNewRunModal();
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
  </script>

  <!-- End-of-day modal (centered) -->
  <div id="summaryModalOverlay" class="modal-overlay" role="dialog" aria-modal="true">
    <div class="modal">
      <h1>Daily Summary</h1>
      <div class="modal-body" id="summaryModalBody"></div>
      <div>
        <h3>Updates</h3>
        <ul class="notes" id="summaryModalNotes"></ul>
      </div>
      <div class="modal-footer">
        <button id="modalAdvanceBtn" class="primary" onclick="commitAdvanceDay()">Advance Day</button>
      </div>
    </div>
  </div>
  <!-- Final-run modal (centered) -->
  <div id="finalModalOverlay" class="modal-overlay" role="dialog" aria-modal="true">
    <div class="modal">
      <div class="modal-body" id="finalModalBody"></div>
      <div>
        <h3>Outcome Drivers</h3>
        <ul class="notes" id="finalModalNotes"></ul>
      </div>
      <div id="finalModalAudit"></div>
      <div class="modal-footer">
        <button id="closeFinalBtn" class="primary" onclick="closeFinalModal()">Close</button>
      </div>
    </div>
  </div>
  <div id="pieceModalOverlay" class="modal-overlay" role="dialog" aria-modal="true">
    <div class="modal">
      <div class="modal-body" id="pieceModalBody"></div>
      <div class="modal-footer">
        <button id="closePieceModalBtn" class="primary" onclick="closePieceModal()">Close</button>
      </div>
    </div>
  </div>
</body>
</html>
"""
