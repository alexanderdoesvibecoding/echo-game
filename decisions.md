Weather

- Takes out 1-3 exposed workstations for 3-9 shifts
- Affected subjobs pause unless they can be moved to other capable stations
- Options:
    - Reroute exposed work
        - Moves affected subjobs to other machines if possible
        - Adds setup and reschedule pressure to the receiving stations
    - Wait it out
        - Affected subjobs lose the weather duration
        - Keeps other queues stable
        - Can unlock Weather cleared early

Workstation breakdown

- Takes out one machine for 3-9 shifts
- Any running subjob on that machine pauses until the station is repaired or rerouted
- Options:
    - Move affected subjobs
        - Moves work to other capable machines if possible
        - Adds setup pressure and may push work already on those machines
        - Can unlock Setup mismatch found
    - Wait for repair
        - Keeps the routing simple
        - Affected work waits for the machine to return

Materials not here

- A required kit, blank, fastener set, or supplied part is not at the station
- The affected subjob halts until usable material is found
- Options:
    - Wait for materials
        - Affected work loses a couple shifts
        - Avoids stealing from another job
        - Can unlock Bulk lot released
    - Use another subjob's material
        - Keeps the current subjob moving
        - Delays the donor subjob a couple shifts
        - Can unlock Phantom stock confirmed
    - Switch to verified work
        - Pulls a different ready subjob forward
        - Leaves this subjob blocked until its material arrives

ECHO recommendation (rare)

- ECHO has a schedule recommendation that changes the whole board
- The move looks disruptive before the benefit is visible
- Options:
    - Take advice
        - All active or queued subjobs lose 1-2 shifts while the plan is reshuffled
        - Can unlock ECHO slack pocket found
    - Ignore the AI
        - Nothing changes now
        - Any hidden scheduling opportunity is missed

Worker took an off day

- The assigned worker is out for the shift
- The affected subjob is not worked unless someone else is put on it
- Options:
    - Find a replacement
        - The subjob can continue this shift
        - Can unlock Replacement handoff check
    - Hold until the worker returns
        - The subjob loses 1 shift
        - Avoids handoff mistakes
        - Can unlock Returning worker shortcut

Calibration drift

- Metrology, inspection, or calibration work from the last 1-2 shifts becomes suspect
- Affected stations run slower until the measurement chain is trusted again
- Options:
    - Recalibrate now
        - Takes the measuring station out for 1-2 shifts
        - Clears the risk before more work is released
        - Can unlock Narrow drift found
    - Add witness checks
        - Current work continues, but affected subjobs take 1 extra shift
        - Reduces rework risk without fully stopping the station
    - Send checks elsewhere
        - Moves verification to another capable station
        - Adds queue pressure to that station

Traveler mismatch

- The paper traveler and the digital route disagree on one operation
- The subjob cannot safely start until the shop knows which instruction is current
- Options:
    - Stop and reconcile it
        - Delays the subjob 1 shift
        - Prevents bad work from entering the next dependency
        - Can unlock Route shortcut approved
    - Use the floor copy
        - No immediate delay
        - May add 2-3 shifts of later correction if the copy was stale
        - Can unlock Wrong revision loaded
    - Start only the unaffected steps
        - Pulls a parallel or downstream-safe subjob forward
        - Leaves the disputed subjob blocked until the next shift

Shared fixture claim

- Two ready subjobs need the same fixture at the same time
- Only one can run unless the player accepts extra setup risk
- Options:
    - Give it to the tightest job
        - Keeps the higher-risk or nearest-due subjob moving
        - Delays the other subjob 2-3 shifts
    - Build a temporary fixture
        - Lets both subjobs start
        - Adds 1 setup shift and a small chance of rework
        - Can unlock Spare fixture certified
    - Keep the original sequence
        - No reschedule churn
        - The second subjob waits for the fixture to free up

Changeover drag

- A workcenter changeover takes longer than planned
- The station loses 1-2 shifts before it can switch families
- Options:
    - Finish similar work first
        - Speeds up nearby same-family subjobs
        - Pushes the odd-family subjob back
    - Pay the changeover now
        - The target subjob keeps its place
        - The station loses the extra setup time immediately
        - Can unlock Family run unlocked
    - Move the odd job
        - Sends the subjob to another capable station
        - Adds setup pressure to the receiving station

Batch window opens

