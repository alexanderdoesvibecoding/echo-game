from __future__ import annotations

from .enums import DecisionType, EventType, JobStatus, TargetType, WorkCenterStatus
from .metrics import update_state_metrics
from .models import DecisionCard, DecisionChoice, Event, Job, Shop, SimulationState, WorkCenter


def generate_decision_cards(state: SimulationState, day: int) -> list[DecisionCard]:
    update_state_metrics(state)
    cards: list[DecisionCard] = []
    for event in _visible_events(state):
        cards.append(_event_card(state, event, len(cards) + 1, day))
        if len(cards) == 2:
            break
    if len(cards) < 3:
        bottleneck = _top_bottleneck(state)
        if bottleneck:
            cards.append(_bottleneck_card(state, bottleneck, len(cards) + 1, day))
    if len(cards) < 3:
        critical = _top_critical_job(state)
        if critical:
            cards.append(_critical_path_card(state, critical, len(cards) + 1, day))
    if len(cards) < 3:
        alternate = _alternate_routing_job(state)
        if alternate:
            cards.append(_alternate_card(state, alternate, len(cards) + 1, day))
    if len(cards) < 3 and _has_idle_opportunity(state):
        cards.append(_idle_card(state, len(cards) + 1, day))
    if len(cards) < 3:
        cards.append(_final_integration_card(state, len(cards) + 1, day))
    while len(cards) < 3:
        cards.append(_strategic_card(state, len(cards) + 1, day))
    return cards[:3]


def apply_choice(state: SimulationState, card: DecisionCard, choice: DecisionChoice) -> str:
    effects = choice.immediate_effects
    effect_type = effects.get("type", "note")
    state.cost += max(0, choice.cost_effect)
    state.reschedule_count += max(0, choice.reschedule_effect)
    _apply_risk_delta(state, card, choice.risk_effect)

    if effect_type == "wait":
        note = _wait_and_absorb(state, card)
    elif effect_type == "resequence":
        note = _resequence(state, card)
    elif effect_type == "protect_critical":
        note = _protect_critical(state)
    elif effect_type == "expedite_event":
        note = _expedite_event(state, effects.get("event_id"))
    elif effect_type == "reroute":
        note = _reroute_targets(state, card)
    elif effect_type == "preempt":
        note = _preempt_for_card(state, card)
    elif effect_type == "split_capacity":
        note = _split_capacity(state, card)
    elif effect_type == "defer":
        note = _defer_lower_risk(state, card)
    elif effect_type == "pull_forward":
        note = _pull_forward_unaffected(state, card)
    else:
        note = "Recorded the scheduling preference for today."
    state.daily_notes.append(note)
    update_state_metrics(state)
    return note


def _visible_events(state: SimulationState) -> list[Event]:
    ids = list(dict.fromkeys(state.active_events + state.known_warnings))
    events = [event for event in state.event_timeline if event.id in ids and not event.resolved]
    return sorted(events, key=lambda event: (0 if event.id in state.active_events else 1, -event.severity, event.start_shift))


def _event_card(state: SimulationState, event: Event, ordinal: int, day: int) -> DecisionCard:
    dtype = _decision_type_for_event(event.type)
    status = "active" if event.id in state.active_events else "warning"
    target = _target_name(state, event.target_type, event.target_id)
    choices = [
        DecisionChoice(
            id="1",
            label="Resequence ready work",
            description="Move ready jobs around the affected path while preserving current work in progress.",
            immediate_effects={"type": "resequence", "event_id": event.id},
            risk_effect=-5,
            cost_effect=4,
            reschedule_effect=1,
        ),
        DecisionChoice(
            id="2",
            label="Expedite resolution",
            description="Spend cost points to shorten the disruption or reduce its severity.",
            immediate_effects={"type": "expedite_event", "event_id": event.id},
            risk_effect=-9,
            cost_effect=35 + event.severity * 8,
            reschedule_effect=1,
        ),
        DecisionChoice(
            id="3",
            label="Protect critical path",
            description="Raise priority on critical dependencies and push them to the front of eligible queues.",
            immediate_effects={"type": "protect_critical", "event_id": event.id},
            risk_effect=-7,
            cost_effect=12,
            reschedule_effect=1,
        ),
    ]
    if event.type in {EventType.MACHINE_DOWN, EventType.MISSING_MATERIAL, EventType.DELAYED_MATERIAL, EventType.INSPECTION_DELAY}:
        choices.append(
            DecisionChoice(
                id="4",
                label="Reroute affected work",
                description="Move the highest-risk affected job to an alternate capable workcenter if one is open.",
                immediate_effects={"type": "reroute", "event_id": event.id},
                risk_effect=-6,
                cost_effect=18,
                reschedule_effect=1,
            )
        )
    else:
        choices.append(
            DecisionChoice(
                id="4",
                label="Wait and contain",
                description="Avoid extra churn now, accepting that downstream slack may tighten.",
                immediate_effects={"type": "wait", "event_id": event.id},
                risk_effect=5,
                cost_effect=0,
                reschedule_effect=0,
            )
        )
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=dtype,
        title=f"{event.type.value} {status}",
        description=f"{target}: {event.description}",
        target_ids=[event.target_id, event.id],
        severity=event.severity,
        choices=choices,
    )


