"""Decision-card factories, templates, and player-facing text."""

from __future__ import annotations

import hashlib
import random

from ..config import GameConfig
from ..enums import DecisionType, EventType, JobStatus, TargetType
from ..metrics import update_state_metrics
from ..models import DecisionCard, DecisionChoice, Event, Job, Shop, SimulationState
from .selectors import (
    _alternate_routing_jobs,
    _handoff_risk_job,
    _has_idle_opportunity,
    _jobs_for_event,
    _quality_triage_job,
    _visible_events,
)

def _generate_scheduled_event_cards(
    state: SimulationState,
    day: int,
    config: GameConfig,
) -> list[DecisionCard]:
    """Build day-fixed decisions from the event timeline, independent of branch."""
    max_event_cards = max(1, min(2, config.max_active_decision_cards_per_day))
    cards: list[DecisionCard] = []
    for ordinal, event in enumerate(_visible_events(state)[:max_event_cards], start=1):
        card = _event_card(state, event, ordinal, day)
        card.id = f"CMP-D{day:02d}-EVENT-{event.id}"
        card.campaign_priority = ordinal
        cards.append(card)
    return cards

def _generate_root_decision_cards(
    state: SimulationState,
    day: int,
    config: GameConfig | None = None,
    include_events: bool = True,
) -> list[DecisionCard]:
    """Generate root cards used as fixed daily decision threads."""
    if config is None:
        config = GameConfig()
        update_state_metrics(state)
    rng = _decision_rng(state, day, config)
    target_count = rng.randint(config.min_decisions_per_day, config.max_decisions_per_day)
    selected: list[DecisionCard] = []
    candidate_pool: list[DecisionCard] = []

    # Keep the most urgent visible disruption in front of the player, then let
    # the rest compete with operational tradeoffs so later questions vary.
    visible_events = _visible_events(state) if include_events else []
    if visible_events:
        selected.append(_event_card(state, visible_events[0], 1, day))
        for event in visible_events[1:]:
            candidate_pool.append(_event_card(state, event, len(candidate_pool) + 1, day))

    candidate_pool.extend(_operational_decision_candidates(state, day, len(candidate_pool) + 1))
    candidate_pool = [card for card in candidate_pool if not _duplicates_any_card(selected, card)]
    candidate_pool.sort(key=lambda card: (rng.random() - card.severity * 0.14, card.type.value, card.title))

    for card in candidate_pool:
        if len(selected) >= target_count:
            break
        if _duplicates_any_card(selected, card):
            continue
        selected.append(card)

    if not selected:
        selected.append(_strategic_card(state, 1, day))
    while len(selected) < target_count:
        selected.append(_fallback_strategic_card(state, len(selected) + 1, day))
    return _renumber_decision_cards(selected, day)

def _operational_decision_candidates(state: SimulationState, day: int, start_ordinal: int = 1) -> list[DecisionCard]:
    """Build the broader daily candidate pool before seeded selection."""
    cards: list[DecisionCard] = []

    def add(card: DecisionCard | None) -> None:
        if card:
            cards.append(card)

    for shop in state.get_bottleneck_shops(3):
        pressure = len(shop.queued_job_ids) + len(shop.blocked_job_ids) * 2
        if pressure >= 2:
            add(_bottleneck_card(state, shop, start_ordinal + len(cards), day))
        if len(shop.queued_job_ids) >= 3:
            add(_queue_congestion_card(state, shop, start_ordinal + len(cards), day))

    for job in state.get_critical_path_jobs()[:3]:
        add(_critical_path_card(state, job, start_ordinal + len(cards), day))

    for job in _alternate_routing_jobs(state)[:3]:
        add(_alternate_card(state, job, start_ordinal + len(cards), day))

    handoff = _handoff_risk_job(state)
    if handoff:
        add(_handoff_card(state, handoff, start_ordinal + len(cards), day))

    quality = _quality_triage_job(state)
    if quality:
        add(_quality_triage_card(state, quality, start_ordinal + len(cards), day))

    if _has_idle_opportunity(state):
        add(_idle_card(state, start_ordinal + len(cards), day))
    if not state.all_pieces_ready():
        add(_completion_readiness_card(state, start_ordinal + len(cards), day))

    add(_strategic_card(state, start_ordinal + len(cards), day))
    return cards

