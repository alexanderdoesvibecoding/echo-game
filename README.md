# ECHO Adventure

ECHO Adventure is a scheduling strategy game set in a fictional advanced manufacturing yard.

The player acts as a manual scheduler trying to finish a short manufacturing project before its deadline. Every run creates a reproducible scenario with shops, workcenters, subjobs, dependencies, routing pressure, and daily scheduling decisions. A hidden automated scheduler runs the same scenario in parallel and is revealed only at the end as an operational benchmark.

## Gameplay

Each day, the player reviews the operating board and responds to daily decision cards.

The goal is to complete all jobs before the deadline while balancing:

- Schedule risk
- Late subjobs
- Reschedules
- Workcenter utilization
- Idle time
- Rework
- Cascading disruption risk

Daily decisions are prepared at game start. Each choice determines the next daily question, but the number shown for the day is exact. If the day has two decisions, the player answers two questions. A strong response can reduce future related disruption, while waiting or deferring can create follow-on risks later in the timeline.

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
python -m echo_adventure --port 8766
```

Use a seed when comparing changes. The same seed should generate the same scenario and event timeline unless scenario-generation logic changes.

The normal scenario is an eight-day focused run with six top-level jobs, five to seven subjobs per job, shorter subjob durations, no random disruptions, no completion-time inspection rework, and three decisions per day. It is intended to be finishable in one short sitting while still showing enough routing and dependency pressure to make ECHO's benchmark meaningful.

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
- Force completion of the day's decision cards before `End Day`.
- Reveal the daily summary, final ECHO comparison, and player-vs-ECHO decision audit.

The Operating Board tabs are:

- `Shops`: queue pressure, blocked work, utilization, idle time, shop risk, and active disruptions.
- `Daily Calendar`: scheduled work for the current day, split across the three shifts.
- `Jobs`: progress and risk for each top-level job, with drill-down into subjobs.
- `Workcenters`: machines/stations for the selected shop. The shop selector appears only in this tab.
- `Critical Path`: subjobs most likely to drive final completion timing.
- `Risk Register`: active warnings, active disruptions, blocked subjobs, and chained event sources.

Daily decisions appear as a modal. The modal can be dismissed so the main board remains inspectable, but all of the day's questions must be submitted before the day can advance.

## Simulation Concepts

### Scenario

A scenario contains:

- Shops
- Workcenters
- Jobs
- Subjobs
- Job dependencies
- Event timeline
- Deadline

Scenario generation lives in `echo_adventure/scenario_generator.py`.

### Jobs and Subjobs

Jobs are the top-level deliverables the player must finish before the deadline. Subjobs represent the actual work required to complete each job. Subjobs can be:

- Not ready
- Ready
- Queued
- Running
- Paused
- Blocked
- Complete
- Rework required

Subjobs carry priority, due shift, risk score, candidate workcenters, and dependency links.

### Rework

Rework can happen through decision/event effects such as:

- Quality rework events.
- Rework spillover events.
- Completion-time inspection rework, if that balance knob is re-enabled.

The default normal run disables random event rework and completion-time inspection rework so the game teaches visible decisions first.

The UI marks subjobs that have had rework with a small red dot next to the subjob id.

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
- Quality rework can spill into related job work.
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
  decisions.py           Daily decision preparation, next-question selection, and choice effects
  metrics.py             Snapshot, risk, critical path, and status refresh
  schedulers/
    manual.py            Player-side scheduler behavior
    automated.py         Hidden ECHO benchmark scheduler
    base.py              Shared scheduler interface/helpers
  ui/
    server.py            Local HTTP server, API session, JSON payloads
    view.py              Browser HTML, CSS, and JavaScript template
```

## Presets and Balance

Game balance is controlled in `echo_adventure/config.py` through one named profile-based preset. The preset is assembled from workload, capacity, disruption, decision, and ECHO policy profiles, then flattened into `GameConfig` for the rest of the simulation:

- `normal`: 8 days, 6 top-level jobs, 5-7 subjobs per job, shorter durations, no random disruptions, and no completion-time rework.

Capacity balance has explicit routing-coverage knobs. `min_capable_workcenters_per_capability`, `min_candidate_workcenters_per_job`, `max_candidate_workcenters_per_job`, and `max_alternate_workcenters_per_job` prevent larger scenarios from creating unfair single-machine traps for common late-game work.

ECHO's hidden benchmark no longer picks decisions from the static campaign graph alone. ECHO scores every reachable downstream decision in the campaign tree, then projects each live choice through the remaining run with the automated scheduler. Projected choices are ranked by finishing the job, finishing in the fewest shifts, and then maximizing the deterministic final score. Set `echo_choice_lookahead_days` to a positive number only when you want to cap that projection for experiments; the default `0` means ECHO looks through the rest of the run. `echo_choice_projection_limit` defaults to `0`, which means projection-only card answering is uncapped.

Completion-time inspection rework is controlled by `completion_rework_probability`, `min_completion_rework_shifts`, and `max_completion_rework_shifts`. Keep these explicit in presets instead of reintroducing hard-coded probabilities in scenario generation.

Normal mode should be finishable by ECHO across sampled seeds. If ECHO cannot finish a normal seed, a human player is unlikely to have a fair path either. Good tuning options are:

- Reduce subjob chain length or duration before adding more deadline days.
- Keep hidden defects disabled by default; teach visible decisions first.
- Preserve challenge with decision pressure and queue tradeoffs, not surprise rework.
- Add known failing seeds to `test_echo_wins_normal_sampled_seeds` before tuning.

## Browser API

The UI server exposes a tiny local JSON API:

### `GET /`

Returns the inline browser UI.

### `GET /api/state`

Returns the complete UI state payload:

- Metrics snapshot
- Shops
- Daily calendar
- Jobs and subjobs
- Workcenters grouped by shop
- Critical path rows
- Risk register rows
- Current daily decision cards and fixed daily progress
- Last daily summary
- Final reveal, when the run is over

### `POST /api/new`

Starts a new session.

Request:

```json
{
  "seed": "12345"
}
```

The seed may be empty or omitted to use a random seed.

### `POST /api/choice`

Applies one daily decision choice and reveals the next daily question when one remains.

Request:

```json
{
  "cardId": "DAY-01-Q01",
  "choiceId": "2"
}
```

### `POST /api/advance`

Advances the run by one day. The server rejects this if any of the day's questions has not been answered.

## Development Notes

Run a compile check after edits:

```bash
python -m py_compile echo_adventure/*.py echo_adventure/**/*.py
```

Run the tests:

```bash
python -m pytest
```

The tests live under `echo_adventure/tests/`. Keep them visible to git; balance regressions are easy to miss if local test files are ignored.

Useful balance check while tuning normal mode:

```bash
python - <<'PY'
from echo_adventure.config import GameConfig
from echo_adventure.tests.test_echo_wins import _run_echo

misses = []
for seed in range(1, 101):
    snapshot = _run_echo(GameConfig.for_preset("normal", seed=seed))
    if not snapshot.deadline_met:
        misses.append(seed)
print(misses)
PY
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