- A shared oven, tank, or cure slot becomes available earlier than expected
- Several compatible subjobs can finish faster if they are ready now
- Options:
    - Fill the batch
        - Pulls compatible work forward
        - Saves 1 shift on each batched subjob
        - Can unlock Batch data accepted
    - Reserve it for critical work
        - Holds the slot for one high-risk job
        - May waste capacity if that job is not ready in time
    - Ignore the window
        - Keeps queues stable
        - Loses the speedup opportunity

Consumables short

- Shop consumables such as adhesive, coolant, shielding gas, wipes, or masking tape are low
- Affected capability work slows down until fresh stock is staged
- Options:
    - Ration to due work
        - Critical or near-due subjobs keep moving
        - Lower-priority subjobs lose 1-2 shifts
    - Borrow from another shop
        - Restores this shop faster
        - Adds a small delay to the donor shop
    - Wait for restock
        - No shop-to-shop disruption
        - Affected work pauses for 2-3 shifts
        - Can unlock Bulk lot released

Label printer outage

- Serialized labels and completion tags cannot be printed at the release desk
- Finished subjobs can pile up without being formally closed
- Options:
    - Handwrite controlled labels
        - Lets one or two finished subjobs close today
        - Adds documentation review risk later
    - Borrow a printer
        - Clears labels after 1 shift
        - Pulls a support resource away from another shop
    - Hold completions
        - Avoids paperwork risk
        - Finished work waits 1-2 shifts before it counts as complete
        - Can unlock Clean packet release

Shop air pressure dip

- Pneumatic tools and clamps lose reliability across part of a shop
- Several workcenters run at reduced throughput for 1-3 shifts
- Options:
    - Throttle noncritical work
        - Keeps key jobs moving at near-normal speed
        - Delays routine subjobs
    - Move hand-tool work forward
        - Uses jobs that do not need shop air
        - Reshuffles the queue
    - Run through it
        - No reschedule
        - All affected workcenters process slower
        - Can unlock Clamp marks found

Coolant change due

- A machining or cutting station needs a coolant change before finish quality degrades
- The station can run now, but risk rises each shift it is deferred
- Options:
    - Service it now
        - Takes the station out for 1 shift
        - Prevents later surface-finish penalties
        - Can unlock Finish window restored
    - Run one more shift
        - Keeps the current subjob moving
        - May add cleanup or finish work later
    - Move precision work away
        - Uses another capable route for sensitive jobs
        - Leaves rougher work on the station

FOD sweep

- Foreign object debris is found in a controlled area
- Work in that area stops while the sweep is completed
- No player choice:
    - The affected shop loses 1 shift
    - The delay is non-contestable and does not create rework
    - Can unlock Covered work reopened

Handoff window missed

- A cross-shop handoff misses the receiving shop's planned intake window
- The receiving station may sit open while the upstream subjob waits to move
- Options:
    - Hold the receiving slot
        - Protects the handoff when it arrives
        - May create idle time
    - Release the slot
        - Keeps the receiving shop productive
        - The handoff waits for the next opening
    - Pull a substitute subjob
        - Uses the open station on other ready work
        - Adds one reschedule

Crane reservation conflict

- A shared crane, lift, or positioner is booked by another shop
- Heavy or awkward subjobs cannot move into place this shift
- Options:
    - Wait for the crane
        - Delays the affected subjob 1-2 shifts
        - Keeps the setup simple
        - Can unlock Combined lift
    - Swap in bench work
        - Pulls smaller work forward
        - Leaves the heavy subjob queued
    - Use the off-shift slot
        - Saves the heavy subjob's schedule
        - Adds strain to the next shift and may slow morning starts

Nesting opportunity

- Two or more compatible subjobs can share a setup, fixture, program, or batch
- Combining them can save time if the player accepts a tighter sequence
- Options:
    - Nest the jobs
        - Saves 1-2 shifts of setup time
        - Locks those subjobs into the same routing choice
    - Nest only low-risk work
        - Saves a smaller amount of time
        - Avoids tying a critical job to a slower batch
    - Keep them separate
        - No setup savings
        - Keeps routing flexible

Old setup sheet

- A proven setup sheet is found for a similar past job
- The station can skip some trial setup if the sheet still matches the current work
- Options:
    - Use it as-is
        - Saves 1 setup shift
        - May cause a minor correction if the old sheet is stale
    - Validate first
        - Takes 1 shift now
        - Gives the setup speedup to later similar jobs
        - Can unlock Setup library update
    - Ignore it
        - No new risk
        - No speedup

