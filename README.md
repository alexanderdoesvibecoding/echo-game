# ECHO Adventure

ECHO Adventure is a scheduling strategy game set in a fictional advanced manufacturing yard.

The player acts as a manual scheduler trying to finish a 15-piece project in 30 in-game days. Every run creates a reproducible manufacturing scenario with shops, workcenters, jobs, dependencies, material problems, quality findings, equipment failures, weather, crew pressure, engineering holds, certification issues, and downstream event cascades. A hidden automated scheduler runs the same scenario in parallel and is revealed only at the end as an operational benchmark.

## Gameplay

Each day, the player reviews the operating board and responds to daily decision cards.

The goal is to complete all puzzle pieces before the deadline while balancing:

- Schedule risk
- Late jobs
- Cost
- Reschedules
- Workcenter utilization
- Idle time
- Rework
- Cascading disruption risk

Daily decisions are intentionally limited. You usually cannot fix everything. A strong response can reduce future related disruption, while waiting or deferring can create follow-on risks later in the timeline.

## Run The Browser Game

```bash
python -m echo_adventure
```

or:

```bash
python main.py
```

Useful flags:

```bash
python -m echo_adventure --seed 12345
python -m echo_adventure --demo
python -m echo_adventure --port 8766
```

Use a seed when comparing changes. The same seed should generate the same scenario and event timeline unless scenario-generation logic changes.

The demo mode is a five-day run with five puzzle pieces, shorter job chains, no random disruptions, and one or two decisions per day. It is intended to be finishable in five minutes or less.

With a fixed seed:

```bash
python -m echo_adventure --seed 4242
```

Then open:

```text
http://127.0.0.1:8765
```

The UI is served by Python's standard-library HTTP server. There is no frontend build step. The HTTP server and browser template live in `echo_adventure/ui/`.

## Browser UI Flow

The browser dashboard has three main responsibilities:

- Show current project position and operating-board tables.
- Force completion of daily decision cards before `End Day`.
- Reveal the daily summary and final ECHO comparison.

The Operating Board tabs are:

- `Shops`: queue pressure, blocked work, utilization, idle time, shop risk, and active disruptions.
- `Daily Calendar`: scheduled work for the current day, split across the three shifts.
- `Pieces`: progress and risk for each puzzle piece, with drill-down into subjobs.
- `Workcenters`: machines/stations for the selected shop. The shop selector appears only in this tab.
- `Critical Path`: jobs most likely to drive final completion timing.
- `Risk Register`: active warnings, active disruptions, blocked jobs, and chained event sources.

Daily decisions appear as a modal. The modal can be dismissed so the main board remains inspectable, but all decisions must be submitted before the day can advance.

## Simulation Concepts

### Scenario

A scenario contains:

- Shops
- Workcenters
- Puzzle pieces
- Jobs
- Job dependencies
- Event timeline
- Deadline

Scenario generation lives in `echo_adventure/scenario_generator.py`.

### Jobs

Jobs represent the actual work required to complete puzzle pieces. Jobs can be:

- Not ready
- Ready
- Queued
- Running
- Paused
- Blocked
- Complete
- Rework required

Jobs carry priority, due shift, risk score, cost weight, candidate workcenters, and dependency links.

### Rework

Rework is intentionally common. It can happen through:

- Quality rework events.
- Rework spillover events.
- Completion-time inspection rework.

The UI marks jobs that have had rework with a small red dot next to the job id.

### Events

Events are disruptions or changing operating conditions. The current catalog includes:

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

Events can have warnings, active durations, severity, target objects, and follow-on effects.

### Cascading Events

Events can now affect later events. When a disruption resolves, the simulation evaluates whether the event creates downstream risk. High-severity or poorly mitigated events can schedule follow-on events later in the timeline.

Examples:

- A material delay can become supplier escalation or logistics backlog.
- A machine failure can become tooling damage or crew shortage.
- Quality rework can spill into related piece work.
- Inspection delay can become a certification audit.
- Engineering holds can become engineering data revisions.

Daily decisions also affect the chain:

- Expediting, rerouting, protecting critical work, resequencing, and pulling work forward reduce related future risk.
- Waiting, deferring, or holding sequence can add later follow-on risks.

The Risk Register shows a `Source` column for chained risks so downstream disruptions can be traced back to earlier events.

## Architecture

```text
main.py
echo_adventure/
  app.py                 Browser game entry point
  config.py              GameConfig and seed resolution
  models.py              Dataclasses for shops, workcenters, jobs, events, state
  enums.py               Status, event, target, and decision enums
  scenario_generator.py  Scenario construction and validation
  simulation.py          Shift/day advancement and job processing
  events.py              Event timeline generation, event handlers, cascades
  decisions.py           Daily decision-card generation and choice effects
  metrics.py             Snapshot, risk, critical path, and status refresh
  schedulers/
    manual.py            Player-side scheduler behavior
    automated.py         Hidden ECHO benchmark scheduler
    base.py              Shared scheduler interface/helpers
  ui/
    server.py            Local HTTP server, API session, JSON payloads
    view.py              Browser HTML, CSS, and JavaScript template
```

## Browser API

The UI server exposes a tiny local JSON API:

### `GET /`

Returns the inline browser UI.

### `GET /api/state`

Returns the complete UI state payload:

- Metrics snapshot
- Shops
- Daily calendar
- Pieces and subjobs
- Workcenters grouped by shop
- Critical path rows
- Risk register rows
- Current daily decision cards
- Last daily summary
- Final reveal, when the run is over

### `POST /api/new`

Starts a new session.

Request:

```json
{ "seed": "12345" }
```

The seed may be empty to use a random seed.

### `POST /api/choice`

Applies one daily decision choice.

Request:

```json
{
  "cardId": "DAY-01-DEC-1",
  "choiceId": "2"
}
```

### `POST /api/advance`

Advances the run by one day. The server rejects this if any current daily decision has not been answered.

## Development Notes

Run a compile check after edits:

```bash
python -m py_compile echo_adventure/*.py echo_adventure/**/*.py
```

Run the UI with a stable seed:

```bash
python -m echo_adventure --seed 1
```

If port `8765` is already in use:

```bash
python -m echo_adventure --port 8766 --seed 1
```

The UI server intentionally keeps state in memory. Refreshing the browser keeps the same server-side run. Starting a new run through the UI replaces the process-wide session.

## Troubleshooting

### The browser shows old UI

Restart the UI server. The browser template lives in `echo_adventure/ui/view.py`, so changes require the server process to be restarted.

### A random seed fails scenario validation

Some random seeds can expose scenario-generation edge cases. Use a fixed known-good seed while developing:

```bash
python -m echo_adventure --seed 1
```

### The decision modal keeps appearing

That is expected when unresolved daily decisions remain. Dismiss it to inspect the board, then reopen it with `Daily Decisions`. The day cannot advance until the choices are submitted.

### Tooltips overlap table text

Tooltip popups are styled as solid high-z-index boxes. If a new tooltip is added, keep it short and let the existing `.info-icon` CSS handle wrapping.