def _duplicates_any_card(cards: list[DecisionCard], candidate: DecisionCard) -> bool:
    """Return whether a candidate repeats the same player-facing pressure."""
    candidate_targets = tuple(target for target in candidate.target_ids if not str(target).startswith("EVT-"))
    candidate_target_set = set(candidate_targets)
    candidate_key = (candidate.type, candidate_targets[:2], candidate.title)
    for card in cards:
        targets = tuple(target for target in card.target_ids if not str(target).startswith("EVT-"))
        if candidate_target_set and candidate_target_set & set(targets):
            return True
        if (card.type, targets[:2], card.title) == candidate_key:
            return True
    return False

def _renumber_decision_cards(cards: list[DecisionCard], day: int) -> list[DecisionCard]:
    """Normalize template IDs after the seeded variety pass chooses an order."""
    renumbered: list[DecisionCard] = []
    for ordinal, card in enumerate(cards, start=1):
        renumbered.append(
            DecisionCard(
                id=f"DAY-{day:02d}-DEC-{ordinal}",
                day=card.day,
                type=card.type,
                title=card.title,
                description=card.description,
                target_ids=list(card.target_ids),
                severity=card.severity,
                choices=_clone_choices(card.choices),
                echo_choice_id=card.echo_choice_id,
                required_tags=list(card.required_tags),
                excluded_tags=list(card.excluded_tags),
                campaign_priority=card.campaign_priority,
            )
        )
    return renumbered

def _decision_rng(state: SimulationState, day: int, config: GameConfig) -> random.Random:
    """Return a deterministic RNG for daily decision-card generation.

    The seed includes only replay-stable inputs, so the same scenario state and
    day always produce the same daily card count. It intentionally does not use
    the module-level random generator, which can be advanced by unrelated code.
    """
    seed_material = ":".join(
        str(part)
        for part in (
            state.seed,
            state.scenario_id,
            day,
            state.current_shift,
            config.min_decisions_per_day,
            config.max_decisions_per_day,
        )
    )
    seed_int = int.from_bytes(hashlib.sha256(seed_material.encode("utf-8")).digest()[:16], "big")
    return random.Random(seed_int)

def _clone_choices(choices: list[DecisionChoice]) -> list[DecisionChoice]:
    """Copy choice templates without carrying branch links between cards."""
    return [
        DecisionChoice(
            id=choice.id,
            label=choice.label,
            description=choice.description,
            immediate_effects=dict(choice.immediate_effects),
            risk_effect=choice.risk_effect,
            reschedule_effect=choice.reschedule_effect,
            next_card_id=choice.next_card_id,
            future_unlock_card_ids=list(choice.future_unlock_card_ids),
            branch_tags_added=list(choice.branch_tags_added),
            score_delta=choice.score_delta,
        )
        for choice in choices
    ]

def _capability_label(capability: str) -> str:
    """Return a readable capability name for decision text."""
    return capability.replace("_", " ")

def _piece_label(piece_id: str) -> str:
    """Return the decision-card label for a top-level job."""
    suffix = piece_id.split("-")[-1] if piece_id else ""
    return f"Job {suffix}" if suffix else "Job"

def _job_state_phrase(state: SimulationState, job: Job) -> str:
    """Summarize a job state without exposing hidden scoring values."""
    if job.is_blocked:
        return "blocked"
    if job.status == JobStatus.RUNNING:
        return "running"
    if job.status == JobStatus.QUEUED:
        return "queued"
    if job.status == JobStatus.READY:
        return "ready"
    if not state.is_dependency_complete(job.id):
        return "waiting on earlier work"
    return "not queued"

def _slack_phrase(state: SimulationState, job: Job) -> str:
    """Describe schedule slack qualitatively."""
    slack = job.due_shift - state.current_shift - job.remaining_duration_shifts
    if slack < 0:
        return "no slack"
    if slack <= 2:
        return "thin slack"
    if slack <= 6:
        return "tightening slack"
    return "some slack"

