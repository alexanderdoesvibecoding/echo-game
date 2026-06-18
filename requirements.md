Terminal-Based Scheduling Strategy Game Requirements
1. Project Summary
Build a terminal-based “choose your own adventure” scheduling strategy game. The game should simulate a complex fictional shipyard-like manufacturing environment where a player acts as a human scheduler trying to complete a large, interdependent set of manufacturing work before a fixed deadline.
The hidden purpose of the game is to demonstrate that an automated scheduling engine, called ECHO, can outperform manual human scheduling when responding to disruptions, bottlenecks, shifting priorities, missing materials, downtime, and other real-world scheduling problems.
During gameplay, the player should not see ECHO recommendations, ECHO decisions, or direct comparisons against ECHO. ECHO should silently run in the background against the same generated scenario and the same disruptive events. At the end of the game, the application should reveal the comparison and explain how ECHO performed better.
This is version 1. The game should be terminal-based for now, but the codebase must be structured so it can later be converted into a richer desktop, web, or graphical application without rewriting the simulation engine.

2. Target User Experience
The player is responsible for scheduling a complex “puzzle” made of 30 separate puzzle pieces. Each puzzle piece requires multiple subjobs to be completed across specialized manufacturing shops. Once all required subjobs for a puzzle piece are finished, that piece becomes available for final integration. Once all 30 pieces are complete, they combine into one finished item.
The player has 30 in-game days to complete the final item.
Each day is divided into three shifts.
The game loop should feel like this:
The player starts a new run.
A full-scale procedurally generated manufacturing scenario is created from a random seed.
The player sees the current schedule board, shop status, risk information, bottlenecks, and open work.
Each day, the player is presented with the top 3 most important scheduling decisions.
Each decision gives the player 2–4 multiple-choice options.
The player chooses how to adapt the schedule.
The simulation advances through three shifts.
Disruptions may occur.
Jobs complete, get delayed, move through dependencies, or become blocked.
The player receives an end-of-day summary.
This repeats until the deadline is reached or all work is complete.
At the end, the game reveals how the hidden automated scheduler performed on the same scenario.
The terminal experience should use tables, panels, progress indicators, and color if possible. A simple wall of plain text is not sufficient unless the terminal does not support rich output.
Use a CLI library such as rich to make the interface readable and visually useful.

3. Core Product Goals
The application must:
Simulate a large, realistic scheduling environment.
Let the player make high-impact scheduling decisions without requiring them to manually assign hundreds of jobs.
Include random disruptions that force rescheduling.
Track operational metrics throughout the run.
Run a hidden automated scheduler in parallel against the same scenario.
Reveal at the end that the automated scheduler performed better.
Be cleanly architected so the simulation engine is independent from the terminal UI.
Be generated procedurally from a seed.
Support replayability by producing different scenarios and events across playthroughs.
Use fictionalized terminology and data.

4. Non-Goals for Version 1
Do not build these in version 1:
No graphical UI.
No web app.
No save/load feature.
No quit-and-resume feature.
No tutorial or onboarding sequence.
No automated test suite required for v1.
No real-world shipyard data.
No real facility names.
No real operational scheduling details that could imply actual shipyard processes.
No daily ECHO recommendations.
No daily player-vs-ECHO comparison.
No labor shortage mechanic.
No multiplayer.
No online features.
No database.
No sample terminal screens in documentation.
No static hand-authored scenario required for v1.
The application may include clean seams for these future features, but they should not be implemented unless they are needed to support the current playable CLI.

5. Technical Stack
Use Python unless there is a strong reason not to.
Recommended baseline:
Python 3.11+
rich for terminal rendering
Standard library dataclasses or pydantic-style models if preferred
Standard library argparse or a lightweight CLI entry point
No database
No web services
No network calls
Local execution only
The project should run from an empty repository.
The game should be startable with one of the following commands:
python -m echo_adventure
or:
python main.py
Include whichever entry point is cleaner for the project layout.
The application should support at least these optional CLI flags:
--seed <int>
--no-color
--debug
Behavior:
--seed should reproduce the same scenario and event sequence.
If no seed is provided, generate a random seed and display it at the start and end of the run.
--no-color should disable colored output where practical.
--debug may show extra internal information for development, but it must not be required for gameplay.

6. Fictionalization Requirements
The game is inspired by complex shipyard scheduling, but it must be fictionalized.
Requirements:
Do not use real shipyard names.
Do not use real vessel names.
Do not use real facility names.
Do not use real production data.
Avoid language that implies the simulation represents an actual classified, sensitive, or operational environment.
The generated shops, workcenters, jobs, and materials should use fictional or generic names.
ECHO is a fictional automated scheduling engine for the purpose of this game.
Use terms such as:
Advanced manufacturing yard
Specialized shops
Workcenters
Puzzle pieces
Final integration
Complex production schedule
Automated scheduling engine
Avoid using real-world program names or sensitive terminology.

7. Game Setting
The game takes place in a fictional advanced manufacturing yard.
The yard is responsible for completing a complex 30-piece project. Each puzzle piece is made up of several subjobs that must be completed by specialized shops. These subjobs have dependencies, require specific workcenter capabilities, and may be disrupted by real-world problems.
The player’s goal is to complete the entire final item by the end of Day 30.
The game should create pressure by making the schedule tight but feasible. The hidden automated scheduler should be able to complete the work by the deadline under normal generated conditions.

8. Scenario Scale Requirements
Version 1 must simulate the full intended scale.
Each generated scenario must include:
30 puzzle pieces
10 specialized shops
Each shop has between 20 and 50 workcenters
Each puzzle piece has between 5 and 15 subjobs
Each subjob belongs to one primary shop
Subjobs may have alternate capable workcenters
Subjobs may span multiple shops per puzzle piece
Not every puzzle piece must use every shop
Some pieces may be heavily concentrated in one shop
Some pieces may be distributed across several shops
Dependencies must exist between subjobs
Once all subjobs for a puzzle piece are complete, that piece is ready for integration
Once all 30 pieces are ready, a final integration step combines them into one finished item
The generated scenario should include enough complexity that a human player cannot trivially optimize it by inspection.
The simulation should remain performant in a terminal. Advancing one day should feel quick.

