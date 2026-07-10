# ECHO Adventure

ECHO Adventure is a local browser strategy game about recovering a manufacturing schedule under pressure.

You play the manual scheduler for a fictional advanced manufacturing yard. Each run generates a deterministic project with shops, workcenters, top-level jobs, subjobs, dependency chains, routing options, due dates, and campaign decision cards. A hidden automated scheduler named ECHO plays the same scenario in parallel, and the comparison is revealed only after the run ends.

The project is intentionally lightweight:

- Python standard library HTTP server
- No frontend build step
- No runtime dependencies declared in `pyproject.toml`
- Static browser assets in plain HTML, CSS, and JavaScript
- One in-memory game session per server process

## Current State

The app is a playable local browser prototype. It has no persistence layer, no authentication, and no multi-user session model. Refreshing the browser keeps the current server-side run; starting a new game replaces the process-wide session. Fixed-seed replay is available from the CLI and JSON API; the visible New Game modal currently starts a fresh standard run with a generated seed.

The default `normal` preset is tuned as a short focused campaign:

- 8 in-game days
- 3 shifts per day
- 6 top-level jobs
- 5 to 7 subjobs per top-level job
- Short subjob durations
- Broad routing coverage across capable workcenters
- No random base disruptions
- No completion-time rework
- 3 sampled named manufacturing decisions per day, with due named follow-ups taking priority

Random base disruptions, extra quality rework events, completion-time rework, and larger scenarios are still available through `GameConfig` for experiments.

## Quick Start

The package metadata currently requires Python 3.14 or newer.

```bash
python3 -m echo_adventure
```

Then open:

```text
http://127.0.0.1:8765
```

Useful run options:

```bash
python3 -m echo_adventure --seed 4242
python3 -m echo_adventure --port 8766
python3 -m echo_adventure --host 127.0.0.1 --port 8765 --seed 12345
```

The compatibility script works too:

```bash
python3 main.py
```

If the package is installed into an environment, the project script is:

```bash
echo-adventure
```

## Gameplay

The goal is to complete all top-level jobs before the deadline while balancing schedule risk, queue pressure, critical-path exposure, reschedules, idle time, rework, disruption recovery, and how closely your choices align with ECHO's benchmark policy.

Each day:

1. Review the operating board, project metrics, job progress, and critical-path pressure.
2. Let the client-side day clock roll while shift snapshots update live metrics.
3. When the clock pauses for a decision event, answer the modal prompt.
4. After all scheduled decisions are answered and the day reaches the end, read the daily summary.
5. Advance from the summary and continue until every job is finished or the deadline arrives.

Daily decisions are sampled from a stable catalog of named manufacturing situations. Some base situations can repeat across a run. Choices can schedule shared named follow-ups through seeded probability edges, while all definitions—including cards not sampled into the current run—remain in the prebuilt graph available to ECHO. The server tracks decision progress and rejects full-day advancement until all currently required decisions are answered.

The player-facing copy describes consequences qualitatively. Internally, promised gains and delays are applied as literal deterministic shift changes, blocks, downtime, capacity openings, or releases.

The final reveal includes:

- Player and ECHO final snapshots
- Final decision score over answered questions
- Metric comparison
- Outcome drivers

The final score shown in the comparison table is the same accumulated decision score shown by the decision chart. Schedule performance is shown separately through deadline, completion, late-work, risk, idle-time, and reschedule metrics.

## Browser UI And API

The backend API lives under `echo_adventure/api/`. The frontend browser assets live under `echo_adventure/ui/`. They are still served together by one local `ThreadingHTTPServer` process.

Important backend files:

- `echo_adventure/api/server.py` owns the local HTTP API request/response plumbing and static asset serving.
- `echo_adventure/api/session.py` owns `GameSession` and `SessionStore`.
- `echo_adventure/api/payloads.py` builds state, summary, chart, and final reveal payloads.
- `echo_adventure/api/review.py` builds final win/loss explanation text.
- `echo_adventure/api/view.py` locates and loads the frontend HTML shell.

Important frontend files:

- `echo_adventure/ui/index.html` contains the browser markup.
- `echo_adventure/ui/styles.css` contains the UI styles and theme rules.
- `echo_adventure/ui/app.js` is the browser ES module entrypoint.
- `echo_adventure/ui/*.js` modules split API calls, UI state, day clock, modals, and renderers without a build step.

The server is the rule authority. The browser stores only presentation state such as modal visibility, day-clock progress, pending choice selection, and theme preference.

The main UI includes:

- Welcome modal with critical-path preview
- Project-position metrics
- Jobs-complete popover and live subjobs-complete counter
- Day progress clock with automatic shift advancement
- Timed daily decision modal
- End-of-day summary modal
- Past-due subjob table
- Update notes
- Submarine assembly puzzle visualization
- Settings menu for new game and light/dark mode
- Final ECHO comparison