def _assigned_location_phrase(state: SimulationState, job: Job) -> str:
    """Describe the current assignment or best-known routing context."""
    if job.assigned_workcenter_id and job.assigned_workcenter_id in state.workcenters:
        wc = state.workcenters[job.assigned_workcenter_id]
        return f"at {wc.name}"
    shop = state.shops.get(job.shop_id)
    if shop:
        return f"in {shop.name}"
    return "not assigned"

def _job_context(state: SimulationState, job: Job) -> str:
    """Build a compact operational context sentence for a job."""
    detail = [f"{job.id} is {_job_state_phrase(state, job)}: {_slack_phrase(state, job)}, {_assigned_location_phrase(state, job)}."]
    if job.critical_path:
        detail.append("Delay here can hold later work.")
    elif job.dependent_job_ids:
        detail.append("It unlocks later work.")
    return " ".join(detail)

def _event_context(state: SimulationState, event: Event, status: str) -> str:
    """Describe why an event matters for the current operating board."""
    if event.type == EventType.UNEXPECTED_JOB:
        timing = "now" if status == "active" else "soon"
        return f"New job is due {timing}; it adds work to the build."
    jobs = _jobs_for_event(state, event)
    timing = "now" if status == "active" else "soon"
    if not jobs:
        return f"This hits {timing}. Your response changes later pressure."

    has_critical = any(job.critical_path for job in jobs)
    has_blocked = any(job.is_blocked for job in jobs)
    has_ready = any(job.status in {JobStatus.READY, JobStatus.QUEUED} for job in jobs)
    context: list[str] = [f"This hits {timing}"]
    if has_critical:
        context.append("near key work")
    elif has_ready:
        context.append("near work that can move")
    else:
        context.append("near later dependencies")
    if has_blocked:
        context.append("with blocked subjobs")
    return "; ".join(context) + "."

def _shop_pressure_description(state: SimulationState, shop: Shop) -> str:
    """Describe shop pressure without showing raw queue counts."""
    has_queued = bool(shop.queued_job_ids)
    has_blocked = bool(shop.blocked_job_ids)
    if has_queued and has_blocked:
        opening = "Queued and blocked work are building here."
    elif has_blocked:
        opening = "Blocked work is making this shop slow."
    elif has_queued:
        opening = "The queue is backing up here."
    else:
        opening = "This shop may become the next pinch point."

    critical_ids = {job.id for job in state.get_critical_path_jobs()}
    touches_critical = bool(critical_ids & (set(shop.queued_job_ids) | set(shop.blocked_job_ids)))
    if touches_critical:
        return f"{opening} Some key work is in the mix."
    return f"{opening} Pick a simple rule for today."

def _idle_capacity_description(state: SimulationState) -> str:
    """Describe the unused-capacity decision in operational terms."""
    ready_jobs = state.get_ready_jobs()
    critical_ready = any(job.critical_path for job in ready_jobs)
    if critical_ready:
        return "Stations are open while key work waits. Use them or keep a buffer?"
    return "Stations are open while work waits. Fill them or save room for trouble?"

def _completion_readiness_description(state: SimulationState) -> str:
    """Describe completion risk without exposing progress fractions."""
    incomplete = [piece for piece in state.pieces.values() if not piece.completed]
    if any(piece.risk_score >= 70 for piece in incomplete):
        return "Some unfinished jobs are getting risky. Pick what gets help today."
    return "The project still has unfinished jobs. Pick what moves first today."