WIP crowding

- Too many partially complete items are sitting in the same area
- The shop slows down because staging space, carts, and access lanes are crowded
- Options:
    - Freeze new starts
        - Stops additional queued work from entering the area
        - Helps running jobs finish cleanly
        - Can unlock Aisles cleared
    - Clear shortest work first
        - Quickly frees floor space
        - May delay more important long jobs
    - Move WIP to overflow
        - Restores shop space
        - Adds transport delay and tracking risk

Cleanliness breach

- A controlled area fails a cleanliness check
- Open work must be protected before normal operations resume
- Options:
    - Full reset
        - Loses 2 shifts in the affected area
        - Removes the risk completely
        - Can unlock Clean room cleared
    - Isolate the zone
        - Only subjobs in the contaminated zone pause
        - Other stations in the shop keep running
    - Continue under covers
        - Keeps work moving
        - Adds later inspection or rework risk
        - Can unlock Covered work reopened

Software seat conflict

- CAM, metrology, or test software licenses are all in use
- A programming-dependent subjob cannot be released until a seat opens
- Options:
    - Reserve the next seat
        - Protects the most urgent subjob
        - Pushes other programming work back
        - Can unlock Program template saved
    - Borrow after hours
        - Clears the affected subjob with a 1-shift delay
        - Slows the next shift's preparation
    - Run a manual fallback
        - Starts sooner
        - Adds 1 shift of operator verification

Network folder offline

- Current work instructions, programs, or acceptance files are temporarily unreachable
- Jobs that already have local copies can run; others must wait
- Options:
    - Use cached copies
        - Keeps familiar work moving
        - Adds document-version risk
        - Can unlock Wrong revision loaded
    - Start independent work
        - Pulls forward jobs that do not need the missing files
        - Reshuffles the queue
    - Wait for IT
        - Avoids version mistakes
        - Affected starts slip 1-2 shifts

Gauge dispute

- Two gauges disagree on a measured feature
- The subjob cannot be confidently accepted until the method is chosen
- Options:
    - Cross-check quickly
        - Delays acceptance 1 shift
        - Usually clears the subjob without rework
    - Run a formal study
        - Delays 2-3 shifts
        - Improves confidence for later similar subjobs
        - Can unlock Gauge method locked
    - Accept the trusted gauge
        - No immediate delay
        - May create a later quality question

Count variance

- Inventory shows enough parts or blanks, but the floor count disagrees
- One capability lane may be starved or overcommitted until the count is settled
- Options:
    - Cycle count now
        - Loses 1 shift on affected starts
        - Prevents scheduling work against phantom stock
    - Consume visible stock
        - Keeps one or two subjobs moving
        - May strand later work if the count is wrong
        - Can unlock Phantom stock confirmed
    - Reassign starts
        - Moves work to jobs with verified stock
        - Adds queue churn

Burr cleanup

- Parts coming out of cutting or machining need more deburr and cleanup than planned
- Downstream fitting or finishing work slows unless cleanup is handled
- Options:
    - Clean before release
        - Adds 1 shift to affected subjobs
        - Protects downstream work
    - Send to finishing early
        - Uses finishing capacity to absorb cleanup
        - May crowd the finishing queue
    - Release rough
        - Keeps the upstream station on schedule
        - Adds risk of downstream delay
        - Can unlock Fit check failed

Cure clock

- A bonded, coated, or potted item needs more dwell time before the next operation
- The next dependency cannot safely start yet
- Options:
    - Wait the clock out
        - Delays the dependent subjob 1-2 shifts
        - No added risk
    - Pull parallel work
        - Keeps the shop productive while the cure completes
        - Adds a reschedule
    - Force the next step
        - Saves time now
        - May create rework later
        - Can unlock Cure failure found

Vacuum leak chase

- A bag, seal, or holding fixture will not hold pressure
- The subjob cannot proceed normally until the leak is addressed
- Options:
    - Chase the leak
        - Delays the subjob 1 shift
        - Usually keeps the original setup
    - Rebuild the setup
        - Delays 2 shifts
        - Greatly reduces later failure risk
    - Run with monitoring
        - Starts now
        - Adds chance of lost work if the leak worsens
        - Can unlock Vacuum trace failed