9. Time Model
The game uses discrete time.
One game day contains three shifts.
The total deadline is 30 days.
Therefore, the main deadline is 90 shifts.
The simulation may display progress by day and shift.
Job durations should be measured in shifts.
End-of-day summaries occur after every three shifts.
Shift names can be generic:
Shift 1
Shift 2
Shift 3
Avoid overcomplicating shift operations. The time model should support future expansion but stay understandable for v1.

10. Workcenter Model
A workcenter is a machine, station, bay, cell, bench, inspection point, or other production resource.
Rules:
A workcenter can process only one job at a time.
A job must be assigned to a capable workcenter.
Workcenters have capabilities.
Not every workcenter can process every job.
Some jobs may have multiple possible workcenters.
Alternate workcenters may be slower or less efficient.
Workcenters can go down due to events.
Workcenters may become blocked by engineering holds, inspection delays, quality issues, or facility events.
A workcenter may have a queue of jobs.
A workcenter’s queue should be visible to the player through inspection screens.
Each workcenter should have at least:
Unique ID
Display name
Shop ID
Capability tags
Efficiency factor
Current status
Current assigned job, if any
Queue
Downtime remaining, if any
Possible workcenter statuses:
Available
Busy
Down
Blocked
Idle
Waiting on material
Waiting on inspection
Waiting on engineering
Weather impacted

11. Shop Model
A shop represents a specialized production area.
Each shop should have:
Unique ID
Display name
20–50 workcenters
Shop capability categories
Active jobs
Queued jobs
Blocked jobs
Completed jobs
Utilization metric
Idle time metric
Bottleneck indicator
Shop names should be fictional/generic. Example categories may include fabrication, machining, finishing, inspection, assembly, integration, coating, precision processing, calibration, or tooling. Do not use real-world names.
The schedule board should display shop-level information first, with optional drill-down into workcenter-level queues.

12. Puzzle Piece Model
The project consists of 30 puzzle pieces.
Each puzzle piece should have:
Unique ID
Display name
5–15 subjobs
Current status
Percent complete
Blocking dependencies
Estimated completion shift
Risk score
Whether it is ready for integration
Possible puzzle piece statuses:
Not Started
In Progress
Blocked
At Risk
Complete
Ready for Integration
Integrated
A puzzle piece is complete only when all of its subjobs are complete.
A puzzle piece is ready for integration when all subjobs are complete and any required inspection or final acceptance job is complete.

13. Job / Subjob Model
Each puzzle piece has 5–15 subjobs.
Each job should have:
Unique ID
Parent puzzle piece ID
Shop ID
Required capability
Candidate workcenters
Assigned workcenter, if scheduled
Base duration in shifts
Adjusted duration after workcenter efficiency
Setup time
Queue time
Transport delay
Dependencies
Status
Priority
Due shift or target milestone
Risk score
Cost rate or cost weight
Whether it is on the critical path
Whether it is blocked
Block reason, if any
Possible job statuses:
Not Ready
Ready
Queued
Scheduled
Running
Paused
Blocked
Complete
Late
Rework Required
Cancelled / Superseded
A job can start only when:
All dependencies are complete.
Its required workcenter capability is available.
Its assigned workcenter is available.
It is not blocked by an active event.
Any required setup, queue, or transport delay has been satisfied.

14. Dependencies
The simulation must include dependency logic.
Requirements:
Dependencies must form a directed acyclic graph.
Jobs may depend on one or more previous jobs.
A job cannot start until all dependencies are complete.
A puzzle piece cannot complete until all of its jobs complete.
Final integration cannot complete until all 30 puzzle pieces are complete.
The schedule board must help the player see blocked jobs and critical dependencies.
Critical path analysis should be available to the player.
Dependency violations must not be allowed.
The generator must ensure dependencies are valid and acyclic.

15. Setup Time, Queue Time, and Transport Delay
The simulation should include simplified versions of setup time, queue time, and transport delay.
These should be measured in shifts.
Rules:
A job may require setup before processing.
Queue time emerges naturally when jobs wait for busy workcenters.
Transport delay may occur when a puzzle piece moves between shops.
Transport delay should be simple, not a major logistics simulation.
Alternate workcenters may add setup or duration penalties.
Preempting a running job may add a small disruption penalty.
Preemption penalty:
Preemption is technically allowed.
The impact should be less than one day.
Model the penalty as less than three shifts.
A reasonable default is one shift or less.
The penalty should affect cost, reschedule count, risk, or queue delay.

16. Player Role
The player is the manual scheduler.
The player should not be expected to manually assign every job across hundreds of workcenters. Instead, the game should automatically maintain a working schedule and surface the most important decisions.
The player’s decisions should affect:
Which jobs are prioritized
Whether to reroute work to alternate workcenters
Whether to wait for repairs or move work
Whether to preempt a lower-priority job
Whether to resequence work around missing materials
Whether to absorb cost to reduce schedule risk
Whether to accept disruption now to protect later critical-path work
Whether to respond aggressively or conservatively to warnings
The player should feel like they are making strategic scheduling decisions, not editing a spreadsheet.