def _event_card(state: SimulationState, event: Event, ordinal: int, day: int) -> DecisionCard:
    """Build a decision card around a specific visible event."""
    dtype = _decision_type_for_event(event.type)
    status = "active" if event.id in state.active_events else "warning"
    target = _target_name(state, event.target_type, event.target_id)
    if event.type == EventType.ECHO_RECOMMENDATION:
        return DecisionCard(
            id=f"DAY-{day:02d}-DEC-{ordinal}",
            day=day,
            type=dtype,
            title="ECHO can help today",
            description="ECHO has a schedule move. Use it or keep the manual plan?",
            target_ids=[event.target_id, event.id],
            severity=event.severity,
            choices=[
                DecisionChoice(
                    id="1",
                    label="Use ECHO",
                    description="Take ECHO's move for today's board.",
                    immediate_effects={"type": "echo_recommendation", "event_id": event.id},
                    risk_effect=-8,
                    reschedule_effect=1,
                ),
                DecisionChoice(
                    id="2",
                    label="Keep manual plan",
                    description="Skip the analysis and run the current plan.",
                    immediate_effects={"type": "wait", "event_id": event.id},
                    risk_effect=2,
                    reschedule_effect=0,
                ),
            ],
        )
    if event.type == EventType.UNEXPECTED_JOB:
        return DecisionCard(
            id=f"DAY-{day:02d}-DEC-{ordinal}",
            day=day,
            type=dtype,
            title="New job arrived",
            description=f"A customer added work. Put it up front or at the back?",
            target_ids=[event.target_id, event.id],
            severity=event.severity,
            choices=[
                DecisionChoice(
                    id="1",
                    label="Put it up front",
                    description="Add the job and start its first subjob soon.",
                    immediate_effects={"type": "prioritize_new_job", "event_id": event.id},
                    risk_effect=-2,
                    reschedule_effect=2,
                ),
                DecisionChoice(
                    id="2",
                    label="Put it at the back",
                    description="Accept it, but keep today's old work ahead.",
                    immediate_effects={"type": "backlog_new_job", "event_id": event.id},
                    risk_effect=4,
                    reschedule_effect=0,
                ),
            ],
        )
    choices = [
        DecisionChoice(
            id="1",
            label="Change the queue",
            description="Move ready work around the trouble spot.",
            immediate_effects={"type": "resequence", "event_id": event.id},
            risk_effect=-5,
            reschedule_effect=1,
        ),
        DecisionChoice(
            id="2",
            label="Fix it now",
            description="Spend effort to shorten the disruption.",
            immediate_effects={"type": "expedite_event", "event_id": event.id},
            risk_effect=-9,
            reschedule_effect=2,
        ),
    ]
    if event.type in {
        EventType.MACHINE_DOWN,
        EventType.MISSING_MATERIAL,
        EventType.DELAYED_MATERIAL,
        EventType.INSPECTION_DELAY,
        EventType.SUPPLIER_ESCALATION,
        EventType.LOGISTICS_BACKLOG,
        EventType.TOOLING_DAMAGE,
        EventType.CERTIFICATION_AUDIT,
    }:
        choices.append(
            DecisionChoice(
                id="3",
                label="Go around it",
                description="Move affected work to another capable station.",
                immediate_effects={"type": "reroute", "event_id": event.id},
                risk_effect=-6,
                reschedule_effect=1,
            )
        )
    else:
        choices.append(
            DecisionChoice(
                id="3",
                label="Ride it out",
                description="Keep the plan steady and absorb the risk.",
                immediate_effects={"type": "wait", "event_id": event.id},
                risk_effect=5,
                reschedule_effect=0,
            )
        )
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=dtype,
        title=f"{event.type.value} {status}",
        description=f"{target}: {event.description} {_event_context(state, event, status)}",
        target_ids=[event.target_id, event.id],
        severity=event.severity,
        choices=choices,
    )

