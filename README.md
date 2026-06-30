# ECHO Adventure

ECHO Adventure is a local browser strategy game about recovering a manufacturing schedule under pressure.

You play the manual scheduler for a fictional advanced manufacturing yard. Every run generates a deterministic project with shops, workcenters, top-level jobs, subjobs, dependencies, routing options, due dates, and daily decision cards. While you make visible scheduling decisions, a hidden automated scheduler named ECHO plays the same scenario in parallel. The comparison is revealed only at the end, so the run stays focused on your operating choices instead of on chasing the benchmark turn by turn.

The project is intentionally lightweight: Python standard library server, no frontend build step, no runtime dependencies declared in `pyproject.toml`, and all UI code served from a single HTML/CSS/JavaScript template.

## Current Status

The current project is a playable local browser prototype. It runs one in-memory game session per server process, has no persistence layer, and keeps the hidden ECHO benchmark private until the run ends.

Recent changes since the previous README update:

- The browser now runs each day on a client-side day clock instead of relying on manual shift clicks.
- Shift snapshots update during the day, so jobs-complete and subjobs-complete metrics move before the end-of-day summary.
- Daily decisions now appear as modal prompts at deterministic, seeded-random points in the day. The day clock pauses while a decision is due.
- End-of-day review has been rebuilt around a summary modal with stats, past-due subjobs, update notes, and the submarine assembly puzzle. The player advances after reading it.
- The final reveal now emphasizes decision score impact, metric comparison, outcome drivers, and the decision audit against ECHO.
- The UI includes a settings menu for starting a new standard run and toggling light/dark mode. Seeded replay is still primarily handled through the CLI or JSON API.

## Quick Start

Use Python 3.14 or newer.

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

If you install the package into an environment, the project scripts are:

```bash
echo-adventure
echo-adventure-ui
```

## What You Do

Each run is a short scheduling campaign. The default `normal` preset is tuned for a focused game:

- 8 in-game days
- 3 shifts per day
- 6 top-level jobs
- 5 to 7 subjobs per top-level job
- Short subjob durations
- No random base disruptions in the default preset
- No completion-time inspection rework in the default preset
- 3 to 4 generated daily decision candidates, with up to 3 active prompts surfaced

The goal is to complete all top-level jobs before the deadline while balancing:

- Schedule risk
- Late subjobs
- Queue pressure
- Critical-path exposure
- Reschedules
- Workcenter utilization
- Idle time
- Rework and disruption recovery
- Whether your choices align with ECHO's benchmark policy

A seed fully controls the generated scenario. Use a fixed seed when comparing changes:

```bash
python3 -m echo_adventure --seed 1
```

The same seed should produce the same scenario and event timeline unless generation or balance logic changes.

## Gameplay Loop

The browser UI presents a compact operating board for the current run.

Each day:

1. Review the welcome preview, project metrics, job progress, and critical-path pressure.
2. Let the day clock roll while shift snapshots update the live metrics.
3. When the clock pauses for a decision event, answer the modal prompt.
4. After all scheduled decisions are answered and the day reaches the end, read the daily summary.
5. Advance from the summary and continue until every job is finished or the deadline arrives.

Daily decisions are prepared as part of a campaign decision graph at scenario creation time. Choices can unlock later questions, add branch tags, alter future risk, and mutate the live schedule. The server tracks current decision progress and rejects full-day advancement until all currently required decisions are answered. The browser surfaces one due decision at a time, using seeded-random timing thresholds so the same run remains replayable.

At the end of the run, the final reveal compares your schedule to ECHO's hidden benchmark run. The reveal includes:

- Player and ECHO final snapshots
- Decision score impact over answered questions
- Decision-by-decision audit
- ECHO's preferred answer for each player decision
- A short explanation of why the run was won or lost

## Browser UI

The browser app lives under `echo_adventure/ui/` and is served by `ThreadingHTTPServer`.

Important UI pieces:

- `echo_adventure/ui/server.py` owns the local HTTP API and `GameSession`.
- `echo_adventure/ui/view.py` contains the inline HTML, CSS, and JavaScript template.
- The server keeps one active session in memory.
- Refreshing the page keeps the same server-side run.
- Starting a new run from the UI replaces the process-wide session.
- The browser keeps only presentation state such as modal visibility, day-clock progress, and theme preference.
- There is no frontend package manager, bundler, or static asset pipeline.

The main screen focuses on operational state rather than a marketing splash:

- Welcome modal with critical-path preview
- Project-position metrics
- Jobs-complete popover and live subjobs-complete counter
- Top-level job progress rows
- Day progress clock with automatic shift advancement
- Inline decision status and timed decision modal
- End-of-day summary modal and persistent summary panel
- Past-due subjob table, update notes, and submarine assembly puzzle visualization
- Settings menu for new game and light/dark mode
- Final ECHO comparison and decision audit

## Core Concepts

### Scenario

A scenario is the generated template for one run. It contains:

- Shops
- Workcenters
- Top-level jobs, called pieces in the data model
- Subjobs, called jobs in the data model
- Dependency links
- Event timeline
- Deadline shift
- Campaign decision cards
- Campaign decision graph indexes

Generation starts in `echo_adventure/scenario_generator.py`.

### Shops And Workcenters

Shops group workcenters and carry roll-up queue, blocked, completed, utilization, idle-time, and risk metrics. Workcenters have capabilities such as cutting, bonding, inspection, tooling, wiring, calibration, assembly, and related manufacturing skills.

Subjobs can be routed to candidate workcenters that match their required capability. The normal preset deliberately requires several capable workcenters per common capability so the game does not collapse into unfair single-machine bottlenecks.

### Top-Level Jobs And Subjobs

The UI calls the player-facing deliverables "jobs." In the Python model those top-level deliverables are `PuzzlePiece` objects, and the schedulable units underneath them are `Job` objects.

Subjobs can move through these statuses:

- Not ready
- Ready
- Queued
- Scheduled
- Running
- Paused
- Blocked
- Complete
- Late
- Rework required
- Cancelled / superseded

Each subjob tracks priority, due shift, risk score, dependency ids, dependent ids, candidate workcenters, assignment, remaining duration, queue time, rework count, and completion shift.

### Dependencies

Most top-level jobs are generated as short dependency chains. A subjob becomes schedulable only after its predecessors are complete. Some generated chains include extra links so the critical path is more interesting than a simple linear queue.

### Shifts And Days

The simulation advances in shifts. A day is a fixed number of shifts from `GameConfig.shifts_per_day`, currently 3 in the normal preset.

In the browser UI, the current day is presented as a short client-side clock. The UI calls `/api/shift` at shift markers so live metrics can update before the day closes. Once all required decisions are complete and the clock reaches the end, the UI calls `/api/advance` to finish the day, build the daily summary, and move the hidden ECHO benchmark forward.

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

### Events

Events represent disruptions, warnings, and changing operating conditions.

The event catalog includes:

- Missing material
- Delayed material
- Machine or workcenter down
- Quality rework
- Priority change
- Inspection delay
- Engineering hold
- Urgent new job inserted
- Weather event
- Facility outage
- Supplier escalation
- Logistics backlog
- Tooling damage
- Crew shortage
- Rework spillover
- Certification audit
- Engineering data revision
- Unexpected job request
- ECHO recommendation

Events can target shops, workcenters, subjobs, top-level jobs, or capabilities. They can have warning shifts, active durations, severities, parent events, chain depth, and effect payloads.

### Cascading Risk

Events and decisions can create downstream consequences. When a disruption resolves, the simulation may schedule follow-on events based on severity and mitigation quality.

Examples:

- Material delays can become supplier escalation or logistics backlog.
- Machine failures can become tooling damage or crew shortage.
- Quality issues can spill into related rework.
- Inspection delays can become certification audits.
- Engineering holds can become data revisions.

Daily decisions can reduce or worsen those chains. Expediting, rerouting, protecting critical work, resequencing, and pulling work forward tend to reduce future risk. Waiting, deferring, or leaving pressure unresolved can create later follow-on risks.

The default normal preset disables random base disruptions and completion-time inspection rework so new runs teach visible decisions first. The event and rework systems remain available for tuning and larger experiments.

## ECHO Benchmark

ECHO is the hidden automated scheduler and decision policy used for comparison.

The benchmark run uses the same generated scenario as the player, but a separate mutable `SimulationState`. That means player and ECHO face the same underlying project, while each scheduler can mutate its own queues, decisions, metrics, and completion history.

ECHO decision selection has two layers:

- Static campaign-tree scoring reads reachable downstream decision paths so a choice with a bad hidden tail can be avoided.
- Live-board forecasting projects each current choice through the remaining run with the automated scheduler, then ranks outcomes by completion, completion shift, final score, remaining jobs, lateness, reschedules, idle time, and risk.

The relevant knobs live in `GameConfig`:

- `echo_choice_lookahead_days`: positive values cap projection depth for experiments; `0` means project through the rest of the run.
- `echo_choice_projection_limit`: positive values cap projection-only card answering; `0` means uncapped.

## Architecture