Tool crib hold

- Required calibrated hand tools are waiting on crib release
- Several starts can proceed only if substitute tools are accepted
- Options:
    - Wait for release
        - Affected starts slip 1 shift
        - No extra verification needed
    - Borrow substitutes
        - Keeps urgent starts moving
        - Delays the donor station's next setup
        - Can unlock Sticker audit hit
    - Split the queue
        - Starts jobs that do not need held tools
        - Leaves tool-dependent jobs blocked

Fixture soak

- A large fixture or tool has not reached the required temperature or condition
- Starting too early risks bad fit or process drift
- Options:
    - Wait for soak
        - Delays the subjob 1 shift
        - Keeps the process clean
    - Preheat a second fixture
        - Sets up another future job faster
        - Uses capacity now
    - Switch to a ready fixture
        - Reroutes the job if another route exists
        - Adds setup churn
        - Can unlock Spare fixture certified

Shift overlap bonus

- Two shifts overlap longer than expected because of a planned meeting cancellation
- The shop has a short window of extra coordination
- Options:
    - Use it for a handoff
        - Reduces delay on one cross-shop dependency
    - Use it for short jobs
        - Completes 1-2 small ready subjobs faster
    - Use it for setup prep
        - Saves 1 shift on a later start

Waste container full

- Scrap, spent media, or used chemical containers are full
- Affected stations cannot keep producing without clearing waste
- Options:
    - Empty containers now
        - Loses 1 shift in the affected area
        - Restores normal throughput
    - Use small interim carts
        - Keeps work moving
        - Slows affected stations for 2 shifts
        - Can unlock Waste lane blocked
    - Divert to another area
        - Clears this shop
        - Adds crowding pressure elsewhere

Preapproved package

- Documentation for one family of work is already accepted by the customer or reviewer
- Compatible completions can close faster today
- Options:
    - Pull matching work forward
        - Saves 1 release shift on compatible subjobs
        - May delay unrelated work
    - Use it on near-complete jobs
        - Converts finished work into completed status faster
        - Gives less help to upstream bottlenecks
        - Can unlock Clean packet release
    - Save the package
        - Keeps today's plan stable
        - May miss the easiest speedup

Expired stickers

- Calibration stickers on several hand tools are out of date
- Tool-dependent starts need confirmation before they can proceed
- Options:
    - Audit and resticker
        - Loses 1 shift now
        - Clears several future starts
    - Swap tools
        - Keeps the highest-priority subjob moving
        - Delays a lower-priority station
    - Keep using them
        - No immediate schedule hit
        - Adds documentation and quality risk
        - Can unlock Sticker audit hit

Vendor rep on site

- A vendor specialist is unexpectedly available for one shift
- They can help with one station, program, or process family
- Options:
    - Use them on setup
        - Saves 1-2 setup shifts on a difficult station
        - Pulls a lead operator away briefly
    - Use them on troubleshooting
        - Reduces risk on a flaky process
        - Does not immediately speed the queue
    - Let them go
        - No disruption
        - Loses the speedup opportunity

Training run

- A newer operator can qualify on a real subjob
- The station runs slower now, but future staffing flexibility improves
- Options:
    - Train on low-risk work
        - Adds 1 shift to that subjob
        - Reduces future crew or routing pressure
        - Can unlock Operator qualified
    - Train on urgent work
        - Keeps the urgent path staffed
        - Adds a chance of rework
    - Postpone training
        - No immediate slowdown
        - No future flexibility gain

Off-peak utility slot

- Power, oven, compressor, or test-cell capacity is cheaper and more available off-cycle
- A workcenter can run an extra slot if the schedule is rearranged
- Options:
    - Run critical work off-peak
        - Saves 1 shift on a high-risk subjob
        - May slow the next normal shift's setup
    - Run batch work off-peak
        - Saves time across several compatible subjobs
        - Locks those jobs into the same sequence
    - Skip the slot
        - Keeps the plan simple
        - No speedup

Floor walk insight

- A supervisor or engineer spots a small method improvement during a floor walk
- It can remove wasted motion if the shop pauses long enough to change the standard work
- Options:
    - Apply it today
        - Loses 1 shift in one station
        - Saves 1 shift on future similar work
        - Can unlock Process tweak validated
    - Apply only to new starts
        - No pause for running work
        - Smaller future speedup
    - Keep the old method
        - No disruption
        - No process improvement

