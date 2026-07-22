# Implement startup-enabled developer mode for ECHO Adventure

Implement a developer mode for the local browser game. This is an implementation task, not another planning pass. Follow the repository instructions in `agents.md`, preserve unrelated user changes, and never modify `todo.md`.

## Required outcome

The game must support:

```bash
python3 -m echo_adventure --dev
python3 -m echo_adventure --dev --seed 12345
```

`--dev` enables a state-aware developer panel, inline decision diagnostics, automated skipping, seeded new-game controls, and automatic browser-console decision-web statistics. A run without `--dev` must retain the current player experience and must not expose developer-only controls, diagnostics, or mutation endpoints.

All automated play must use the existing `GameSession.apply_choice()` and `GameSession.advance_day()` paths. Do not directly complete jobs, set dates, edit scores, jump node IDs, or manufacture final results. Preserve the core invariant: only the exact ECHO path may tie; every divergent path must lose to ECHO.

Do not add new tests or test files. Expand the appropriate existing backend and UI test functions, parameterizations, fixtures, and assertions when coverage must change.

## Existing architecture to reuse

- `echo_adventure/api/server.py` owns CLI parsing, HTTP routes, and construction of `SessionStore`.
- `echo_adventure/api/session.py` owns `GameSession`, player/ECHO traversal, day advancement, overtime, and final assembly.
- `echo_adventure/api/payloads.py` constructs browser payloads. Its card serializer will need player/session context for developer diagnostics.
- `echo_adventure/decision_web.py` contains the fully materialized preplanned DAG. Every node stores `optimal_choice_id`, `optimal_completion_day`, `optimal_future_score`, transitions, and a `DecisionWebState.day`.
- `echo_adventure/decisions/cards.py` contains runtime ECHO choice selection and deterministic follow-up construction.
- `DecisionChoice` already stores `score_delta`, `day_changes`, and `follow_ups`.
- `DecisionCard` already stores exact reverse follow-up provenance: source day, definition, title, choice ID, and choice label.
- `echo_adventure/ui/dayClock.js` owns the presentation clock and automatic day advance.
- `echo_adventure/ui/app.js` is the browser state/action coordinator.
- `echo_adventure/ui/renderDecisions.js` renders active choices.
- `echo_adventure/ui/modals.js` and `index.html` own the new-game modal and settings UI.
- `scripts/benchmark_decision_web.py` already demonstrates portable peak-RSS collection and node/edge/timing calculations. Reuse or extract its approach rather than inventing incompatible units.

The `code-review-graph` tool was unavailable during planning. If it is available when executing this prompt, repository instructions require running `code-review-graph build` before and after the implementation.

## 1. Developer-mode plumbing and isolation

Add a boolean `--dev` CLI option and propagate it through:

```text
main() -> run_ui_server() -> SessionStore -> every replacement GameSession
```

Recommended defaults and behavior:

- All Python entry points remain backward compatible with `dev_mode=False` defaults.
- `SessionStore` owns the server-level dev-mode flag so `/api/new` cannot accidentally turn it off.
- State payloads include a top-level `developer` object only when dev mode is active. Standard-mode payloads should omit it.
- Developer HTTP endpoints must return `404 Not Found` when dev mode is disabled. Do not rely on hidden JavaScript controls for access control.
- Continue accepting the existing optional `seed` body on `/api/new`; the seeded UI described below should use it.
- Update README quick-start/API documentation with `--dev` and the developer behavior.

Suggested dev payload shape (adapt names only if a clearer internally consistent contract emerges):

```json
{
  "developer": {
    "generation": {},
    "runState": {
      "inDecisionWeb": true,
      "canSkipToEnd": true,
      "canSkipToDay": true
    }
  }
}
```

Keep detailed generation data and decision diagnostics inside this dev-only object or dev-only nested card fields.

## 2. State-aware developer panel

Add a clearly identified, collapsible `DEV MODE` panel that remains available anywhere at least one developer action is applicable. Its contents must react to the current state rather than showing nonsensical disabled actions.

Required state behavior:

- During an active preplanned run, show instant progression, decision-diagnostic visibility, strategy selection, skip-to-day, and skip-to-end.
- During overtime/final assembly, show instant progression, diagnostics when a decision exists, strategy selection, and skip-to-end. Hide skip-to-day because the player is no longer at a node in the preplanned decision web.
- At game over, hide all skip and instant-progression actions. Keep only useful run information and access to starting a new game/seed controls.
- While a new game or skip request is running, disable conflicting actions and show a compact busy state.
- If a modal is open, the panel must either remain usable when appropriate or deliberately reduce itself to controls that do not conflict with that modal. It must not be accidentally buried by z-index.
- The panel should not appear at all in standard mode.