def _bottleneck_card(state: SimulationState, shop: Shop, ordinal: int, day: int) -> DecisionCard:
    queued = len(shop.queued_job_ids)
    blocked = len(shop.blocked_job_ids)
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.BOTTLENECK,
        title=f"Bottleneck pressure in {shop.name}",
        description=f"{queued} queued jobs and {blocked} blocked jobs are concentrating risk in this shop.",
        target_ids=[shop.id],
        severity=min(5, 1 + queued // 4 + blocked // 2),
        choices=[
            DecisionChoice(
                id="1",
                label="Split capacity",
                description="Distribute queued work across alternate capable workcenters, increasing reschedules.",
                immediate_effects={"type": "split_capacity"},
                risk_effect=-7,
                cost_effect=16,
                reschedule_effect=2,
            ),
            DecisionChoice(
                id="2",
                label="Protect critical jobs",
                description="Move critical-path jobs to the front and let lower-risk work wait.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-8,
                cost_effect=10,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Defer low-risk work",
                description="Reduce congestion by lowering priority on jobs with more slack.",
                immediate_effects={"type": "defer"},
                risk_effect=-3,
                cost_effect=4,
                reschedule_effect=1,
            ),
        ],
    )


def _critical_path_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    piece = state.pieces.get(job.piece_id)
    piece_name = piece.name if piece else "Final integration"
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.CRITICAL_PATH,
        title=f"Critical path exposure on {job.id}",
        description=f"{piece_name} depends on {job.required_capability} work due by shift {job.due_shift}.",
        target_ids=[job.id],
        severity=5 if job.risk_score >= 70 else 4,
        choices=[
            DecisionChoice(
                id="1",
                label="Protect critical path",
                description="Boost this dependency and downstream unlocks ahead of routine queue work.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-8,
                cost_effect=12,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Reroute job",
                description="Use an alternate capable workcenter even if setup cost rises.",
                immediate_effects={"type": "reroute"},
                risk_effect=-6,
                cost_effect=20,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Preempt lower priority",
                description="Interrupt lower-priority work if it is occupying the best capable workcenter.",
                immediate_effects={"type": "preempt"},
                risk_effect=-7,
                cost_effect=24,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Hold sequence",
                description="Keep the current queue stable and avoid immediate churn.",
                immediate_effects={"type": "wait"},
                risk_effect=4,
                cost_effect=0,
                reschedule_effect=0,
            ),
        ],
    )


def _alternate_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.ALTERNATE_ROUTING,
        title=f"Alternate routing available for {job.id}",
        description=f"{job.required_capability} work can move off its current queue, but setup and coordination cost will rise.",
        target_ids=[job.id],
        severity=3,
        choices=[
            DecisionChoice(
                id="1",
                label="Reroute job",
                description="Move the job to the best open alternate workcenter.",
                immediate_effects={"type": "reroute"},
                risk_effect=-6,
                cost_effect=18,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Wait one day",
                description="Avoid extra setup cost and preserve the current workcenter queue.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
                cost_effect=0,
                reschedule_effect=0,
            ),
            DecisionChoice(
                id="3",
                label="Pull forward peers",
                description="Use the alternate capacity for other ready jobs in the same capability family.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                cost_effect=8,
                reschedule_effect=1,
            ),
        ],
    )