Wash tank chemistry

- A wash, etch, or prep tank is drifting out of range
- Surface-prep or coating starts become risky until the bath is corrected
- Options:
    - Change the bath
        - Takes the tank out for 1-2 shifts
        - Clears the risk
        - Can unlock Finish window restored
    - Send work to another prep route
        - Keeps urgent jobs moving
        - Crowds the alternate route
    - Keep running light work
        - Allows only low-risk subjobs to continue
        - High-risk work waits

Rack shortage

- Finished or in-process parts need racks, carts, or protected stands that are already full
- Work can finish, but it cannot safely move or stage
- Options:
    - Clear old racks
        - Pulls effort toward closing or moving finished WIP
        - Delays new starts
    - Build temporary racks
        - Takes 1 shift of shop support
        - Restores staging capacity
        - Can unlock Rack recovery sprint
    - Keep parts at stations
        - No immediate support work
        - Ties up workcenters after jobs finish

Safety drill

- A required emergency drill interrupts production
- No work can continue while the drill is active
- No player choice:
    - Every active station loses 1 shift
    - No rework or extra risk is created

Access badge failure

- A secure area badge reader fails during shift start
- Only work outside that area can begin on time
- Options:
    - Wait for security
        - Secure-area jobs slip 1 shift
        - No reschedule churn
    - Pull open-area work
        - Keeps available shops productive
        - Delays secure-area dependencies
    - Escort critical staff
        - Keeps one critical station running
        - Slows support response elsewhere

Reference sample missing

- A golden sample, master pattern, or comparison artifact is not at the station
- Work that needs visual or fit comparison cannot be accepted
- Options:
    - Search now
        - Delays the affected subjob 1 shift
        - Usually clears the acceptance path
    - Borrow a sister sample
        - Keeps the station moving
        - Adds acceptance risk
    - Switch to measured criteria
        - Uses metrology or inspection capacity
        - Reduces subjective risk but crowds that lane
        - Can unlock Gauge method locked

Staging map reset

- The floor layout changes because a large item must be moved through the area
- Queues that relied on nearby staging lose their planned positions
- Options:
    - Redraw staging now
        - Adds 1 reschedule
        - Prevents access conflicts later
        - Can unlock Aisles cleared
    - Move only critical WIP
        - Protects the most important work
        - Leaves some routine work harder to reach
    - Let shops improvise
        - No immediate reschedule
        - May add idle time as people search for parts

Narrow drift found

- Flows from Calibration drift if the player chose Recalibrate now
- The recalibration finds the drift was limited to one reference, not the whole measurement chain
- Options:
    - Release quarantined work
        - Clears several held completions or blocked starts
        - Gains 3-5 shifts compared with checking each one again
    - Release only critical work
        - Gains 2-3 shifts on high-risk jobs
        - Leaves routine work held for normal review
    - Keep everything quarantined
        - No added risk
        - Loses the chance to recover the earlier delay

Route shortcut approved

- Flows from Traveler mismatch if the player chose Stop and reconcile it
- Engineering confirms the current route had an unnecessary step copied from an older build
- Options:
    - Apply the shortcut broadly
        - Removes 1 shift from several matching subjobs
        - Adds a reschedule because those jobs now move sooner
    - Apply it only here
        - Saves 2 shifts on the disputed subjob path
        - Does not help unrelated jobs
    - Keep the old route
        - Avoids changing active work instructions
        - Gives up the shortcut

Spare fixture certified

- Flows from either Shared fixture claim if the player chose Build a temporary fixture, or Fixture soak if the player chose Switch to a ready fixture
- The alternate fixture passed checks and can become another qualified fixture
- Options:
    - Certify it for the family
        - Costs 1 more review shift now
        - Gains 4-6 shifts across future fixture-limited work
    - Use it only on low-risk jobs
        - Gains 2-3 shifts
        - Keeps critical work on the original fixture
    - Retire the fixture
        - No certification work
        - The earlier setup cost does not create a future benefit

Family run unlocked

- Flows from Changeover drag if the player chose Pay the changeover now
- The station is finally set up for a family of similar work
- Options:
    - Pull the whole family forward
        - Saves 3-5 setup shifts across matching subjobs
        - Locks those jobs into this station's queue
    - Pull only critical matches
        - Saves 2-3 shifts on high-risk work
        - Leaves the rest of the queue flexible
    - Tear down after this job
        - Keeps the old schedule order
        - Wastes the expensive changeover