Prefer a focused `echo_adventure/ui/devTools.js` module and add it to `STATIC_ASSETS` rather than making `app.js` or `modals.js` much larger.

## 3. Instant time progression

Add an `Instant progression` toggle, defaulting to off on each page load. This is browser presentation state, not `GameConfig` and not saved simulation state.

When enabled:

- Reveal the current decision immediately instead of waiting for its day-clock threshold.
- Reveal the next same-day decision immediately after an answer.
- When all decisions are answered, call the normal `/api/advance` endpoint immediately.
- Commit the returned state immediately instead of opening the daily-summary modal.
- Continue to show the normal final reveal.
- Never issue duplicate choice or advance requests.
- Respect welcome/new-game overlays and any developer request already in flight.

When disabled again, reset/synchronize the clock so elapsed time accumulated while instant mode was on does not cause a surprise duplicate advance.

Do not change server-side sequencing guards. Instant mode only removes browser waiting and the summary interruption.

## 4. Visible, toggleable decision diagnostics

Add a `Show choice diagnostics` toggle to the developer panel. It must default to off so ordinary test decisions are not biased. The user must not need to open the browser console or run JavaScript to inspect a choice.

When enabled, render an obvious but compact diagnostic block on every visible choice. At minimum show:

- Raw schedule score delta (`DecisionChoice.score_delta`).
- Public score before the choice, public score delta, and resulting public score using the existing scoring helpers.
- Concrete job-day changes, with readable job labels/names as well as IDs where useful.
- Whether this is ECHO's preferred choice.
- The preference basis.
- For a preplanned node, the predicted completion day reached by taking this choice and then following the solved optimal continuation. This value also supports the `worst` strategy.
- Follow-up information described in the next section.

Preference labels must be honest:

- Preplanned campaign: `ECHO preferred` means the exact backward-solved choice for that node.
- Overtime: identify it as the best locally evaluated choice for the current runtime state; there is no solved successor web.
- Player-only final assembly: do not claim ECHO took or preferred a choice. Label the stored selection as the best player-only choice or recommendation.

Changing the diagnostic toggle must only rerender the browser. It must not request or mutate game state.

## 5. Forward and reverse follow-up inspection

Expose follow-up diagnostics only in dev mode and only render them when `Show choice diagnostics` is enabled.

### Reverse inspection

The model already stores the exact provenance on `DecisionCard`:

- `follow_up_source_day`
- `follow_up_source_definition_id`
- `follow_up_source_title`
- `follow_up_source_choice_id`
- `follow_up_source_choice_label`

When the current card is a follow-up, show a clear `Generated by` section containing that source day, source decision/title, source choice, and affected job. Reuse these fields; do not create a second provenance system.

### Forward inspection inside the preplanned web

For each choice at the current `player_node_id`, determine exactly whether its transition schedules a follow-up by inspecting the already-built successor state and its pending-source fields. Do not reroll probability.

If it schedules one, inspect the reachable successor subgraph while that same pending source remains active and collect the realized follow-up cards whose stored source matches the current card/choice. Deduplicate variants by a stable semantic signature. Return enough data to display:

- Scheduled target definition/title.
- Earliest/possible day or days.
- Whether some continuations cancel it because the originating job completes.
- Every distinct realized card variant found.
- The variant's choices, raw score deltas, and concrete job-day effects.

Use a visited-node set and stop traversing a branch once the matching pending source is consumed, canceled, or replaced. Cache the result per `(node_id, choice_id)` if needed; do not repeatedly scan the whole DAG on every render. Keep this logic read-only.

### Runtime overtime inspection

Runtime follow-ups are not materialized until later state exists. Refactor/reuse the existing deterministic follow-up occurrence predicate so application and diagnostics cannot disagree. Show whether the current choice will schedule a runtime follow-up, its target, delay, and the catalog/result possibilities available. If concrete future job-day effects cannot yet be known, say `Effect determined when follow-up appears`; do not present a projection as exact.

Final-assembly cards are player-only and schedule no follow-ups under current rules.

## 6. Automated skip API and strategies

Add one dev-only route:

```text
POST /api/dev/skip
```

Body:

```json
{
  "strategy": "echo",
  "targetDay": null
}
```

`targetDay: null` means finish the run. A positive future integer means stop at the start of that reachable day, with that day's first unanswered decision available normally.

Supported strategies:

- `echo`: choose `node.optimal_choice_id` in the preplanned web; use the existing local ECHO selector during overtime. For player-only final assembly, use the card's stored best player-only choice.
- `random`: choose a valid choice using a dedicated deterministic RNG derived from the accepted seed and current skip starting point. The same seed and same starting state should produce the same automated path. Do not use global randomness.
- `first`: choose `card.choices[0]`.
- `last`: choose `card.choices[-1]`. Never assume a fixed third choice.
- `worst`: in the preplanned web, prefer the latest predicted completion day obtainable after this choice and an optimal continuation; break ties by the lowest resulting raw score, then a stable choice-ID rule. In overtime, predict the immediate resulting completion day from remaining job durations, prefer the latest, then the lowest resulting score.

The server-side runner must repeatedly call only normal session operations:

```text
if a current card exists -> select and apply one choice
else if ready_to_advance() -> advance one day
else -> raise an invariant error
```

Return the ordinary state payload at the requested day or at game over. The browser replaces its state with that response, resets pending choice/clock/modal state, and renders normally.

Reject unknown strategies, non-integer target days, current/past target days, unavailable target days, standard-mode calls, and calls after game over with clear `400` or `404` responses as appropriate.

### Infinite-run protection

All skip strategies need a generous maximum-action/day guard. `worst` needs additional protection after leaving the decision web:

- When only one job remains, prefer the worst choice among choices that do not increase that job's remaining duration before the normal daily tick. This guarantees that the daily tick makes progress.
- If no progress-safe choice exists, fall back to the earliest-finishing/local-ECHO choice rather than repeatedly choosing a delay.
- Track consecutive days without progress in the maximum remaining duration (or another small state signature) and abort with a clear error before an infinite loop if future rules make even the fallback non-progressing.

Do not weaken normal game rules globally merely to accommodate automated `worst` play.

## 7. Simple future-day reachability

Specific-day skipping applies only while the player is still in the preplanned decision web.

Keep the check simple and strategy-consistent:

1. Starting from the current player node (or the already-selected pending daily transition), walk the immutable decision web without mutating the session.
2. At each node, select the next transition using the same strategy selector the real skip will use.
3. Collect future `DecisionWebState.day` values until the path completes or enters overtime.
4. A target day is reachable for that strategy only if it appears in this dry traversal.
5. Preflight the entire target request before applying any choices so an unreachable target cannot partially mutate the live session.

Expose the strategy's reachable future days to the dev UI and use a select/dropdown instead of accepting arbitrary free text. Recalculate the list when the strategy or game state changes. If the chosen strategy would finish before a later day, that later day is correctly unavailable; the user can select another strategy such as `worst`.

For deterministic `random` reachability, derive each node's selection from stable seed/node/start-state material so the dry traversal and actual traversal always agree.

When the target is reached, stop immediately after advancing into that day and leave its decision unanswered.

## 8. Automatic browser-console generation statistics

In every dev-mode game, automatically log decision-web generation statistics to the browser console. This must not depend on a UI toggle. Log once after the initial `/api/state` response and once after each successful `/api/new` response. Do not print these statistics to the terminal.

The web is generated before the browser loads, so measure and retain the data in `GameSession`, expose it in the dev-only state payload, and have the browser call something like:

```js
console.info("[ECHO dev] Decision web generation", stats);
```

Include all of these fields:

- Accepted seed.
- Whether the requested startup/new-game seed was explicit or random.
- Total generation time, covering scenario creation, all discarded random seeds, and the accepted web.
- Accepted web generation time.
- Number of timed-out random seeds discarded.
- Node count.
- Edge count.
- Optimal completion day.
- Nodes per second, based on accepted node count / accepted web generation time.
- Peak memory usage in bytes, labeled in the console as process peak RSS and optionally accompanied by a human-readable MiB value.

Use `time.perf_counter()` for durations. Derive edges with:

```python
sum(len(node.transitions) for node in web.nodes.values())
```

Use the same `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` platform normalization already present in `scripts/benchmark_decision_web.py`. Always include the peak-memory key; if the platform lacks `resource`, use `null` and log `unavailable` rather than failing startup. Be explicit that later in-process new games report the process high-water RSS, not an isolated fresh-process peak.

Do not log on every choice/advance payload. A small browser-side logged-generation token/set is acceptable, but loading and starting a new game with the same seed must still log each distinct generation once.

## 9. Seed controls for new games

In dev mode, enhance the existing New Game modal:

- Add an editable seed text box initialized to the current accepted seed whenever the modal opens.
- Add a nearby `Seeded run` checkbox/toggle.
- Keep the checkbox off by default when opening the modal so the existing New Game behavior remains random unless the developer opts in.
- If checked, require a valid integer and send it as `{ "seed": value }` to `/api/new`.
- If unchecked, omit the seed or send `null` so `GameSession` selects random seeds and retains the existing timeout/retry behavior.
- Keep the current game intact if validation or generation fails.
- After a successful new game, update the field to the newly accepted seed for the next time the modal opens.
- In standard mode, retain the current simple new-game modal without seed controls.

The field should remain readable/copyable even while `Seeded run` is off; visually indicate that it will only be used when the toggle is on.

## 10. Suggested internal helpers

Names may vary, but keep selection logic centralized so inspection, reachability, and actual skipping cannot disagree. Useful boundaries include:

- `GameSession.developer_payload()` or a dedicated `api/developer.py` helper.
- `GameSession.skip(strategy, target_day=None)`.
- A preplanned `ordered_choices_for_strategy(node, strategy, random_context)` / `select_choice...` helper.
- A runtime selector for first/last/random/worst/echo.
- `reachable_days(strategy)` using immutable dry traversal.
- `choice_outcome(...)` for completion-day and score comparisons.
- A cached preplanned follow-up inspection helper.
- `_peak_rss_bytes()` shared with or behaviorally aligned to the benchmark.

Avoid a second simulation engine, deep-copying the entire decision web, or direct state patching.

## 11. Tests to update

Do not add new tests, new test functions, or new test files. Incorporate the required coverage into existing test functions, parameterizations, fixtures, and assertions, especially in:

- `tests/api/test_session_payloads_server.py`
- `tests/api/test_decisions_and_web.py` if a pure selection/follow-up helper needs coverage
- `tests/api/test_full_campaigns.py` only where full default-size integration adds unique confidence
- `tests/ui/app_smoke.test.mjs`
- `tests/ui/summary_decisions_clock.test.mjs`
- `tests/ui/final_modals.test.mjs` if the new-game/dev panel UI belongs there

Required backend coverage:

- `--dev`/server/session propagation while existing default signatures still work.
- Standard payloads omit developer data and dev route returns 404.
- Dev payload contains all required generation fields and exact choice diagnostics.
- Explicit versus random generation statistics, including discarded timeout count and total/accepted timing shape.
- Forward preplanned follow-up inspection agrees with stored transitions; reverse provenance is exposed.
- Runtime follow-up diagnostic occurrence agrees with actual scheduling.
- `first` and `last` use actual list boundaries for variable choice counts.
- `echo` from an untouched run ties.
- A prior divergent player choice followed by `echo` skip still loses.
- `random`, `first`, `last`, and `worst` complete valid runs.
- `worst` prefers later completion before lower score when those disagree.
- `worst` post-web safety cannot loop forever with a crafted existing test fixture.
- Reachable target-day skip stops at the start of the requested day with an unanswered card.
- Unreachable target requests fail before mutating session state.
- Endpoint validation and disabled-mode behavior.
- New sessions retain server-level dev mode and accept explicit seed `0`/negative values consistently with existing parsing.

Required UI coverage:

- Panel is absent in standard mode.
- Panel shows/hides controls based on preplanned, overtime/final-assembly, busy, and game-over states.
- Diagnostics default off and toggle visibly without an API call.
- Inline diagnostic markup includes score, preference, effects, and forward/reverse follow-up details with HTML escaping.
- Instant mode reveals decisions and advances exactly once while bypassing the summary modal.
- Skip request resets pending UI/clock/modal state and renders returned target/final state.
- Generation stats log once on initial load and once per new game, without choice/advance duplicates.
- Dev new-game seed controls send a seed only when enabled and display validation errors without losing the current state.

Update test DOM fixtures and `uiState` reset helpers for every new element/state key.

## 12. Verification and completion

Follow `agents.md` progress tracking throughout implementation. For the completed code change, run and report the exact result of:

```bash
python3 -m compileall echo_adventure
.venv/bin/pytest
npm run test:ui
git diff --check
```

Then briefly start the app in developer mode on a free local port with seed `100007` (the repository's required routine verification seed), fetch `/api/state`, confirm the dev payload and required generation fields, exercise at least one dev skip request, and stop the server before finishing. Do not open the application for the user and do not leave any process running.

Also confirm a standard-mode state payload omits developer data and its `/api/dev/skip` request is unavailable.

The finished implementation should be cohesive and modest: dev mode orchestrates and inspects the real game; it does not bypass or fork the game's rules.
