"""Event generation, event effects, and downstream disruption cascades."""

from __future__ import annotations

from random import Random
from typing import Iterable

from .config import GameConfig
from .enums import EventType, JobStatus, TargetType, WorkCenterStatus
from .models import Event, Job, PuzzlePiece, Shop, SimulationState, WorkCenter


EVENT_SEQUENCE = [
    EventType.DELAYED_MATERIAL,
    EventType.MISSING_MATERIAL,
    EventType.MACHINE_DOWN,
    EventType.QUALITY_REWORK,
    EventType.PRIORITY_CHANGE,
    EventType.INSPECTION_DELAY,
    EventType.ENGINEERING_HOLD,
    EventType.URGENT_JOB,
    EventType.WEATHER,
    EventType.FACILITY_OUTAGE,
    EventType.SUPPLIER_ESCALATION,
    EventType.LOGISTICS_BACKLOG,
    EventType.TOOLING_DAMAGE,
    EventType.CREW_SHORTAGE,
    EventType.REWORK_SPILLOVER,
    EventType.CERTIFICATION_AUDIT,
    EventType.ENGINEERING_DATA_REVISION,
    EventType.UNEXPECTED_JOB,
]

MAX_EVENT_CHAIN_DEPTH = 2
ECHO_RECOMMENDATION_PROBABILITY = 0.18
UNEXPECTED_JOB_NAMES = [
    "Surge",
    "Harbor",
    "Keystone",
    "Meridian",
    "Northstar",
    "Outrider",
]


def generate_event_timeline(
    rng: Random,
    config: GameConfig,
    shops: dict[str, Shop],
    workcenters: dict[str, WorkCenter],
    pieces: dict[str, PuzzlePiece],
    jobs: dict[str, Job],
) -> list[Event]:
    """Build the base disruption timeline for a scenario."""
    deadline = config.deadline_shift
    all_jobs = list(jobs.values())
    timeline: list[Event] = []
    base_event_count = rng.randint(config.min_base_events, config.max_base_events)
    extra_rework_count = rng.randint(
        config.min_extra_quality_rework_events,
        config.max_extra_quality_rework_events,
    )
    if base_event_count <= 0 and extra_rework_count <= 0:
        return timeline
    if base_event_count < len(EVENT_SEQUENCE):
        event_types = rng.sample(EVENT_SEQUENCE, k=base_event_count)
    else:
        filler_count = max(0, base_event_count - len(EVENT_SEQUENCE))
        # The full-game catalog guarantees broad variety, then extra/filler
        # events create enough density that a player cannot absorb everything.
        event_types = (
            EVENT_SEQUENCE
            + [rng.choice(EVENT_SEQUENCE) for _ in range(filler_count)]
        )
    event_types.extend(EventType.QUALITY_REWORK for _ in range(extra_rework_count))
    rng.shuffle(event_types)
    if rng.random() < ECHO_RECOMMENDATION_PROBABILITY:
        event_types.append(EventType.ECHO_RECOMMENDATION)
        rng.shuffle(event_types)

    # Force early warning variety without overwriting explicit extra rework.
    replaceable_indexes = [
        index
        for index, event_type in enumerate(event_types)
        if event_type != EventType.QUALITY_REWORK
    ]
    if replaceable_indexes and EventType.WEATHER not in event_types:
        event_types[replaceable_indexes[0]] = EventType.WEATHER
    if len(replaceable_indexes) > 1 and EventType.DELAYED_MATERIAL not in event_types:
        event_types[replaceable_indexes[1]] = EventType.DELAYED_MATERIAL

    for index, event_type in enumerate(event_types, start=1):
        latest_start = deadline - 5
        if event_type == EventType.ECHO_RECOMMENDATION:
            latest_start = max(6, deadline - 3)
        elif event_type == EventType.UNEXPECTED_JOB:
            latest_start = max(6, deadline - 6)
        elif event_type in {EventType.URGENT_JOB, EventType.QUALITY_REWORK}:
            latest_start = deadline - 11
        elif event_type in {EventType.ENGINEERING_HOLD, EventType.FACILITY_OUTAGE}:
            latest_start = deadline - 8
        start_shift = rng.randint(5, max(6, latest_start))
        severity = rng.randint(1, 5)
        duration = _duration_for(event_type, severity, rng)
        target_type, target_id = _target_for(event_type, rng, shops, workcenters, pieces, all_jobs)
        has_warning = event_type in {
            EventType.WEATHER,
            EventType.DELAYED_MATERIAL,
            EventType.UNEXPECTED_JOB,
        } or rng.random() < 0.22
        warning_shift = None
        if has_warning:
            lead_time = config.shifts_per_day if event_type == EventType.UNEXPECTED_JOB else rng.randint(2, 7)
            warning_shift = max(1, start_shift - lead_time)
        event = Event(
            id=f"EVT-{index:04d}",
            type=event_type,
            target_type=target_type,
            target_id=target_id,
            start_shift=start_shift,
            duration_shifts=duration,
            severity=severity,
            has_advance_warning=has_warning,
            warning_shift=warning_shift,
            description=_description_for(event_type, target_type, target_id, severity),
            effects={},
        )
        timeline.append(event)
    return sorted(timeline, key=lambda event: (event.start_shift, event.id))


