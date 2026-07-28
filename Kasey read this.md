# Kasey, read this first

This is the quick mental model for ECHO Adventure. You do not need to learn
every file before making a change.

## The whole game in 30 seconds

- A seed creates 20 independent jobs. Each job is also one submarine puzzle
  piece.
- Before play starts, the backend generates every reachable ordinary decision
  state and solves the best route through them.
- The player and ECHO start with separate copies of the same jobs. The player
  chooses normally; ECHO follows the solved route.
- After all questions for a day are answered, every unfinished job loses one
  remaining day.
- ECHO must win every divergent run. The only tie is when the player reproduces
  ECHO's exact optimal path.

That last rule is the most important invariant in the repository.

## The normal flow of one run

```text
seed
  -> generate jobs
  -> generate and solve the decision web
  -> create matching player and ECHO states
  -> show a question
  -> apply both actors' choices
  -> repeat until the day's questions are done
  -> advance every unfinished job by one workday
  -> show the daily summary and next puzzle pieces
  -> repeat until the final comparison
```

`GameSession` in `echo_adventure/api/session.py` is the conductor for that
flow. If you are unsure where a phase change happens, start there.

## What “the decision web” means

The web in `echo_adventure/decision_web.py` is a directed acyclic graph (DAG).
It is generated at startup so ECHO knows the outcome of every ordinary choice
before the player begins.

One graph node contains only the state that can affect the future:

- the day and question number;
- every job's remaining days;
- which jobs are complete;
- the one pending follow-up, if a previous choice scheduled one.

Each choice is an edge to the next state. When two different histories produce
the same future state, they reuse the same node. That reconvergence is why this
is a graph rather than a huge duplicated choice tree.

After every reachable node exists, the builder solves backward from the end.
ECHO chooses by this order:

1. earliest completion day;
2. highest decision score;
3. lowest cumulative unfinished job-days;
4. stable choice ID as the final tie-break.

The ordinary web covers play before day 25. If an attempted web would make
ECHO's best route enter overtime, generation tries another deterministic
schedule for the same job scenario. Player routes that fall out of the web can
continue with runtime-generated overtime questions.

## Where decisions come from

There are three layers:

| File | Responsibility |
| --- | --- |
| `echo_adventure/decisions/definitions.py` | The declarative catalog: question text, choices, score strength, icons, and possible follow-ups. |
| `echo_adventure/decisions/cards.py` | Turns catalog entries into state-specific cards with real job targets and add/remove-day effects. It also creates overtime and final-assembly cards. |
| `echo_adventure/decisions/effects.py` | Applies the selected effects, records history, and schedules eligible follow-ups. |

A choice never creates a hidden simulation mechanic. Its gameplay effect is
adding or removing days from named jobs. The narrative is context around that
job-day model.

Follow-ups remember the earlier choice and its originating job. They appear
later only if their deterministic roll succeeds and that job is still active.
The preplanned graph keeps one pending follow-up per route so graph growth stays
bounded.

## Player versus ECHO

`echo_adventure/echo.py` advances ECHO through the optimal edge already stored
on each graph node. `GameSession` keeps ECHO synchronized with the player's
question slot and workday, but ECHO mutates its own simulation state.

The player may enter overtime after the preplanned horizon. If ECHO is already
finished and the player has one job left, the player may receive one bounded,
player-only Final Assembly batch. Its acceleration cap is intentionally chosen
so a divergent player cannot catch or beat ECHO.

At the end, `echo_adventure/api/review.py` explains the result using the same
ordering as the graph solver. If a new outcome appears that lets a divergent
route tie or win, treat it as a correctness bug.

## Backend and browser responsibilities

- `echo_adventure/api/session.py` owns mutable run state and all phase
  transitions.
- `echo_adventure/api/server.py` exposes the small local HTTP API and static UI.
- `echo_adventure/api/payloads.py` converts session state into the browser
  contract.
- `echo_adventure/api/developer.py` and `automation.py` inspect or automate the
  real session in developer mode.
- `echo_adventure/ui/app.js` coordinates browser requests and rendering.
- `dayClock.js`, `renderDecisions.js`, `renderSummary.js`, and `renderFinal.js`
  own the major UI regions.
- `ui/state.js` holds browser-only state such as open modals, pending selection,
  animation progress, and developer display preferences.

`SessionStore` locks mutations because the HTTP server is threaded. Standard
mode must omit all developer metadata and return `404` for developer-only
routes; hiding the panel in JavaScript is not enough.

## Where to start for common changes

- Add or edit question content: `decisions/definitions.py`, then catalog tests.
- Change how choice scores become job days: `decisions/cards.py` and
  `decisions/effects.py`; also check graph and full-campaign tests.
- Change the daily/game phase flow: `api/session.py`, then payload and session
  tests.
- Change API fields: `api/payloads.py`, UI consumers, and both standard/dev-mode
  tests.
- Change a screen: the matching `ui/render*.js` file plus `ui/styles.css`.
- Change graph behavior: `decision_web.py`; use seed `100007` and watch startup
  time, node count, and the exact-path/divergent-path guarantees.

## Running and checking it

```bash
# Standard game
python3 -m echo_adventure --seed 100007

# Developer controls and diagnostics
python3 -m echo_adventure --dev --seed 100007

# Complete API and UI suite
npm t

# Decision-web performance benchmark
python3 scripts/benchmark_decision_web.py
```

Developer mode is the fastest way to inspect why a choice is preferred, follow
a route, or skip to a reachable day. It uses the real game rules, not a separate
simulation.

When changing code, keep comments focused on purpose and reasoning—especially
around graph bounds, phase transitions, ECHO guarantees, and developer-mode
isolation. Also preserve `todo.md` and every log file.
