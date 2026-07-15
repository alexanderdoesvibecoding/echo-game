# Implementation prompt: player and ECHO completion timelines

Implement the following change in the ECHO Adventure repository. Follow all repository instructions in `AGENTS.md`/`agents.md`, preserve unrelated work, do not inspect or run anything under `tests/`, and do not modify `todo.md`.

## Objective

Replace the main window's current visible per-day percentage progress bar with two vertically stacked estimated-completion timeline bars:

1. `YOU:` — the player's projected completion timeline.
2. `ECHO:` — ECHO's projected completion timeline.

The timelines must make the effect of decisions immediately visible. A poor player answer can move the player's estimated completion date later and move their submarine backward on the newly expanded scale. A good answer can move the date earlier and move the submarine forward. ECHO must make its own best choice at the same time the player confirms each decision, so ECHO's estimate and submarine animate immediately as well.

## Timeline behavior

- Stack the two timeline rows vertically. Do not combine the actors on a shared track.
- Each row has its own independent date scale.
- Both scales always begin on the fixed story start date, July 1, using the configured schedule start date as the source of truth.
- Each row ends at that actor's current estimated completion date. The two right endpoints may therefore show different dates.
- Keep the physical track width consistent between the two rows. A later estimate expands the amount of time represented by that actor's track rather than requiring a shared scale with the other actor.
- Show the start date at the left and the actor's estimated completion date at the right.
- Place a submarine immediately above the tip of each row's completed/elapsed portion. It should visually ride above the bar, remain inside the usable bounds at both endpoints, and not obscure the date labels.
- Compute the submarine position from elapsed story time over the actor's independently projected schedule range. At the start of July 1 it should be at the beginning; when the current story date reaches the displayed completion date it should be at the end.
- Clamp the displayed estimated completion date so it can never appear earlier than the current story date. In other words, use the visual equivalent of `max(projected completion date, current date)`. Preserve the existing game-completion rules; this is a visual safeguard, not a new completion mechanic.
- Recalculate and animate a row immediately whenever its projected completion date changes after a confirmed decision or day advancement.
- Animate both the scale/end-date change and submarine movement smoothly. Respect `prefers-reduced-motion` by disabling or minimizing the transition.
- Use accessible actor/date text and useful timeline semantics. Do not rely on color alone to distinguish `YOU:` from `ECHO:`.

## Bar and submarine appearance

- Use solid-color timeline fills rather than the current multicolor gradient treatment.
- Reuse the existing submarine asset at `echo_adventure/ui/assets/virginia-submarine-cutout.png`. Do not create or substitute a new submarine image asset.
- Render the submarine as a clearly visible, fully opaque, solid-color silhouette. Using the existing PNG's alpha shape as a CSS mask is acceptable and is preferable if it avoids the faded/transparency problem. Do not reduce opacity on the submarine or any ancestor that would make it washed out.
- Use the same submarine design for both rows. The `YOU:` and `ECHO:` labels are the primary identity cues; actor-specific colors may be used as a secondary cue if they work in both light and dark themes.
- Keep the icon compact and responsive so the timelines work at narrow viewport widths.

## ECHO decision timing

Change ECHO from choosing all of its daily answers during day advancement to choosing incrementally when the player confirms answers:

- When the player confirms one decision through `/api/choice`, apply the player's selected choice first and then apply exactly one not-yet-applied ECHO choice for the same daily decision slot.
- ECHO must continue using its existing policy of selecting its best available choice. Do not weaken or randomize ECHO's policy.
- Preserve ECHO as an independent simulation. Its choice should be based on ECHO's own daily card/state for that ordinal slot, not by applying the player's selected choice to ECHO.
- Generate/cache ECHO's daily cards in a stable way so repeated state reads and UI renders cannot regenerate, skip, or duplicate ECHO decisions.
- Track how many ECHO choices have been applied for the current day. An API retry, duplicate player submission, or repeated payload construction must not apply an ECHO choice twice.
- When the player confirms the second decision of a day, ECHO applies its second decision, and so on.
- Day advancement must no longer reapply ECHO's decisions. It should perform only the remaining once-per-day ECHO simulation work after all expected choices have already been made.
- If ECHO has already completed, leave its final completion state stable and do not attempt additional choices.
- Preserve deterministic behavior for a given seed and preserve the existing final comparison/history data as far as possible.
- Keep ECHO's actual answer details hidden during active play unless they are already intentionally exposed elsewhere. The live UI should reveal ECHO's estimated completion date and movement, not necessarily its answer text.

