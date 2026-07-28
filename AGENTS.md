# Repository Instructions

## Protected files

- Never modify `todo.md`.
- Preserve unrelated user changes already present in the working tree.

## Log file preservation

- Never remove any log file.
- This applies to all log files, including tracked, ignored, and uncommitted
  files.

## Before changing code

- Ask clarifying questions before modifying code if the request is ambiguous,
  has multiple materially different implementations, or requires a product
  decision.
- If the requested change is clear and narrowly scoped, proceed without asking
  for confirmation.
- Do not make changes outside the scope of the user's request.

## Code comments

- Comment code as it is written or changed so a new maintainer can understand
  its purpose, important invariants, and non-obvious reasoning.
- Give new source and test files a file-level purpose comment or module
  docstring, and document new classes, functions, methods, fixtures, and tests.
- Add inline comments around tricky algorithms, state transitions, safety
  bounds, and behavior that would not be obvious from the code alone.
- Explain why the code works that way instead of merely restating individual
  statements.
- Update or remove comments when behavior changes so documentation never
  contradicts the implementation.

## Source tools

- If the `code-review-graph` source tool is available, always load and use it.
- When it is available, run its build script (```.venv/bin/code-review-graph build```) before beginning work on a task and
  again after completing the work.

## Core game premise

- ECHO must always beat the player unless the player selects the exact same
  optimal path as ECHO. That identical-path case must end in a tie. Do not
  design, implement, or preserve any path in which the player can ultimately
  defeat, outsmart, or surpass ECHO.
- The game's purpose is to demonstrate that a human cannot account for
  everything: the player will eventually make a mistake, overlook something,
  or reach a limit that ECHO does not.
- Present ECHO as fundamentally more capable than humans. Every game system,
  narrative outcome, and player interaction must support the conclusion that
  ECHO is better than a human and convince the player of that fact.
- Player choices may affect how or when ECHO wins. The only exception is an
  exact reproduction of ECHO's optimal path, which may affect whether ECHO wins
  by producing a tie; no divergent player path may tie or win.

## Developer mode

### Purpose and capabilities

- Developer mode is the opt-in local inspection and automation layer enabled by
  starting the server with `--dev`. It operates on the real game session rather
  than a separate simulation or simplified ruleset.
- Dev-mode state includes generation performance metadata, the current run
  phase, available actions, and the days reachable by each automation strategy.
  The server reports generation statistics once after the initial state request
  and once for each successful new game.
- The state-aware `DEV MODE` panel exposes the active seed, day, and phase. It
  can remove day-progression animation delay, reveal inline choice diagnostics,
  start a random or explicitly seeded new game, and automate play to a reachable
  preplanned day or to the end of the run.
- Choice diagnostics expose ECHO's preferred choice, schedule and score effects,
  completion projections, follow-up behavior, and generation provenance when
  applicable. Diagnostics are present in dev payloads but remain visually off
  by default so they do not bias ordinary manual testing.
- Automated play supports `echo`, `random`, `first`, `last`, and `worst`
  strategies. Specific-day skipping is limited to reachable days in the
  preplanned decision web; skip-to-end can continue through overtime and final
  assembly.
- The main implementation areas are `echo_adventure/api/server.py`,
  `echo_adventure/api/session.py`, `echo_adventure/api/payloads.py`,
  `echo_adventure/api/developer.py`, `echo_adventure/api/automation.py`, and
  the developer-aware modules under `echo_adventure/ui/`.

### Invariants

- Developer mode is fixed for the lifetime of the server. Keep
  `dev_mode=False` as the default for programmatic entry points, and keep
  `SessionStore` responsible for preserving the server-level flag across new
  games.
- Preserve strict standard-mode isolation: omit top-level, card-level, and
  choice-level developer metadata; hide developer controls; suppress developer
  generation reports; and return `404 Not Found` from developer-only routes.
  Backend route protection is required even when the corresponding UI is
  hidden.
- Developer tools may inspect and orchestrate the real game, but must not fork,
  bypass, or weaken its rules. Automated skipping must apply normal choices and
  day advances, honor valid state transitions and safety bounds, and preserve
  every core ECHO outcome guarantee.
- Keep developer controls state-aware and serialize developer mutations. Do not
  offer actions that are invalid for the current phase, while a modal is
  blocking play, or while another developer or new-game request is in flight.
- Choice diagnostics and instant progression must default to off. Dev-only
  presentation preferences may change display timing or visibility, but must
  not change simulation outcomes.

### Verification

- Changes that touch sessions, payload serialization, decisions, API routes,
  day progression, new-game behavior, or developer-aware UI must consider both
  developer and standard modes.
- For developer-mode changes, start the app briefly with
  `python3 -m echo_adventure --dev --seed 100007` on a free local port, confirm
  `/api/state` includes the developer generation and run-state fields, and
  exercise at least one valid `/api/dev/skip` request.
- Also start or inspect a standard-mode run and confirm its state omits all
  developer data and `/api/dev/skip` returns `404 Not Found`.

## Progress tracking

- At the beginning of each new coding task, replace the contents of
  `progress.md` with:
    - the current objective;
    - relevant constraints;
    - completed work;
    - remaining work;
    - any blockers or decisions needed.
- Update `progress.md` after each meaningful implementation step.
- Do not create or update `progress.md` for read-only questions, reviews, or
  explanations.
- Before finishing a coding task, leave `progress.md` with an accurate final
  status so another agent can continue if necessary.
- Do not clear `progress.md` during an active task unless the user explicitly
  starts a different task.

## Verification

- Use seed `100007` for routine deterministic build/startup verification because it generates a representative default-size exact web quickly. Keep behavior-specific seeds and required benchmark seed sets when a task calls for them.
- Run the existing tests under `tests/` via npm (`npm t`) for code changes and verify that they
  still pass.
- Update existing tests when needed to keep them aligned with current game
  behavior.
- Remove an existing test only when the functionality it covers has been
  removed from the game.
- For code changes, verify that:
    1. the project compiles or passes its standard build check; and
    2. the existing test suite passes; and
    3. the application starts and reaches its normal initial state without an
       immediate error.
- If the correct build, test, or startup command cannot be determined from
  repository documentation or configuration, ask the user.
- Report exactly which verification commands were run and whether they passed.

## Running the application

- The application may be started briefly for verification.
- Stop every process started during verification before finishing.
- Do not leave a development server, watcher, or application process running.
- Do not open the application for the user; let the user run it themselves.