def _bottleneck_card(state: SimulationState, shop: Shop, ordinal: int, day: int) -> DecisionCard:
    """Build a card for queue pressure concentrated in one shop."""
    queued = len(shop.queued_job_ids)
    blocked = len(shop.blocked_job_ids)
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.BOTTLENECK,
        title=f"{shop.name} is backing up",
        description=_shop_pressure_description(state, shop),
        target_ids=[shop.id],
        severity=min(5, 1 + queued // 4 + blocked // 2),
        choices=[
            DecisionChoice(
                id="1",
                label="Split the load",
                description="Move eligible work to other capable stations.",
                immediate_effects={"type": "split_capacity"},
                risk_effect=-7,
                reschedule_effect=2,
            ),
            DecisionChoice(
                id="2",
                label="Due dates first",
                description="Run the nearest due work first.",
                immediate_effects={"type": "resequence"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Push easy work back",
                description="Make room by delaying work with slack.",
                immediate_effects={"type": "defer"},
                risk_effect=-3,
                reschedule_effect=1,
            ),
        ],
    )

def _queue_congestion_card(state: SimulationState, shop: Shop, ordinal: int, day: int) -> DecisionCard:
    """Build a card for a shop queue that needs a dispatching rule."""
    queued_jobs = [state.jobs[job_id] for job_id in shop.queued_job_ids if job_id in state.jobs]
    critical_count = sum(1 for job in queued_jobs if job.critical_path)
    description = (
        f"{shop.name} has several subjobs waiting for the same kind of station. Pick the dispatch rule."
    )
    if critical_count:
        description += f" {critical_count} waiting subjob(s) matter a lot."
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.QUEUE_CONGESTION,
        title=f"{shop.name} queue is crowded",
        description=description,
        target_ids=[shop.id],
        severity=min(5, 2 + len(queued_jobs) // 3 + critical_count),
        choices=[
            DecisionChoice(
                id="1",
                label="Due dates first",
                description="Run the nearest due work first.",
                immediate_effects={"type": "resequence"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Split the queue",
                description="Move some work to other capable stations.",
                immediate_effects={"type": "split_capacity"},
                risk_effect=-6,
                reschedule_effect=2,
            ),
            DecisionChoice(
                id="3",
                label="Push slack back",
                description="Delay work that has room.",
                immediate_effects={"type": "defer"},
                risk_effect=-2,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Keep the line",
                description="Do not change the queue today.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
                reschedule_effect=0,
            ),
        ],
    )

def _critical_path_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    """Build a card for a subjob that threatens final completion timing."""
    piece_name = _piece_label(job.piece_id)
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.CRITICAL_PATH,
        title=f"{piece_name} is at risk",
        description=f"{piece_name} needs {_capability_label(job.required_capability)} work. {_job_context(state, job)}",
        target_ids=[job.id],
        severity=5 if job.risk_score >= 70 else 4,
        choices=[
            DecisionChoice(
                id="1",
                label="Protect this job",
                description="Put this dependency ahead of routine starts.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-6,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Reroute it",
                description="Move it to another capable station.",
                immediate_effects={"type": "reroute"},
                risk_effect=-6,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Bump lower work",
                description="Interrupt lower-priority work if it blocks this job.",
                immediate_effects={"type": "preempt"},
                risk_effect=-7,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Hold the line",
                description="Keep the queue steady and accept the risk.",
                immediate_effects={"type": "wait"},
                risk_effect=4,
                reschedule_effect=0,
            ),
        ],
    )

def _handoff_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    """Build a card around a cross-shop dependency handoff."""
    piece_name = _piece_label(job.piece_id)
    predecessor_names = [
        state.shops[state.jobs[dep_id].shop_id].name
        for dep_id in job.dependency_ids
        if dep_id in state.jobs and state.jobs[dep_id].shop_id in state.shops
    ]
    source = predecessor_names[0] if predecessor_names else "an upstream shop"
    destination = state.shops[job.shop_id].name if job.shop_id in state.shops else "the receiving shop"
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.PRIORITY_CHANGE,
        title=f"Handoff into {destination}",
        description=f"{piece_name} is moving from {source} to {destination}. {_job_context(state, job)}",
        target_ids=[job.id],
        severity=4 if job.critical_path or job.risk_score >= 55 else 3,
        choices=[
            DecisionChoice(
                id="1",
                label="Pull feeder work",
                description="Move earlier work up so the handoff is ready.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Hold a slot",
                description="Keep receiving capacity open for this handoff.",
                immediate_effects={"type": "resequence"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Reroute feeder",
                description="Use a different station if the current lane is tight.",
                immediate_effects={"type": "reroute"},
                risk_effect=-5,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Let shops sort it",
                description="Keep the handoff informal today.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
                reschedule_effect=0,
            ),
        ],
    )

def _alternate_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    """Build a card when a risky subjob has viable alternate routing."""
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.ALTERNATE_ROUTING,
        title=f"{job.id} has another route",
        description=f"{_capability_label(job.required_capability).title()} work can move. {_job_context(state, job)}",
        target_ids=[job.id],
        severity=3,
        choices=[
            DecisionChoice(
                id="1",
                label="Reroute it",
                description="Move the subjob to another capable station.",
                immediate_effects={"type": "reroute"},
                risk_effect=-6,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Wait one day",
                description="Keep the current queue and avoid setup churn.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
                reschedule_effect=0,
            ),
            DecisionChoice(
                id="3",
                label="Move similar work",
                description="Use the open route for related ready work.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
        ],
    )

def _quality_triage_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    """Build a card for preventive quality or rework containment."""
    piece_name = _piece_label(job.piece_id)
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.QUALITY_REWORK,
        title=f"{job.id} may need rework",
        description=f"{piece_name} has little room for a quality loop. {_job_context(state, job)}",
        target_ids=[job.id],
        severity=4 if job.critical_path or job.risk_score >= 55 else 3,
        choices=[
            DecisionChoice(
                id="1",
                label="Check it now",
                description="Add a quick containment check before it moves on.",
                immediate_effects={"type": "resequence"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Use clean capacity",
                description="Move it to a less crowded station.",
                immediate_effects={"type": "reroute"},
                risk_effect=-5,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Slow suspect starts",
                description="Hold lower-urgency starts until this clears.",
                immediate_effects={"type": "defer"},
                risk_effect=-2,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Wait for proof",
                description="Do nothing unless a defect is confirmed.",
                immediate_effects={"type": "wait"},
                risk_effect=4,
                reschedule_effect=0,
            ),
        ],
    )

def _idle_card(state: SimulationState, ordinal: int, day: int) -> DecisionCard:
    """Build a card for unused capacity while ready work exists."""
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.IDLE_WORKCENTER,
        title="A station is idle",
        description=_idle_capacity_description(state),
        target_ids=[],
        severity=3,
        choices=[
            DecisionChoice(
                id="1",
                label="Fill it now",
                description="Move ready work into the open station.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Save it",
                description="Keep the station open for trouble.",
                immediate_effects={"type": "wait"},
                risk_effect=2,
                reschedule_effect=0,
            ),
            DecisionChoice(
                id="3",
                label="Move short jobs",
                description="Use the open station for quick ready work.",
                immediate_effects={"type": "resequence"},
                risk_effect=-3,
                reschedule_effect=1,
            ),
        ],
    )