## Core Concepts

### Scenario

A scenario is the generated template for one run. It contains shops, workcenters, top-level jobs, subjobs, job dependency links, an event timeline, a deadline shift, campaign decision cards, and campaign graph indexes.

Generation starts in `echo_adventure/scenario_generator.py`.

### Shops And Workcenters

Shops group workcenters and carry roll-up queue, blocked, completed, utilization, idle-time, and risk metrics. Workcenters have capabilities such as cutting, bonding, inspection, tooling, wiring, calibration, assembly, and related manufacturing skills.

Subjobs can be routed to candidate workcenters that match their required capability. The normal preset deliberately requires several capable workcenters per common capability so the game does not collapse into unfair single-machine bottlenecks.

### Top-Level Jobs And Subjobs

The UI calls the player-facing deliverables "jobs." In the Python model those top-level deliverables are `PuzzlePiece` objects, and the schedulable units underneath them are `Job` objects.

Subjobs can move through these runtime statuses:

- Not ready
- Ready
- Queued
- Running
- Paused
- Blocked
- Complete
- Rework required

Each subjob tracks priority, due shift, risk score, dependency ids, dependent ids, candidate workcenters, assignment, remaining duration, queue time, rework count, and completion shift.

### Shifts And Days

The simulation advances in shifts. A day is a fixed number of shifts from `GameConfig.shifts_per_day`, currently 3 in the normal preset.

`advance_shift` performs one unit of work in this order:

1. Increment the current shift.
2. Refresh event state.
3. Update metrics.
4. Let the scheduler plan the shift.
5. Start queued jobs on available workcenters.
6. Process active workcenters.
7. Age queues.
8. Refresh metrics again.

`advance_day` plans the day, then processes up to one day's worth of shifts unless the project completes or the deadline is reached first. `GameSession` wraps this with summary bookkeeping, active-card resets, and benchmark advancement.

### Manufacturing Resources

The scenario includes real worker qualifications and availability, shared fixtures/tools/support assets, material and consumable stock, controlled documents and revisions, and inspection methods. A typed shared-resource model also covers cranes, racks, carts, software seats, batch slots, tanks, utility windows, controlled areas, staging lanes, label printers, waste containers, and reference samples. Most of this state stays behind the scenes; decision cards expose only the affected job/shop context needed to understand the choice.

### Events And Cascades

Events represent disruptions, warnings, and changing operating conditions. The catalog includes material problems, machine downtime, quality rework, priority changes, inspection delays, engineering holds, urgent inserted work, weather, facility outages, supplier escalation, logistics backlog, tooling damage, crew shortage, rework spillover, certification audits, engineering data revisions, unexpected job requests, and ECHO recommendations.

Events can target shops, workcenters, subjobs, top-level jobs, or capabilities. They can have warning shifts, active durations, severities, parent events, chain depth, and effect payloads.

When a disruption resolves, the simulation may schedule follow-on events based on severity and mitigation quality. Daily decisions can reduce or worsen those chains. Expediting, rerouting, protecting critical work, resequencing, and pulling work forward tend to reduce future risk. Waiting, deferring, or leaving pressure unresolved can create later follow-on risks.

## ECHO Benchmark

ECHO is the hidden automated scheduler and decision policy used for comparison.

The benchmark run uses the same generated scenario as the player, but a separate mutable `SimulationState`. Player and ECHO face the same underlying project while each scheduler mutates its own queues, decisions, metrics, and completion history.

ECHO decision selection has two layers:

- Static graph scoring uses every named edge and its probability to estimate expected downstream cost.
- Live-board forecasting deep-copies the state, applies the exact same parameterized effects and seeded follow-up resolution used by the player path, projects each current choice through the remaining run, then ranks outcomes by completion, completion shift, projected decision score, remaining jobs, lateness, reschedules, idle time, and risk. Because the fixed run seed determines each edge outcome, ECHO can project the exact branch for that run while static fallback scoring remains probability-aware.

Relevant ECHO knobs in `GameConfig`:

- `echo_choice_lookahead_days`: positive values cap projection depth for experiments; `0` means project through the rest of the run.
- `echo_choice_projection_limit`: positive values cap projection-only card answering; `0` means uncapped.

## Architecture

