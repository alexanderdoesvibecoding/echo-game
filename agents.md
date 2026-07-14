# Repository Instructions

## Protected files

- Do not read, run, create, or modify anything under `tests/`.
- Never modify `todo.md`.
- Preserve unrelated user changes already present in the working tree.

## Before changing code

- Ask clarifying questions before modifying code if the request is ambiguous,
  has multiple materially different implementations, or requires a product
  decision.
- If the requested change is clear and narrowly scoped, proceed without asking
  for confirmation.
- Do not make changes outside the scope of the user's request.

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

- Do not perform extensive testing.
- Do not inspect or run the unit tests under `tests/`.
- For code changes, verify only that:
    1. the project compiles or passes its standard build check; and
    2. the application starts and reaches its normal initial state without an
       immediate error.
- If the correct build or startup command cannot be determined from repository
  documentation or configuration, ask the user.
- Report exactly which verification commands were run and whether they passed.

## Running the application

- The application may be started briefly for verification.
- Stop every process started during verification before finishing.
- Do not leave a development server, watcher, or application process running.
- Do not open the application for the user; let the user run it themselves.