def _completion_readiness_card(state: SimulationState, ordinal: int, day: int) -> DecisionCard:
    """Build a card for late-stage readiness of remaining top-level jobs."""
    late_stage_day = max(1, int((state.deadline_shift / state.shifts_per_day) * 0.67))
    incomplete_pieces = sorted(
        [piece for piece in state.pieces.values() if not piece.completed],
        key=lambda piece: (-piece.risk_score, piece.estimated_completion_shift, piece.id),
    )
    target_ids = [piece.id for piece in incomplete_pieces[:3]]
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.COMPLETION_READINESS,
        title="Unfinished jobs remain",
        description=_completion_readiness_description(state),
        target_ids=target_ids,
        severity=4 if day >= late_stage_day else 3,
        choices=[
            DecisionChoice(
                id="1",
                label="Finish near-done jobs",
                description="Push jobs that are closest to complete.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-5,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Clear blockers",
                description="Spend effort where work is stuck.",
                immediate_effects={"type": "resequence"},
                risk_effect=-4,
                reschedule_effect=2,
            ),
            DecisionChoice(
                id="3",
                label="Keep a buffer",
                description="Avoid queue churn and save recovery room.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
                reschedule_effect=0,
            ),
        ],
    )

def _strategic_card(state: SimulationState, ordinal: int, day: int) -> DecisionCard:
    """Build a general strategy card when no sharper risk is available."""
    bottlenecks = state.get_bottleneck_shops(1)
    target_ids = [bottlenecks[0].id] if bottlenecks else []
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.STRATEGIC_PRIORITY,
        title="Pick today's rule",
        description="Several queues are close. What wins today?",
        target_ids=target_ids,
        severity=2,
        choices=[
            DecisionChoice(
                id="1",
                label="Due dates first",
                description="Run the work with the nearest due date.",
                immediate_effects={"type": "resequence"},
                risk_effect=-3,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Open stations first",
                description="Fill idle capacity before it is wasted.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Stable queues",
                description="Let the current shop order run.",
                immediate_effects={"type": "wait"},
                risk_effect=2,
                reschedule_effect=0,
            ),
        ],
    )