def _duration_for(event_type: EventType, severity: int, rng: Random) -> int:
    """Choose an event duration, scaling severe events without exceeding caps."""
    base = {
        EventType.MISSING_MATERIAL: (2, 5),
        EventType.DELAYED_MATERIAL: (2, 6),
        EventType.MACHINE_DOWN: (1, 5),
        EventType.QUALITY_REWORK: (1, 3),
        EventType.PRIORITY_CHANGE: (1, 1),
        EventType.INSPECTION_DELAY: (1, 4),
        EventType.ENGINEERING_HOLD: (2, 6),
        EventType.URGENT_JOB: (1, 1),
        EventType.WEATHER: (2, 5),
        EventType.FACILITY_OUTAGE: (1, 4),
        EventType.SUPPLIER_ESCALATION: (2, 5),
        EventType.LOGISTICS_BACKLOG: (2, 5),
        EventType.TOOLING_DAMAGE: (2, 4),
        EventType.CREW_SHORTAGE: (1, 3),
        EventType.REWORK_SPILLOVER: (1, 3),
        EventType.CERTIFICATION_AUDIT: (2, 4),
        EventType.ENGINEERING_DATA_REVISION: (1, 3),
        EventType.UNEXPECTED_JOB: (1, 1),
        EventType.ECHO_RECOMMENDATION: (1, 1),
    }[event_type]
    return min(8, rng.randint(*base) + max(0, severity - 3))


def _target_for(
    event_type: EventType,
    rng: Random,
    shops: dict[str, Shop],
    workcenters: dict[str, WorkCenter],
    pieces: dict[str, PuzzlePiece],
    jobs: list[Job],
) -> tuple[TargetType, str]:
    """Pick a target object appropriate for the event type."""
    if event_type in {EventType.MACHINE_DOWN, EventType.TOOLING_DAMAGE}:
        return TargetType.WORKCENTER, rng.choice(list(workcenters.keys()))
    if event_type in {EventType.WEATHER, EventType.FACILITY_OUTAGE, EventType.CREW_SHORTAGE, EventType.LOGISTICS_BACKLOG}:
        return TargetType.SHOP, rng.choice(list(shops.keys()))
    if event_type in {
        EventType.ENGINEERING_HOLD,
        EventType.REWORK_SPILLOVER,
        EventType.CERTIFICATION_AUDIT,
        EventType.ENGINEERING_DATA_REVISION,
    }:
        return TargetType.PIECE, rng.choice(list(pieces.keys()))
    if event_type == EventType.URGENT_JOB:
        return TargetType.PIECE, rng.choice(list(pieces.keys()))
    if event_type == EventType.PRIORITY_CHANGE and rng.random() < 0.35:
        return TargetType.PIECE, rng.choice(list(pieces.keys()))
    if event_type == EventType.ECHO_RECOMMENDATION:
        return TargetType.CAPABILITY, "ECHO"
    if event_type == EventType.UNEXPECTED_JOB:
        return TargetType.CAPABILITY, "NEW_JOB"
    return TargetType.JOB, rng.choice(jobs).id


def _description_for(event_type: EventType, target_type: TargetType, target_id: str, severity: int) -> str:
    """Return the player-facing description for an event."""
    target = target_id.replace("-", " ")
    if event_type == EventType.MISSING_MATERIAL:
        return f"Material kit for {target} is missing at release check."
    if event_type == EventType.DELAYED_MATERIAL:
        return f"Material arrival risk is reported for {target}."
    if event_type == EventType.MACHINE_DOWN:
        return f"{target} has an unplanned equipment fault."
    if event_type == EventType.QUALITY_REWORK:
        return f"Quality review flags extra work on {target}."
    if event_type == EventType.PRIORITY_CHANGE:
        return f"Priority signal changes for {target}; downstream order may need revision."
    if event_type == EventType.INSPECTION_DELAY:
        return f"Inspection availability slips for {target}."
    if event_type == EventType.ENGINEERING_HOLD:
        return f"Engineering hold placed on {target} pending clarification."
    if event_type == EventType.URGENT_JOB:
        return f"Urgent required work is inserted into {target}."
    if event_type == EventType.WEATHER:
        return f"Weather exposure may reduce throughput in {target}."
    if event_type == EventType.FACILITY_OUTAGE:
        return f"Facility interruption affects {target}."
    if event_type == EventType.SUPPLIER_ESCALATION:
        return f"Supplier recovery plan slips for {target}; substitute flow may be needed."
    if event_type == EventType.LOGISTICS_BACKLOG:
        return f"Internal logistics backlog delays movement through {target}."
    if event_type == EventType.TOOLING_DAMAGE:
        return f"Tooling damage is found at {target}; setup and recovery will take extra time."
    if event_type == EventType.CREW_SHORTAGE:
        return f"Crew availability drops in {target}; available capacity is reduced."
    if event_type == EventType.REWORK_SPILLOVER:
        return f"Related quality findings spread into {target}."
    if event_type == EventType.CERTIFICATION_AUDIT:
        return f"Certification audit requests additional evidence for {target}."
    if event_type == EventType.ENGINEERING_DATA_REVISION:
        return f"Engineering data revision changes acceptance criteria for {target}."
    if event_type == EventType.UNEXPECTED_JOB:
        return "A new customer job arrived outside the initial job list."
    if event_type == EventType.ECHO_RECOMMENDATION:
        return "Someone is working on this app called ECHO; would you want to use its recommendation?"
    return f"Severity {severity} disruption affects {target_type.value} {target_id}."


