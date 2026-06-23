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

    html[data-theme="dark"] .tabbar button {
      background: #1a202a;
      color: #a5b0b8;
    }

    html[data-theme="dark"] .tabbar button.active {
      background: #2a3543;
      border-bottom-color: #2a3543;
      color: #5dd9e0;
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

    html[data-theme="dark"] .shift-lane,
    html[data-theme="dark"] .calendar-job {
      background: #252d38;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .shift-lane-head {
      background: #1a202a;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .calendar-meta,
    html[data-theme="dark"] .calendar-empty {
      color: #a5b0b8;
    }

    html[data-theme="dark"] .calendar-empty {
      background: #1a202a;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .settings-panel {
      background: #1a202a;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .settings-warning {
      background: #3a2a1a;
      border-color: #7a5a2a;
      color: #f0ad4e;
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
    .settings-fields {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .settings-fields label,
    .settings-form label {
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .settings-fields input,
    .settings-form input,
    .settings-form select {
      width: 100%;
      min-width: 0;
    }
    .settings-warning {
      padding: 9px 10px;
      border: 1px solid #e0b96a;
      border-radius: 8px;
      background: #fff7e2;
      color: #805b13;
      font-weight: 700;
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
      grid-template-columns: repeat(6, minmax(120px, 1fr));
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

    .tabbar {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 10px 14px 0;
    }
    .tabbar button {
      height: 32px;
      border-radius: 6px 6px 0 0;
      background: #f0f3ef;
      display: inline-flex;
      align-items: center;
    }
    .tabbar button.active {
      background: #fff;
      border-bottom-color: #fff;
      color: var(--teal-dark);
    }
    .view { display: none; padding: 14px; }
    .view.active { display: block; }
    .view-controls {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
    }

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

    .daily-calendar {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 12px;
    }
    .shift-lane {
      min-width: 0;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcf9;
    }
    .shift-lane-head {
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 10px;
      padding: 10px 11px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }
    .shift-jobs {
      display: grid;
      gap: 8px;
      max-height: 520px;
      overflow: auto;
      padding: 10px;
    }
    .calendar-job {
      min-width: 0;
      padding: 9px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--teal);
      border-radius: 8px;
      background: #fff;
    }
    .calendar-job.warn { border-left-color: var(--amber); }
    .calendar-job.danger { border-left-color: var(--red); }
    .calendar-job.info { border-left-color: var(--teal); }
    .calendar-job-top {
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 8px;
      flex-wrap: wrap;
    }
    .calendar-tags {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 4px;
    }
    .calendar-meta {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 4px 8px;
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }
    .calendar-meta span {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .calendar-empty {
      padding: 14px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--muted);
      text-align: center;
      font-weight: 650;
    }

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
    .tabbar .info-icon:hover::after {
      width: min(280px, 70vw);
      white-space: normal;
      line-height: 1.3;
      text-align: left;
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
          <span class="badge warn" id="decisionProgress">0/0 Daily Decisions Handled</span>
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
      <section>
        <div class="section-head">
          <div>
            <h2>Project Position</h2>
            <div class="subtle" id="projectedText">Projected completion</div>
          </div>
        </div>
        <div class="metrics" id="metrics"></div>
      </section>

      <section>
        <div class="section-head">
          <h2>Operating Board</h2>
        </div>
        <div class="tabbar">
          <button data-tab="shops" class="active">Shops<span class="info-icon" data-tooltip="Shows queue pressure, blocked work, workstation utilization, idle time, shop risk, and active disruptions by shop.">i</span></button>
          <button data-tab="calendar">Daily Calendar<span class="info-icon" data-tooltip="Shows the subjobs planned across today's three work shifts from current workcenter queues.">i</span></button>
          <button data-tab="pieces">Jobs<span class="info-icon" data-tooltip="Shows each job's completion progress, blocked subjob count, critical-path exposure, final subjob due date, and risk.">i</span></button>
          <button data-tab="workcenters">Workcenters<span class="info-icon" data-tooltip="Shows the selected shop's machines or stations, current subjob, queue depth, next subjob, capability, and downtime.">i</span></button>
          <button data-tab="critical">Critical Path<span class="info-icon" data-tooltip="Shows subjobs most likely to control the final completion date, including slack, blockers, downstream impact, and risk.">i</span></button>
          <button data-tab="risks">Risk Register<span class="info-icon" data-tooltip="Shows active disruptions, warnings, and blocked subjobs that need schedule response or mitigation.">i</span></button>
        </div>
        <div id="shops" class="view active"><div class="table-wrap"><table id="shopsTable"></table></div></div>
        <div id="calendar" class="view"><div id="dailyCalendar" class="daily-calendar"></div></div>
        <div id="pieces" class="view"><div class="table-wrap"><table id="piecesTable"></table></div></div>
        <div id="workcenters" class="view">
          <div class="view-controls">
            <select id="shopSelect" aria-label="Select shop"></select>
          </div>
          <div class="table-wrap"><table id="workcentersTable"></table></div>
        </div>
        <div id="critical" class="view"><div class="table-wrap"><table id="criticalTable"></table></div></div>
        <div id="risks" class="view"><div class="table-wrap"><table id="risksTable"></table></div></div>
      </section>

      <section id="summarySection" class="hidden">
        <div class="section-head"><h2>End-of-Day Summary</h2></div>
        <div class="split">
          <div class="reveal-panel" id="summaryMetrics"></div>
          <div class="reveal-panel"><h3>Updates</h3><ul class="notes" id="summaryNotes"></ul></div>
        </div>
      </section>

      <section id="finalSection" class="hidden">
        <div class="section-head">
          <div>
            <h2>Final Operational Comparison</h2>
            <div class="subtle">The silent benchmark is revealed only after the run ends.</div>
          </div>
        </div>
        <div class="split">
          <div class="reveal-panel"><h3>Metric Comparison</h3><table id="finalTable"></table></div>
          <div class="reveal-panel"><h3>Outcome Drivers</h3><ul class="notes" id="finalNotes"></ul></div>
        </div>
      </section>
    </div>

  </main>

  <div id="welcomeModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="welcomeModalTitle">
    <div class="modal">
      <h1 id="welcomeModalTitle">Welcome</h1>
      <div class="welcome-copy">
        <p>You are managing a manufacturing schedule under disruption. Each day, inspect the operating board, read the active risks, and choose how the yard should respond.</p>
        <p>Your goal is to complete every job before <span id="welcomeDeadline">the deadline</span> while balancing cost, reschedules, workstation utilization, and schedule risk.</p>
        <ul>
          <li>Review shops, workcenters, jobs, the critical path, and the risk register.</li>
          <li>Answer the daily decision cards to resequence, reroute, expedite, or protect critical work.</li>
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
          <div class="subtle">Choose a preset, seed, and scenario size.</div>
        </div>
        <button id="closeNewRunModalBtn" class="icon-button" title="Close new run settings" onclick="closeNewRunModal()">×</button>
      </div>
      <div class="modal-body">
        <div class="settings-form">
          <label>
            Preset
            <select id="runPresetSelect">
              <option value="normal">Normal</option>
              <option value="demo">Demo</option>
              <option value="custom">Custom</option>
            </select>
          </label>
          <label>
            Seed
            <input id="runSeedInput" inputmode="numeric" placeholder="Random">
          </label>
          <div id="settingsWarning" class="settings-warning hidden">
            Editing these fields can make the game unplayable or impossible to finish.
          </div>
          <div id="newRunError" class="modal-error hidden"></div>
          <div class="settings-fields">
            <label>
              Days
              <input id="runDaysInput" type="number" min="1" max="90">
            </label>
            <label>
              Jobs
              <input id="runPiecesInput" type="number" min="1" max="30">
            </label>
            <label>
              Min Subjobs per Job
              <input id="runMinJobsInput" type="number" min="1" max="20">
            </label>
            <label>
              Max Subjobs per Job
              <input id="runMaxJobsInput" type="number" min="1" max="20">
            </label>
          </div>
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
    let activeTab = "shops";
    // Client-side modal state is intentionally local. The server remains the
    // source of truth for the run, decisions, and day advancement rules.
    let welcomeModalVisible = false;
    let decisionModalVisible = false;
    let newRunModalVisible = false;
    let settingsMenuOpen = false;
    let settingsEdited = false;
    let finalModalDismissed = false;
    let dismissedDecisionKey = null;
    let suppressNextDecisionPrompt = false;
    const runPresets = {
      normal: { totalDays: 15, pieceCount: 15, minJobsPerPiece: 5, maxJobsPerPiece: 10 },
      demo: { totalDays: 5, pieceCount: 5, minJobsPerPiece: 1, maxJobsPerPiece: 2 }
    };

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
        clampRunSettings();
        const minJobs = Number($("runMinJobsInput").value);
        const maxJobs = Number($("runMaxJobsInput").value);
        if (minJobs > maxJobs) {
          showNewRunError("Minimum subjobs per job cannot be greater than maximum subjobs per job.");
          return;
        }
        const seed = $("runSeedInput").value.trim();
        const mode = $("runPresetSelect").value;
        state = await api("/api/new", {
          method: "POST",
          body: JSON.stringify({
            seed,
            mode,
            settings: {
              total_days: $("runDaysInput").value,
              piece_count: $("runPiecesInput").value,
              min_jobs_per_piece: $("runMinJobsInput").value,
              max_jobs_per_piece: $("runMaxJobsInput").value
            }
          })
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
        decisionModalVisible = true;
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
          finalModalVisible = true;
          finalModalDismissed = false;
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
      suppressNextDecisionPrompt = true;
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
      renderShopOptions();
      renderTables();
      renderDecisions();
      renderSummary();
      renderSummaryModal();
      renderFinal();
      renderPieceModal();
      renderWelcomeModal();
      renderNewRunModal();
      renderSettingsMenu();
      maybeAutoOpenDecisionModal();
      renderDecisionModal();
      // Auto-open final modal if run finished.
      if (state.finalReveal && !finalModalVisible && !finalModalDismissed) finalModalVisible = true;
      renderFinalModal();
    }

    function selectedDecisionCount() {
      return state ? state.decisions.filter(card => card.selectedChoice).length : 0;
    }

    function readyToAdvance() {
      return Boolean(state && !state.gameOver && selectedDecisionCount() === state.decisions.length);
    }

    function decisionPromptKey() {
      if (!state) return "";
      const nextCard = state.decisions.find(card => !card.selectedChoice);
      // A dismissed decision modal should stay dismissed only until the next
      // unresolved card appears or the day's completion state changes.
      return `${state.day}:${selectedDecisionCount()}:${nextCard ? nextCard.id : "complete"}`;
    }

    function maybeAutoOpenDecisionModal() {
      // Decisions should be "in your face" when they need attention, but not
      // fight with other modals or reopen immediately after the user dismisses.
      if (!state || state.gameOver || welcomeModalVisible || finalModalVisible || modalVisible || pieceModalVisible) {
        return;
      }
      const hasOpenDecision = state.decisions.some(card => !card.selectedChoice);
      if (!hasOpenDecision) {
        suppressNextDecisionPrompt = false;
        return;
      }
      if (hasOpenDecision && suppressNextDecisionPrompt) {
        dismissedDecisionKey = decisionPromptKey();
        suppressNextDecisionPrompt = false;
        decisionModalVisible = false;
        return;
      }
      if (hasOpenDecision && dismissedDecisionKey !== decisionPromptKey()) {
        decisionModalVisible = true;
      }
    }

    function openDecisionModal() {
      if (!state || state.gameOver) return;
      dismissedDecisionKey = null;
      decisionModalVisible = true;
      renderDecisionModal();
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

    function renderWelcomeModal() {
      const overlay = document.getElementById("welcomeModalOverlay");
      if (!overlay) return;
      overlay.classList.toggle("active", welcomeModalVisible);
    }

    function closeWelcomeModal() {
      welcomeModalVisible = false;
      suppressNextDecisionPrompt = true;
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
      settingsEdited = false;
      showNewRunError("");
      const mode = state ? state.mode || "normal" : "normal";
      $("runPresetSelect").value = mode;
      applyRunSettings(state && state.settings ? state.settings : runPresets[mode]);
      $("runSeedInput").value = "";
      renderNewRunModal();
    }

    function closeNewRunModal() {
      newRunModalVisible = false;
      showNewRunError("");
      renderNewRunModal();
    }

    function renderNewRunModal() {
      const overlay = $("newRunModalOverlay");
      const warning = $("settingsWarning");
      if (!overlay || !warning) return;
      overlay.classList.toggle("active", newRunModalVisible);
      warning.classList.toggle("hidden", !settingsEdited);
    }

    function applyRunSettings(settings) {
      $("runDaysInput").value = settings.totalDays;
      $("runPiecesInput").value = settings.pieceCount;
      $("runMinJobsInput").value = settings.minJobsPerPiece;
      $("runMaxJobsInput").value = settings.maxJobsPerPiece;
      clampRunSettings();
    }

    function applyRunPreset() {
      const preset = $("runPresetSelect").value;
      if (preset === "custom") {
        settingsEdited = true;
        renderNewRunModal();
        return;
      }
      applyRunSettings(runPresets[preset] || runPresets.normal);
      settingsEdited = false;
      renderNewRunModal();
    }

    function markSettingsEdited() {
      clampRunInput(this);
      $("runPresetSelect").value = "custom";
      settingsEdited = true;
      showNewRunError("");
      renderNewRunModal();
    }

    function clampRunInput(input) {
      if (!input || input.value === "") return;
      const min = Number(input.min);
      const max = Number(input.max);
      let value = Number(input.value);
      if (!Number.isFinite(value)) {
        input.value = input.min || "";
        return;
      }
      if (Number.isFinite(min) && value < min) value = min;
      if (Number.isFinite(max) && value > max) value = max;
      input.value = String(Math.trunc(value));
    }

    function clampRunSettings() {
      ["runDaysInput", "runPiecesInput", "runMinJobsInput", "runMaxJobsInput"].forEach(id => clampRunInput($(id)));
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
      body.innerHTML = `
        <table>
          <tbody>
            <tr><td>Deadline met</td><td>${p.deadlineMet ? "Yes" : "No"}</td><td>${a.deadlineMet ? "Yes" : "No"}</td></tr>
            <tr><td>Project completed</td><td>${p.finalItemCompleted ? "Yes" : "No"}</td><td>${a.finalItemCompleted ? "Yes" : "No"}</td></tr>
            <tr><td>Completion</td><td>${p.completion || "Not complete"}</td><td>${a.completion || "Not complete"}</td></tr>
            <tr><td>Jobs complete</td><td>${p.piecesCompleted}</td><td>${a.piecesCompleted}</td></tr>
            <tr><td>Subjobs completed</td><td>${p.jobsCompleted}</td><td>${a.jobsCompleted}</td></tr>
            <tr><td>Subjobs late</td><td>${p.jobsLate}</td><td>${a.jobsLate}</td></tr>
            <tr><td>Workstation Utilization</td><td>${fmtPct(p.utilization)}</td><td>${fmtPct(a.utilization)}</td></tr>
            <tr><td>Idle time</td><td>${p.idleTime}</td><td>${a.idleTime}</td></tr>
            <tr><td>Reschedules</td><td>${p.reschedules}</td><td>${a.reschedules}</td></tr>
            <tr><td>Cost</td><td>${fmtNum(p.cost)}</td><td>${fmtNum(a.cost)}</td></tr>
            <tr><td>Schedule risk</td><td>${Math.round(p.scheduleRisk)}</td><td>${Math.round(a.scheduleRisk)}</td></tr>
          </tbody>
        </table>
      `;
      body.scrollTop = 0;
      notes.innerHTML = (final.explanation || []).map(note => `<li>${escapeHtml(note)}</li>`).join("");
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
        ["Workstation Utilization", fmtPct(snap.utilization), snap.utilization, "info", "How busy your workstations are (0% = idle, 100% = fully busy)."],
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

    function renderShopOptions() {
      const select = $("shopSelect");
      const current = select.value || state.shops[0]?.id;
      // Preserve the selected shop across refreshes unless a new run no longer
      // contains that shop id.
      select.innerHTML = state.shops.map(shop => `<option value="${shop.id}">${shop.name}</option>`).join("");
      select.value = state.shops.some(shop => shop.id === current) ? current : state.shops[0]?.id;
    }

    function renderTables() {
      // Tables are rebuilt from the latest state payload. This is simple and
      // adequate for the small local dashboard; no client-side cache is needed.
      table($("shopsTable"), ["Shop", "Active", "Queued", "Blocked", "Complete", "Util.", "Idle", "Risk", "Risk Job", "Event"], state.shops.map(shop => [
        shop.name,
        shop.active,
        shop.queued,
        shop.blocked,
        shop.completed,
        fmtPct(shop.utilization),
        shop.idle,
        badge(Math.round(shop.risk), shop.risk > 70 ? "danger" : shop.risk > 40 ? "warn" : "info"),
        shop.highestRiskPiece,
        shop.event || "-"
      ]));

      table($("piecesTable"), ["Job", "Status", "Progress", "Subjobs", "Blocked", "Critical", "Due Date", "Risk"], state.pieces.sort((a, b) => {
        const numA = parseInt(a.id.replace(/\D/g, '')) || 0;
        const numB = parseInt(b.id.replace(/\D/g, '')) || 0;
        return numA - numB;
      }).map(piece => [
        `<button class="link-button" onclick="openPieceModal('${piece.id}')">${escapeHtml(piece.displayId || piece.id)}</button>`,
        badge(pieceStatusLabel(piece.status), pieceStatusTone(piece.status)),
        progressCell(piece.progress, piece.status),
        `${piece.completed}/${piece.total}`,
        piece.blocked,
        piece.critical ? "Yes" : "",
        piece.dueDate,
        Math.round(piece.risk)
      ]));

      const shopId = $("shopSelect").value || state.shops[0]?.id;
      table($("workcentersTable"), ["Workcenter", "Status", "Current", "Remain", "Queue", "Next", "Capability", "Down"], (state.workcenters[shopId] || []).map(wc => [
        wc.id,
        badge(wc.status, wc.status === "Busy" ? "info" : wc.status === "Idle" || wc.status === "Available" ? "good" : "danger"),
        jobLabel(wc.current, wc.currentRework),
        wc.remaining,
        wc.queue,
        jobLabel(wc.next, wc.nextRework),
        wc.capability,
        wc.down
      ]));

      table($("criticalTable"), ["Subjob", "Shop", "WC", "Remain", "Slack", "Block", "Impact", "Risk"], state.criticalPath.map(job => [
        jobLabel(job.id, job.rework),
        job.shop,
        job.workcenter,
        job.remaining,
        badge(job.slack, job.slack < 0 ? "danger" : job.slack < 8 ? "warn" : "info"),
        job.block,
        job.impact,
        Math.round(job.risk)
      ]));

      table($("risksTable"), ["Status", "ID", "Risk", "Affected", "Severity", "Shifts", "Source", "Response"], state.risks.map(risk => [
        badge(risk.status, risk.status === "Active" || risk.status === "Blocked" ? "danger" : "warn"),
        jobLabel(risk.id, risk.rework),
        risk.type,
        risk.affected,
        risk.severity,
        risk.shifts,
        risk.source || "-",
        risk.response
      ]));

      renderDailyCalendar();
    }

    function renderDailyCalendar() {
      const target = $("dailyCalendar");
      if (!target) return;
      const calendar = state.dailyCalendar || { label: "Day", shifts: [] };
      target.innerHTML = (calendar.shifts || []).map(shift => `
        <div class="shift-lane">
          <div class="shift-lane-head">
            <div>
              <h3>${escapeHtml(shift.dayLabel || shift.label)}</h3>
              <div class="subtle">${escapeHtml(calendar.label || "")}</div>
            </div>
            <span class="badge info">${(shift.jobs || []).length} subjobs</span>
          </div>
          <div class="shift-jobs">
            ${(shift.jobs || []).length ? shift.jobs.map(renderCalendarJob).join("") : `<div class="calendar-empty">No scheduled subjobs</div>`}
          </div>
        </div>
      `).join("");
    }

    function renderCalendarJob(job) {
      const tone = job.late ? "danger" : job.critical ? "warn" : job.status === "Running" ? "info" : "";
      const statusTone = job.late ? "danger" : job.status === "Running" ? "info" : "good";
      return `
        <article class="calendar-job ${tone}">
          <div class="calendar-job-top">
            <strong>${jobLabel(job.id, job.rework)}</strong>
            <div class="calendar-tags">
              ${badge(job.late ? "Late" : job.status, statusTone)}
              ${job.critical ? badge("Critical", "warn") : ""}
            </div>
          </div>
          <div class="calendar-meta">
            <span>${escapeHtml(job.piece)}</span>
            <span>${escapeHtml(job.shop)}</span>
            <span>${escapeHtml(job.workcenter)}</span>
            <span>${escapeHtml(job.capability)}</span>
            <span>Remain ${escapeHtml(job.remaining)}</span>
            <span>Due ${escapeHtml(job.due)}</span>
          </div>
        </article>
      `;
    }

    function renderDecisions() {
      const chosenCount = state.decisions.filter(card => card.selectedChoice).length;
      const totalCount = state.decisions.length;
      const remainingCount = Math.max(0, totalCount - chosenCount);
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

      progress.textContent = `${chosenCount}/${totalCount} Daily Decisions Handled`;
      progress.className = `badge ${remainingCount ? "warn" : "good"}`;
      decisionBtn.disabled = false;
      decisionBtn.textContent = remainingCount ? `Daily Decisions (${remainingCount})` : "Daily Decisions";
      advanceBtn.disabled = !readyToAdvance();
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

      const chosenCount = selectedDecisionCount();
      const totalCount = state.decisions.length;
      const nextCard = state.decisions.find(card => !card.selectedChoice);
      overlay.classList.add("active");
      subtitle.textContent = `${chosenCount}/${totalCount} responses selected`;

      if (nextCard) {
        // Only one open card is shown at a time. Submitting it asks the server
        // for the updated state, which may expose the next required card.
        body.innerHTML = `
          <div class="decision">
            <div class="decision-head">
              <div class="decision-title">
                <div>
                  <h2>${escapeHtml(nextCard.title)}</h2>
                  <div class="subtle">${escapeHtml(nextCard.type)} | Severity ${nextCard.severity}</div>
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
      `;
      $("summaryNotes").innerHTML = (summary.notes || []).map(note => `<li>${escapeHtml(note)}</li>`).join("") || "<li>No notable notes recorded.</li>";
    }

    function renderFinal() {
      const final = state.finalReveal;
      $("finalSection").classList.toggle("hidden", !final);
      if (!final) return;
      const p = final.player;
      const a = final.automated;
      table($("finalTable"), ["Metric", "Player", "ECHO"], [
        ["Deadline met", p.deadlineMet ? "Yes" : "No", a.deadlineMet ? "Yes" : "No"],
        ["Project completed", p.finalItemCompleted ? "Yes" : "No", a.finalItemCompleted ? "Yes" : "No"],
        ["Completion", p.completion || "Not complete", a.completion || "Not complete"],
        ["Jobs complete", p.piecesCompleted, a.piecesCompleted],
        ["Subjobs completed", p.jobsCompleted, a.jobsCompleted],
        ["Subjobs late", p.jobsLate, a.jobsLate],
        ["Workstation Utilization", fmtPct(p.utilization), fmtPct(a.utilization)],
        ["Idle time", p.idleTime, a.idleTime],
        ["Reschedules", p.reschedules, a.reschedules],
        ["Cost", fmtNum(p.cost), fmtNum(a.cost)],
        ["Schedule risk", Math.round(p.scheduleRisk), Math.round(a.scheduleRisk)]
      ]);
      $("finalNotes").innerHTML = final.explanation.map(note => `<li>${escapeHtml(note)}</li>`).join("");
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

    // Tab selection only changes visibility; all tab tables are refreshed from
    // the latest payload whenever renderTables runs.
    document.querySelectorAll(".tabbar button").forEach(button => {
      button.addEventListener("click", () => {
        activeTab = button.dataset.tab;
        document.querySelectorAll(".tabbar button").forEach(item => item.classList.toggle("active", item.dataset.tab === activeTab));
        document.querySelectorAll(".view").forEach(view => view.classList.toggle("active", view.id === activeTab));
      });
    });

    $("shopSelect").addEventListener("change", renderTables);
    $("settingsMenuBtn").addEventListener("click", toggleSettingsMenu);
    $("openNewRunModalBtn").addEventListener("click", openNewRunModal);
    $("decisionBtn").addEventListener("click", openDecisionModal);
    $("advanceBtn").addEventListener("click", prepareAdvanceDay);
    $("runPresetSelect").addEventListener("change", applyRunPreset);
    ["runDaysInput", "runPiecesInput", "runMinJobsInput", "runMaxJobsInput"].forEach(id => {
      $(id).addEventListener("input", markSettingsEdited);
    });
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
