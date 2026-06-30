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

    html[data-theme="dark"] .decision-prompt {
      background: #252d38;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .decision-prompt p {
      color: #f0f3f5;
    }

    html[data-theme="dark"] .day-progress-track {
      background: #252d38;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .day-progress-fill {
      background: #5dd9e0;
    }

    html[data-theme="dark"] .day-progress-fill.paused {
      background: #f0ad4e;
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
      position: relative;
    }
    .metric strong {
      display: block;
      font-size: 22px;
      line-height: 1.1;
      margin-top: 6px;
    }
    .metric.hoverable {
      cursor: help;
      border-color: rgba(22, 124, 120, 0.34);
      box-shadow: 0 0 0 1px rgba(22, 124, 120, 0.08);
    }
    .metric-title-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .metric-hint {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      min-height: 22px;
      padding: 2px 7px;
      border: 1px solid rgba(22, 124, 120, 0.22);
      border-radius: 999px;
      color: var(--teal-dark);
      background: rgba(22, 124, 120, 0.08);
      font-size: 11px;
      font-weight: 760;
      line-height: 1;
      white-space: nowrap;
    }
    .metric-hint::after {
      content: "";
      width: 0;
      height: 0;
      border-left: 4px solid transparent;
      border-right: 4px solid transparent;
      border-top: 5px solid currentColor;
      flex: 0 0 auto;
    }
    .metric-popover {
      display: none;
      position: absolute;
      top: calc(100% + 8px);
      left: 0;
      z-index: 50;
      width: min(560px, calc(100vw - 44px));
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
      cursor: default;
    }
    .metric.hoverable:hover .metric-popover,
    .metric.hoverable:focus-within .metric-popover {
      display: block;
    }
    .metric-popover h3 {
      margin-bottom: 9px;
    }
    .metric-popover-frame {
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    .metric-popover table {
      table-layout: auto;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 12px;
    }
    .metric-popover th {
      background: #f6f8f5;
    }
    .metric-popover th,
    .metric-popover td {
      border-bottom: 0;
      padding: 7px 8px;
      white-space: nowrap;
    }
    .metric-popover td:first-child {
      white-space: normal;
      min-width: 92px;
    }
    html[data-theme="dark"] .metric-popover {
      background: #1a202a;
      border-color: #3a4352;
    }
    html[data-theme="dark"] .metric.hoverable {
      border-color: rgba(93, 217, 224, 0.32);
      box-shadow: 0 0 0 1px rgba(93, 217, 224, 0.08);
    }
    html[data-theme="dark"] .metric-hint {
      background: rgba(93, 217, 224, 0.1);
      border-color: rgba(93, 217, 224, 0.22);
      color: #5dd9e0;
    }
    html[data-theme="dark"] .metric-popover-frame {
      border-color: #3a4352;
    }
    html[data-theme="dark"] .metric-popover th {
      background: #252d38;
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
      width: 100%;
    }
    .decision-choices {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 8px;
      padding: 10px;
    }
    .decision-choices .choice {
      width: 100%;
      min-height: 76px;
      margin: 0;
    }
    .inline-decision-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
      padding: 2px 10px 10px;
    }
    .decision-status-panel {
      display: grid;
      gap: 10px;
    }
    .decision-status-panel .inline-decision-actions {
      padding: 0;
    }
    .day-clock {
      display: grid;
      gap: 7px;
    }
    .day-clock-row {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .day-progress-track {
      width: 100%;
      height: 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #eef2ee;
      overflow: hidden;
    }
    .day-progress-fill {
      height: 100%;
      width: 0;
      border-radius: 999px;
      background: var(--teal);
      transition: width 180ms linear, background-color 180ms ease;
    }
    .day-progress-fill.paused {
      background: var(--amber);
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
      position: relative;
      overflow: visible;
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
    .chart-dot {
      cursor: pointer;
    }
    .chart-dot:focus {
      outline: none;
      filter: drop-shadow(0 0 4px rgba(22, 124, 120, 0.32));
    }
    .chart-tooltip {
      position: absolute;
      z-index: 5;
      display: none;
      width: min(320px, calc(100vw - 64px));
      padding: 10px 11px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      box-shadow: var(--shadow);
      font-size: 12px;
      line-height: 1.35;
      pointer-events: none;
    }
    .chart-tooltip.active { display: block; }
    .chart-tooltip strong {
      display: block;
      margin-bottom: 5px;
      font-size: 13px;
    }
    .chart-tooltip div { margin-top: 3px; }
    html[data-theme="dark"] .chart-tooltip {
      background: #1a202a;
      border-color: #3a4352;
    }
    .submarine-puzzle {
      display: grid;
      gap: 10px;
      margin-bottom: 14px;
    }
    .puzzle-caption {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
      color: var(--muted);
    }
    .puzzle-caption strong {
      color: var(--ink);
    }
    .puzzle-stage {
      width: 100%;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: linear-gradient(180deg, #f0f4f2 0%, #fafbf8 100%);
    }
    .puzzle-stage svg {
      display: block;
      width: 100%;
      height: auto;
    }
    .puzzle-slot {
      fill: rgba(255, 255, 255, 0.48);
      stroke: rgba(102, 112, 109, 0.42);
      stroke-width: 1.6;
      stroke-dasharray: 6 5;
    }
    .puzzle-piece {
      transition: opacity 180ms ease, filter 180ms ease, stroke-width 180ms ease;
    }
    .puzzle-piece.placed {
      fill: #728481;
      stroke: #f7faf7;
      stroke-width: 1.5;
    }
    .puzzle-piece.unplaced {
      fill: #fbfaf4;
      stroke: rgba(102, 112, 109, 0.76);
      stroke-width: 1.7;
      filter: drop-shadow(0 7px 9px rgba(32, 37, 36, 0.16));
    }
    .puzzle-piece.newly-placed {
      stroke: var(--ink);
      stroke-width: 2.4;
      filter: drop-shadow(0 4px 5px rgba(32, 37, 36, 0.18));
    }
    .piece-detail {
      fill: none;
      stroke: rgba(32, 37, 36, 0.34);
      stroke-width: 3;
      stroke-linecap: round;
      stroke-linejoin: round;
      pointer-events: none;
    }
    .piece-detail-fill {
      fill: rgba(247, 250, 247, 0.65);
      stroke: rgba(32, 37, 36, 0.38);
      stroke-width: 3;
      pointer-events: none;
    }
    .puzzle-label {
      font-weight: 800;
      pointer-events: none;
      text-anchor: middle;
      dominant-baseline: middle;
    }
    .puzzle-legend,
    .puzzle-added {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .legend-swatch {
      width: 13px;
      height: 13px;
      border-radius: 3px;
      border: 1px solid var(--line);
      display: inline-block;
    }
    .legend-swatch.placed { background: #728481; }
    .legend-swatch.waiting { background: #fbfaf4; }
    .legend-swatch.slot { background: rgba(255, 255, 255, 0.48); border-style: dashed; }
    .puzzle-added .badge {
      border-radius: 6px;
    }
    html[data-theme="dark"] .puzzle-stage {
      background: linear-gradient(180deg, #17212a 0%, #111821 100%);
    }
    html[data-theme="dark"] .puzzle-slot {
      fill: rgba(37, 45, 56, 0.42);
      stroke: rgba(165, 176, 184, 0.42);
    }
    html[data-theme="dark"] .puzzle-piece.placed {
      fill: #7f9490;
      stroke: #111821;
    }
    html[data-theme="dark"] .puzzle-piece.unplaced {
      fill: #252d38;
      stroke: rgba(165, 176, 184, 0.78);
    }
    html[data-theme="dark"] .piece-detail {
      stroke: rgba(240, 243, 245, 0.38);
    }
    html[data-theme="dark"] .piece-detail-fill {
      fill: rgba(240, 243, 245, 0.14);
      stroke: rgba(240, 243, 245, 0.42);
    }
    html[data-theme="dark"] .legend-swatch.waiting {
      background: #252d38;
    }
    html[data-theme="dark"] .legend-swatch.slot {
      background: rgba(37, 45, 56, 0.42);
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
    .decision-modal {
      max-width: 720px;
    }
    .decision-modal-meta {
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 650;
    }
    .decision-modal-body {
      display: grid;
      gap: 10px;
    }
    .decision-prompt {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfcf9;
    }
    .decision-prompt p {
      margin: 10px 0 0;
      color: var(--ink);
    }
    .decision-modal-choices {
      grid-template-columns: 1fr;
      padding: 0;
    }
    .decision-modal-choices .choice {
      min-height: 68px;
    }
    .welcome-modal {
      max-width: 760px;
    }
    .welcome-copy {
      display: grid;
      gap: 14px;
      margin: 10px 0 4px;
      color: var(--muted);
    }
    .welcome-copy p {
      margin: 0;
    }
    .welcome-visual {
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: linear-gradient(180deg, #edf6f5 0%, #f8fbf8 100%);
    }
    .welcome-visual svg {
      display: block;
      width: 100%;
      height: auto;
    }
    .welcome-blurb {
      color: var(--ink);
      font-size: 18px;
      line-height: 1.45;
      max-width: 620px;
    }
    .welcome-critical {
      display: grid;
      gap: 8px;
    }
    .welcome-critical-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .welcome-critical-list li {
      min-height: 48px;
      padding: 8px 9px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcf9;
    }
    .welcome-critical-list strong {
      display: block;
      color: var(--ink);
      font-size: 13px;
    }
    .welcome-critical-list span {
      display: block;
      margin-top: 2px;
      color: var(--muted);
      font-size: 12px;
    }
    html[data-theme="dark"] .welcome-visual {
      background: linear-gradient(180deg, #16212a 0%, #111821 100%);
    }
    html[data-theme="dark"] .welcome-critical-list li {
      background: #252d38;
      border-color: #3a4352;
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
          <span class="badge warn" id="decisionProgress">Decisions Pending</span>
        </div>
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
          <div class="reveal-panel"><h3>Decision Score Impact</h3><div id="finalCompletionChart"></div></div>
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
    <div class="modal welcome-modal">
      <h1 id="welcomeModalTitle">Welcome</h1>
      <div class="welcome-copy">
        <div class="welcome-visual" aria-label="Submarine">
          <svg viewBox="0 0 720 250" role="img" aria-label="Submarine underway">
            <defs>
              <linearGradient id="welcomeSubBody" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#24a19c"></stop>
                <stop offset="100%" stop-color="#0d5552"></stop>
              </linearGradient>
            </defs>

            <path d="M 60 135 L 85 135 M 50 100 L 60 135 L 50 170" fill="none" stroke="#0d5552" stroke-width="8" stroke-linecap="round"></path>
            <path d="M 110 105 L 75 90 L 85 135 Z" fill="#146b67"></path>
            <path d="M 110 165 L 75 180 L 85 135 Z" fill="#146b67"></path>
            <path d="M 80 135 C 80 80, 160 85, 350 85 C 560 85, 660 100, 660 135 C 660 170, 560 185, 350 185 C 160 185, 80 190, 80 135 Z" fill="url(#welcomeSubBody)"></path>
            <path d="M 300 86 L 310 35 L 380 35 L 390 86 Z" fill="#146b67"></path>
            <path d="M 330 35 L 330 15 L 340 15 M 360 35 L 360 20" fill="none" stroke="#0d5552" stroke-width="5" stroke-linecap="round"></path>
            <path d="M 140 105 C 260 100, 480 100, 620 115" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="4" stroke-linecap="round"></path>
            <g fill="#dff6f4" stroke="#0b4542" stroke-width="4">
              <circle cx="200" cy="135" r="14"></circle>
              <circle cx="260" cy="135" r="14"></circle>
              <circle cx="460" cy="135" r="14"></circle>
              <circle cx="520" cy="135" r="14"></circle>
            </g>
          </svg>
        </div>
        <p class="welcome-blurb" id="welcomeBlurb">Your job is to get these jobs done on time. Each decision you make can risk or reward other jobs.</p>
        <div class="welcome-critical">
          <h3>Critical Path Jobs</h3>
          <ul class="welcome-critical-list" id="welcomeCriticalPath"></ul>
        </div>
      </div>
      <div class="modal-footer">
        <button id="closeWelcomeBtn" class="primary" onclick="closeWelcomeModal()">Start</button>
      </div>
    </div>
  </div>

  <div id="newRunModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="newRunModalTitle">
    <div class="modal">
      <div class="modal-titlebar">
        <div>
          <h1 id="newRunModalTitle">New Game</h1>
          <div class="subtle">Start a fresh run with the standard scenario.</div>
        </div>
        <button id="closeNewRunModalBtn" class="icon-button" title="Close new run settings" onclick="closeNewRunModal()">×</button>
      </div>
      <div class="modal-body">
        <div class="settings-form">
          <p class="subtle">FILLER TEXT (DON'T TOUCH YET)</p>
          <div id="newRunError" class="modal-error hidden"></div>
        </div>
      </div>
      <div class="modal-footer">
        <button onclick="closeNewRunModal()">Cancel</button>
        <button class="primary" onclick="startNewRun()">Start Game</button>
      </div>
    </div>
  </div>

  <div id="decisionModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="decisionModalTitle">
    <div class="modal decision-modal">
      <div class="modal-titlebar">
        <div>
          <h1 id="decisionModalTitle">Daily Decision</h1>
          <div class="decision-modal-meta" id="decisionModalMeta"></div>
        </div>
        <button id="closeDecisionModalBtn" class="icon-button" title="Close decision" onclick="closeDecisionModal()">×</button>
      </div>
      <div class="modal-body decision-modal-body" id="decisionModalBody"></div>
      <div class="modal-footer" id="decisionModalFooter"></div>
    </div>
  </div>

  <script>
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

    function loosePiecePosition(index) {
      const positions = [
        { x: 112, y: 64, angle: -10 },
        { x: 260, y: 56, angle: 7 },
        { x: 430, y: 62, angle: -5 },
        { x: 610, y: 70, angle: 9 },
        { x: 128, y: 356, angle: 8 },
        { x: 300, y: 365, angle: -7 },
        { x: 480, y: 360, angle: 6 },
        { x: 650, y: 344, angle: -8 },
      ];
      if (index < positions.length) return positions[index];
      const extra = index - positions.length;
      const column = extra % 4;
      const row = Math.floor(extra / 4);
      return {
        x: 120 + column * 170,
        y: row % 2 === 0 ? 50 : 370,
        angle: index % 2 === 0 ? -6 : 6,
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
      const height = 420;
      const slots = submarinePieceSlots(total);
      const slotMarkup = slots.map((slot) => `
        <path class="puzzle-slot" d="${slot.path}">
          <title>${escapeHtml(`${slot.part} slot`)}</title>
        </path>
      `).join("");
      const placedMarkup = tiles.map((tile, index) => (
        tile.completed ? renderPuzzleSection(tile, slots[index], "placed") : ""
      )).join("");
      const unplacedMarkup = tiles
        .map((tile, index) => ({ tile, index, slot: slots[index] }))
        .filter((item) => !item.tile.completed)
        .map((item, looseIndex) => {
          const position = loosePiecePosition(looseIndex);
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
            <strong>Submarine Assembly</strong>
            <span>${puzzle.completed}/${puzzle.total} sections assembled; ${puzzle.completedToday} placed today</span>
          </div>
          <div class="puzzle-stage">
            <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Submarine puzzle showing assembled and waiting sections">
              <g aria-hidden="true">${slotMarkup}</g>
              <g>${placedMarkup}</g>
              <g>${unplacedMarkup}</g>
            </svg>
          </div>
          <div class="puzzle-legend">
            <span><span class="legend-swatch placed"></span> Assembled in submarine</span>
            <span><span class="legend-swatch waiting"></span> Waiting outside</span>
            <span><span class="legend-swatch slot"></span> Empty slot</span>
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
      body.innerHTML = `
        ${renderSubmarinePuzzle(summary.puzzle, "summary-modal")}
        <table>
          <tbody>
            <tr><td>Subjobs completed today</td><td>${summary.completedToday}</td></tr>
            <tr><td>Subjobs remaining</td><td>${summary.jobsRemaining}</td></tr>
            <tr><td>Jobs complete</td><td>${summary.piecesCompleted}/${payload.pieces.length}</td></tr>
            <tr><td>Subjobs behind schedule</td><td>${summary.jobsBehindSchedule}</td></tr>
            <tr><td>Subjobs late</td><td>${summary.jobsLate}</td></tr>
            <tr><td>Risk</td><td>${Math.round(summary.risk)}/100</td></tr>
            <tr><td>Projected completion</td><td>${summary.projectedCompletion}</td></tr>
          </tbody>
        </table>

        <h3>Past Due Subjobs</h3>
        ${renderPastDueJobs(summary.pastDueJobs)}

        <h3>Updates</h3>
        <ul class="notes">
          ${(summary.notes || []).map(note => `<li>${escapeHtml(note)}</li>`).join("") || "<li>No notable notes recorded.</li>"}
        </ul>
      `;
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
      const progressState = decisionProgress();
      const decisionsPending = progressState.total > 0 && progressState.completed < progressState.total;
      const progress = $("decisionProgress");
      const advanceBtn = $("advanceBtn");

      if (state.gameOver) {
        progress.textContent = "Run complete";
        progress.className = "badge good";
        if (advanceBtn) advanceBtn.disabled = true;
        return;
      }

      progress.textContent = decisionsPending ? "Decisions Pending" : "Decisions Complete";
      progress.className = `badge ${decisionsPending ? "warn" : "good"}`;
      if (advanceBtn) advanceBtn.disabled = !readyToAdvance();
    }

    function renderInlineDecisions() {
      const subtitle = $("inlineDecisionSubtitle");
      const body = $("inlineDecisionBody");
      if (!subtitle || !body) return;

      if (modalVisible && pendingAdvanceState) {
        subtitle.textContent = "";
        body.innerHTML = "";
        return;
      }

      if (!state || state.gameOver) {
        subtitle.textContent = "Run complete";
        body.innerHTML = `
          <div class="reveal-panel">
            <h3>Campaign decisions are complete.</h3>
            <div class="subtle">Review the final operational comparison at the top of the page.</div>
          </div>
        `;
        return;
      }

      const progressState = decisionProgress();
      subtitle.textContent = `Day ${Math.round(dayCyclePercent())}%`;
      const nextCard = currentOpenDecisionCard();

      if (nextCard) {
        if (!nextCard.choices.some(choice => choice.id === pendingChoice)) {
          pendingChoice = null;
        }
        const decisionDue = nextDecisionIsDue();
        const threshold = Math.round(nextDecisionThreshold());
        const title = decisionDue ? "Decision Event" : "Day In Motion";
        const badge = decisionDue ? `<span class="badge warn">Paused</span>` : `<span class="badge info">Rolling</span>`;
        const status = decisionDue
          ? "Paused for decision"
          : `Next decision near ${threshold}%`;
        const detail = decisionDue
          ? `${escapeHtml(nextCard.title)}`
          : "Work is moving through the day. The next decision will interrupt automatically.";
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
      $("summaryMetrics").innerHTML = `
        <h3>Day Result</h3>
        ${renderSubmarinePuzzle(summary.puzzle, "summary-panel")}
        <table>
          <tbody>
            <tr><td>Subjobs completed today</td><td>${summary.completedToday}</td></tr>
            <tr><td>Subjobs remaining</td><td>${summary.jobsRemaining}</td></tr>
            <tr><td>Jobs complete</td><td>${summary.piecesCompleted}/${state.pieces.length}</td></tr>
            <tr><td>Subjobs behind schedule</td><td>${summary.jobsBehindSchedule}</td></tr>
            <tr><td>Subjobs late</td><td>${summary.jobsLate}</td></tr>
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
  </script>

  <!-- End-of-day modal (centered) -->
  <div id="summaryModalOverlay" class="modal-overlay" role="dialog" aria-modal="true">
    <div class="modal">
      <h1>Daily Summary</h1>
      <div class="modal-body" id="summaryModalBody"></div>
      <div class="modal-footer">
        <button id="modalAdvanceBtn" class="primary" onclick="commitAdvanceDay()">Advance Day</button>
      </div>
    </div>
  </div>
</body>
</html>
"""