## API/state requirements

- During an active game, expose enough data for both timeline rows. At minimum this should include, for both the player and ECHO:
  - current/projected completion day;
  - formatted projected completion date;
  - actual completion day/date when complete, if applicable.
- Continue exposing the current story day/date and configured start date or an equivalent unambiguous start-day value.
- Use the backend's projected-completion calculation as the source of truth. Do not duplicate job-schedule estimation logic in JavaScript.
- Return the updated player and ECHO projections in the `/api/choice` response so both rows can update immediately after confirmation.

## Existing day-cycle behavior

- Remove/replace only the visible day-percentage progress presentation. Preserve the existing internal day-cycle timer that controls when decision events appear and when a completed day advances.
- The UI may continue to display concise workday/paused status text and the button for opening the next decision, but the old percentage and gradient bar should no longer be the main progress visualization.
- Be mindful that the inline decision area currently rerenders frequently as the timer ticks. Implement timeline updates so DOM replacement does not cancel or prevent the projected-date/submarine transition. Prefer persistent timeline elements updated through styles/attributes, or another approach that reliably animates from the previous values.

## Edge cases

- July 1 start state and a one-day projected range must not cause division by zero or invalid CSS values.
- Clamp all visual percentages to `0–100%`.
- Dates that cross into another month must display correctly through the existing calendar helpers.
- A projected date equal to the current date should place the submarine at the end of the track.
- A projected date that would mathematically precede the current date should display as the current date without changing the simulation's actual result.
- Starting a new run must reset both timeline rows and all incremental ECHO decision bookkeeping.
- Light theme, dark theme, responsive layouts, modal pausing, and reduced-motion mode must remain usable.

## Likely implementation areas

Inspect and update the relevant implementation rather than assuming this list is exhaustive:

- `echo_adventure/api/session.py` for incremental ECHO choice ownership and day advancement.
- `echo_adventure/echo.py` for separating ECHO's per-choice behavior from its daily simulation tick.
- `echo_adventure/api/payloads.py` for live player/ECHO timeline data.
- `echo_adventure/ui/dayClock.js` and `echo_adventure/ui/renderDecisions.js` for replacing the visible day bar while retaining timer behavior.
- `echo_adventure/ui/styles.css` for the stacked timelines, solid bars, opaque submarine mask/image, animation, responsive behavior, dark theme, and reduced motion.
- `echo_adventure/ui/submarineVisual.js` if sharing the existing submarine asset cleanly requires extending the current helper.

## Acceptance criteria

- The main active-game window displays two stacked rows labeled `YOU:` and `ECHO:`.
- Both rows start on July 1 and independently end at the correct actor-specific estimate.
- Each row has a fully visible submarine above its elapsed-time tip using the existing PNG asset.
- Confirming a bad player answer can immediately extend the player's represented schedule and move their submarine backward.
- Confirming a better answer can immediately shorten the player's represented schedule and move their submarine forward.
- At that same confirmation moment, ECHO makes exactly one best-choice decision and its estimate/submarine animates to the new position.
- ECHO decisions are not applied again during day advancement.
- Advancing the story date moves both submarines forward according to their own scales.
- Neither displayed completion endpoint can appear before the current story date.
- The old visible day percentage/gradient progress bar is gone, while timed decision presentation and automatic day advancement still work.
- A seeded run remains deterministic, final comparison/history remains coherent, and a new run fully resets the feature.
- The project passes its standard build/compile check and starts to its normal initial state without an immediate error. Follow repository verification limits: do not inspect or run unit tests, do not perform extensive testing, and stop every process started for startup verification.

Before finishing, report the files changed, briefly explain the ECHO synchronization approach, and list the exact allowed verification commands run with their results.