```text
main.py
echo_adventure/
  __main__.py            Module entry point for python3 -m echo_adventure
  app.py                 Package entry point for the browser game
  config.py              GameConfig, balance profiles, presets, seed handling
  models.py              Dataclasses for shops, jobs, events, decisions, and state
  domain.py              Worker, material, document, and shared-resource runtime constraints
  enums.py               Status, event, target, and decision enums
  scenario_generator.py  Scenario construction, validation, due dates, graph setup
  simulation.py          Shift/day advancement and job processing
  events.py              Event timeline generation, handlers, cascades
  decisions/             Named decision definitions, graph, effects, scoring, selectors
    __init__.py          Backward-compatible public decision API
    definitions.py       Stable manufacturing cards, choices, effects, and named edges
    graph.py             Sampling, shared follow-up scheduling, and stale-target filtering
    cards.py             Legacy generic card factories (not used by the named campaign)
    effects.py           Typed parameterized choice effects shared by player and ECHO
    scoring.py           Probability-aware static ECHO graph scoring
    selectors.py         Shared target expansion for decision effects and ECHO scoring
  echo.py                Hidden ECHO decision policy, live forecasts, and benchmark decision flow
  metrics.py             Snapshots, final score, risk, critical path, status refresh
  schedulers/
    base.py              Shared scheduler interface and helper functions
    manual.py            Player-side scheduler behavior
    automated.py         Hidden ECHO benchmark scheduler
  api/
    server.py            Local HTTP routing, JSON API, and static asset serving
    session.py           GameSession and SessionStore
    payloads.py          State, summary, chart, and final reveal payloads
    review.py            Final win/loss explanation text
    view.py              Frontend HTML loader
  ui/
    index.html           Browser shell
    styles.css           Styles and theme rules
    app.js               Browser ES module entrypoint
    api.js               Fetch helper
    state.js             Client presentation state
    dayClock.js          Day clock and automatic shift advancement
    render*.js           Metrics, decisions, summary, and final reveal renderers
    modals.js            Modal and theme controls
    html.js              DOM and escaping helpers
tests/
  api/                   Python backend coverage for core logic, events, decisions, API payloads, and regressions
  ui/                    Node runtime tests for browser ES modules and renderer behavior
```

## Balance And Configuration

Balance is assembled in `echo_adventure/config.py` from profile dataclasses:

- `WorkloadProfile`
- `CapacityProfile`
- `DisruptionProfile`
- `DecisionProfile`
- `EchoProfile`

Those profiles are flattened into `GameConfig`, which the rest of the simulation consumes.

Useful workload knobs:

- `total_days`
- `shifts_per_day`
- `piece_count`
- `min_jobs_per_piece`
- `max_jobs_per_piece`
- `min_job_duration_shifts`
- `max_job_duration_shifts`
- `setup_time_choices`
- `transport_delay_probability`

Useful capacity knobs:

- `shop_count`
- `min_workcenters_per_shop`
- `max_workcenters_per_shop`
- `min_capable_workcenters_per_capability`
- `min_candidate_workcenters_per_job`
- `max_candidate_workcenters_per_job`
- `max_alternate_workcenters_per_job`

Useful disruption and rework knobs:

- `min_base_events`
- `max_base_events`
- `min_extra_quality_rework_events`
- `max_extra_quality_rework_events`
- `completion_rework_probability`
- `min_completion_rework_shifts`
- `max_completion_rework_shifts`

Useful decision graph knobs:

- `min_decisions_per_day`
- `max_decisions_per_day`
- `max_campaign_decision_nodes`
- `max_future_unlocks_per_choice`
- `max_active_decision_cards_per_day`
- `max_branch_variants_per_day`

Tuning principles:

- Use fixed seeds when comparing balance changes.
- Reduce subjob chain length or duration before adding more deadline days.
- Keep hidden defects disabled in the default preset; teach visible decisions first.
- Preserve challenge with decision pressure, routing choices, and queue tradeoffs.
- If ECHO cannot finish a normal seed, the scenario is probably unfair for a human player too.

## Local API

The browser UI talks to a small local JSON API.

### `GET /`

Returns the browser UI.

### `GET /api/state`

Returns the current run state. The payload includes:

- Run seed
- Game-over flag
- Current day
- Shifts per day
- Projected completion
- Metrics snapshot
- Top-level job rows with completion, due, and projected finish data
- Critical-path rows
- Active decision cards
- Decision progress
- Recent applied-choice notes
- Last daily summary with stats, past-due jobs, puzzle tiles, and notes
- Final reveal, once the run is over

### `POST /api/new`

Starts a new run and replaces the active in-memory session.

Request:

```json
{
  "seed": "12345"
}
```

The seed may be empty, omitted, or `null` to use a random replayable seed. The current browser settings menu starts a standard random-seed run; fixed-seed replay is primarily handled through the CLI or JSON API.

### `POST /api/choice`

Applies one choice to one active decision card.

Request:

```json
{
  "cardId": "CMP-D01-ROOT",
  "choiceId": "2"
}
```

The response includes the refreshed state plus an `action` object with the choice note and whether all current decisions are complete.

### `POST /api/shift`

Advances the player simulation by one shift. The browser uses this automatically while the day clock is rolling.

Request:

```json
{}
```

