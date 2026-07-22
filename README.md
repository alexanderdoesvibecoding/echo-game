<div align="center">
  <img src="echo_adventure/ui/assets/logos/echo-logo-full.png" alt="ECHO Adventure" width="520">
  <p><strong>Build the submarine. Make every call. Discover how close you can come to perfect.</strong></p>
</div>

ECHO Adventure is a local, browser-based decision game about assembling a submarine through 20 concurrent jobs. Every day brings operational choices that can speed up work, introduce delays, and reshape the route to completion.

You are not alone in the scenario. Before you make your first decision, ECHO solves the entire decision web and begins its own hidden run. It has already found the best possible route. Your choices determine only how closely you can follow it—and where you fall behind.

## Quick start

ECHO Adventure requires **Python 3.14 or newer** and has no third-party runtime dependencies.

```bash
python3 -m echo_adventure
```

When initialization finishes, visit [http://127.0.0.1:8765](http://127.0.0.1:8765). Press `Ctrl+C` in the terminal to stop the server.

For an unseeded run, startup gives each randomly selected scenario seed 15 seconds to fully materialize and solve its exact decision web. If it exceeds that budget, the partial web is discarded and a fresh random seed is tried. The game never starts from an incomplete solution.

To replay a deterministic scenario, supply a seed:

```bash
python3 -m echo_adventure --seed 12345
```

Explicit replay seeds are never substituted or time-limited, so the same requested seed continues to produce the same complete scenario and decision web.

The installed console entry point accepts the same options:

```bash
echo-adventure --seed 12345 --host 127.0.0.1 --port 8765
```

## The challenge

Your mission is to finish all 20 jobs and assemble the complete submarine. Each job begins with its own remaining duration, and every game day advances every unfinished job by exactly one day. Before the day can end, you must answer a queue of operational questions.

Each answer changes the remaining duration of one or more jobs. Ordinary preplanned questions use a deterministic seed-derived job schedule with alternating two-day and one-day target windows. Some choices also unlock preplanned follow-ups tied to their originating job, so a decision may continue to shape the run several days later. Ordinary decisions reveal their stated schedule effects; scenario copy adds context, never hidden simulation rules. If ECHO has already finished while the player has fallen behind with one job remaining at the end of a workday, the player receives one bounded Final Assembly Lock-In batch after that day's summary. Any ordinary questions already in progress are completed first. Final choices can preserve, delay, or accelerate the remaining job without displaying exact time changes. The job remains ordinary work and continues progressing one day at a time after the batch, without further questions; those question-free workdays run at an accelerated pace and retain their end-of-day summaries.

Meanwhile, ECHO independently follows the globally optimal route it calculated before play began.

### The outcome is guaranteed

ECHO minimizes completion day, maximizes decision score among equally fast routes, and then minimizes cumulative unfinished job-days measured after each day's decisions. A stable path tiebreak applies only when all three scheduling outcomes are equal. As a result:

- Reproduce ECHO's exact optimal path and the run ends in a tie.
- Diverge anywhere and ECHO wins by completion day, decision score, cumulative unfinished work, or the stable path tiebreak.
- No divergent route can defeat, outsmart, or surpass ECHO.

The question is not whether ECHO made a mistake. It is whether you can avoid making one.

## How a run works

1. **Generate the scenario.** A seed creates 20 jobs, their starting durations, and a complete decision web shared by the player and ECHO.
2. **Answer the day's questions.** Each ordinary day presents two to three decisions. Answers explicitly add or remove days from affected jobs. A lagging player receives only one final bounded batch after ECHO is done and a single job remains.
3. **Advance the workday.** After every question is answered, every unfinished job loses exactly one remaining day.
4. **Assemble the submarine.** Each completed job reveals another piece of the final submarine.
5. **Compare against ECHO.** When all work is complete, the game reveals completion timing, score history, choice alignment, and the reason ECHO won—or why the exact-path run tied.

## Decision score

The displayed decision score is a 0-100 rating derived from raw schedule points. It starts at **50.00**, which represents a neutral route before any decisions are made.

Each choice first receives raw schedule points from its stated job-day effect:

```text
raw choice points = -1 * total job-day change
```

So a choice that removes 2 total job-days is worth `+2` raw points, a choice that adds 2 total job-days is worth `-2` raw points, and a neutral choice is worth `0`. The run's raw score is the cumulative sum of those raw choice points.

The public score converts that unbounded raw total into a bounded 0-100 value:

```text
public score = 50 + (50 * raw score / (abs(raw score) + 10))
```

The result is clamped to `0-100` and rounded to two decimals. A raw score of `0` displays as `50.00`; positive raw scores move toward `100`, and negative raw scores move toward `0`. Because the conversion is monotonic, the route with the higher raw score also has the higher displayed score.

ECHO still optimizes completion day first. Among routes that finish on the same day, it maximizes raw schedule points, which also maximizes the displayed 0-100 score.

## Simulation rules

| System            | Behavior                                                                                                                                                                                                  |
|-------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Jobs              | Every run contains exactly 20 independent jobs, each paired with one submarine piece.                                                                                                                     |
| Starting duration | Jobs begin at 5–15 days, weighted toward shorter durations while keeping every configured duration possible.                                                                                              |
| Daily decisions   | Each day presents a configurable two to three questions.                                                                                                                                                  |
| Question targets  | Ordinary preplanned questions follow a seed-derived 200-entry schedule in alternating two-day/one-day windows. Follow-ups stay with their originating job; extended-play targets remain independently randomized. |
| Choice effects    | A choice only adds or removes stated job-days; narrative context creates no hidden state.                                                                                                                 |
| Daily progress    | Every unfinished job loses exactly one remaining day when the day advances.                                                                                                                               |
| Follow-ups        | Eligible follow-ups are rolled during web generation and stored as preplanned successor questions. Follow-ups with multiple possible results select one result during startup, before either route begins. They may amplify, reverse, or preserve an earlier effect, but never exactly cancel its job-day change. |
| Decision web      | Equivalent future states reconverge, forming a directed acyclic graph instead of a duplicated history tree.                                                                                               |
| Solved horizon    | The complete web covers days 1–24. If ECHO's route would reach day 25, the web is regenerated around the same job scenario so ECHO always finishes inside the solved region.                              |
| Extended play     | Runtime generation continues after day 24 while multiple player jobs remain. Once ECHO is finished and a lagging player has one job left, one player-only Final Assembly Lock-In batch replaces all later questions; the unchanged job then progresses normally to completion. |
| Win condition     | Only an exact reproduction of ECHO's optimal path ties. Every divergent path loses.                                                                                                                       |

There are deliberately no subjobs, dependencies, shifts, resources, queues, deadlines, workstations, employees, materials, inspections, routing, or rework systems. The model is entirely about job-days, decisions, and the gap between a human route and ECHO's optimum.

## Configuration

The game is configured through `GameConfig` in `echo_adventure/config.py`.

| Field                               |      Default | Purpose                                                       |
|-------------------------------------|-------------:|---------------------------------------------------------------|
| `start_date`                        | `2026-07-01` | Calendar date displayed for game day 1.                       |
| `job_count`                         |         `20` | Number of jobs and submarine pieces.                          |
| `min_job_duration_days`             |          `5` | Shortest generated starting duration.                         |
| `max_job_duration_days`             |         `15` | Longest generated starting duration.                          |
| `min_decisions_per_day`             |          `2` | Minimum daily question count.                                 |
| `max_decisions_per_day`             |          `3` | Maximum daily question count.                                 |
| `max_campaign_day`                  |         `25` | Boundary between the preplanned web and runtime continuation. |
| `day_cycle_duration_ms`             |       `6000` | Workday animation duration.                                   |
| `daily_summary_counter_duration_ms` |       `2000` | Daily-summary counter animation duration.                     |
| `seed`                              |       `None` | Optional deterministic scenario seed.                         |

Example:

```python
from echo_adventure.config import GameConfig

config = GameConfig(
    seed=12345,
    min_decisions_per_day=3,
    max_decisions_per_day=3,
)
```

## Benchmark decision-web generation

Run the repeatable startup benchmark after changes that may affect decision-web size or generation performance:

```bash
python3 scripts/benchmark_decision_web.py
```

The default benchmark runs seeds 1 through 10 in isolated processes and reports scenario-generation time, web-generation time, node and edge counts, solved completion day, throughput, and peak resident memory. Imports are excluded from the timings, while memory includes the Python process and the retained web.

Use a shorter seed list, repeat each seed, or emit JSON for automated comparisons:

```bash
python3 scripts/benchmark_decision_web.py --seeds 1 2 3 --runs 3
python3 scripts/benchmark_decision_web.py --json
```

Every benchmark also writes the same output to `log/<timestamp>.log`. Pass `--no-console-output` (or its shorter aliases `--no-console` and `--quiet`) to write only to that log file.

Optional `--max-median-web-seconds` and `--max-peak-rss-mib` thresholds make the command exit unsuccessfully when an explicitly configured performance limit is exceeded. Without thresholds, performance results are informational and only generation failures produce an unsuccessful exit.

## Architecture

```text
echo_adventure/
├── __main__.py            python -m echo_adventure entry point
├── app.py                 Package-level application entry point
├── config.py              Run settings and calendar labels
├── models.py              Jobs, choices, scenarios, and simulation state
├── scenario_generator.py  Deterministic 20-job scenario generation
├── decision_web.py        Startup DAG generation and global optimization
├── simulation.py          Once-per-day job progression
├── metrics.py             Completion and remaining-work snapshots
├── echo.py                ECHO's traversal of the solved optimal policy
├── decisions/
│   ├── cards.py           Preplanned cards and runtime continuation
│   ├── definitions.py     Decision catalog
│   └── effects.py         Explicit add/remove-day effects
├── api/
│   ├── server.py          Local JSON and static-file server
│   ├── session.py         Player and ECHO session ownership
│   ├── payloads.py        Browser response payloads
│   └── review.py          Final player-versus-ECHO analysis
└── ui/                    Browser interface and submarine assembly view
```

## HTTP API

The browser uses a small local JSON API served from the same process.

| Method | Route          | Description                                                                                                                     |
|--------|----------------|---------------------------------------------------------------------------------------------------------------------------------|
| `GET`  | `/api/state`   | Return the active run and current preplanned web node.                                                                          |
| `POST` | `/api/new`     | Start a new run. Accepts an optional integer `seed`.                                                                            |
| `POST` | `/api/choice`  | Apply the player's `cardId` and `choiceId`, move to the preplanned successor, and advance ECHO through the matching daily slot. |
| `POST` | `/api/advance` | Advance one workday in each active simulation after all daily questions are answered.                                           |

There is no shift endpoint.

## Use the simulation directly

The simulation can also be driven without the browser:

```python
from echo_adventure.config import GameConfig
from echo_adventure.scenario_generator import generate_scenario
from echo_adventure.simulation import advance_day, initialize_state

config = GameConfig(seed=12345)
scenario = generate_scenario(config)
state = initialize_state(scenario)

print(len(state.jobs))  # 20
while not state.final_item_completed:
    advance_day(state)
```

This low-level example advances job work only. The browser session layer owns daily decisions, the preplanned web, ECHO's parallel run, and the final comparison.