Bulk lot released

- Flows from either Consumables short if the player chose Wait for restock, or Materials not here if the player chose Wait for materials
- The restock arrives as a full lot with matched batch paperwork
- Options:
    - Run the full lot immediately
        - Restores paused work and saves 3-4 shifts on repeated setup
        - Crowds the affected shop for one day
    - Feed only due work
        - Recovers 2 shifts on near-due subjobs
        - Preserves some stock for later
    - Stage it normally
        - No new queue churn
        - The earlier waiting remains a pure delay

Clean packet release

- Flows from either Label printer outage if the player chose Hold completions, or Preapproved package if the player chose Use it on near-complete jobs
- The official labels and packets are now clean enough for batch closeout
- Options:
    - Close the whole backlog
        - Several finished subjobs count complete at once
        - Gains 3-5 shifts versus piecemeal document review
    - Close only due jobs
        - Gains 2 shifts where schedule pressure is highest
        - Leaves some packets for normal closeout
    - Keep reviewing one by one
        - Lowest documentation risk
        - No catch-up benefit

Finish window restored

- Flows from either Coolant change due if the player chose Service it now, or Wash tank chemistry if the player chose Change the bath
- The serviced process is holding finish quality better than expected
- Options:
    - Run precision work through it
        - Removes 1 finish or inspection shift from several sensitive subjobs
        - Pulls them into this station's queue
    - Run only the critical job
        - Saves 2 shifts on the highest-risk path
        - Leaves routine work unchanged
    - Return to normal dispatch
        - Stable queue
        - No extra benefit from the service window

Combined lift

- Flows from Crane reservation conflict if the player chose Wait for the crane
- The delayed crane slot is long enough to move multiple staged jobs together
- Options:
    - Combine all lifts
        - Recovers the lost shift and saves 2-3 more on heavy handoffs
        - Requires several jobs to wait for the same move
    - Combine critical lifts
        - Gains 2 shifts on high-risk handoffs
        - Leaves lower-priority moves separate
    - Move only the original job
        - Avoids staging complexity
        - The crane delay stays mostly unrecovered

Setup library update

- Flows from Old setup sheet if the player chose Validate first
- The old setup sheet is now confirmed and can be added to the live setup library
- Options:
    - Publish it for every matching station
        - Saves 1 setup shift on several future starts
        - Adds a small chance of one station misreading the update
    - Give it to one station
        - Saves 2-3 shifts total with little risk
        - Does not help other routes
    - Archive it as reference only
        - No process-change risk
        - No schedule recovery

Aisles cleared

- Flows from either WIP crowding if the player chose Freeze new starts, or Staging map reset if the player chose Redraw staging now
- The reset clears floor space and makes parts easier to move and find
- Options:
    - Restart with a clean pull list
        - Gains 3-4 shifts through faster handoffs and fewer blocked stations
        - Adds one reschedule
    - Restart only critical lanes
        - Gains 2 shifts on the riskiest jobs
        - Some routine WIP remains slow
    - Resume the old queue
        - No reschedule churn
        - Only part of the freeze is recovered

Clean room cleared

- Flows from Cleanliness breach if the player chose Full reset
- The full reset qualifies the area for faster controlled work release
- Options:
    - Release all controlled work
        - Gains 4-5 shifts across clean-area subjobs
        - Crowds the controlled-area queue
    - Release the critical path only
        - Gains 2-3 shifts with less crowding
        - Leaves lower-risk work waiting
    - Keep normal release checks
        - Lowest quality risk
        - The two lost shifts are not recovered

Program template saved

- Flows from Software seat conflict if the player chose Reserve the next seat
- The reserved programming time produces a reusable program template
- Options:
    - Reuse it broadly
        - Saves 3-5 programming or verification shifts on similar subjobs
        - Adds a version-control risk if the family is not identical
    - Reuse it only on matching jobs
        - Saves 2-3 shifts
        - Leaves questionable jobs on the old path
    - Do not reuse it
        - No version risk
        - The reserved-seat delay has no upside

Gauge method locked