def _idle_card(state: SimulationState, ordinal: int, day: int) -> DecisionCard:
    ready_count = len(state.get_ready_jobs())
    idle_count = len(state.get_available_workcenters())
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.IDLE_WORKCENTER,
        title="Idle capacity while work is ready",
        description=f"{idle_count} workcenters are open while {ready_count} jobs are ready or nearly ready.",
        target_ids=[],
        severity=3,
        choices=[
            DecisionChoice(
                id="1",
                label="Pull forward ready work",
                description="Release additional ready jobs into available queues.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                cost_effect=6,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Protect critical jobs",
                description="Use idle capacity only where it helps critical dependencies.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-6,
                cost_effect=10,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Keep buffers open",
                description="Preserve open capacity for expected disruption recovery.",
                immediate_effects={"type": "wait"},
                risk_effect=2,
                cost_effect=0,
                reschedule_effect=0,
            ),
        ],
    )


def _final_integration_card(state: SimulationState, ordinal: int, day: int) -> DecisionCard:
    complete_pieces = sum(1 for piece in state.pieces.values() if piece.ready_for_integration)
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.FINAL_INTEGRATION,
        title="Final integration readiness",
        description=f"{complete_pieces}/30 puzzle pieces are ready; late dependencies can starve the final integration bay.",
        target_ids=[state.final_integration_job],
        severity=4 if day >= 20 else 3,
        choices=[
            DecisionChoice(
                id="1",
                label="Protect final dependencies",
                description="Raise priority on jobs that unlock the most remaining pieces.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-7,
                cost_effect=12,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Expedite acceptance",
                description="Spend cost points to reduce handoff delay for the most complete pieces.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-5,
                cost_effect=22,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Hold integration buffer",
                description="Avoid overloading final integration before more pieces are ready.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
                cost_effect=0,
                reschedule_effect=0,
            ),
        ],
    )


def _strategic_card(state: SimulationState, ordinal: int, day: int) -> DecisionCard:
    bottlenecks = state.get_bottleneck_shops(1)
    target_ids = [bottlenecks[0].id] if bottlenecks else []
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.STRATEGIC_PRIORITY,
        title="Strategic priority review",
        description="Several queues are close in priority; today’s rule will shape which dependencies unlock first.",
        target_ids=target_ids,
        severity=2,
        choices=[
            DecisionChoice(
                id="1",
                label="Earliest due first",
                description="Favor jobs with the nearest target milestone.",
                immediate_effects={"type": "resequence"},
                risk_effect=-3,
                cost_effect=4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Critical path first",
                description="Favor jobs with low slack and high downstream dependency value.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-5,
                cost_effect=8,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Stabilize queues",
                description="Avoid churn and let current workcenter queues run.",
                immediate_effects={"type": "wait"},
                risk_effect=2,
                cost_effect=0,
                reschedule_effect=0,
            ),
        ],
    )


def _resequence(state: SimulationState, card: DecisionCard) -> str:
    affected = 0
    for wc in state.workcenters.values():
        before = list(wc.queue)
        wc.queue.sort(key=lambda job_id: (state.jobs[job_id].due_shift, -state.jobs[job_id].priority))
        if wc.queue != before:
            affected += 1
    for job in state.get_ready_jobs()[:12]:
        job.priority += 3
    return f"Resequenced {affected} queues around the highlighted issue."


def _wait_and_absorb(state: SimulationState, card: DecisionCard) -> str:
    affected = 0
    limit = 8 if card.type in {DecisionType.CRITICAL_PATH, DecisionType.FINAL_INTEGRATION} else 4
    delay = 3 if card.severity >= 4 else 2
    if card.type in {DecisionType.CRITICAL_PATH, DecisionType.FINAL_INTEGRATION}:
        delay += 1
    for job in _jobs_for_card(state, card)[:limit]:
        if job.status not in {JobStatus.COMPLETE, JobStatus.RUNNING}:
            job.priority = max(5, job.priority - 6)
            job.remaining_duration_shifts += delay
            affected += 1
    for target_id in card.target_ids:
        event = _event_by_id(state, target_id)
        if event and event.id in state.active_events:
            event.duration_shifts += 1
    if affected:
        return f"Held sequence; {affected} affected job(s) absorbed extra queue or coordination delay."
    return "Held current sequence and accepted near-term risk."


