# Repository Instructions

## Protected files

- Never modify `todo.md`.
- Preserve unrelated user changes already present in the working tree.

## Before changing code

- Ask clarifying questions before modifying code if the request is ambiguous,
  has multiple materially different implementations, or requires a product
  decision.
- If the requested change is clear and narrowly scoped, proceed without asking
  for confirmation.
- Do not make changes outside the scope of the user's request.

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
- Run the existing tests under `tests/` for code changes and verify that they
  still pass.
- Update existing tests when needed to keep them aligned with current game
  behavior.
- Do not add new tests.
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
