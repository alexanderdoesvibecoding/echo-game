# Decision Implementation Audit

This is a feasibility pass for `decisions.md` against the current Python implementation. It does not propose code changes.

## Current Python Fit

The existing simulation already has useful primitives:

- Jobs can be blocked, paused, queued, rerouted, preempted, reprioritized, delayed, shortened, completed, or forced into rework.
- Workcenters can be available, busy, down, blocked, idle, or weather impacted.
- Events can target jobs, pieces, shops, workcenters, or capabilities.
- Existing event types cover material delay, missing material, machine down, quality rework, priority change, inspection delay, engineering hold, urgent job, weather, facility outage, supplier escalation, logistics backlog, tooling damage, crew shortage, rework spillover, certification audit, engineering data revision, unexpected job, and ECHO recommendation.
- Existing decision effects cover wait, resequence, protect critical work, expedite event, reroute, preempt, split capacity, defer, pull forward, ECHO recommendation, prioritize new job, and backlog new job.

The current model does not have first-class state for workers, fixtures, tools, gauges, documents, label printers, carts, consumables, cranes, software licenses, clean rooms, batches, or family/setup libraries. Those can be approximated with job delays and risk, but they are not real resources yet.

## ECHO Implications

ECHO can already do the important kind of lookahead: it deep-copies the current state, applies a choice, auto-answers future visible cards, advances the simulation, then compares projected completion, lateness, risk, idle time, reschedules, and score.

That means the "looks bad now, good later" idea is viable, but only if the future consequence is real in the Python state. Text such as `Can unlock Weather cleared early` has no effect until it becomes either:

- a real `future_unlock_card_ids` edge to a prebuilt card,
- a branch tag that reveals the card later,
- or a scheduled follow-on event/card created by the choice.

For ECHO to choose correctly, the follow-up card also needs meaningful effects. If the future card only changes `score_delta`, ECHO can prefer it in static scoring, but the live simulation will not show the operational gain. If the future card actually removes duration, releases blocked work, opens capacity, or prevents rework, ECHO's projection can learn it naturally.

Shared follow-ups are also viable. Multiple choices can point at the same `DecisionCard.id`; the current model already supports multiple choices unlocking the same future card.

## Legend

- Native: mostly implementable with existing event/effect primitives.
- Primitive: needs new card templates or small effect handlers, but can use current job/workcenter/risk/duration state.
- Domain: wants new domain state to feel real instead of being a disguised delay/risk modifier.
- Graph/ECHO: needs named follow-up edges and ECHO scoring/projection support.

## Base Decisions