- Flows from either Gauge dispute if the player chose Run a formal study, or Reference sample missing if the player chose Switch to measured criteria
- The extra measurement work produces an accepted method for the whole feature family
- Options:
    - Standardize the method
        - Saves 1 acceptance shift on several future subjobs
        - Requires one reschedule to pull them forward
    - Use it on late jobs
        - Gains 2 shifts where lateness is likely
        - Does not improve the rest of the family
    - File the study only
        - Strong documentation
        - No schedule speedup

Operator qualified

- Flows from Training run if the player chose Train on low-risk work
- The newer operator is now qualified to cover the same capability
- Options:
    - Open a second lane
        - Gains 3-5 shifts by running compatible work in parallel
        - Adds supervision load for one day
    - Use them as relief
        - Prevents one future off-day or crew shortage delay
        - Smaller immediate gain
    - Keep them shadowing
        - No added risk
        - No near-term schedule recovery

Process tweak validated

- Flows from Floor walk insight if the player chose Apply it today
- The method improvement works and can be rolled into similar stations
- Options:
    - Roll it out now
        - Saves 1 shift on several future similar subjobs
        - Briefly slows each station during the change
    - Roll it out to one bottleneck
        - Gains 2-3 shifts with little disruption
        - Leaves other stations unchanged
    - Keep it local
        - No rollout disruption
        - The improvement stays small

Rack recovery sprint

- Flows from Rack shortage if the player chose Build temporary racks
- The temporary racks create a clean lane for closing and moving finished work
- Options:
    - Clear finished WIP first
        - Frees tied-up workcenters and gains 3-4 shifts
        - Delays a few new starts
    - Clear critical WIP first
        - Gains 2 shifts on the risky path
        - Leaves some stations still crowded
    - Leave racks as overflow
        - Prevents more crowding
        - Does not recover the earlier support time

Batch data accepted

- Flows from Batch window opens if the player chose Fill the batch
- The batch record is cleaner than expected and the whole group can be accepted together
- Options:
    - Close the batch as one
        - Gains 2-3 more shifts on compatible subjobs
        - Adds no extra risk beyond the original batch choice
    - Split only the urgent pieces
        - Gains 1-2 shifts on due work
        - Leaves the rest for normal closeout
    - Recheck each piece
        - Keeps maximum traceability
        - Gives up the extra batch benefit

Clamp marks found

- Flows from Shop air pressure dip if the player chose Run through it
- Running through weak shop air left clamp marks on several parts
- Options:
    - Rework affected parts
        - Adds 2-4 shifts of rework
        - Prevents the marks from reaching final inspection
    - Sort only critical parts
        - Adds 1-2 shifts now
        - Leaves some lower-priority rework risk active
    - Accept the marks
        - No immediate rework
        - Can create a larger final inspection delay later

Covered work reopened

- Flows from either Cleanliness breach if the player chose Continue under covers, or FOD sweep if protected WIP needs acceptance afterward
- Inspectors will not accept the covered work without reopening and checking it
- Options:
    - Reopen everything
        - Loses 3-4 shifts across the affected area
        - Clears the acceptance risk
    - Reopen only due work
        - Loses 2 shifts
        - Leaves routine work waiting for later review
    - Argue the containment
        - No immediate shop work
        - Adds audit risk and may block final closeout

Wrong revision loaded

- Flows from either Network folder offline if the player chose Use cached copies, or Traveler mismatch if the player chose Use the floor copy
- One cached or floor-controlled file was an older revision
- Options:
    - Correct the affected work
        - Adds 2-3 shifts to the subjob that used the stale file
        - Prevents the mistake from spreading
    - Stop the whole family
        - Loses 2 shifts across similar work
        - Confirms no other cached file is wrong
    - Patch only the next step
        - Smaller delay now
        - Leaves later rework risk

Phantom stock confirmed

- Flows from either Count variance if the player chose Consume visible stock, or Materials not here if the player chose Use another subjob's material
- The missing inventory was real, not a count error
- Options:
    - Strip parts from slack jobs
        - Keeps the urgent subjob alive
        - Delays lower-priority jobs 2-4 shifts
    - Stop the affected family
        - Blocks several starts until stock returns
        - Avoids stealing from other jobs
    - Keep searching
        - Loses 1 more shift
        - May still end with the same shortage

Fit check failed

