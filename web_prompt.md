You are working in my current ECHO Game repo.

Goal:
Convert the decision system from separate daily decision webs into a literal prebuilt campaign-wide decision tree, so that choices made early in the game can directly determine which decision cards appear many days later. The design goal is high replay divergence: it should be next to impossible for two players to get the exact same final score unless they make the same or nearly identical decision path.

Important context:
Right now, the code appears to generate separate daily decision webs. Each day has its own root decision card, and Day 1 choices do not directly route the player into different Day 5 decision paths. I want to change that.

Do not just add random score noise. The score uniqueness should come from the player’s full decision path, branch consequences, state changes, and deterministic path-specific modifiers.

Please inspect the repo first, especially these files if they exist:

- echo_adventure/decisions.py
- echo_adventure/scenario_generator.py
- echo_adventure/models.py
- echo_adventure/ui/server.py
- echo_adventure/ui/view.py
- tests related to decisions, scoring, scenario generation, or determinism

Main objective:
Replace the current “daily independent decision webs” architecture with a prebuilt campaign-wide decision tree or campaign-wide decision DAG generated at scenario creation.

Definition of success:
At scenario creation, the game should create one overall campaign decision structure. The player starts at a Day 1 campaign root. Each choice should be able to point to future nodes, including nodes several days later. A Day 1 choice should be capable of changing the Day 5 cards the player sees.

The campaign graph may be a tree or a DAG internally, but behaviorally it must feel like a campaign-wide branching tree. Future decision cards must be assigned during scenario generation, not generated fresh at the start of each day.

High-level behavior:
The player should no longer simply get:

Day 1 daily web
Day 2 daily web
Day 3 daily web
Day 4 daily web
Day 5 daily web

Instead, the player should get something more like:

Day 1 choice A -> one possible Day 2/3/5 future route
Day 1 choice B -> a different possible Day 2/3/5 future route
Day 1 choice C -> another possible Day 2/3/5 future route

Choices later in the game should continue branching the campaign route.

Requirements:

1. Campaign-wide decision graph

Create a campaign-wide graph generated at scenario creation.

It should have one campaign root or a small set of campaign roots, starting on Day 1.

Each decision card should be able to contain or reference:

- card id
- day
- title
- description/body
- choices
- parent card id, if applicable
- parent choice id, if applicable
- child card ids for immediate follow-up questions
- future unlocks or future branch targets
- branch tags / branch keys / required flags / excluded flags, if helpful
- deterministic branch scoring metadata, if helpful

Keep compatibility with existing fields where possible, but add new model fields if necessary.

2. Early choices must affect later days

A Day 1 choice must be able to alter which decision cards appear on later days, including at least Day 5 or later.

Please add at least one deterministic test or test fixture proving this:

- Start a scenario with a fixed seed.
- Choose option A on a Day 1 decision.
- Advance to Day 5.
- Record active Day 5 decision card ids/titles.
- Restart the same seed.
- Choose option B on the same Day 1 decision.
- Advance to Day 5.
- Assert the Day 5 decision cards are different.

3. Prebuilt, not runtime-generated

The full campaign decision graph should be generated during scenario/scenario-state creation.

After scenario creation, the system should select from the already-built graph based on the player’s branch path, decision history, branch flags, and current day.

Do not solve this by generating Day 5 cards at the start of Day 5. The future cards should already exist in the campaign graph.

It is fine if active-card filtering happens at runtime, but the card objects and branch relationships should already be created.

4. Branch state projection

During campaign graph generation, choices should project likely future consequences.

For example:

- choosing to ignore a supplier risk on Day 1 can create a later supplier-crisis decision
- choosing to protect critical-path work can create a later resource-strain decision
- choosing to follow ECHO can create later trust/reliance/automation-related decisions
- choosing to reroute work can create later schedule or quality tradeoffs
- choosing to wait can create later escalation cards

This projection does not have to perfectly simulate the whole game state for every branch, but each branch should carry enough metadata to make future decision routes meaningfully different.

Implement this with branch tags/flags if that is cleaner.

Example branch tags:

- supplier_risk_ignored
- supplier_risk_mitigated
- critical_path_protected
- crew_overloaded
- echo_trusted
- echo_overridden
- quality_debt_created
- schedule_debt_created
- cost_debt_created
- risk_debt_created

Later cards can require or prefer these tags.

5. Active decision card selection

Update the logic that determines today’s active decision cards.

Instead of looking only at daily roots, it should use:

- current day
- player decision history
- active campaign branch path
- branch tags / flags
- unlocked future nodes
- already completed card ids
- current simulation state, if needed