def _protect_critical(state: SimulationState) -> str:
    critical = state.get_critical_path_jobs()[:10]
    for job in critical:
        job.priority += 10
        if job.assigned_workcenter_id and job.status == JobStatus.QUEUED:
            state.assign_job(job.id, job.assigned_workcenter_id, front=True)
    return f"Protected {len(critical)} critical-path jobs by raising priority and queue position."


def _expedite_event(state: SimulationState, event_id: str | None) -> str:
    event = _event_by_id(state, event_id)
    if not event:
        return "Expedite budget reserved for the highest active disruption."
    reduction = 2 if event.severity >= 4 else 1
    event.duration_shifts = max(1, event.duration_shifts - reduction)
    event.severity = max(1, event.severity - 1)
    if event.type in {EventType.MISSING_MATERIAL, EventType.DELAYED_MATERIAL, EventType.INSPECTION_DELAY}:
        for job_id in event.effects.get("blocked_job_ids", [])[:2]:
            if job_id in state.jobs and state.jobs[job_id].block_reason:
                state.jobs[job_id].priority += 12
    return f"Expedited {event.id}; expected disruption duration reduced by {reduction} shift(s)."


def _reroute_targets(state: SimulationState, card: DecisionCard) -> str:
    jobs = _jobs_for_card(state, card)
    moved = 0
    for job in jobs[:3]:
        alt = _best_alternate_workcenter(state, job)
        if alt:
            state.assign_job(job.id, alt.id, front=job.critical_path)
            job.priority += 5
            moved += 1
    return f"Rerouted {moved} affected job(s) to alternate capable workcenters."


def _preempt_for_card(state: SimulationState, card: DecisionCard) -> str:
    for job in _jobs_for_card(state, card):
        for wc_id in job.candidate_workcenter_ids:
            if wc_id not in state.workcenters:
                continue
            wc = state.workcenters[wc_id]
            if wc.current_job_id and state.jobs[wc.current_job_id].priority + 15 < job.priority:
                state.preempt_current_job(wc.id, job.id)
                return f"Preempted lower-priority work on {wc.name} for {job.id}."
    return "No safe preemption was available; priority was raised instead."


def _split_capacity(state: SimulationState, card: DecisionCard) -> str:
    shop_ids = [target for target in card.target_ids if target in state.shops]
    moved = 0
    for shop_id in shop_ids:
        shop = state.shops[shop_id]
        queued = [state.jobs[job_id] for job_id in shop.queued_job_ids if job_id in state.jobs]
        for job in queued:
            alt = _best_alternate_workcenter(state, job)
            if alt and alt.shop_id != shop_id:
                state.assign_job(job.id, alt.id)
                moved += 1
                if moved >= 6:
                    return f"Split {moved} queued jobs across alternate capacity."
    return f"Split {moved} queued jobs across alternate capacity."


def _defer_lower_risk(state: SimulationState, card: DecisionCard) -> str:
    shop_ids = [target for target in card.target_ids if target in state.shops]
    jobs = [
        job
        for job in state.jobs.values()
        if not job.is_complete and not job.critical_path and (not shop_ids or job.shop_id in shop_ids)
    ]
    for job in sorted(jobs, key=lambda item: (item.risk_score, -item.due_shift))[:12]:
        job.priority = max(10, job.priority - 8)
    return f"Deferred {min(12, len(jobs))} lower-risk jobs to relieve queue pressure."


def _pull_forward_unaffected(state: SimulationState, card: DecisionCard) -> str:
    moved = 0
    ready = sorted(state.get_ready_jobs(), key=lambda job: (-job.priority, job.due_shift))
    for job in ready[:18]:
        alt = _best_alternate_workcenter(state, job, allow_primary=True)
        if alt:
            state.assign_job(job.id, alt.id, front=job.critical_path)
            moved += 1
    return f"Pulled forward {moved} ready jobs into available capacity."


def _apply_risk_delta(state: SimulationState, card: DecisionCard, delta: int) -> None:
    for job in _jobs_for_card(state, card)[:8]:
        job.risk_score = max(0, min(100, job.risk_score + delta))
    for target_id in card.target_ids:
        if target_id in state.shops:
            state.shops[target_id].risk_score = max(0, min(100, state.shops[target_id].risk_score + delta))
        if target_id in state.pieces:
            state.pieces[target_id].risk_score = max(0, min(100, state.pieces[target_id].risk_score + delta))