17. Daily Game Loop
Each in-game day should follow this structure:
17.1 Start-of-Day Phase
Display:
Current day number
Project status
Pieces completed
Jobs completed
Jobs late
Active disruptions
Known warnings
Shop utilization summary
Major bottlenecks
Critical path summary
Schedule risk score
Current projected completion day/shift
Do not show ECHO.
17.2 Schedule Board Phase
Display a large but readable schedule board.
The default board should include shop-level information:
Shop name
Active jobs
Queued jobs
Blocked jobs
Idle workcenters
Utilization
Bottleneck status
At-risk jobs
Next major dependency unlock
The player should be able to inspect additional views before making decisions.
Required inspection views:
Shop status
Workcenter queues
Puzzle piece progress
Critical path
Risk register
Do not include an ECHO recommendation view.
17.3 Decision Phase
Each day, present the top 3 high-impact scheduling decisions.
Each decision should have:
A short narrative description
The affected shop, workcenter, job, or puzzle piece
2–4 possible choices
A clear tradeoff for each choice
Immediate expected consequence
Possible longer-term consequence
The choices should be meaningful. Avoid fake choices where one answer is obviously always correct.
However, the automated scheduler should still be designed to select consistently strong options based on its heuristic.
17.4 Hidden Automated Scheduler Phase
After the player makes decisions for the day, the hidden automated scheduler should independently make its own scheduling decisions for its own copy of the scenario state.
Rules:
The automated scheduler sees the same scenario.
The automated scheduler receives the same events.
The automated scheduler receives the same advance warnings.
The automated scheduler does not reveal its decisions to the player.
The automated scheduler does not produce daily recommendations.
The automated scheduler is not a character or personality.
The automated scheduler should run silently.
The automated scheduler should use a strong heuristic.
The automated scheduler should not make obviously poor decisions.
The player should not know the exact automated results until the final reveal.
17.5 Shift Simulation Phase
Advance the simulation through three shifts.
For each shift:
Start ready jobs when workcenters are available.
Continue running jobs.
Complete jobs whose remaining duration reaches zero.
Unlock dependent jobs.
Apply active disruptions.
Trigger any scheduled random events.
Update queues.
Update utilization.
Update idle time.
Update cost.
Update risk.
The player does not need to approve every shift transition.
17.6 End-of-Day Summary Phase
Display an end-of-day summary for the player’s schedule only.
Include:
Jobs completed today
Jobs remaining
Pieces completed
Pieces still in progress
Jobs late
New blockers
Reschedules performed
Cost impact
Utilization
Idle time
Schedule risk
Current projected completion day/shift
Notable consequences from today’s decisions
Warnings for upcoming days, where applicable
Do not compare against ECHO here.

18. Decision Card Requirements
The game should generate decision cards from the current state.
Each day should include exactly 3 decision cards unless:
The game has already ended.
There are fewer than 3 meaningful decisions available, in which case fill with strategic prioritization decisions.
A severe event requires one or more urgent response cards.
Decision cards should be selected from the highest-impact issues based on:
Critical path impact
Bottleneck severity
Number of dependent jobs affected
Proximity to deadline
Schedule risk
Workcenter utilization
Job priority
Event severity
Cost impact
Probability of cascading delay
Decision card types should include:
Machine or workcenter down
Missing or delayed material
Quality rework
Priority change
Inspection delay
Engineering hold
Urgent new job inserted
Weather or facility outage
Bottleneck overload
Critical path slippage
Workcenter idle despite available work
Alternate routing opportunity
Queue congestion
Final integration risk
Each card must have 2–4 choices.
Example choice categories:
Wait
Reroute
Preempt
Resequence
Expedite
Defer
Split capacity
Protect critical path
Prioritize urgent work
Accept cost increase
Accept schedule risk
Reduce disruption now
Reduce risk later
Do not hardcode every decision as static text. Use structured decision generation where possible.

19. Random Event System
The game must include randomly generated disruptions.
The event sequence should be generated from the scenario seed or from a derived event seed. The same event sequence must be applied to both the player simulation and the hidden automated scheduler simulation.
Required event types:
Missing material
Delayed material
Machine or workcenter down
Quality rework
Priority change
Inspection delay
Engineering hold
Urgent new job inserted
Weather event
Facility outage
Do not include labor shortage events.
Events should have:
Event ID
Event type
Target shop, workcenter, job, puzzle piece, or capability
Start day/shift
Duration
Severity
Whether advance warning exists
Warning day/shift, if applicable
Player-facing description
Mechanical effects
Resolution conditions
Some events should be known in advance.
Advance-warning events must include at least:
Weather events
Delayed materials
The player should be able to respond to warnings before the disruption fully occurs.
Event behavior should differ across playthroughs unless the same seed is reused.

20. Event Application Rules
Events must be fair between the player and hidden automated scheduler.
Rules:
Generate the event timeline once.
Apply the same event timeline to the player state and automated scheduler state.
Events should target stable object IDs where possible.
If an event targets a job that is in a different state between the player and automated scheduler, apply the event logically to that job in each state.
If an event targets a workcenter, that workcenter should be impacted in both simulations.
If an event targets a capability, all relevant capable workcenters may be impacted.
If an event targets a shop, the same shop should be impacted in both simulations.
Do not allow the automated scheduler to avoid an event through hidden knowledge unless the player also received an advance warning.
The automated scheduler may respond better to warnings because of better scheduling logic.
Events should create immediate consequences and accumulated consequences.