```text
main.py
echo_adventure/
  __main__.py            Module entry point for python3 -m echo_adventure
  app.py                 Package entry point for the browser game
  config.py              GameConfig, balance profiles, presets, seed handling
  models.py              Dataclasses for shops, jobs, events, decisions, state
  enums.py               Status, event, target, and decision enums
  scenario_generator.py  Scenario construction, validation, due dates, graph setup
  simulation.py          Shift/day advancement and job processing
  events.py              Event timeline generation, handlers, cascades
  decisions.py           Campaign graph, active cards, choice effects, scoring
  echo.py                Hidden ECHO decision policy and benchmark decision flow
  metrics.py             Snapshots, final score, risk, critical path, status refresh
  schedulers/
    base.py              Shared scheduler interface and helper functions
    manual.py            Player-side scheduler behavior
    automated.py         Hidden ECHO benchmark scheduler
  ui/
    server.py            Local HTTP server, GameSession, JSON payloads
    view.py              Browser HTML, CSS, and JavaScript template
  tests.py               unittest coverage for decision, scenario, and UI payload logic
```

## Balance And Configuration

Balance is assembled in `echo_adventure/config.py` from profile dataclasses:

- `WorkloadProfile`
- `CapacityProfile`
- `DisruptionProfile`
- `DecisionProfile`
- `EchoProfile`

Those profiles are flattened into `GameConfig`, which the rest of the simulation consumes.

The currently named preset is:

- `normal`: 8 days, 6 top-level jobs, 5 to 7 subjobs per top-level job, shorter durations, broad routing coverage, no random base events, no completion-time rework, and 3 to 4 generated daily decision candidates with up to 3 active prompts surfaced.

Important tuning principles:

- Reduce subjob chain length or duration before adding more deadline days.
- Keep hidden defects disabled in the default preset; teach visible decisions first.
- Preserve challenge with decision pressure, routing choices, and queue tradeoffs.
- Use fixed seeds when tuning.
- If ECHO cannot finish a normal seed, the scenario is probably unfair for a human player too.

Useful capacity knobs:

- `min_capable_workcenters_per_capability`
- `min_candidate_workcenters_per_job`
- `max_candidate_workcenters_per_job`
- `max_alternate_workcenters_per_job`

Useful rework knobs:

- `completion_rework_probability`
- `min_completion_rework_shifts`
- `max_completion_rework_shifts`

Useful decision graph knobs:

- `min_decisions_per_day`
- `max_decisions_per_day`
- `max_campaign_decision_nodes`
- `max_campaign_branch_depth`
- `max_future_unlocks_per_choice`
- `max_active_decision_cards_per_day`
- `max_branch_variants_per_day`

## Local API

The browser UI talks to a small local JSON API.

### `GET /`

Returns the inline browser UI.

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

The seed may be empty, omitted, or `null` to use a random replayable seed.

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

The response includes the refreshed state plus a `shiftAdvance` object with the shift number, game-over flag, and whether the shift completed the day.

### `POST /api/advance`

Advances the player simulation through the rest of the current day, creates the daily summary, and advances ECHO's hidden benchmark for the day. The server rejects this request if required decisions are still unanswered.

Request:

```json
{}
```

The response includes the refreshed state plus an `advance` object.

## Development

Run a compile check:

```bash
python3 -m compileall echo_adventure main.py
```

Run the unit tests:

```bash
python3 -m unittest echo_adventure.tests
```

The tests currently live in `echo_adventure/tests.py` and use the standard-library `unittest` runner.

Current coverage focuses on:

- ECHO static choice scoring through reachable downstream decision trees
- Final decision-chart payload shape
- Empty decision-chart payload behavior
- Scenario due-date spread across configured total days
- Shift-by-shift browser session progression before day summary

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

Use `python3`. This project expects Python 3.14 or newer.

```bash
python3 --version
```

### The browser shows old UI

Restart the UI server. The browser template is embedded in `echo_adventure/ui/view.py`, so changes require a server restart.

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

The clock pauses when a decision is due or when the end-of-day summary is open. Answer the decision modal, or use `Advance Day` in the daily summary. The server also rejects `/api/advance` until all required decisions are answered.

### Shift advancement looks different from day advancement

That is expected. `/api/shift` advances one shift and can update the live snapshot before an end-of-day summary exists. `/api/advance` finishes the current day, advances ECHO's daily benchmark state, and creates the daily summary.

### Tooltips overlap table text

Tooltip popups are styled as solid high-z-index boxes. If a new tooltip is added, keep the text short and let the existing `.info-icon` CSS handle wrapping.
