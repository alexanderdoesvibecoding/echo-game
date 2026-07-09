# Implementation Prompt: Replace Current Decisions With The New Manufacturing Decision System

You are working in the `echo_adventure` repository. Your task is to implement the new decision system described in `decisions.md`, using `decision-implementation-audit.md` as the architecture/feasibility guide.

This is expected to be a sweeping change. Do not treat the current decision code as sacred. Preserve useful simulation primitives where possible, but replace the current generic decision catalog and generic branch-tag campaign behavior with the new named manufacturing decisions and their named follow-ups.

## Source Of Truth

- `decisions.md` is the product/design source of truth for the new decisions, options, immediate effects, and follow-up relationships.
- `decision-implementation-audit.md` explains how the current Python fits those decisions and which areas require new domain state.
- The existing Python implementation is the starting point, not the final shape.

## Product Requirements

1. Replace the current player-facing decision set with the decisions in `decisions.md`.
2. Use real simulation objects wherever appropriate, not only generic risk/delay modifiers.
3. Only some decisions have follow-ups. Follow-ups are allowed to be probabilistic.
4. ECHO should know the entire decision graph, including possible probabilistic follow-ups and their probabilities/outcomes.
5. No-choice cards should still appear as single-choice cards. Their single choice should be inert, with wording like acknowledging the event. They should not be automatic hidden events.
6. Shift gains and losses should be literal. If a choice says it loses 2 shifts, add 2 shifts of duration/blocking/downtime. If it gains 5 shifts, literally subtract or recover 5 shifts where the design says it should.
7. Shared follow-ups are allowed and expected. Multiple earlier choices can unlock the same later decision.
8. Keep the run deterministic for a fixed seed. Probabilistic follow-ups should use seeded deterministic randomness, not ambient randomness.

## Important Current Architecture

Current useful primitives:

- `Job`: status, priority, due shift, risk, dependencies, assigned workcenter, setup/transport time, remaining duration, rework count.
- `WorkCenter`: status, current job, queue, downtime, capabilities.
- `Event`: target type/id, start/duration/severity, effects dict, parent/chain fields.
- `DecisionCard` and `DecisionChoice`: already support `future_unlock_card_ids`, `branch_tags_added`, and `score_delta`.
- `apply_choice` already applies immediate effects and records decision history.
- ECHO already deep-copies state, applies choices, projects future decisions, advances days, and ranks forecast outcomes.

Current limitations to fix:

- Domain resources such as workers, fixtures, tools, gauges, documents, consumables, cranes, racks, carts, software seats, batches, clean rooms, and setup libraries are not first-class objects.
- The campaign graph is generic branch-tag based. The new design needs named graph edges such as `Weather -> Weather cleared early`.
- The current effect system has only generic effect names such as `wait`, `reroute`, `resequence`, `pull_forward`, etc. The new decisions need parameterized effects and some domain-specific handlers.
- ECHO's static and live scoring know only current effect names. New effects must be scored, and ECHO projection must see real state changes.

## Desired Architecture Direction

Prefer a real domain model. Add new dataclasses/enums as needed, likely including some or all of:

- Worker or crew resources with skills, availability, qualification, and fatigue/support load.
- Fixture/tool resources with capabilities, certification/calibration state, current holder, and availability.
- Material/consumable stock or kits with lot/verification/donor relationships.
- Documentation artifacts such as travelers, setup sheets, program templates, labels, packets, revisions, and approval state.
- Inspection/metrology/gauge/method state.
- Batch/window resources such as ovens, cure slots, wash tanks, cranes, utility slots, racks/carts/staging lanes.
- Controlled areas or shop zones for clean room, FOD, access badge, and staging-map decisions.
- Job family/route metadata so broad effects can apply to "matching" work, not arbitrary jobs.

You do not need to over-model every concept if a generic domain object covers it well. For example, `SupportResource` or `SharedResource` may cover cranes, software seats, racks, label printers, and tanks if it remains clear and testable.

## Named Decision Graph

Replace or extend the existing generic branch-tag graph with a named decision graph.

Requirements:

- Every card from `decisions.md` should be represented by a stable internal card id.
- Each choice that says `Can unlock X` should encode a possible edge to the `X` card.
- Not every `Can unlock X` edge has to fire. Add a deterministic probability/condition layer.
- ECHO must know the full graph and probabilities/outcomes.
- Player should not see future cards until they unlock.
- Multiple choices may point to the same follow-up card.
- Follow-up cards should retain their source context where useful, but they should be reusable from multiple sources.

Suggested model:

- Add a `DecisionDefinition` or similar that is separate from runtime `DecisionCard`.
- Add `DecisionOutcome`/`DecisionEffect` definitions with typed effect parameters.
- Add `FollowUpEdge` with `target_card_id`, `probability`, `delay_days` or `delay_shifts`, and optional source/context tags.
- At scenario generation, prebuild the full graph so ECHO can inspect/project it.
- At runtime, unlock or schedule follow-up cards deterministically based on choice, seed, and edge probability.

## Effect System

Add a parameterized effect engine rather than one bespoke function per option. It should be able to express:

- Add/subtract remaining duration from selected jobs.
- Add/subtract base/setup/transport duration for future matching jobs.
- Block/release selected jobs.
- Take workcenters/resources down for N shifts.
- Open or free capacity for N shifts.
- Reroute or reassign selected jobs.
- Move jobs to queue front/back.
- Add rework.
- Add or remove inspection/documentation/acceptance holds.
- Add or remove support resource constraints.
- Add or remove material/consumable constraints.
- Modify risk and priority.
- Apply literal shift gains/losses.
- Schedule named follow-ups with chance.

Keep existing generic effects if they remain useful, but they should become a subset of this richer system.

## ECHO Requirements

ECHO should know the entire decision graph and use it.

Concrete requirements:

- ECHO's live projection must apply the exact same choice effects and probabilistic follow-up resolution as the player path, using deterministic seeded randomness.
- ECHO should evaluate expected value when a follow-up is probabilistic. It can do this by enumerating seeded branches, weighting outcomes, or by using deterministic known outcomes for the run seed. Pick one approach and document it.
- Static scoring must understand new effect types enough to be stable when live projection is capped or fails.
- ECHO should be able to choose apparently bad immediate options when the future expected payoff is better.
- ECHO should avoid tempting immediate options when they produce bad follow-ups.
- ECHO must support shared follow-up cards.

Important subtlety:

- If an option's future gain is only represented as `score_delta`, ECHO can prefer it statically but the simulation will not prove the operational outcome. Prefer real state changes so projection naturally sees completion/risk/lateness effects.

## No-Choice Cards

Cards like `Safety drill` and `FOD sweep` should become single-choice decisions, not hidden automatic events.

Implementation guidance:

- Present one option such as `Acknowledge` or `Absorb the delay`.
- The option itself has no strategic effect.
- The card/effect applies the unavoidable state change exactly once.
- ECHO should choose that single option and move on.

## Literal Shift Accounting

Treat shift numbers in `decisions.md` literally enough that the player can feel the promise.

Examples:

- "Loses 2 shifts" should add 2 shifts to remaining duration, block for 2 shifts, or take a resource down for 2 shifts.
- "Gains 5 shifts" should subtract 5 total shifts from affected work, release blocked work earlier by 5 shifts, reduce downtime by 5 shifts, or otherwise produce an equivalent literal recovery.
- Do not hide gains/losses only in abstract risk.

Risk can still exist, but it should be separate from the literal shift effect.

## Implementation Scope

This is a maximal implementation prompt. The goal is not a tiny wrapper over current generic decisions.

Minimum acceptable end state:

- The game uses the decisions from `decisions.md`, not the old generated decision set.
- The decision graph has named cards and named follow-up edges.
- Follow-up probabilities are deterministic per seed.
- ECHO sees and projects the new graph.
- A meaningful subset of new domain resources exists as real state, especially workers/skills, fixtures/tools, documents/revisions, material/consumables, and staging/WIP/support resources.
- All decision options mutate state in a way that corresponds to their text.
- Existing UI can display and answer the cards without breaking.

Better end state:

- Most or all domain concepts in `decision-implementation-audit.md` are represented by real objects.
- The final review/summary explains key decisions, follow-up outcomes, and ECHO's correct/incorrect long-term calls.
- The UI exposes enough context for resource constraints to make sense to the player.

## Suggested Work Plan

1. Read `README.md`, `decisions.md`, `decision-implementation-audit.md`, and the current decision/event/ECHO code.
2. Design the new domain state and named decision definition format.
3. Add or update dataclasses/enums for domain resources and decision definitions.
4. Extend scenario generation to create resource inventories and metadata needed by the decisions.
5. Replace generic campaign generation with a named graph generated from decision definitions.
6. Implement a typed, parameterized effect engine.
7. Port every decision in `decisions.md` into definitions and effects.
8. Implement probabilistic follow-up scheduling/unlocking.
9. Update ECHO static scoring and live projection for new effects and follow-up probabilities.
10. Update API payloads/UI only as needed to expose new cards and avoid crashes.
11. Add focused tests for graph edges, probabilistic follow-ups, literal shift effects, no-choice cards, shared follow-ups, and ECHO lookahead.
12. Run the app once locally to make sure a standard run loads and decisions can be answered.

## Testing Expectations

Add or update tests for:

- Every `Can unlock` target in `decisions.md` resolves to a real decision id.
- Follow-up probability is deterministic for a fixed seed.
- Shared follow-up cards can be unlocked from multiple prior choices.
- No-choice cards have exactly one inert choice but still apply their unavoidable effect once.
- Literal shift loss/gain effects change durations/downtime/blocking by the promised amount.
- ECHO picks a worse-immediate/better-later option when projection shows it is better.
- ECHO avoids a tempting immediate option when projection shows bad follow-up consequences.
- ECHO projection remains deterministic.
- Existing daily decision API and UI payloads still work.

## Non-Goals

- Do not keep the old decision catalog as the primary gameplay system.
- Do not implement the new decisions as text-only cards with generic `note` effects.
- Do not make probabilistic follow-ups unknowable to ECHO.
- Do not turn no-choice decisions into invisible background events.
- Do not rely only on abstract risk score when the decision text promises specific shift gains or losses.

## Final Deliverable

When done, report:

- Which domain resources were added.
- How named decisions are defined.
- How follow-up probabilities work.
- How ECHO knows and evaluates the graph.
- Any decisions that were approximated rather than fully modeled.
- What tests were run.