21. Specific Event Behaviors
21.1 Missing or Delayed Material
Effects:
Blocks one or more jobs.
May delay dependent jobs.
May increase schedule risk.
May force resequencing.
Possible player responses:
Wait for material.
Resequence unrelated ready work.
Move shop capacity to another puzzle piece.
Expedite material at additional cost.
Protect downstream critical work by starting alternate dependencies.
Advance warning:
Delayed material should often produce a warning before the actual delay.
Missing material may sometimes be discovered without warning.
21.2 Machine or Workcenter Down
Effects:
Workcenter cannot process jobs.
Running job pauses or must be rerouted.
Queue may grow.
Critical path may shift.
Possible player responses:
Wait for repairs.
Move job to alternate capable workcenter.
Kick a current job off an alternate machine to make room.
Resequence shop work until repair is complete.
Preemption should cause a small penalty but less than one day.
21.3 Quality Rework
Effects:
A completed or in-progress job may require additional work.
A downstream dependency may be blocked.
Cost and schedule risk increase.
Possible player responses:
Rework immediately.
Defer rework and continue other jobs.
Assign rework to fastest capable workcenter.
Assign rework to less disruptive workcenter.
21.4 Priority Change
Effects:
A job, piece, or urgent task becomes more important.
Existing queue order may become suboptimal.
Lower-priority work may be delayed.
Possible player responses:
Fully accept the priority change.
Partially absorb it while protecting current critical path.
Delay lower-risk work.
Split available capacity.
21.5 Inspection Delay
Effects:
Jobs awaiting inspection cannot unlock downstream work.
Workcenter queues may idle because dependencies remain blocked.
Risk increases for affected pieces.
Possible player responses:
Wait.
Resequence other ready jobs.
Move inspection to alternate capable workcenter if available.
Prioritize jobs that do not require the delayed inspection path.
21.6 Engineering Hold
Effects:
A job, group of jobs, capability, or piece is blocked.
Dependent work cannot start.
Other ready work should be resequenced.
Possible player responses:
Hold affected work.
Shift capacity to unaffected critical-path jobs.
Expedite review at cost.
Replan downstream sequence.
21.7 Urgent New Job Inserted
Effects:
Adds a new required job to the schedule.
May belong to an existing puzzle piece or final integration.
Consumes shop capacity.
May delay existing work.
Possible player responses:
Insert immediately.
Schedule at next available slot.
Preempt lower-priority work.
Protect current critical path and accept risk on urgent task.
21.8 Weather or Facility Outage
Effects:
Impacts one or more shops, capabilities, transport steps, or workcenters.
May reduce throughput for a duration.
Should usually provide advance warning.
Possible player responses:
Pre-stage work.
Shift work to unaffected shops.
Pull forward indoor/unaffected jobs.
Accept delay and protect bottleneck recovery.

22. Hidden Automated Scheduler / ECHO
ECHO is the automated scheduling engine.
Important gameplay requirement:
ECHO must not be shown as an advisor during normal gameplay.
ECHO must not provide daily recommendations.
ECHO must not be personified.
ECHO should not have personality text.
ECHO should run as a silent background comparison.
ECHO should be revealed at the end through metrics and explanation.
Internally, ECHO should use a scheduling heuristic that is stronger than the player’s default/manual scheduling system.
ECHO should evaluate:
Critical path
Minimum slack
Earliest due date
Workcenter capability
Workcenter efficiency
Queue length
Bottleneck severity
Setup penalty
Transport delay
Disruption impact
Rework impact
Cost impact
Schedule risk
Idle workcenter avoidance
Dependency unlock value
Downstream cascading effects
Whether preemption is worth the penalty
ECHO should not be wrong in the sense of making obviously poor scheduling choices. It may not be mathematically optimal, but it should be consistently strong and robust.
The automated scheduler should normally outperform the player unless the player makes near-optimal choices throughout the game. The final experience should strongly demonstrate that automated scheduling is more effective than manual scheduling in a disruption-heavy environment.

23. Scheduler Architecture
There should be at least two scheduler implementations behind a common interface.
23.1 Scheduler Interface
Create a scheduler abstraction such as:
class Scheduler:
   def plan_day(self, state, known_events, warnings):
       ...
The exact implementation can differ, but the architecture should clearly separate scheduling strategy from the simulation engine.
23.2 Player / Manual Scheduler
The player scheduler should:
Maintain the current player schedule.
Apply player decisions.
Use a basic default dispatching strategy for work not explicitly controlled by the player.
Be affected by suboptimal player choices.
Allow bottlenecks and delays to accumulate.
Respect dependencies and workcenter capabilities.
The player should not manually place every job. The system should translate high-level player choices into schedule changes.
23.3 Hidden Automated Scheduler
The automated scheduler should:
Maintain its own independent copy of the scenario state.
Receive the same events and warnings.
Replan silently after disruptions.
Use stronger heuristics.
Attempt to minimize lateness, idle time, reschedules, risk, and cost.
Protect critical path work.
Keep bottleneck workcenters utilized.
Avoid unnecessary preemption.
Use alternate workcenters when it improves schedule outcome.
Complete the final item by Day 30 when the generated scenario is feasible.

24. Automated Scheduler Heuristic
Implement ECHO as a heuristic scheduler, not a hardcoded outcome.
A suitable scoring approach:
For each ready job and candidate workcenter, compute a priority score based on:
Critical path weight
Slack remaining
Due shift urgency
Number of downstream dependencies unlocked
Puzzle piece risk
Workcenter efficiency
Setup cost
Transport delay
Queue length
Bottleneck status
Event risk
Cost penalty
Preemption penalty
Whether the assignment reduces future idle time
The scheduler should prefer:
Jobs on the critical path.
Jobs with low slack.
Jobs that unlock many downstream dependencies.
Jobs that use bottleneck workcenters efficiently.
Jobs that can finish before known disruptions.
Jobs that reduce future blocking.
Reroutes that reduce total lateness.
Preemption only when the downstream benefit exceeds the penalty.
The heuristic should re-run after:
Each day’s warnings
Each player day equivalent for automated state
Each triggered event
Each completed job
Each workcenter recovery
Each urgent inserted job
Each blocked job becoming ready
The automated scheduler should not depend on scripted choices to win. It should actually evaluate the generated state.