| Decision | Fit | Notes |
| --- | --- | --- |
| Severe Weather | Native + Graph/ECHO | Weather events and workcenter disruption already exist. `Wait it out -> Weather cleared early` needs explicit future unlock. |
| Workstation Breakdown | Native + Graph/ECHO | Machine down and reroute are native. Setup mismatch follow-up needs a named edge and probably a setup penalty effect. |
| Materials Have Not Arrived | Native + Graph/ECHO | Missing/delayed material exists. Using another job's material needs donor-job selection; shared follow-ups are feasible. |
| ECHO Recommendation (Rare) | Native-ish + Graph/ECHO | ECHO recommendation exists, but current effect is probabilistic and not "all subjobs lose 1-2 shifts." The slack-pocket payoff needs explicit graph/effect work. |
| Worker Took the Day Off | Domain + Graph/ECHO | No worker model exists. Can fake with job delay/rework, but replacements, worker return, and qualifications need worker/crew state. |
| Calibration drift | Domain + Graph/ECHO | Could fake via inspection/metrology job delays. Real drift/quarantine/release wants measurement-domain state. |
| Traveler mismatch | Domain + Graph/ECHO | Current engineering hold/data revision can approximate. Route/traveler versions are not modeled. |
| Shared fixture claim | Domain + Graph/ECHO | Candidate workcenters exist, but fixtures are not resource objects. Real implementation needs fixture availability/certification state. |
| Changeover drag | Primitive + Graph/ECHO | Setup time exists on jobs. Family-level setup persistence does not, so "family run" needs new grouping or tags. |
| Batch window opens | Domain + Graph/ECHO | Pull-forward is native. True batch/cure-slot sharing needs batch/window state. |
| Consumables short | Domain + Graph/ECHO | Can approximate as capability/shop slowdown. Real consumable inventory and donor shop stock do not exist. |
| Label printer outage | Domain + Graph/ECHO | Completion gating can be faked by blocked jobs. Documentation/label queues are not modeled. |
| Shop air pressure dip | Primitive + Graph/ECHO | Shop/workcenter slowdown can be done with blocked/down/efficiency-like effects. Clamp marks are quality follow-up. |
| Coolant change due | Domain + Graph/ECHO | Can fake with one-shift station downtime and quality risk. Coolant condition is not modeled. |
| FOD sweep | Primitive + Graph/ECHO | Shop work stoppage is easy. Non-choice cards may need UI/API handling if truly automatic. |
| Handoff window missed | Primitive | Cross-shop dependencies and transport exist enough to approximate. Receiving-slot reservation is not first-class. |
| Crane reservation conflict | Domain + Graph/ECHO | Heavy-move/crane resources do not exist. Can approximate with transport delay/blocking. |
| Nesting opportunity | Domain | Setup savings can be applied to jobs, but compatible nesting groups and locked routing need new metadata. |
| Old setup sheet | Domain + Graph/ECHO | Setup savings are easy; setup sheet validation/library state is new. |
| WIP crowding | Primitive + Graph/ECHO | Queue pressure and idle time exist. WIP floor-space state would make it richer but is not mandatory. |
| Cleanliness breach | Domain + Graph/ECHO | Can block a shop/area. Clean-room/covered-work acceptance wants domain state. |
| Software seat conflict | Domain + Graph/ECHO | No software license resource exists. Can approximate as programming-capability bottleneck. |
| Network folder offline | Domain + Graph/ECHO | Can approximate as engineering hold or document risk. File/version state is new. |
| Gauge dispute | Domain + Graph/ECHO | Inspection/metrology capabilities exist. Gauge identity/method acceptance is new. |
| Count variance | Domain + Graph/ECHO | Material shortage exists. Inventory counts/donor stock are new. |
| Burr cleanup | Primitive + Graph/ECHO | Add cleanup duration or downstream rework using existing job fields. |
| Cure clock | Primitive + Graph/ECHO | Dependency delay can be implemented now. Cure physics/history would be new. |
| Vacuum leak chase | Primitive + Graph/ECHO | Setup delay/rework risk fits current primitives. Leak traces are not modeled. |
| Tool crib hold | Domain + Graph/ECHO | No calibrated tool inventory exists. Can fake as job block or station delay. |
| Fixture soak | Domain + Graph/ECHO | Similar to fixture state; can approximate with setup delay. |
| Shift overlap bonus | Primitive | Speedups, handoff relief, and setup prep can be done with duration reductions/pull-forward. |
| Waste container full | Domain + Graph/ECHO | Can block/slown shop. Waste containers/carts/lane occupancy are new. |
| Preapproved package | Domain + Graph/ECHO | Documentation speedups can reduce closeout duration, but packages are new. |
| Expired stickers | Domain + Graph/ECHO | Tool calibration/documentation state is new. Can fake with audit/rework risk. |
| Vendor rep on site | Primitive | One-shot speedup/risk reduction can be implemented with current effects. Vendor availability state is optional. |
| Training run | Domain + Graph/ECHO | Qualification/future staffing needs worker/skill state. Can fake as future capacity/speedup. |
| Off-peak utility slot | Domain | Extra capacity windows are not modeled. Can fake with duration reduction or temporary extra workcenter availability. |
| Floor walk insight | Primitive + Graph/ECHO | Process improvement can be duration reduction for matching jobs; matching/family metadata is the missing bit. |
| Wash tank chemistry | Domain + Graph/ECHO | Can block prep/coating jobs. Tank chemistry state is new. |
| Rack shortage | Domain + Graph/ECHO | Can fake as workcenter tie-up/blocking. Racks/carts/staging state is new. |
| Safety drill | Native-ish | Global one-shift loss is easy. Needs support for automatic/no-choice cards if not presented as a choice. |
| Access badge failure | Domain | Secure-area concept does not exist. Can approximate by shop block/open-area pull-forward. |
| Reference sample missing | Domain + Graph/ECHO | Can block inspection/fit work. Samples/master artifacts are new. |
| Staging map reset | Domain + Graph/ECHO | Queue reshuffle and transport delay fit current primitives. Staging map/floor location state is new. |

## Follow-Up Decisions