The player should only see cards that belong to their current campaign route.

Avoid showing cards from branches they did not choose.

6. Scoring uniqueness

Update scoring so that two different decision paths are extremely unlikely to produce the exact same final score.

Do not add pure random noise.

Use deterministic, explainable score differentiation based on decision path.

Possible implementation:

- Add a decision path signature based on the ordered sequence of card ids and choice ids.
- Add small deterministic score deltas to each choice.
- Add branch-specific modifiers that affect project score, cost score, schedule score, quality score, safety/risk score, or ECHO comparison.
- Add a visible score breakdown item such as “Decision Path Differentiator” or “Strategic Path Signature”.
- Use enough score precision that ties are rare, such as one or two decimals if the existing UI can support it.
- The same seed and same exact decisions must always produce the same score.
- Different decisions should usually produce different scores, even when the broad outcome looks similar.

Important:
The score differentiator should be deterministic and tied to the decision path. Do not use nondeterministic randomness at final scoring time.

7. Determinism

Preserve deterministic behavior.

Same scenario seed + same decisions should produce:

- same campaign graph
- same active cards each day
- same simulation results
- same final score
- same ECHO comparison results

Different decision paths should produce different active future cards and usually different scores.

Add tests for this.

8. ECHO automated path

If the game has an automated ECHO player or benchmark state, update it to use the same campaign-wide graph system.

ECHO should traverse the campaign graph using its chosen decisions, not the old independent daily web logic.

Make sure the player and ECHO can diverge into different campaign branches.

9. UI compatibility

Update the UI/server layer so the decision panel still works.

The player should still be able to:

- see today’s active decision card/cards
- choose an option
- apply the choice
- advance days
- see consequences
- finish the game
- see final score

Do not break the existing UI layout unless required.

If useful, add small UI text that indicates campaign branching, such as:

“Campaign branch affected by earlier decisions”

But keep the UI simple.

10. Backward compatibility / cleanup

Remove or deprecate old assumptions that each day has a fully independent decision root.

If fields like daily_decision_roots or daily_decision_counts are still useful for indexing, they can remain, but they should now be derived from the campaign-wide graph instead of representing separate independent daily webs.

Avoid breaking save/load if the project has persistence. If save files exist, handle missing new fields gracefully.

11. Practical graph size

A literal full tree can explode exponentially. Implement a practical bounded campaign graph.

Use clear config constants for limits, such as:

- max campaign nodes
- max branch depth
- max future unlocks per choice
- max active decision cards per day
- max branch variants per day

The graph should still provide meaningful campaign-wide branching, but it should not create millions of nodes.

Add comments explaining how graph size is controlled.

Behaviorally, the important thing is that future nodes are prebuilt and branch-dependent.

12. Tests to add or update

Please add or update tests for:

A. Campaign graph exists at scenario creation

Assert the scenario has a campaign-wide decision graph before gameplay begins.

B. Day 1 affects Day 5

With the same seed, two different Day 1 choices should lead to different Day 5 active decision cards.

C. Determinism

Same seed and same choices produce identical campaign graph, card order, final state, and score.

D. Score diversity

Run a deterministic simulation of many different valid decision paths, for example 100 or 200 paths.

Assert that the number of unique final scores is very high, for example at least 95% unique scores.

Do not make this test flaky. Use deterministic seeded path selection.

E. No invalid branch leakage

Cards from an unchosen branch should not appear for the player.

F. Existing tests still pass

Run the current test suite and fix regressions.

13. Code quality

Please keep the implementation clean and readable.

Prefer small helper functions over one giant function.

Use clear names, for example:

- generate_campaign_decision_graph
- CampaignDecisionGraph
- campaign_root_card_id
- campaign_branch_tags
- decision_path_signature
- active_campaign_decision_cards
- unlock_future_decision_nodes
- project_choice_branch_state
- apply_campaign_choice
- score_decision_path_differentiator

Use dataclasses or existing model patterns consistently with the repo.

14. Acceptance criteria

The task is complete when:

- The game no longer relies on independent daily decision webs.
- A campaign-wide decision graph is generated at scenario creation.
- A Day 1 choice can change Day 5 decision cards.
- Future branch cards are prebuilt, not created at the future day.
- Player and ECHO can diverge onto different campaign paths.
- Different decision paths produce highly unique final scores.
- Same seed plus same choices remains deterministic.
- The UI still works.
- Tests pass.
- Python compiles successfully.

Please implement the changes, then summarize:

- what files changed
- how the new campaign-wide graph works
- how early decisions affect later cards
- how score uniqueness is achieved
- what tests were added
- any limits or tradeoffs in the implementation