25. Scenario Generation
The scenario must be procedurally generated from a seed.
Requirements:
If a seed is provided, the same scenario and event sequence should be produced.
If no seed is provided, generate a random seed.
Display the seed so the run can be reproduced.
Use a deterministic random number generator object rather than global randomness.
Generate shops first.
Generate workcenters for each shop.
Generate capabilities.
Generate puzzle pieces.
Generate subjobs.
Generate dependencies.
Generate internal target dates or due shifts.
Generate event timeline.
Validate feasibility.
If the scenario is infeasible for ECHO, regenerate or adjust until it is feasible.
The generated scenario should be tight but not impossible.
Validation requirements:
Exactly 30 puzzle pieces.
Exactly 10 shops.
Each shop has 20–50 workcenters.
Each piece has 5–15 subjobs.
Dependencies are acyclic.
Every job has at least one capable workcenter.
Final integration is possible.
Hidden automated scheduler can complete the final item by Day 30 under the generated event sequence.
Scenario is not trivially easy. There should be meaningful bottlenecks, disruptions, and risk.

26. Feasibility and Difficulty
There is only one difficulty level.
The game is intended to simulate a realistic scheduling challenge, not arcade difficulty levels.
The scenario should be:
Complex
Disruption-heavy
Feasible
Tight
Risky
Not arbitrary
Not impossible
Not trivial
The hidden automated scheduler should be able to complete the project by the deadline in the generated scenario.
The player may succeed or fail depending on decisions.
Bad decisions should have both:
Immediate consequences
Accumulated consequences
For example:
Waiting on a down machine may immediately delay one job and later block a chain of dependent jobs.
Preempting too often may solve today’s issue but increase reschedules, cost, and accumulated risk.
Ignoring a weather warning may cause a future shop outage to hit critical-path jobs.
Over-prioritizing urgent inserted work may protect one metric but delay final integration.

27. Metrics
Track metrics for both the player simulation and hidden automated scheduler simulation.
During gameplay, display only the player’s metrics.
At final reveal, display player and automated scheduler metrics side by side.
Required metrics:
Pieces completed
Jobs completed
Jobs remaining
Jobs late
Workcenter utilization
Idle time
Number of reschedules
Cost
Schedule risk
Deadline met
Final item completed
Projected completion day/shift during gameplay
Actual completion day/shift at game end
Do not use “days remaining” as a primary metric.
27.1 Pieces Completed
Count puzzle pieces whose required subjobs are complete and accepted.
27.2 Jobs Completed
Count all completed subjobs, rework jobs, inserted urgent jobs, and final integration jobs as appropriate.
27.3 Jobs Late
A job is late if it completes after its target milestone shift.
27.4 Utilization
Utilization should be calculated as:
busy workcenter shifts / available workcenter shifts
Track globally and by shop.
27.5 Idle Time
Idle time should be calculated as available workcenter shifts where the workcenter is not busy.
Idle time should distinguish between:
True idle because no work is ready
Idle because work is blocked
Idle because of poor scheduling
Idle because of disruption
A simple implementation is acceptable for v1 as long as the summary is understandable.
27.6 Reschedules
A reschedule occurs when:
A job is moved to another workcenter.
A job is moved to a different shift/day.
A running job is preempted.
Queue order is changed in response to disruption.
Work is rerouted due to an event.
27.7 Cost
Cost can be abstract.
Cost should increase from:
Processing jobs
Idle time
Expedite actions
Rework
Rescheduling
Preemption
Late jobs
Facility outage impact
Use of less efficient alternate workcenters
The exact dollar values do not need to be realistic. Use an abstract “cost points” model.
27.8 Schedule Risk
Schedule risk should be represented as a score, ideally 0–100.
Risk should increase when:
Critical path slack decreases.
Jobs become late.
More jobs become blocked.
Bottleneck queues grow.
Important workcenters go down.
Events impact high-priority jobs.
Final integration is threatened.
Risk should decrease when:
Critical jobs complete.
Blocked jobs are unblocked.
Slack improves.
Bottlenecks clear.
Pieces complete.
Known warnings are mitigated.

28. Final Reveal
At the end of the run, reveal that an automated scheduler was running silently in the background.
The final reveal should include:
A side-by-side metric comparison.
Whether the player completed the final item by Day 30.
Whether the automated scheduler completed the final item by Day 30.
Player completion day/shift, if completed.
Automated scheduler completion day/shift.
Jobs completed comparison.
Jobs late comparison.
Pieces completed comparison.
Utilization comparison.
Idle time comparison.
Reschedule comparison.
Cost comparison.
Schedule risk comparison.
A short explanation of how the automated scheduler did better.
The final explanation should mention that ECHO:
Protected critical-path work.
Used alternate workcenters more effectively.
Responded earlier to warnings.
Reduced idle bottleneck time.
Avoided unnecessary preemption.
Resequenced work around blocked jobs.
Reduced cascading delays.
Maintained better utilization.
Reduced overall schedule risk.
Do not overdo the reveal with personality or marketing language. It should feel like an operational comparison.

29. CLI Interface Requirements
Use a rich terminal interface.
Required UI capabilities:
Colored headings
Tables
Panels
Progress indicators
Clear input prompts
Readable summaries
Compact status boards
Drill-down inspection menus
Graceful handling of invalid input
Support for plain output through --no-color
The player should interact through numeric menu choices. Arrow-key navigation is not required.
29.1 Main Menu
The main menu should include:
Start new game
Start new game with seed
Quit
No save/load.
29.2 In-Day Menu
Before making the day’s decisions, the player should be able to inspect:
Overview
Shop status
Workcenter queues
Puzzle piece progress
Critical path
Risk register
Continue to decisions
29.3 Decision Input
For each of the day’s 3 decision cards:
Display the decision.
Show 2–4 choices.
Ask the player to select one.
Validate the input.
Apply the selected choice.
Show a short confirmation of the chosen action.
29.4 End-of-Day Input
After the summary:
Let the player continue to the next day.
Let the player quit the current run without saving.
If the player quits, no resume is required.

