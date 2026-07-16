# ECHO Adventure

ECHO Adventure is a local browser game about completing twenty independent jobs. Every job is also one piece of the submarine assembly puzzle. At startup, the game generates one complete seed-specific decision web shared by the player and a hidden ECHO run.

## Game rules

- Every run contains exactly 20 jobs.
- Each job starts with a random runtime from 5 through 15 days, weighted toward 5–7 days while retaining occasional longer jobs.
- There are no subjobs, dependencies, shifts, resources, queues, events, or deadline.
- Every unfinished job loses one remaining day whenever a game day advances.
- Each day presents a configurable 2–4 questions.
- Every question is one node in the startup-generated web. Its answer selects the already-generated next node.
- A question either adds days to a job or set of jobs, or removes days from a job or set of jobs.
- Equivalent future states reconverge into the same node, making the complete web a directed acyclic graph rather than a duplicated history tree. Preplanned questions change their exact primary job, which keeps this reconvergence tractable without horizon-based effect capping.
- Probabilistic follow-ups are rolled while the web is generated and become preplanned successor questions.
- A follow-up can amplify, reverse, or leave in place its triggering answer, but it never exactly cancels that answer's job-day change.
- Manufacturing situations such as equipment, staffing, material, weather, and quality issues are flavor text only. They have no hidden model or effect beyond the job-day change stated on the answer.
- The run ends only after all 20 jobs are complete. The full web covers days 1–24, and question generation continues seamlessly from day 25 if work remains. Runtime generation uses the complete base catalog, prioritizes its least-used definitions without weighting, and continues to surface eligible follow-ups.
- Before the player sees the first question, ECHO solves every node backward. It minimizes final completion day, maximizes decision score among equal completion days, and then uses a stable choice-ID tiebreak.
- During play, ECHO traverses that solved route independently: each accepted player answer applies one matching-slot ECHO answer, and day advancement applies ECHO's once-per-day work tick without replaying its decisions.
- If ECHO's solved route would reach day 25, the question web is regenerated while preserving the job scenario. ECHO therefore always finishes inside the completely solved portion of the run.
- A player who reproduces ECHO's exact optimal path ties ECHO. Every divergent path ranks behind ECHO by completion day, score, or the stable path tiebreak.

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
- `max_campaign_day = 25` (runtime-generation boundary)
- `day_cycle_duration_ms`
- `daily_summary_counter_duration_ms`

## Architecture

```text
echo_adventure/
  config.py               Jobs, runtime, question-count, horizon, and UI timing settings
  models.py               Flat job, decision, scenario, and state dataclasses
  scenario_generator.py   Deterministic twenty-job generation
  decision_web.py         Days 1–24 startup DAG generation and global optimization
  simulation.py           Once-per-day job progression
  metrics.py              Completion and remaining-work rollups
  echo.py                 Hidden traversal of the globally optimal web policy
  decisions/
    cards.py              Preplanned card construction and runtime continuation generation
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

- `GET /api/state` returns the active run and current preplanned web node.
- `POST /api/new` starts a new run. An optional integer `seed` may be supplied.
- `POST /api/choice` applies the player's answer, moves to its preplanned successor node, and applies ECHO's independent optimal answer for the same daily slot using `cardId` and `choiceId`.
- `POST /api/advance` removes one day from every unfinished job in each still-active simulation after all daily questions are answered.

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