def refresh_event_state(state: SimulationState) -> None:
    """Apply warnings, starts, resolutions, and countdown updates for a shift."""
    current = state.current_shift
    # Warnings become visible before event start, giving schedulers and players
    # a chance to mitigate a future disruption.
    for event in state.event_timeline:
        if event.has_advance_warning and event.warning_shift == current and event.id not in state.known_warnings:
            state.known_warnings.append(event.id)
            state.daily_notes.append(f"Warning received: {event.description}")

    # Resolve first so a workcenter/job can become available before newly
    # starting events for the same shift are applied.
    for event in state.event_timeline:
        if event.started and not event.resolved and current >= event.end_shift:
            resolve_event(state, event)

    for event in state.event_timeline:
        if not event.started and event.start_shift == current:
            apply_event_start(state, event)

    for event in state.event_timeline:
        if event.started and not event.resolved:
            remaining = max(0, event.end_shift - current)
            for wc_id in event.effects.get("workcenter_ids", []):
                if wc_id in state.workcenters:
                    state.workcenters[wc_id].downtime_remaining = remaining


def apply_event_start(state: SimulationState, event: Event) -> None:
    """Apply the immediate state mutation caused by a newly active event."""
    event.started = True
    if event.id not in state.active_events:
        state.active_events.append(event.id)
    state.daily_notes.append(f"Disruption active: {event.description}")
    if event.id in state.known_warnings:
        state.known_warnings.remove(event.id)

    if event.type in {
        EventType.MISSING_MATERIAL,
        EventType.DELAYED_MATERIAL,
        EventType.INSPECTION_DELAY,
        EventType.SUPPLIER_ESCALATION,
        EventType.LOGISTICS_BACKLOG,
        EventType.CERTIFICATION_AUDIT,
    }:
        _block_target_jobs(state, event, reason=event.type.value)
    elif event.type in {EventType.MACHINE_DOWN, EventType.TOOLING_DAMAGE}:
        _set_workcenters_down(state, event, [event.target_id], WorkCenterStatus.DOWN, event.type.value)
    elif event.type in {EventType.ENGINEERING_HOLD, EventType.ENGINEERING_DATA_REVISION}:
        job_ids = list(state.pieces[event.target_id].job_ids)
        _block_jobs(state, event, job_ids, reason=event.type.value)
    elif event.type in {EventType.QUALITY_REWORK, EventType.REWORK_SPILLOVER}:
        _apply_quality_rework(state, event)
    elif event.type == EventType.PRIORITY_CHANGE:
        _apply_priority_change(state, event)
    elif event.type == EventType.URGENT_JOB:
        _insert_urgent_job(state, event)
    elif event.type == EventType.UNEXPECTED_JOB:
        insert_unexpected_job(state, event, prioritize=False)
    elif event.type == EventType.WEATHER:
        shop = state.shops[event.target_id]
        affected = _sample_ids(shop.workcenter_ids, max(2, len(shop.workcenter_ids) // 3))
        _set_workcenters_down(state, event, affected, WorkCenterStatus.WEATHER_IMPACTED, event.type.value)
    elif event.type == EventType.FACILITY_OUTAGE:
        shop = state.shops[event.target_id]
        affected = _sample_ids(shop.workcenter_ids, max(3, len(shop.workcenter_ids) // 4))
        _set_workcenters_down(state, event, affected, WorkCenterStatus.BLOCKED, event.type.value)
    elif event.type == EventType.CREW_SHORTAGE:
        shop = state.shops[event.target_id]
        affected = _sample_ids(shop.workcenter_ids, max(1, len(shop.workcenter_ids) // 4))
        _set_workcenters_down(state, event, affected, WorkCenterStatus.BLOCKED, event.type.value)


def resolve_event(state: SimulationState, event: Event) -> None:
    """Clear reversible event effects and evaluate downstream cascade risk."""
    event.resolved = True
    if event.id in state.active_events:
        state.active_events.remove(event.id)

    for job_id in event.effects.get("blocked_job_ids", []):
        if job_id not in state.jobs:
            continue
        job = state.jobs[job_id]
        # Block reasons include the event id, so resolution only clears blocks
        # caused by this event and leaves overlapping disruptions intact.
        if job.status != JobStatus.COMPLETE and job.block_reason and event.id in job.block_reason:
            job.block_reason = None
            job.status = JobStatus.READY if state.is_dependency_complete(job.id) else JobStatus.NOT_READY
            state.blocked_jobs.discard(job.id)

    for wc_id in event.effects.get("workcenter_ids", []):
        if wc_id not in state.workcenters:
            continue

        wc = state.workcenters[wc_id]

        overlapping_event = _active_workcenter_event_for(state, wc_id)
        if overlapping_event:
            wc.status = _workcenter_status_for_event(overlapping_event)
            wc.downtime_remaining = max(0, overlapping_event.end_shift - state.current_shift)
            wc.blocked_reason = f"{overlapping_event.id}: {overlapping_event.type.value}"

            if wc.current_job_id and wc.current_job_id in state.jobs:
                state.jobs[wc.current_job_id].status = JobStatus.PAUSED

            continue

        wc.downtime_remaining = 0
        wc.blocked_reason = None

        if wc.current_job_id:
            job = state.jobs[wc.current_job_id]
            job.status = JobStatus.RUNNING
            wc.status = WorkCenterStatus.BUSY
        else:
            wc.status = WorkCenterStatus.AVAILABLE

    _schedule_cascading_events(state, event)
    state.daily_notes.append(f"Resolved: {event.description}")


def _active_workcenter_event_for(state: SimulationState, wc_id: str) -> Event | None:
    """Return another active event that still disrupts the workcenter."""
    candidates = [
        active_event
        for active_event in state.event_timeline
        if active_event.started
        and not active_event.resolved
        and wc_id in active_event.effects.get("workcenter_ids", [])
    ]

    if not candidates:
        return None

    return max(candidates, key=lambda active_event: (active_event.end_shift, active_event.start_shift, active_event.id))


def _workcenter_status_for_event(event: Event) -> WorkCenterStatus:
    """Return the workcenter status produced by a workcenter-disruption event."""
    if event.type in {EventType.MACHINE_DOWN, EventType.TOOLING_DAMAGE}:
        return WorkCenterStatus.DOWN

    if event.type == EventType.WEATHER:
        return WorkCenterStatus.WEATHER_IMPACTED

    return WorkCenterStatus.BLOCKED


def _block_target_jobs(state: SimulationState, event: Event, reason: str) -> None:
    """Expand an event target into concrete jobs and block them."""
    if event.target_type == TargetType.JOB:
        _block_jobs(state, event, [event.target_id], reason)
    elif event.target_type == TargetType.PIECE:
        _block_jobs(state, event, state.pieces[event.target_id].job_ids, reason)
    elif event.target_type == TargetType.SHOP:
        jobs = [job.id for job in state.jobs.values() if job.shop_id == event.target_id and not job.is_complete]
        _block_jobs(state, event, jobs, reason)


def _block_jobs(state: SimulationState, event: Event, job_ids: Iterable[str], reason: str) -> None:
    """Block jobs and record exactly which ones this event must later release."""
    affected: list[str] = []
    for job_id in job_ids:
        if job_id not in state.jobs:
            continue
        job = state.jobs[job_id]
        if job.status == JobStatus.COMPLETE:
            continue
        state.remove_job_from_queues(job_id)
        job.status = JobStatus.BLOCKED
        job.block_reason = f"{event.id}: {reason}"
        affected.append(job_id)
        state.blocked_jobs.add(job_id)
        if job.assigned_workcenter_id:
            wc = state.workcenters[job.assigned_workcenter_id]
            if wc.current_job_id == job_id:
                wc.current_job_id = None
                wc.status = WorkCenterStatus.AVAILABLE
    event.effects.setdefault("blocked_job_ids", []).extend(affected)


def _set_workcenters_down(
    state: SimulationState,
    event: Event,
    workcenter_ids: list[str],
    status: WorkCenterStatus,
    reason: str,
) -> None:
    """Set workcenters into a disrupted status and pause their current jobs."""
    affected: list[str] = []
    for wc_id in workcenter_ids:
        if wc_id not in state.workcenters:
            continue
        wc = state.workcenters[wc_id]
        wc.status = status
        wc.downtime_remaining = event.duration_shifts
        wc.blocked_reason = f"{event.id}: {reason}"
        affected.append(wc_id)
        if wc.current_job_id:
            job = state.jobs[wc.current_job_id]
            job.status = JobStatus.PAUSED
            job.risk_score += event.severity * 2
    event.effects.setdefault("workcenter_ids", []).extend(affected)


def _apply_quality_rework(state: SimulationState, event: Event) -> None:
    """Add rework to incomplete jobs or insert follow-on work for completed jobs."""
    target_id = event.target_id
    if event.target_type == TargetType.PIECE and target_id in state.pieces:
        candidates = [
            state.jobs[job_id]
            for job_id in state.pieces[target_id].job_ids
            if job_id in state.jobs and not state.jobs[job_id].is_complete
        ]
        for job in sorted(candidates, key=lambda item: (-item.risk_score, item.due_shift))[: max(1, event.severity // 2)]:
            job.rework_count += 1
            job.remaining_duration_shifts += max(1, event.severity // 2)
            job.status = JobStatus.REWORK_REQUIRED if not job.block_reason else job.status
            job.risk_score += event.severity * 4
            event.effects.setdefault("rework_job_ids", []).append(job.id)
        return
    if target_id not in state.jobs:
        return
    job = state.jobs[target_id]
    job.rework_count += 1
    if job.status == JobStatus.COMPLETE:
        new_job = _create_follow_on_job(
            state,
            event,
            piece_id=job.piece_id,
            shop_id=job.shop_id,
            capability=job.required_capability,
            dependencies=[job.id],
            duration=max(1, event.severity),
            priority=job.priority + 12,
        )
        new_job.rework_count = 1
    else:
        job.remaining_duration_shifts += max(1, event.severity)
        job.status = JobStatus.REWORK_REQUIRED if not job.block_reason else job.status
        job.risk_score += event.severity * 4


def _apply_priority_change(state: SimulationState, event: Event) -> None:
    """Raise priority and pull due dates forward for affected jobs."""
    if event.target_type == TargetType.PIECE:
        targets = [state.jobs[job_id] for job_id in state.pieces[event.target_id].job_ids]
    else:
        targets = [state.jobs[event.target_id]] if event.target_id in state.jobs else []
    for job in targets:
        if job.status != JobStatus.COMPLETE:
            job.priority += 15 + event.severity * 3
            job.due_shift = max(state.current_shift + 2, job.due_shift - event.severity * 2)
            job.risk_score += event.severity * 2
    event.effects["priority_job_ids"] = [job.id for job in targets]
    state.reschedule_count += 1


def _insert_urgent_job(state: SimulationState, event: Event) -> None:
    """Insert a new required subjob into a top-level job during the active run."""
    piece_id = event.target_id
    piece = state.pieces[piece_id]
    existing_jobs = [state.jobs[job_id] for job_id in piece.job_ids]
    completed = [job for job in existing_jobs if job.status == JobStatus.COMPLETE]
    if completed:
        anchor = max(completed, key=lambda job: job.completed_shift or 0)
        dependencies = [anchor.id]
    else:
        anchor = min(existing_jobs, key=lambda job: job.due_shift)
        dependencies = list(anchor.dependency_ids)
    new_job = _create_follow_on_job(
        state,
        event,
        piece_id=piece_id,
        shop_id=anchor.shop_id,
        capability=anchor.required_capability,
        dependencies=dependencies,
        duration=1 + min(2, max(1, event.severity // 2)),
        priority=85 + event.severity,
    )


def insert_unexpected_job(state: SimulationState, event: Event, prioritize: bool) -> str:
    """Insert or reprioritize a new top-level job caused by an unexpected request."""
    piece_id = event.effects.get("unexpected_piece_id")
    if piece_id in state.pieces:
        effective_prioritize = prioritize or event.effects.get("priority_mode") == "prioritized"
        _set_unexpected_job_priority(state, piece_id, effective_prioritize)
        event.effects["priority_mode"] = "prioritized" if effective_prioritize else "backlog"
        return piece_id

    rng = Random(f"{state.seed}:{event.id}:unexpected-job")
    piece_index = _next_piece_index(state)
    piece_id = f"PIECE-{piece_index:02d}"
    piece_name = UNEXPECTED_JOB_NAMES[(piece_index - 1) % len(UNEXPECTED_JOB_NAMES)]
    job_count = min(4, max(2, 2 + event.severity // 2))
    priority = 92 if prioritize else 32
    piece_job_ids: list[str] = []
    previous_job_id: str | None = None

    shop_ids = list(state.shops.keys())
    dominant_shop_id = rng.choice(shop_ids)
    for job_index in range(1, job_count + 1):
        shop_id = dominant_shop_id if rng.random() < 0.6 else rng.choice(shop_ids)
        shop = state.shops[shop_id]
        capability = rng.choice(shop.capabilities)
        candidate_ids = _candidate_workcenters_for_state(state, capability, shop_id, rng)
        duration = rng.randint(1, 2 if prioritize else 3)
        job_id = f"JOB-{piece_index:02d}-{job_index:03d}"
        dependency_ids = [previous_job_id] if previous_job_id else []
        due_shift = _unexpected_due_shift(state, job_index, job_count, prioritize)

        state.jobs[job_id] = Job(
            id=job_id,
            piece_id=piece_id,
            shop_id=shop_id,
            required_capability=capability,
            candidate_workcenter_ids=candidate_ids,
            assigned_workcenter_id=None,
            base_duration_shifts=duration,
            remaining_duration_shifts=duration,
            setup_time_shifts=0,
            transport_delay_shifts=0,
            dependency_ids=dependency_ids,
            status=JobStatus.NOT_READY,
            priority=max(10, priority - job_index * 2),
            due_shift=due_shift,
            risk_score=float(18 + event.severity * 4),
        )
        if previous_job_id and previous_job_id in state.jobs:
            state.jobs[previous_job_id].dependent_job_ids.append(job_id)
        previous_job_id = job_id
        piece_job_ids.append(job_id)

    state.pieces[piece_id] = PuzzlePiece(
        id=piece_id,
        name=f"Job {piece_index:02d} - {piece_name}",
        job_ids=piece_job_ids,
        total_job_count=len(piece_job_ids),
    )
    event.effects["unexpected_piece_id"] = piece_id
    event.effects["inserted_job_ids"] = list(piece_job_ids)
    event.effects["priority_mode"] = "prioritized" if prioritize else "backlog"

    _set_unexpected_job_priority(state, piece_id, prioritize)
    state.daily_notes.append(
        f"Added unexpected job {piece_id} to the submarine build "
        f"({'prioritized' if prioritize else 'back of queue'})."
    )
    return piece_id


def _set_unexpected_job_priority(state: SimulationState, piece_id: str, prioritize: bool) -> None:
    """Apply queue priority for the unexpected top-level job."""
    piece = state.pieces[piece_id]
    for index, job_id in enumerate(piece.job_ids):
        job = state.jobs[job_id]
        if job.is_complete:
            continue
        if prioritize:
            job.priority = max(job.priority, 94 - index * 3)
            job.due_shift = max(state.current_shift + 1, min(job.due_shift, state.current_shift + 2 + index * 2))
        else:
            job.priority = min(job.priority, 38 + index * 2)

    first_job = state.jobs[piece.job_ids[0]]
    if first_job.status == JobStatus.COMPLETE:
        return
    first_job.status = JobStatus.READY if not first_job.dependency_ids else first_job.status
    wc_id = _best_workcenter_for_job(state, first_job)
    if wc_id:
        state.assign_job(first_job.id, wc_id, front=prioritize)


def _next_piece_index(state: SimulationState) -> int:
    """Return the next top-level job index."""
    max_index = 0
    for piece_id in state.pieces:
        suffix = piece_id.split("-")[-1]
        if suffix.isdigit():
            max_index = max(max_index, int(suffix))
    return max_index + 1


def _unexpected_due_shift(state: SimulationState, job_index: int, job_count: int, prioritize: bool) -> int:
    """Pick due shifts for a runtime-added top-level job."""
    remaining = max(1, state.deadline_shift - state.current_shift - 1)
    if prioritize:
        offset = min(remaining, 2 + job_index * 2)
    else:
        offset = max(job_index + 1, int((job_index / job_count) * remaining))
    return max(state.current_shift + 1, min(state.deadline_shift - 1, state.current_shift + offset))


def _candidate_workcenters_for_state(
    state: SimulationState,
    capability: str,
    primary_shop_id: str,
    rng: Random,
) -> list[str]:
    """Return capable workcenters for a runtime-created job."""
    primary = [
        wc.id
        for wc in state.workcenters.values()
        if wc.shop_id == primary_shop_id and capability in wc.capabilities
    ]
    alternates = [
        wc.id
        for wc in state.workcenters.values()
        if wc.shop_id != primary_shop_id and capability in wc.capabilities
    ]
    rng.shuffle(primary)
    rng.shuffle(alternates)
    candidate_ids = primary[:3] + alternates[:3]
    return candidate_ids or [wc.id for wc in state.workcenters.values() if capability in wc.capabilities]


def _best_workcenter_for_job(state: SimulationState, job: Job) -> str | None:
    """Return a capable queue target for a runtime-added job."""
    candidates = [
        state.workcenters[wc_id]
        for wc_id in job.candidate_workcenter_ids
        if wc_id in state.workcenters
        and job.required_capability in state.workcenters[wc_id].capabilities
        and state.workcenters[wc_id].status
        not in {WorkCenterStatus.DOWN, WorkCenterStatus.BLOCKED, WorkCenterStatus.WEATHER_IMPACTED}
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda wc: (
            len(wc.queue) + (1 if wc.current_job_id else 0),
            0 if wc.shop_id == job.shop_id else 1,
            wc.id,
        ),
    ).id


def _create_follow_on_job(
    state: SimulationState,
    event: Event,
    piece_id: str,
    shop_id: str,
    capability: str,
    dependencies: list[str],
    duration: int,
    priority: int,
) -> Job:
    """Create a generated subjob caused by rework or urgent inserted work."""
    piece = state.pieces[piece_id]
    job_id = _next_subjob_id(state, piece_id)
    candidate_ids = [
        wc.id for wc in state.workcenters.values() if capability in wc.capabilities
    ]
    job = Job(
        id=job_id,
        piece_id=piece_id,
        shop_id=shop_id,
        required_capability=capability,
        candidate_workcenter_ids=candidate_ids,
        assigned_workcenter_id=None,
        base_duration_shifts=duration,
        remaining_duration_shifts=duration,
        setup_time_shifts=0,
        transport_delay_shifts=0,
        dependency_ids=list(dependencies),
        status=JobStatus.NOT_READY,
        priority=priority,
        due_shift=min(state.deadline_shift - 1, state.current_shift + 5),
        risk_score=event.severity * 4,
    )
    state.jobs[job.id] = job
    piece.job_ids.append(job.id)
    piece.total_job_count += 1
    for dep_id in dependencies:
        if dep_id in state.jobs and job.id not in state.jobs[dep_id].dependent_job_ids:
            state.jobs[dep_id].dependent_job_ids.append(job.id)
    event.effects.setdefault("inserted_job_ids", []).append(job.id)
    state.daily_notes.append(f"Inserted required subjob {job.id} into {piece.name}.")
    return job


def _next_subjob_id(state: SimulationState, piece_id: str) -> str:
    """Return the next JOB-XX-XXX id for a top-level job."""
    prefix = f"JOB-{piece_id.split('-')[-1]}-"
    max_index = 0
    for job_id in state.jobs:
        if not job_id.startswith(prefix):
            continue
        suffix = job_id.removeprefix(prefix)
        if suffix.isdigit():
            max_index = max(max_index, int(suffix))
    return f"{prefix}{max_index + 1:03d}"


def schedule_follow_on_event(
    state: SimulationState,
    source_event: Event,
    event_type: EventType,
    target_type: TargetType,
    target_id: str,
    delay_shifts: int,
    severity: int,
    duration_shifts: int | None = None,
    description: str | None = None,
) -> Event | None:
    """Schedule a future chained event if depth/deadline limits allow it."""
    if source_event.chain_depth >= MAX_EVENT_CHAIN_DEPTH:
        return None
    start_shift = max(state.current_shift + 1, source_event.end_shift + delay_shifts)
    if start_shift >= state.deadline_shift:
        return None
    event = Event(
        id=_next_event_id(state),
        type=event_type,
        target_type=target_type,
        target_id=target_id,
        start_shift=start_shift,
        duration_shifts=duration_shifts or min(6, max(1, severity)),
        severity=max(1, min(5, severity)),
        has_advance_warning=True,
        warning_shift=max(state.current_shift + 1, start_shift - 2),
        description=description or _description_for(event_type, target_type, target_id, severity),
        effects={"source_event_id": source_event.id},
        parent_event_id=source_event.id,
        chain_depth=source_event.chain_depth + 1,
    )
    state.event_timeline.append(event)
    state.event_timeline.sort(key=lambda item: (item.start_shift, item.id))
    source_event.effects.setdefault("follow_on_event_ids", []).append(event.id)
    state.daily_notes.append(f"Follow-on risk scheduled from {source_event.id}: {event.description}")
    return event


def _schedule_cascading_events(state: SimulationState, event: Event) -> None:
    """Evaluate whether a resolved event creates a later related disruption."""
    if event.effects.get("cascade_evaluated") or event.chain_depth >= MAX_EVENT_CHAIN_DEPTH:
        return
    event.effects["cascade_evaluated"] = True
    # Mitigation from player choices reduces pressure; unresolved work impact
    # increases it. Only meaningful pressure is allowed to spawn cascades.
    mitigation = int(event.effects.get("mitigation_score", 0))
    pressure = event.severity + len(event.effects.get("blocked_job_ids", [])) // 4 - mitigation
    if pressure < 3:
        return

    rng = Random(f"{state.seed}:{event.id}:{state.current_shift}:cascade")
    if pressure < 5 and rng.random() > 0.55:
        return

    event_type, target_type, target_id = _cascade_target(state, event, rng)
    if not target_id:
        return
    severity = max(1, min(5, pressure + rng.randint(-1, 1)))
    delay = rng.randint(1, 4)
    schedule_follow_on_event(
        state=state,
        source_event=event,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        delay_shifts=delay,
        severity=severity,
        duration_shifts=_duration_for(event_type, severity, rng),
        description=_cascade_description(event, event_type, target_type, target_id, severity),
    )


def _cascade_target(
    state: SimulationState,
    event: Event,
    rng: Random,
) -> tuple[EventType, TargetType, str]:
    """Map a source event into the most plausible follow-on event target."""
    if event.type in {EventType.MISSING_MATERIAL, EventType.DELAYED_MATERIAL, EventType.SUPPLIER_ESCALATION}:
        if event.target_type == TargetType.JOB and event.target_id in state.jobs:
            job = state.jobs[event.target_id]
            if rng.random() < 0.55:
                return EventType.LOGISTICS_BACKLOG, TargetType.SHOP, job.shop_id
            return EventType.SUPPLIER_ESCALATION, TargetType.JOB, job.id
        return EventType.LOGISTICS_BACKLOG, event.target_type, event.target_id
    if event.type in {EventType.MACHINE_DOWN, EventType.TOOLING_DAMAGE}:
        wc = state.workcenters.get(event.target_id)
        if wc and rng.random() < 0.5:
            return EventType.CREW_SHORTAGE, TargetType.SHOP, wc.shop_id
        return EventType.TOOLING_DAMAGE, event.target_type, event.target_id
    if event.type in {EventType.QUALITY_REWORK, EventType.REWORK_SPILLOVER}:
        piece_id = _piece_for_event(state, event)
        return EventType.REWORK_SPILLOVER, TargetType.PIECE, piece_id
    if event.type in {EventType.INSPECTION_DELAY, EventType.CERTIFICATION_AUDIT}:
        piece_id = _piece_for_event(state, event)
        return EventType.CERTIFICATION_AUDIT, TargetType.PIECE, piece_id
    if event.type in {EventType.ENGINEERING_HOLD, EventType.ENGINEERING_DATA_REVISION}:
        piece_id = _piece_for_event(state, event)
        return EventType.ENGINEERING_DATA_REVISION, TargetType.PIECE, piece_id
    if event.type in {EventType.WEATHER, EventType.FACILITY_OUTAGE, EventType.CREW_SHORTAGE, EventType.LOGISTICS_BACKLOG}:
        if event.target_type == TargetType.SHOP:
            return EventType.CREW_SHORTAGE if rng.random() < 0.5 else EventType.LOGISTICS_BACKLOG, TargetType.SHOP, event.target_id
    if event.type in {EventType.PRIORITY_CHANGE, EventType.URGENT_JOB}:
        piece_id = _piece_for_event(state, event)
        return EventType.ENGINEERING_DATA_REVISION, TargetType.PIECE, piece_id
    if event.type == EventType.UNEXPECTED_JOB:
        piece_id = _piece_for_event(state, event)
        return EventType.PRIORITY_CHANGE, TargetType.PIECE, piece_id
    return EventType.LOGISTICS_BACKLOG, event.target_type, event.target_id


def _cascade_description(
    source_event: Event,
    event_type: EventType,
    target_type: TargetType,
    target_id: str,
    severity: int,
) -> str:
    """Build a description that preserves the source event relationship."""
    base = _description_for(event_type, target_type, target_id, severity)
    return f"{base} Follow-on effect from {source_event.id}."


def _piece_for_event(state: SimulationState, event: Event) -> str:
    """Resolve the affected piece for event types that cascade at piece level."""
    if event.effects.get("unexpected_piece_id") in state.pieces:
        return event.effects["unexpected_piece_id"]
    if event.target_type == TargetType.PIECE and event.target_id in state.pieces:
        return event.target_id
    if event.target_type == TargetType.JOB and event.target_id in state.jobs:
        return state.jobs[event.target_id].piece_id
    if event.effects.get("blocked_job_ids"):
        job_id = event.effects["blocked_job_ids"][0]
        if job_id in state.jobs:
            return state.jobs[job_id].piece_id
    return next(iter(state.pieces))


def _next_event_id(state: SimulationState) -> str:
    """Return the next unused event id in EVT-#### form."""
    existing = {event.id for event in state.event_timeline}
    index = len(existing) + 1
    while True:
        event_id = f"EVT-{index:04d}"
        if event_id not in existing:
            return event_id
        index += 1


def _sample_ids(ids: list[str], count: int) -> list[str]:
    """Pick a deterministic prefix sample from an already-randomized id list."""
    # Deterministic enough for an already-generated ordered list; avoids touching global randomness.
    return ids[: max(0, min(count, len(ids)))]