30. Schedule Board Requirements
The schedule board should be large enough to communicate complexity but not so dense that it becomes unreadable.
The default schedule board should summarize all 10 shops.
For each shop, show:
Shop name
Active jobs
Queued jobs
Blocked jobs
Completed jobs
Utilization percentage
Idle workcenters
Highest-risk puzzle piece
Bottleneck indicator
Current major event, if any
The workcenter queue view should let the player inspect a selected shop and see:
Workcenter ID
Status
Current job
Remaining shifts
Queue length
Next queued job
Capability
Downtime remaining, if any
The puzzle piece progress view should show:
Piece ID/name
Status
Completed subjobs
Total subjobs
Blocked subjobs
Critical-path marker
Estimated completion shift
Risk score
The critical path view should show:
Critical jobs
Their shop/workcenter
Remaining duration
Slack
Blocking issue, if any
Downstream piece or final integration impact
The risk register should show:
Active risks
Known warnings
Affected jobs/pieces/shops
Severity
Days/shifts until impact
Suggested category of response, but not an automated recommendation
The risk register may say things like “mitigation recommended” or “critical-path exposure,” but it must not say “ECHO recommends…”

31. Data Model Requirements
The implementation should use explicit domain models.
The exact code structure is flexible, but the following concepts should exist.
31.1 GameConfig
Fields:
total_days
shifts_per_day
piece_count
shop_count
min_workcenters_per_shop
max_workcenters_per_shop
min_jobs_per_piece
max_jobs_per_piece
seed
use_color
debug
31.2 Scenario
Fields:
scenario_id
seed
shops
workcenters
pieces
jobs
dependencies
event_timeline
final_integration_job
deadline_shift
31.3 Shop
Fields:
id
name
capabilities
workcenter_ids
active_job_ids
queued_job_ids
blocked_job_ids
completed_job_ids
utilization
idle_time
risk_score
31.4 WorkCenter
Fields:
id
shop_id
name
capabilities
efficiency
status
current_job_id
queue
downtime_remaining
blocked_reason
31.5 PuzzlePiece
Fields:
id
name
job_ids
status
completed_job_count
total_job_count
risk_score
estimated_completion_shift
ready_for_integration
integrated
31.6 Job
Fields:
id
piece_id
shop_id
required_capability
candidate_workcenter_ids
assigned_workcenter_id
base_duration_shifts
remaining_duration_shifts
setup_time_shifts
transport_delay_shifts
dependency_ids
dependent_job_ids
status
priority
due_shift
risk_score
cost_weight
critical_path
block_reason
31.7 Event
Fields:
id
type
target_type
target_id
start_shift
duration_shifts
severity
has_advance_warning
warning_shift
description
effects
resolved
31.8 DecisionCard
Fields:
id
day
type
title
description
target_ids
severity
choices
31.9 DecisionChoice
Fields:
id
label
description
immediate_effects
risk_effect
cost_effect
reschedule_effect
31.10 MetricSnapshot
Fields:
shift
day
pieces_completed
jobs_completed
jobs_remaining
jobs_late
utilization
idle_time
reschedules
cost
schedule_risk
projected_completion_shift
final_item_completed
deadline_met

32. State Management
Keep separate state objects for:
Player simulation
Hidden automated scheduler simulation
Both states should reference the same base scenario structure but maintain independent mutable runtime state.
Do not mutate shared objects in a way that causes player and automated states to affect each other.
Recommended approach:
Generate immutable or base scenario data.
Deep-copy or initialize two runtime states from the scenario.
Apply the same event timeline to both states.
Apply player choices only to player state.
Apply automated scheduler decisions only to automated state.
The simulation engine should not know or care whether a state belongs to the player or automated scheduler. It should simply advance a state according to decisions and events.

33. Architecture Requirements
The code must be structured for future GUI conversion.
Simulation logic must not be embedded in terminal rendering code.
Use a layered structure:
Domain models
Scenario generation
Scheduling logic
Event system
Simulation engine
Metrics calculation
CLI presentation
Application orchestration
The CLI should call application services, not directly manipulate low-level job state.
Use pure or mostly pure functions where practical.
Avoid global mutable state.
Pass the random generator explicitly where possible.

34. Recommended File Structure
Use this or a very similar structure:
.
├── README.md
├── requirements.md
├── pyproject.toml
├── main.py
└── echo_adventure/
   ├── __init__.py
   ├── __main__.py
   ├── app.py
   ├── config.py
   ├── models.py
   ├── enums.py
   ├── scenario_generator.py
   ├── simulation.py
   ├── events.py
   ├── decisions.py
   ├── metrics.py
   ├── schedulers/
   │   ├── __init__.py
   │   ├── base.py
   │   ├── manual.py
   │   └── automated.py
   └── cli/
       ├── __init__.py
       ├── renderer.py
       ├── menus.py
       └── input.py
File responsibilities:
app.py
Application orchestration.
Responsible for:
Starting a new game
Creating the scenario
Initializing player and automated states
Running the daily loop
Triggering final reveal
config.py
Configuration constants and CLI config.
models.py
Core domain models.
enums.py
Enums for statuses, event types, decision types, etc.
scenario_generator.py
Procedural generation for:
Shops
Workcenters
Capabilities
Puzzle pieces
Jobs
Dependencies
Final integration job
Event timeline
Feasibility validation
simulation.py
Core simulation engine.
Responsible for:
Advancing shifts
Starting jobs
Completing jobs
Unlocking dependencies
Applying delays
Handling queues
Updating state
events.py
Event generation and event application.
decisions.py
Decision card generation and decision effect application.
metrics.py
Metric calculations.
schedulers/base.py
Scheduler interface or abstract base class.
schedulers/manual.py
Manual/player scheduling helper logic.
schedulers/automated.py
Hidden automated scheduler heuristic.
cli/renderer.py
Rich terminal display functions.
cli/menus.py
Menu flow and screen composition.
cli/input.py
Validated input helpers.

