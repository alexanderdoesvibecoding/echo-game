# Implement deterministic two-day random job targeting

Implement the change described below in the current `echo_adventure` repository. Treat the repository contents and its `AGENTS.md`/`agents.md` instructions as authoritative at implementation time. Before editing, inspect the working tree and relevant source again so later repository changes are preserved rather than overwritten.

## Objective

Replace the main campaign's current behavior of targeting the longest unfinished job for every ordinary preplanned decision with a deterministic random job schedule organized into two-day targeting windows.

At the same time, reduce the default number of decisions per day from 2–4 to 2–3. Preserve the current exact, fully materialized decision DAG and ECHO's globally optimal solution. Do not replace it with approximation, sampling, beam search, lazy guessing, or heuristic planning.

## Current implementation context

This prompt was prepared against commit `de0adf5`. Revalidate these details before changing anything:

- `echo_adventure/config.py` currently defaults to `min_decisions_per_day = 2` and `max_decisions_per_day = 4`.
- `echo_adventure/decision_web.py::_DecisionWebBuilder` deterministically generates daily question counts and definitions, materializes every reachable state, and backward-solves the complete graph.
- `_DecisionWebBuilder._build_card()` currently sorts unfinished jobs by descending `remaining_days` and assigns `primary = incomplete[0]`, which makes ordinary decisions target the longest-ECD job.
- Pending follow-ups override that ordinary primary selection and remain tied to their originating job.
- `echo_adventure/decisions/cards.py::build_preplanned_decision_card()` applies preplanned choices to the selected primary job.
- `echo_adventure/api/session.py` uses the exact decision web during the preplanned campaign. Overtime separately calls `generate_daily_decision_cards()`, whose job targets are already independently randomized at runtime.
- ECHO's objective order in `_DecisionWebBuilder._solve()` is earliest completion day, then highest decision score among equally fast routes, then the stable choice/path tiebreak.
- Existing tests require exact-path ties and require every divergent player route to lose to ECHO.

## Required behavior

### Daily decision count

- Change the default game configuration to 2–3 decisions per day:
  - minimum remains `2`;
  - maximum changes from `4` to `3`.
- Keep the existing configuration fields and validation. Do not hard-code question counts outside `GameConfig`.
- The new defaults apply to both the preplanned campaign and overtime because both already consume the configuration.

### Deterministic 200-entry job schedule

- Build a deterministic schedule containing exactly 200 job IDs for each decision-web builder.
- Seed it only from stable run inputs, using the scenario/game seed and a stable suffix. Do not use global random state, node creation order, object hashes, wall-clock time, or process-dependent values.
- The same game seed must produce an identical schedule, identical decision web, identical ECHO route, and identical cards across separate runs.
- Build the 200 entries as independently shuffled blocks of all scenario job IDs:
  1. start with the builder's stable sorted `job_ids`;
  2. use one locally seeded `random.Random` instance;
  3. repeatedly copy and shuffle the complete job-ID block;
  4. append blocks until at least 200 entries exist;
  5. truncate to exactly 200 entries.
- This keeps representation balanced and works for non-default job counts. If schedule lookup ever passes the end, wrap cyclically with modulo 200.
- Use named constants for the schedule length (`200`) and window duration (`2`) rather than unexplained literals. Do not add public configuration knobs unless the current architecture clearly requires them.

### Two-day ordinary-target windows

- The nominal schedule position for an ordinary preplanned decision is its zero-based two-day window:

  ```python
  window_index = (state.day - 1) // 2
  ```

- Days 1–2 therefore begin at schedule entry 0, days 3–4 at entry 1, days 5–6 at entry 2, and so on.
- For an ordinary preplanned card, begin at the nominal schedule position and scan forward cyclically until finding an unfinished job. Use that job as the card's `primary` target.
- Do not add a mutable schedule cursor to `DecisionWebState`. Target selection must remain a pure deterministic function of the seed-derived schedule, current day/window, and which jobs are complete. This is the behavior covered by the performance benchmark.
- All ordinary decisions within the same two-day window and the same completion state should therefore use the same affected job.
- If a choice completes that job during the window, later ordinary nodes should deterministically advance to the next scheduled unfinished job by using the same forward scan.
- Never select a completed job when at least one unfinished job exists.
- Preserve the existing ordering of `incomplete` jobs when passing `ordered_targets` into `build_preplanned_decision_card()` unless a change is strictly necessary. Only replace how the ordinary `primary` job is selected.

### Follow-ups

- Preserve the existing follow-up exception exactly: a pending follow-up remains tied to its originating active job.
- A follow-up should not use or advance the ordinary two-day target selection.
- Preserve current follow-up probability, timing, cancellation avoidance, and daily-boundary behavior.

### Overtime

- Do not apply the 200-entry schedule or two-day window policy during overtime.
- Keep overtime's existing runtime `generate_daily_decision_cards()` job selection fully random and deterministic under its existing seed rules.
- Do not add persistent overtime schedule/window state.
- Overtime should receive 2–3 questions per day through the changed configuration defaults, but its targeting mechanics should otherwise remain unchanged.

### ECHO guarantees

These are hard requirements:

- Retain the complete exact decision graph and solve every reachable choice represented by it.
- ECHO must still select the globally optimal route for the generated seed under the existing lexicographic objective:
  1. earliest completion day;
  2. highest decision score among routes completing on that earliest day;
  3. stable path/choice tiebreak.