def _fallback_strategic_card(state: SimulationState, ordinal: int, day: int) -> DecisionCard:
    """Build extra broad-planning cards to satisfy the daily card count."""
    bottlenecks = state.get_bottleneck_shops(1)
    target_ids = [bottlenecks[0].id] if bottlenecks else []
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.STRATEGIC_PRIORITY,
        title=f"Small tradeoff {ordinal}",
        description="No single problem owns the day. Pick the shop rule.",
        target_ids=target_ids,
        severity=2,
        choices=[
            DecisionChoice(
                id="1",
                label="Rebalance work",
                description="Move attention toward urgent queues.",
                immediate_effects={"type": "resequence"},
                risk_effect=-2,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Pull work forward",
                description="Use open capacity before the day gets crowded.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-3,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Stay steady",
                description="Keep queues intact today.",
                immediate_effects={"type": "wait"},
                risk_effect=2,
                reschedule_effect=0,
            ),
        ],
    )

def _target_name(state: SimulationState, target_type: TargetType, target_id: str) -> str:
    """Resolve an event target into display text for a card description."""
    if target_type == TargetType.SHOP and target_id in state.shops:
        return state.shops[target_id].name
    if target_type == TargetType.WORKCENTER and target_id in state.workcenters:
        return state.workcenters[target_id].name
    if target_type == TargetType.PIECE and target_id in state.pieces:
        return _piece_label(target_id)
    return target_id

def _decision_type_for_event(event_type: EventType) -> DecisionType:
    """Map specific disruption types into broader decision-card categories."""
    return {
        EventType.MISSING_MATERIAL: DecisionType.MISSING_MATERIAL,
        EventType.DELAYED_MATERIAL: DecisionType.MISSING_MATERIAL,
        EventType.MACHINE_DOWN: DecisionType.MACHINE_DOWN,
        EventType.QUALITY_REWORK: DecisionType.QUALITY_REWORK,
        EventType.PRIORITY_CHANGE: DecisionType.PRIORITY_CHANGE,
        EventType.INSPECTION_DELAY: DecisionType.INSPECTION_DELAY,
        EventType.ENGINEERING_HOLD: DecisionType.ENGINEERING_HOLD,
        EventType.URGENT_JOB: DecisionType.URGENT_JOB,
        EventType.WEATHER: DecisionType.WEATHER,
        EventType.FACILITY_OUTAGE: DecisionType.WEATHER,
        EventType.SUPPLIER_ESCALATION: DecisionType.MISSING_MATERIAL,
        EventType.LOGISTICS_BACKLOG: DecisionType.MISSING_MATERIAL,
        EventType.TOOLING_DAMAGE: DecisionType.MACHINE_DOWN,
        EventType.CREW_SHORTAGE: DecisionType.BOTTLENECK,
        EventType.REWORK_SPILLOVER: DecisionType.QUALITY_REWORK,
        EventType.CERTIFICATION_AUDIT: DecisionType.INSPECTION_DELAY,
        EventType.ENGINEERING_DATA_REVISION: DecisionType.ENGINEERING_HOLD,
        EventType.UNEXPECTED_JOB: DecisionType.UNEXPECTED_JOB,
        EventType.ECHO_RECOMMENDATION: DecisionType.ECHO_RECOMMENDATION,
    }[event_type]