35. Simulation State Requirements
Create a runtime state object representing the current simulation state.
Fields should include:
current_shift
current_day
shops
workcenters
pieces
jobs
active_events
known_warnings
completed_jobs
blocked_jobs
scheduled_jobs
reschedule_count
cost
metric_history
final_item_completed
completion_shift
The state should expose helper methods or services for:
Getting ready jobs
Getting blocked jobs
Getting critical path jobs
Getting bottleneck shops
Getting available workcenters
Assigning jobs
Rerouting jobs
Preempting jobs
Completing jobs
Applying event effects
Recalculating risk
Recalculating projected completion

36. Critical Path and Risk
The player must be able to inspect the critical path.
The critical path does not need to be mathematically perfect, but it should be useful.
A reasonable v1 approach:
Build dependency graph.
Estimate remaining duration for each job.
Include queue, setup, and transport estimates.
Calculate longest remaining path to final integration.
Mark jobs on or near that path as critical.
Calculate slack against deadline.
Use low slack to increase risk.
Risk score should combine:
Critical path slack
Number of blocked critical jobs
Bottleneck queue depth
Active events
Known warnings
Jobs late
Remaining work vs remaining capacity
Final integration readiness

37. Manual Scheduling Behavior
The player is making high-level decisions, but the game still needs to schedule many jobs automatically.
The manual scheduler should:
Use the player’s choices as constraints or preferences.
Fill open workcenter slots using a basic dispatching rule.
Respect dependencies and capabilities.
Be less sophisticated than ECHO.
Not intentionally sabotage the player.
Produce plausible manual scheduling behavior.
A reasonable manual dispatching rule:
Prioritize jobs by visible priority and due shift.
Keep current workcenter assignments when possible.
Avoid rerouting unless the player chooses it.
Use first available capable workcenter.
Do not aggressively optimize critical path.
Do not aggressively predict cascading delays.
Do not preempt unless the player chooses it.
This ensures the player’s decisions matter while still allowing the automated baseline to outperform.

38. Automated Scheduling Behavior
The automated scheduler should:
Recompute priorities frequently.
Prefer critical-path jobs.
Minimize slack violations.
Use alternate workcenters effectively.
Keep bottleneck workcenters busy.
Resequence around blocked jobs quickly.
Respond to warnings before disruptions hit.
Preempt only when it creates clear downstream benefit.
Reduce idle time.
Reduce late jobs.
Reduce total cost where possible.
Reduce final schedule risk.
It should not require player input.
It should not generate visible recommendations.
It should not be scripted to magically win. Its results should emerge from better scheduling logic.

39. Final Integration
Final integration represents combining all completed puzzle pieces into one finished item.
Requirements:
Final integration cannot begin until all 30 puzzle pieces are complete.
Final integration should require one or more final jobs.
Final integration jobs should use workcenters like any other job.
Final integration should be included in the deadline.
The final item is complete only when final integration completes.
The player wins if final integration completes by the end of Day 30.
The automated scheduler should also be evaluated against this same condition.
The generated scenario must account for final integration time when determining feasibility.

40. Win / Loss Conditions
The player wins if:
final item completed by the end of Day 30
The player loses if:
final item not completed by the end of Day 30
Even if the player loses, still show the final comparison.
The final report should make clear whether:
The player completed by the deadline.
The automated scheduler completed by the deadline.
The automated scheduler completed earlier.
The automated scheduler had fewer late jobs.
The automated scheduler had lower cost.
The automated scheduler had lower risk.
The automated scheduler used the yard more efficiently.

41. Game Tone
The tone should be:
Operational
Strategic
Clear
Slightly tense
Fictional
Professional
Avoid:
Comedy-heavy writing
Overly dramatic writing
Mascot behavior
ECHO personality
Military realism
Real-world sensitive details
The game should feel like a scheduling pressure simulation, not a fantasy adventure.

42. Input Handling
All player choices should be robustly validated.
Requirements:
Numeric menu choices.
Re-prompt on invalid input.
Clear error messages.
Support quitting from major prompts where reasonable.
Do not crash on unexpected input.
Avoid requiring exact text commands.
Keep prompts readable.
No save is required when quitting.

43. Procedural Names and IDs
Use stable IDs internally.
Examples of ID patterns:
SHOP-01
WC-01-001
PIECE-01
JOB-01-001
EVT-0001
Display names can be more readable but should remain fictional.
Avoid names that imply real-world sensitive operations.

44. Performance Requirements
The simulation should be responsive.
Targets:
Generate scenario within a few seconds.
Advance one day quickly.
Render screens without excessive delay.
Avoid heavy optimization libraries.
Avoid brute-force search over all possible schedules if it becomes slow.
Use heuristics and priority queues where useful.
The full scale of 30 pieces, 10 shops, 200–500 workcenters, and hundreds of jobs must be supported.

45. Error Handling and Validation
The app should gracefully handle:
Invalid CLI flags
Invalid menu input
Scenario generation failure
Infeasible generated scenario
No available workcenter for a job
Empty queues
Completed game state
Terminal width limitations
If scenario generation produces an infeasible case, regenerate with adjusted parameters or report a clear internal error in debug mode.
For normal players, avoid exposing stack traces.

46. Debug Mode
Debug mode is optional but useful.
If implemented, --debug may show:
Seed
Scenario validation details
Event timeline
Hidden scheduler completion result
Internal risk calculations
Scheduling scores
Debug mode is for development only.
Normal gameplay must not expose hidden automated scheduler behavior before the final reveal.

47. Development Constraints for Coding Agent
This repository starts empty.
The coding agent should:
Create the project structure.
Implement the CLI game.
Keep code readable.
Use type hints.
Prefer simple, maintainable heuristics.
Avoid overengineering.
Avoid adding unnecessary dependencies.
Do not implement a test suite for v1.
Do not implement save/load.
Do not implement a GUI.
Do not use real-world data.
Do not expose ECHO recommendations during gameplay.
Ensure the game can run from the command line.
Ensure a full run can be completed interactively.
The coding agent should not stop after creating only scaffolding. The result should be a playable v1.