- Flows from Burr cleanup if the player chose Release rough
- Downstream fitting finds the rough release damaged fit timing
- Options:
    - Pull it back for cleanup
        - Adds 2-3 shifts and one handoff delay
        - Protects later assembly work
    - Clean at the fitting station
        - Crowds the fitting lane for 2 shifts
        - Avoids an extra transport move
    - Force the fit
        - Saves time now
        - Can create final alignment rework

Cure failure found

- Flows from Cure clock if the player chose Force the next step
- The forced part fails a later cure or bond check
- Options:
    - Strip and redo
        - Adds 3-5 shifts
        - Restores the part to a clean route
    - Add a repair patch
        - Adds 2 shifts
        - Leaves extra inspection burden later
    - Keep building over it
        - Avoids immediate lost time
        - Greatly increases final rework risk

Vacuum trace failed

- Flows from Vacuum leak chase if the player chose Run with monitoring
- The monitoring record shows the leak crossed the allowed limit
- Options:
    - Scrap and restart the setup
        - Loses 3-4 shifts
        - Clears the process-risk tail
    - Rework the suspect zone
        - Loses 2 shifts
        - Leaves some acceptance risk
    - Ask for a deviation
        - No immediate rework
        - May trigger an audit or customer hold

Waste lane blocked

- Flows from Waste container full if the player chose Use small interim carts
- Interim carts have filled the waste lane and now block material movement
- Options:
    - Stop and clear the lane
        - Loses 2 shifts in the affected shop
        - Restores normal movement
    - Move the carts outside
        - Loses 1 shift
        - Adds compliance risk
    - Work around the lane
        - Keeps some work moving
        - Adds transport delay to every affected handoff

Sticker audit hit

- Flows from either Expired stickers if the player chose Keep using them, or Tool crib hold if the player chose Borrow substitutes
- A tool audit catches a calibration sticker problem after work has already moved on
- Options:
    - Reinspect affected work
        - Loses 2-3 shifts
        - Clears the documentation issue
    - Reinspect only critical work
        - Loses 1-2 shifts
        - Leaves routine work under a documentation flag
    - Contest the audit
        - No immediate reinspection
        - Adds certification risk near the end of the run

Weather cleared early

- Flows from Weather if the player chose Wait it out
- The weather cell moves through faster than forecast and the exposed stations can reopen cleanly
- Options:
    - Restart the held work first
        - Recovers 2-4 shifts on the subjobs that waited
        - Crowds those stations for the next shift
    - Restart critical work only
        - Recovers 1-2 shifts on the riskiest subjobs
        - Leaves routine work in the normal queue
    - Keep the revised queue
        - No reschedule churn
        - Loses most of the early-clear benefit

Setup mismatch found

- Flows from Workstation breakdown if the player chose Move affected subjobs
- The receiving machine can do the work, but its setup datum does not match the broken machine's plan
- Options:
    - Rework the moved setup
        - Adds 2-3 shifts to the moved subjob
        - Keeps the alternate route usable
    - Move the work back
        - Waits for the original machine
        - Avoids creating setup rework on the alternate route
    - Shim the mismatch
        - Loses 1 shift now
        - Adds later inspection risk

ECHO slack pocket found

- Flows from ECHO recommendation if the player chose Take advice
- The reshuffle exposed idle capacity that the manual queue was hiding
- Options:
    - Trust the full reshuffle
        - Gains 4-6 shifts across several subjobs
        - Adds visible reschedule churn
    - Use only the safe moves
        - Gains 2-3 shifts
        - Leaves some possible savings unused
    - Roll back the advice
        - Restores the old plan
        - The initial reshuffle delay becomes a pure loss

Replacement handoff check

- Flows from Worker took an off day if the player chose Find a replacement
- The replacement worker's handoff needs review before the next dependency trusts the work
- Options:
    - Check the handoff now
        - Loses 1 shift
        - Usually prevents rework
    - Let the replacement continue
        - No immediate delay
        - May add 2-3 shifts of rework if the handoff was misunderstood
    - Pair the replacement with a lead
        - Keeps the subjob moving
        - Slows another station for 1 shift

Returning worker shortcut

- Flows from Worker took an off day if the player chose Hold until the worker returns
- The returning worker already knows a faster safe setup for the paused work
- Options:
    - Use the shortcut
        - Recovers the lost shift and saves 1-2 more
        - Locks the subjob to that worker's station
    - Use only part of it
        - Recovers the lost shift
        - Avoids committing the whole route
    - Resume normally
        - No shortcut risk
        - The off-day delay remains