| Decision | Fit | Notes |
| --- | --- | --- |
| Narrow drift found | Domain + Graph/ECHO | Requires quarantine/release semantics to be real. Could approximate by unblocking/shortening inspection jobs. |
| Route shortcut approved | Primitive + Graph/ECHO | Can reduce duration on selected jobs. Needs route/family matching for broad application. |
| Spare fixture certified | Domain + Graph/ECHO | Needs fixture/certification state to be more than a generic capacity speedup. |
| Family run unlocked | Domain + Graph/ECHO | Needs job-family/setup persistence to be real. |
| Bulk lot released | Domain + Graph/ECHO | Current material blocks can be released, but lot/batch paperwork is new. |
| Clean packet release | Domain + Graph/ECHO | Needs completion/document backlog state or a clean closeout approximation. |
| Finish window restored | Primitive + Graph/ECHO | Can reduce inspection/finish durations for targeted jobs. Process-window state is optional. |
| Combined lift | Domain + Graph/ECHO | Needs crane/heavy-move grouping for realism; can approximate by reducing transport delay. |
| Setup library update | Domain + Graph/ECHO | Needs reusable setup library/family metadata. Can approximate with duration reductions. |
| Aisles cleared | Primitive + Graph/ECHO | Queue, transport, and blocked-station relief can be done with current fields. |
| Clean room cleared | Domain + Graph/ECHO | Needs controlled-area release state; can approximate by unblocking jobs. |
| Program template saved | Domain + Graph/ECHO | Needs program/template/family state. Can approximate by reducing programming-like job durations. |
| Gauge method locked | Domain + Graph/ECHO | Needs method acceptance state; can approximate by reducing inspection/metrology duration. |
| Operator qualified | Domain + Graph/ECHO | Needs worker/skill state for lasting capacity. Can fake by lowering future crew shortage risk. |
| Process tweak validated | Primitive + Graph/ECHO | Can reduce duration on matched jobs if matching logic exists. |
| Rack recovery sprint | Domain + Graph/ECHO | Needs rack/staging state for real effect; can approximate by freeing blocked jobs/workcenters. |
| Batch data accepted | Domain + Graph/ECHO | Needs batch closeout state; can approximate as completion/inspection speedup. |
| Clamp marks found | Primitive + Graph/ECHO | Quality rework/duration/risk support exists. |
| Covered work reopened | Domain + Graph/ECHO | Needs covered-work/acceptance state; can approximate with inspection delay/rework. |
| Wrong revision loaded | Domain + Graph/ECHO | Engineering data revision exists; file revision state is new. |
| Phantom stock confirmed | Domain + Graph/ECHO | Missing material/logistics backlog exists; donor-stock logic is new. |
| Fit check failed | Primitive + Graph/ECHO | Quality rework/delay fits current model. |
| Cure failure found | Primitive + Graph/ECHO | Rework and added duration fit current model. |
| Vacuum trace failed | Primitive + Graph/ECHO | Rework/audit risk can be modeled with existing event types. |
| Waste lane blocked | Domain + Graph/ECHO | Can block shop/logistics; lane/cart state is new. |
| Sticker audit hit | Domain + Graph/ECHO | Certification audit exists; tool-sticker traceability is new. |
| Weather cleared early | Native + Graph/ECHO | Can shorten weather event/unblock workcenters. Needs explicit follow-up edge. |
| Setup mismatch found | Primitive + Graph/ECHO | Can add setup/rework shifts after reroute. |
| ECHO slack pocket found | Native-ish + Graph/ECHO | Current ECHO effect can protect/pull/shorten jobs, but this named payoff needs explicit follow-up effect. |
| Replacement handoff check | Domain + Graph/ECHO | Needs worker handoff state or can be faked by rework risk. |
| Returning worker shortcut | Domain + Graph/ECHO | Needs worker identity/known setup state; can approximate by duration reduction. |

## Scale Estimate

Smallest credible implementation:

- Keep the current core model.
- Add named card factories for a subset of decisions.
- Map most options to existing effects plus new effect parameters such as `duration_delta`, `block_jobs`, `release_jobs`, `reduce_event_duration`, and `schedule_named_followup`.
- Encode the follow-up graph with explicit card ids.
- Teach ECHO static scoring about the new effect names.

This would make maybe 40-50 of the cards playable enough, but some would be flavor over generic delay/risk mechanics.

More satisfying implementation:

- Add first-class resource state for at least workers/skills, fixtures/tools, documents/revisions, material/consumable stock, and staging/WIP constraints.
- Add selector helpers for "matching family", "same capability", "same route", "donor job", "controlled area", "tool-dependent work", and "finished-but-not-closed work".
- Replace the generic branch-tag campaign graph with a named decision graph where `Can unlock X` is an actual edge.
- Add deterministic branch outcomes so ECHO can know future outcomes while the player only sees them later.

That is sweeping, but it is feasible. The current architecture is not hostile to it: `Event.effects` is flexible, `DecisionChoice.future_unlock_card_ids` already exists, and ECHO already projects long-term outcomes. The main missing piece is domain state, not the concept of forecasting.

## Highest-Risk Design Questions

1. Do we want domain resources to be real objects, or just modifiers on jobs/workcenters?
2. Should every decision have deterministic follow-ups, or should some follow-ups be seeded chance?
3. How much of the future graph should ECHO know? Current ECHO effectively knows the graph and can simulate it.
4. Should no-choice cards appear in the UI, or should they be automatic events with summary notes?
5. Do we want "gain 5 shifts" to literally subtract remaining duration, or to emerge through unblocking/rerouting/extra capacity?

My recommendation is to first implement a thin named-decision graph and a small set of generic parameterized effects. Then add domain state only where the gameplay proves it needs it.