48. Suggested Implementation Order
Build in this order:
Phase 1: Project Setup
Create Python package structure.
Add CLI entry point.
Add rich dependency.
Add basic main menu.
Add config object.
Phase 2: Domain Models
Add enums.
Add models for shops, workcenters, pieces, jobs, events, decisions, metrics, and simulation state.
Add helper methods for job readiness and dependency checks.
Phase 3: Scenario Generator
Generate shops and workcenters.
Generate capabilities.
Generate 30 puzzle pieces.
Generate 5–15 jobs per piece.
Generate dependencies.
Generate final integration job.
Generate due shifts.
Validate scenario.
Phase 4: Event System
Generate seeded event timeline.
Add missing material events.
Add machine down events.
Add quality rework events.
Add priority change events.
Add inspection delay events.
Add engineering hold events.
Add urgent inserted job events.
Add weather/facility events.
Add warnings for weather and delayed materials.
Phase 5: Simulation Engine
Advance shifts.
Start jobs.
Complete jobs.
Unlock dependencies.
Update queues.
Apply event effects.
Track utilization.
Track idle time.
Track cost.
Track risk.
Track reschedules.
Phase 6: Schedulers
Implement manual scheduler.
Implement automated scheduler.
Ensure both operate on independent states.
Ensure both receive the same events.
Ensure automated scheduler runs silently.
Phase 7: Decisions
Generate top 3 daily decision cards.
Add 2–4 choices per card.
Apply player choice effects.
Make choices meaningful and tied to simulation state.
Phase 8: CLI Rendering
Render main menu.
Render schedule board.
Render shop status.
Render workcenter queues.
Render piece progress.
Render critical path.
Render risk register.
Render decision cards.
Render end-of-day summary.
Render final reveal.
Phase 9: Balancing
Tune scenario generation.
Tune event frequency.
Tune cost model.
Tune risk model.
Tune ECHO heuristic.
Ensure ECHO usually completes by Day 30.
Ensure player choices can create meaningful success or failure.

49. Acceptance Criteria
The v1 implementation is complete when all of the following are true.
49.1 Launch
The game can be launched from the terminal.
The player can start a new game.
The player can optionally provide a seed.
The game displays the seed used for the run.
49.2 Scenario
A generated scenario contains exactly 30 puzzle pieces.
A generated scenario contains exactly 10 shops.
Each shop contains between 20 and 50 workcenters.
Each puzzle piece contains between 5 and 15 subjobs.
Jobs have dependencies.
Jobs require capable workcenters.
Final integration exists.
The deadline is Day 30.
49.3 Gameplay
The game advances by days.
Each day contains three simulated shifts.
Each day presents a schedule board.
Each day presents 3 high-impact decision cards.
Each decision card has 2–4 choices.
Player choices affect the schedule.
End-of-day summaries are shown.
The player can complete or fail the project.
49.4 Events
Random events occur across the game.
Event sequences differ across different seeds.
Same seed reproduces the same event sequence.
Events are applied to both player and automated scheduler simulations.
Missing/delayed material events exist.
Machine down events exist.
Quality rework events exist.
Priority change events exist.
Inspection delay events exist.
Engineering hold events exist.
Urgent inserted jobs exist.
Weather or facility events exist.
Labor shortages do not exist.
Weather and delayed material events can provide advance warning.
49.5 Hidden Automated Scheduler
The automated scheduler runs in the background.
The automated scheduler receives the same scenario.
The automated scheduler receives the same event sequence.
The automated scheduler makes independent scheduling decisions.
The player does not see automated recommendations.
The player does not see daily automated comparisons.
The automated scheduler uses a heuristic, not a hardcoded final score.
The automated scheduler generally performs better than the player.
49.6 Metrics
The game tracks pieces completed.
The game tracks jobs completed.
The game tracks jobs late.
The game tracks utilization.
The game tracks idle time.
The game tracks reschedules.
The game tracks cost.
The game tracks schedule risk.
The game tracks projected completion.
The game tracks deadline success/failure.
49.7 Final Reveal
At game end, the final report reveals ECHO.
The final report compares player metrics to automated scheduler metrics.
The final report explains how ECHO performed better.
The explanation references scheduling behavior, not personality.
The reveal happens only at the end.
49.8 Architecture
Simulation logic is separated from CLI rendering.
Scheduler logic is separated from simulation logic.
Scenario generation is separated from gameplay loop.
Metrics are calculated in a dedicated module or service.
The codebase can support a future GUI without rewriting the simulation engine.

50. Manual QA Checklist
Before considering v1 done, manually verify:
Run the game with no seed.
Run the game with a fixed seed.
Confirm the fixed seed reproduces the same scenario.
Confirm the player can inspect all required views.
Confirm daily decisions appear.
Confirm choices change the simulation.
Confirm random events occur.
Confirm warnings appear before at least some weather/material events.
Confirm the player can reach Day 30.
Confirm final reveal appears.
Confirm ECHO was not shown during daily gameplay.
Confirm final metrics compare player vs ECHO.
Confirm the game does not crash on invalid input.
Confirm no labor shortage events occur.
Confirm final integration is required to win.

51. Key Design Principle
The central design principle is:
The player experiences the difficulty of manual scheduling under disruption. ECHO is not a helper during the game; it is the hidden benchmark revealed at the end.
Everything in the design should reinforce this.
The player should feel the complexity of:
Too many jobs
Too many workcenters
Tight dependencies
Blocked work
Queue pressure
Uncertain disruptions
Cascading delays
Cost tradeoffs
Schedule risk
The final reveal should make it clear that automated scheduling performed better because it continuously evaluated dependencies, bottlenecks, risk, utilization, and alternate routing more effectively than a human scheduler making manual decisions.