The response includes the refreshed state plus a `shiftAdvance` object with the shift number, game-over flag, and whether the shift completed the day. If the shift completes the day, the server also builds the daily summary and advances ECHO's benchmark for that day.

### `POST /api/advance`

Advances the player simulation through the rest of the current day, creates the daily summary, and advances ECHO's hidden benchmark for the day. The server rejects this request if required decisions are still unanswered.

Request:

```json
{}
```

The response includes the refreshed state plus an `advance` object.

## Development

Run a quiet compile check:

```bash
python3 -m compileall -q echo_adventure main.py
```

Run the unit tests:

```bash
npm test
```

Backend tests use `pytest` against the Python code. Frontend tests use Node's built-in test runner against the browser ES modules with a lightweight DOM stub.

Run each side directly:

```bash
npm run test:backend
npm run test:frontend
```

Install requirements:

- Python with `pytest` available in the environment.
- Node.js 18 or newer. No npm package install is required because the frontend tests only use Node built-ins.

Current coverage focuses on:

- ECHO static choice scoring through reachable downstream decision trees
- ECHO forecast error logging and heuristic fallback
- Runtime frontend renderer behavior for metrics, day-clock decisions, final chart tooltips, and modal/theme state
- Final decision-chart payload shape
- Empty decision-chart payload behavior
- Thread-safe session replacement while an action is in flight
- Extra quality rework event generation when base events are disabled
- Scenario due-date spread across configured total days
- Shift-by-shift browser session progression before day summary
- Frozen summary puzzle and past-due payloads after later state changes
- Config validation, model helpers, metrics, schedulers, event effects, decision effects/selectors, card factories, ECHO policy helpers, and API/server payload routing

Run the UI with a stable seed while developing:

```bash
python3 -m echo_adventure --seed 1
```

If port `8765` is already in use:

```bash
python3 -m echo_adventure --port 8766 --seed 1
```

## Handy Inspection Snippets

Generate one scenario and print high-level shape:

```bash
python3 - <<'PY'
from echo_adventure.config import GameConfig
from echo_adventure.scenario_generator import generate_scenario

scenario = generate_scenario(GameConfig.for_preset("normal", seed=1))
print(scenario.scenario_id)
print("shops:", len(scenario.shops))
print("workcenters:", len(scenario.workcenters))
print("top-level jobs:", len(scenario.pieces))
print("subjobs:", len(scenario.jobs))
print("events:", len(scenario.event_timeline))
print("decision cards:", len(scenario.decision_cards))
print("deadline shift:", scenario.deadline_shift)
PY
```

Run ECHO over a small seed sample:

```bash
python3 - <<'PY'
from echo_adventure.config import GameConfig
from echo_adventure.echo import apply_echo_decisions_for_day
from echo_adventure.metrics import calculate_snapshot
from echo_adventure.scenario_generator import generate_scenario
from echo_adventure.schedulers.automated import AutomatedScheduler
from echo_adventure.simulation import advance_day, initialize_state

misses = []
for seed in range(1, 21):
    config = GameConfig.for_preset("normal", seed=seed)
    scenario = generate_scenario(config)
    state = initialize_state(scenario, config.shifts_per_day)
    scheduler = AutomatedScheduler()
    completed_days = set()
    while state.current_shift < state.deadline_shift and not state.final_item_completed:
        apply_echo_decisions_for_day(state, config, completed_days)
        advance_day(state, scheduler)
    snapshot = calculate_snapshot(state)
    if not snapshot.deadline_met:
        misses.append(seed)
print("misses:", misses)
PY
```

## Troubleshooting

### `python` is not found

Use `python3`. The package metadata currently requires Python 3.14 or newer.

```bash
python3 --version
```

### The browser shows old UI

Restart the UI server. `echo_adventure/api/view.py` reads `echo_adventure/ui/index.html` at import time, and the server serves the browser ES modules plus `ui/styles.css` as known frontend assets.

### Port 8765 is already in use

Run on another port:

```bash
python3 -m echo_adventure --port 8766
```

### A random seed fails scenario validation

Some generation changes can expose edge cases. Reproduce with a fixed seed, then inspect the generated scenario:

```bash
python3 -m echo_adventure --seed 1
```

### The day clock is paused

The clock pauses when a decision is due or when the end-of-day summary is open. Answer the decision modal, or advance from the daily summary. The server also rejects `/api/advance` until all required decisions are answered.

### Shift advancement looks different from day advancement

That is expected. `/api/shift` advances one shift and can update the live snapshot before an end-of-day summary exists. `/api/advance` finishes the current day, advances ECHO's daily benchmark state, and creates the daily summary.

### Tooltips overlap table text

Tooltip popups are styled as solid high-z-index boxes. If a new tooltip is added, keep the text short and let the existing `.info-icon` CSS handle wrapping.