def _jobs_for_card(state: SimulationState, card: DecisionCard) -> list[Job]:
    jobs: list[Job] = []
    for target_id in card.target_ids:
        if target_id in state.jobs:
            jobs.append(state.jobs[target_id])
        elif target_id in state.shops:
            jobs.extend(
                job
                for job in state.jobs.values()
                if job.shop_id == target_id and not job.is_complete and job.status != JobStatus.RUNNING
            )
        elif target_id in state.pieces:
            jobs.extend(state.jobs[job_id] for job_id in state.pieces[target_id].job_ids if job_id in state.jobs)
        elif target_id.startswith("EVT-"):
            event = _event_by_id(state, target_id)
            if event:
                jobs.extend(_jobs_for_event(state, event))
    if not jobs:
        jobs = state.get_critical_path_jobs()[:5] or state.get_ready_jobs()[:5]
    return sorted(
        list({job.id: job for job in jobs if not job.is_complete}.values()),
        key=lambda job: (job.critical_path, job.risk_score, job.priority),
        reverse=True,
    )


def _jobs_for_event(state: SimulationState, event: Event) -> list[Job]:
    if event.target_type == TargetType.JOB and event.target_id in state.jobs:
        return [state.jobs[event.target_id]]
    if event.target_type == TargetType.PIECE and event.target_id in state.pieces:
        return [state.jobs[job_id] for job_id in state.pieces[event.target_id].job_ids if job_id in state.jobs]
    if event.target_type == TargetType.SHOP and event.target_id in state.shops:
        return [job for job in state.jobs.values() if job.shop_id == event.target_id and not job.is_complete]
    if event.target_type == TargetType.WORKCENTER and event.target_id in state.workcenters:
        wc = state.workcenters[event.target_id]
        ids = list(wc.queue)
        if wc.current_job_id:
            ids.append(wc.current_job_id)
        return [state.jobs[job_id] for job_id in ids if job_id in state.jobs]
    return []


def _best_alternate_workcenter(
    state: SimulationState,
    job: Job,
    allow_primary: bool = False,
) -> WorkCenter | None:
    candidates: list[WorkCenter] = []
    for wc_id in job.candidate_workcenter_ids:
        if wc_id not in state.workcenters:
            continue
        wc = state.workcenters[wc_id]
        if wc.status in {WorkCenterStatus.DOWN, WorkCenterStatus.BLOCKED, WorkCenterStatus.WEATHER_IMPACTED}:
            continue
        if not allow_primary and wc.id == job.assigned_workcenter_id:
            continue
        if job.required_capability in wc.capabilities:
            candidates.append(wc)
    if not candidates:
        return None
    return min(candidates, key=lambda wc: (len(wc.queue) + (1 if wc.current_job_id else 0), -wc.efficiency, wc.id))


def _event_by_id(state: SimulationState, event_id: str | None) -> Event | None:
    if not event_id:
        return None
    return next((event for event in state.event_timeline if event.id == event_id), None)


def _target_name(state: SimulationState, target_type: TargetType, target_id: str) -> str:
    if target_type == TargetType.SHOP and target_id in state.shops:
        return state.shops[target_id].name
    if target_type == TargetType.WORKCENTER and target_id in state.workcenters:
        return state.workcenters[target_id].name
    if target_type == TargetType.PIECE and target_id in state.pieces:
        return state.pieces[target_id].name
    return target_id


def _decision_type_for_event(event_type: EventType) -> DecisionType:
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
    }[event_type]


def _top_bottleneck(state: SimulationState) -> Shop | None:
    shops = state.get_bottleneck_shops(1)
    if not shops:
        return None
    shop = shops[0]
    if len(shop.queued_job_ids) + len(shop.blocked_job_ids) < 2:
        return None
    return shop


def _top_critical_job(state: SimulationState) -> Job | None:
    critical = state.get_critical_path_jobs()
    return critical[0] if critical else None


def _alternate_routing_job(state: SimulationState) -> Job | None:
    candidates = [
        job
        for job in state.jobs.values()
        if not job.is_complete
        and len(job.candidate_workcenter_ids) > 1
        and (job.critical_path or job.risk_score > 40)
        and _best_alternate_workcenter(state, job) is not None
    ]
    return sorted(candidates, key=lambda job: (job.critical_path, job.risk_score), reverse=True)[0] if candidates else None


def _has_idle_opportunity(state: SimulationState) -> bool:
    return bool(state.get_ready_jobs()) and bool(state.get_available_workcenters())