- A player following ECHO's exact optimal path must tie.
- Every divergent player path must lose by completion day, decision score, or the stable path tiebreak.
- Never introduce a fallback that lets an unresolved, timed-out, sampled, or partially solved graph start a game.
- Preserve runtime/web drift validation and ECHO's no-overtime optimal-route guarantee.

## Implementation guidance

Prefer a narrowly scoped implementation in `echo_adventure/decision_web.py`:

- Add private named constants for the 200-entry schedule length and two-day window.
- Generate and store the immutable schedule in `_DecisionWebBuilder.__init__()` after `job_ids` is established.
- Consider a small private helper for schedule construction and another for selecting the scheduled unfinished job. Keep the selection logic easy to test directly.
- In `_build_card()`, use scheduled selection for the ordinary primary, then retain the existing pending-follow-up override.
- Keep the schedule independent of `generation_attempt` unless current retry semantics prove that including it is necessary. The desired rule is that target ordering is a stable property of the game seed.
- Avoid unrelated decision-web, scoring, UI, or simulation refactors.

Update current copy and defaults wherever the repository still says 2–4 or “two to four,” including at least:

- `echo_adventure/config.py`;
- the applicable docstring in `echo_adventure/decisions/cards.py`;
- `README.md` gameplay, feature, and configuration-default descriptions;
- existing tests that assert the old default or the old full-campaign range.

## Existing tests to update

Follow the repository rule: update existing tests; do not add new test files or new test functions.

Extend the most relevant existing tests so they cover all of the following:

- `GameConfig` defaults are `(2, 3)`.
- Default full-campaign question counts are always between 2 and 3.
- Schedule construction is deterministic for the same seed and contains exactly 200 entries.
- The schedule is made from balanced shuffled job blocks and works with non-default job counts.
- Two builders or complete webs generated from the same scenario/config are identical.
- Ordinary target selection uses the correct two-day window position.
- Multiple ordinary questions in one window retain the same target while it is unfinished.
- Selection advances deterministically when the scheduled target is complete.
- Selection wraps safely through the 200-entry schedule.
- Ordinary targets are not systematically the longest remaining job; a stable representative seed demonstrates non-longest selection.
- Follow-ups remain attached to their originating job.
- Overtime card generation retains its existing independently randomized targeting behavior.
- Every node remains fully solved and every node's `echo_choice_id` matches its exact backward-solved optimum.
- Existing exhaustive small-web objective-order coverage still proves that no divergent route can beat or tie ECHO.
- Existing default full-campaign exact and divergent cases still produce a tie and an ECHO win respectively.

Prefer extending existing tests in:

- `tests/api/test_config_scenario_simulation.py`;
- `tests/api/test_decisions_and_web.py`;
- `tests/api/test_full_campaigns.py`;
- existing overtime/session tests if an assertion needs alignment.

Do not weaken assertions merely to make the new implementation pass.

## Performance acceptance criteria

The exact graph must remain practical to generate.

Previous exploratory benchmarks using five default-size seeds (`12345`, `24680`, `97531`, `13579`, and `86420`) with 2–3 decisions per day and two-day windows produced:

- 2,982–53,019 graph nodes;
- 0.31–5.19 seconds generation time;
- successful exact generation on attempt 0 for every sampled seed;
- 6–9 distinct affected jobs along ECHO's optimal route.

Treat these as context, not as a substitute for verification against the implementation and current code.

- Benchmark at least those five seeds after implementation using the real `generate_decision_web()`/`GameSession` path.
- Report node count, generation time, generation attempt, optimal completion day, and target variation for each seed.
- The user's acceptable startup threshold is under 10 seconds per tested default-size seed in the local environment.
- Do not put a brittle wall-clock assertion in the normal unit suite.
- If any representative seed exceeds 10 seconds, fails exact generation, enters overtime on ECHO's optimal path, or expands unexpectedly beyond the measured scale, stop and report the evidence. Do not weaken ECHO or silently change targeting semantics to recover performance.

## Required workflow and verification

Follow all repository instructions, including progress tracking and protected files.

1. Inspect `git status` before editing and preserve unrelated user work.
2. Never modify `todo.md`.
3. Use Code Review Graph if available; run its required build/update step before and after implementation.
4. Update `progress.md` throughout the task as required by repository instructions.
5. Make only scoped source, documentation, and existing-test changes.
6. Run the project's standard build/compile check.
7. Run the complete existing test suite under `tests/`.
8. Run the broader five-seed performance benchmark described above.
9. Start the application with a fixed seed, verify that it reaches its normal initial API/UI state without an immediate error, and stop every process started for verification.
10. Confirm the final working tree contains only intended changes and that no server or watcher remains running.

At minimum, determine and run the repository's current equivalents of:

```text
python3 -m compileall -q echo_adventure tests
npm test
python3 -m echo_adventure --seed 12345
```

Also run the standard packaging/build command documented or configured by the repository. If a required command cannot be determined from the current repository, ask before proceeding.

## Final report

Report:

- the exact targeting behavior implemented;
- how same-seed determinism is guaranteed;
- how follow-ups and overtime differ from ordinary preplanned decisions;
- every source, documentation, and existing-test file changed;
- benchmark results for each seed;
- every verification command run and whether it passed;
- confirmation that ECHO remains globally exact and that only its identical path ties;
- any remaining risk or deviation from this prompt.
