# ECHO Adventure

ECHO Adventure is a local browser game about completing twenty independent jobs. Every job is also one piece of the submarine assembly puzzle. A hidden ECHO run plays the same generated scenario and is revealed when the player finishes.

## Game rules

- Every run contains exactly 20 jobs.
- Each job starts with a random runtime from 5 through 15 days.
- There are no subjobs, dependencies, shifts, resources, queues, events, or deadline.
- Every unfinished job loses one remaining day whenever a game day advances.
- Each day presents a configurable 2–4 questions.
- A question either adds days to a job or set of jobs, or removes days from a job or set of jobs.
- Manufacturing situations such as equipment, staffing, material, weather, and quality issues are flavor text only. They have no hidden model or effect beyond the job-day change stated on the answer.
- The run ends only after all 20 jobs are complete.

## Run the app

Requires Python 3.14 or newer.

```bash
python3 -m echo_adventure
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). Stop the server with `Ctrl+C`.

Use a reproducible seed when needed:

```bash
python3 -m echo_adventure --seed 12345
```

## Configuration

The normal run is defined in `echo_adventure/config.py`:

- `job_count = 20`
- `min_job_duration_days = 5`
- `max_job_duration_days = 15`
- `min_decisions_per_day = 2`
- `max_decisions_per_day = 4`
- `day_cycle_duration_ms`
- `daily_summary_counter_duration_ms`

There is deliberately no deadline or maximum-day setting.

## Architecture

```text
echo_adventure/
  config.py               Jobs, runtime, question-count, and UI timing settings
  models.py               Flat job, decision, scenario, and state dataclasses
  scenario_generator.py   Deterministic twenty-job generation
  simulation.py           Once-per-day job progression
  metrics.py              Completion and remaining-work rollups
  echo.py                 Hidden best-choice benchmark
  decisions/
    cards.py              Deterministic daily question bank
    effects.py            Explicit add/remove-day effects
  api/
    session.py            Player and ECHO session ownership
    payloads.py           Browser payload construction
    review.py             Final comparison text
    server.py             Local JSON/static server
  ui/                     Browser interface and twenty-piece submarine puzzle
```

The state model intentionally contains no shops, workstations, employees, materials, documents, inspections, routing, or rework. Flavor copy never creates hidden state.

## HTTP API

- `GET /api/state` returns the active run.
- `POST /api/new` starts a new run. An optional integer `seed` may be supplied.
- `POST /api/choice` applies one answer using `cardId` and `choiceId`.
- `POST /api/advance` removes one day from every unfinished job after all daily questions are answered.

There is no shift endpoint.

## Core usage

```python
from echo_adventure.config import GameConfig
from echo_adventure.scenario_generator import generate_scenario
from echo_adventure.simulation import advance_day, initialize_state

config = GameConfig.for_preset("normal", seed=12345)
scenario = generate_scenario(config)
state = initialize_state(scenario)

print(len(state.jobs))  # 20
while not state.final_item_completed:
    advance_day(state)
```
