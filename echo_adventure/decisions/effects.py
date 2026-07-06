"""Choice application and decision effect handlers."""

from __future__ import annotations

import random

from ..enums import DecisionType, EventType, JobStatus, TargetType
from ..events import JOB_BLOCKING_EVENT_TYPES, insert_unexpected_job, schedule_follow_on_event
from ..metrics import update_state_metrics
from ..models import DecisionCard, DecisionChoice, DecisionRecord, Event, Job, SimulationState
from .cards import _piece_label
from .graph import apply_campaign_choice
from .scoring import select_echo_choice
from .selectors import (
    _best_alternate_workcenter,
    _event_by_id,
    _events_related,
    _jobs_for_card,
    _piece_id_for_event,
)

def apply_choice(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    actor: str = "player",
    echo_choice: DecisionChoice | None = None,
) -> str:
    """Apply one selected choice and return a player-facing audit note."""
    if echo_choice is None:
        echo_choice = select_echo_choice(card)
    effects = choice.immediate_effects
    effect_type = effects.get("type", "note")
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
    elif effect_type == "echo_recommendation":
        note = _use_echo_recommendation(state, card)
    elif effect_type == "prioritize_new_job":
        note = _add_unexpected_job(state, effects.get("event_id"), prioritize=True)
    elif effect_type == "backlog_new_job":
        note = _add_unexpected_job(state, effects.get("event_id"), prioritize=False)
    else:
        note = "Recorded the scheduling preference for today."
    # Choices affect both the current board and the future event chain. The
    # forward effect is recorded after the immediate action mutates priorities.
    forward_note = _apply_forward_decision_effect(state, card, choice)
    if forward_note:
        note = f"{note} {forward_note}"
    apply_campaign_choice(state, card, choice)
    state.daily_notes.append(note)
    state.decision_history.append(
        DecisionRecord(
            day=card.day,
            card_id=card.id,
            card_title=card.title,
            actor=actor,
            choice_id=choice.id,
            choice_label=choice.label,
            echo_choice_id=echo_choice.id if echo_choice else None,
            echo_choice_label=echo_choice.label if echo_choice else None,
            aligned_with_echo=bool(echo_choice and choice.id == echo_choice.id),
            note=note,
        )
    )
    update_state_metrics(state)
    return note

def _resequence(state: SimulationState, card: DecisionCard) -> str:
    """Sort queues by due date/priority and nudge ready work upward."""
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
    """Accept near-term delay and increase future pressure for affected work."""
    affected = 0
    limit = 8 if card.type in {DecisionType.CRITICAL_PATH, DecisionType.COMPLETION_READINESS} else 4
    delay = 3 if card.severity >= 4 else 2
    if card.type in {DecisionType.CRITICAL_PATH, DecisionType.COMPLETION_READINESS}:
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
            event.effects["mitigation_score"] = int(event.effects.get("mitigation_score", 0)) - 2
    if affected:
        return f"Held sequence; {affected} affected subjob(s) absorbed extra queue or coordination delay."
    return "Held current sequence and accepted near-term risk."

def _protect_critical(state: SimulationState) -> str:
    """Raise critical-path subjob priorities and pull queued ones forward."""
    critical = state.get_critical_path_jobs()[:10]
    accelerated = 0
    assigned = 0
    for job in critical:
        job.priority += 12
        if job.assigned_workcenter_id and job.status == JobStatus.QUEUED:
            state.assign_job(job.id, job.assigned_workcenter_id, front=True)
            assigned += 1
        elif job.status == JobStatus.READY:
            target = _best_alternate_workcenter(state, job, allow_primary=True)
            if target and state.assign_job(job.id, target.id, front=True):
                assigned += 1
        if _prepare_urgent_job(job):
            accelerated += 1
    detail = f"Protected {len(critical)} critical-path subjobs by raising priority"
    if assigned:
        detail += f", front-loading {assigned}"
    if accelerated:
        detail += f", accelerating {accelerated}"
    return f"{detail}."

def _prepare_urgent_job(job: Job) -> bool:
    """Make urgent work genuinely shorter, including before duration locking."""
    if job.is_complete:
        return False
    changed = False
    if not job.started_once and job.base_duration_shifts > 1:
        job.base_duration_shifts -= 1
        changed = True
    if job.remaining_duration_shifts > 1:
        job.remaining_duration_shifts -= 1
        changed = True
    return changed

def _expedite_event(state: SimulationState, event_id: str | None) -> str:
    """Shorten and soften an active or warned event."""
    event = _event_by_id(state, event_id)
    if not event:
        return "Expedite budget reserved for the highest active disruption."
    reduction = 2 if event.severity >= 4 else 1
    event.duration_shifts = max(1, event.duration_shifts - reduction)
    event.severity = max(1, event.severity - 1)
    event.effects["mitigation_score"] = int(event.effects.get("mitigation_score", 0)) + 3
    if event.type in JOB_BLOCKING_EVENT_TYPES:
        for job_id in event.effects.get("blocked_job_ids", [])[:2]:
            if job_id in state.jobs and state.jobs[job_id].block_reason:
                state.jobs[job_id].priority += 12
    return f"Expedited {event.id}; expected disruption duration reduced by {reduction} shift(s)."

def _reroute_targets(state: SimulationState, card: DecisionCard) -> str:
    """Move affected subjobs to less-loaded alternate workcenters."""
    jobs = _jobs_for_card(state, card)
    moved = 0
    for job in jobs[:3]:
        alt = _best_alternate_workcenter(state, job)
        if not alt:
            continue
        current = state.workcenters.get(job.assigned_workcenter_id) if job.assigned_workcenter_id else None
        current_disrupted = bool(current and current.is_disrupted)
        if job.status == JobStatus.RUNNING and not current_disrupted:
            continue
        if current and not current_disrupted:
            if alt.load >= current.load:
                continue
        if alt:
            state.assign_job(job.id, alt.id, front=job.critical_path)
            job.priority += 5
            moved += 1
    if moved:
        return f"Rerouted {moved} affected subjob(s) to alternate capable workcenters."
    boosted = 0
    prepared = 0
    for job in jobs[:3]:
        if job.is_complete:
            continue
        job.priority += 8
        if job.assigned_workcenter_id and job.status == JobStatus.QUEUED:
            state.assign_job(job.id, job.assigned_workcenter_id, front=True)
        elif job.status == JobStatus.READY:
            target = _best_alternate_workcenter(state, job, allow_primary=True)
            if target:
                state.assign_job(job.id, target.id, front=True)
        if _prepare_urgent_job(job):
            prepared += 1
        boosted += 1
    if boosted:
        note = f"No better route was open; raised priority on {boosted} urgent subjob(s)"
        if prepared:
            note += f" and prepared {prepared}"
        return f"{note}."
    return "No better route was open today."

def _preempt_for_card(state: SimulationState, card: DecisionCard) -> str:
    """Interrupt lower-priority work when a card's target justifies it."""
    jobs = _jobs_for_card(state, card)
    for job in jobs:
        for wc_id in job.candidate_workcenter_ids:
            if wc_id not in state.workcenters:
                continue
            wc = state.workcenters[wc_id]
            if wc.current_job_id and state.jobs[wc.current_job_id].priority + 15 < job.priority:
                state.preempt_current_job(wc.id, job.id)
                return f"Preempted lower-priority work on {wc.name} for {job.id}."
    boosted = 0
    prepared = 0
    for job in jobs[:3]:
        if job.is_complete:
            continue
        job.priority += 9
        if job.assigned_workcenter_id and job.status == JobStatus.QUEUED:
            state.assign_job(job.id, job.assigned_workcenter_id, front=True)
        if _prepare_urgent_job(job):
            prepared += 1
        boosted += 1
    if boosted:
        note = f"No safe preemption was available; raised priority on {boosted} urgent subjob(s)"
        if prepared:
            note += f" and prepared {prepared}"
        return f"{note}."
    return "No safe preemption was available; priority was raised instead."

def _split_capacity(state: SimulationState, card: DecisionCard) -> str:
    """Move queued shop work across alternate capable capacity."""
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
                    return f"Split {moved} queued subjobs across alternate capacity."
    return f"Split {moved} queued subjobs across alternate capacity."

def _defer_lower_risk(state: SimulationState, card: DecisionCard) -> str:
    """Lower priority on slack-rich subjobs so urgent work can flow first."""
    shop_ids = [target for target in card.target_ids if target in state.shops]
    jobs = [
        job
        for job in state.jobs.values()
        if not job.is_complete and not job.critical_path and (not shop_ids or job.shop_id in shop_ids)
    ]
    for job in sorted(jobs, key=lambda item: (item.risk_score, -item.due_shift))[:12]:
        job.priority = max(10, job.priority - 8)
    return f"Deferred {min(12, len(jobs))} lower-risk subjobs to relieve queue pressure."

def _pull_forward_unaffected(state: SimulationState, card: DecisionCard) -> str:
    """Queue ready subjobs into available capacity before it is wasted."""
    moved = 0
    ready = sorted(state.get_ready_jobs(), key=lambda job: (-job.priority, job.due_shift))
    for job in ready[:18]:
        alt = _best_alternate_workcenter(state, job, allow_primary=True)
        if alt:
            state.assign_job(job.id, alt.id, front=job.critical_path)
            moved += 1
    if moved:
        return f"Pulled forward {moved} ready subjobs into available capacity."
    prepared = 0
    for job in _jobs_for_card(state, card)[:3]:
        job.priority += 6
        if _prepare_urgent_job(job):
            prepared += 1
    if prepared:
        return f"No ready work could move; prepared {prepared} urgent subjob(s)."
    return f"Pulled forward {moved} ready subjobs into available capacity."

def _use_echo_recommendation(state: SimulationState, card: DecisionCard) -> str:
    """Apply the experimental ECHO recommendation with a deterministic failure chance."""
    event_id = next((target_id for target_id in card.target_ids if _event_by_id(state, target_id)), card.id)
    roll = random.Random(f"{state.seed}:{event_id}:echo-recommendation")
    if roll.random() < 0.28:
        return "ECHO recommendation did not produce a usable move; the team lost some analysis time."

    protected_note = _protect_critical(state)
    pulled_note = _pull_forward_unaffected(state, card)
    accelerated = 0
    for job in state.get_critical_path_jobs()[:4]:
        if job.status in {JobStatus.QUEUED, JobStatus.READY} and job.remaining_duration_shifts > 1:
            job.remaining_duration_shifts -= 1
            accelerated += 1
    return f"ECHO recommendation worked: {protected_note} {pulled_note} Accelerated {accelerated} critical subjob(s)."

def _add_unexpected_job(state: SimulationState, event_id: str | None, prioritize: bool) -> str:
    """Add the event's new top-level job with the selected priority mode."""
    event = _event_by_id(state, event_id)
    if not event:
        return "No new job request was available to add."
    piece_id = insert_unexpected_job(state, event, prioritize=prioritize)
    mode = "prioritized" if prioritize else "added to the back of the queue"
    return f"{_piece_label(piece_id)} was {mode}; the submarine build now has {len(state.pieces)} top-level jobs."

def _apply_forward_decision_effect(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
) -> str:
    """Translate a decision into future mitigation or follow-on risk."""
    event = _event_by_id(state, choice.immediate_effects.get("event_id"))
    if not event:
        return ""
    effect_type = choice.immediate_effects.get("type", "note")
    mitigation_delta = {
        "expedite_event": 3,
        "reroute": 2,
        "protect_critical": 2,
        "resequence": 1,
        "split_capacity": 1,
        "pull_forward": 1,
        "prioritize_new_job": 1,
        "backlog_new_job": -1,
        "preempt": 1,
        "echo_recommendation": 2,
        "wait": -2,
        "defer": -1,
    }.get(effect_type, 0)
    # mitigation_score is later consumed by the cascade evaluator. Positive
    # choices reduce pressure; passive/defer choices can create a new event.
    event.effects["mitigation_score"] = int(event.effects.get("mitigation_score", 0)) + mitigation_delta
    event.effects.setdefault("decision_history", []).append(
        {
            "day": state.current_day,
            "card": card.id,
            "choice": choice.label,
            "effect": effect_type,
            "mitigation": mitigation_delta,
        }
    )
    if mitigation_delta > 0:
        affected = _soften_related_future_events(state, event, mitigation_delta)
        if affected:
            return f"Future related risk was reduced on {affected} event(s)."
        return "Future cascade risk was reduced."
    if mitigation_delta < 0:
        follow_on = _schedule_decision_follow_on(state, event, abs(mitigation_delta), choice.label)
        if follow_on:
            return f"Follow-on risk {follow_on.id} was added to the timeline."
    return ""

def _soften_related_future_events(state: SimulationState, source_event: Event, strength: int) -> int:
    """Reduce severity/duration on future events related to the mitigated one."""
    affected = 0
    for event in state.event_timeline:
        if event.id == source_event.id or event.started or event.resolved:
            continue
        if event.start_shift <= state.current_shift:
            continue
        if not _events_related(state, source_event, event):
            continue
        event.severity = max(1, event.severity - min(2, strength))
        event.duration_shifts = max(1, event.duration_shifts - 1)
        event.effects.setdefault("upstream_mitigations", []).append(source_event.id)
        affected += 1
        if affected >= strength:
            break
    return affected

def _schedule_decision_follow_on(
    state: SimulationState,
    source_event: Event,
    pressure: int,
    choice_label: str,
) -> Event | None:
    """Schedule one downstream risk caused by a low-mitigation decision."""
    key = f"decision_follow_on:{choice_label}"
    if key in source_event.effects:
        return None
    event_type, target_type, target_id = _decision_follow_on_target(state, source_event)
    if not target_id:
        return None
    follow_on = schedule_follow_on_event(
        state=state,
        source_event=source_event,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        delay_shifts=2 + min(3, source_event.severity),
        severity=max(1, min(5, source_event.severity + pressure - 1)),
        description=f"Deferred response to {source_event.id} creates a downstream {event_type.value.lower()} risk.",
    )
    if follow_on:
        source_event.effects[key] = follow_on.id
    return follow_on

def _decision_follow_on_target(state: SimulationState, source_event: Event) -> tuple[EventType, TargetType, str]:
    """Choose the plausible event type/target for a decision-driven cascade."""
    if source_event.type == EventType.UNEXPECTED_JOB:
        piece_id = source_event.effects.get("unexpected_piece_id")
        if piece_id in state.pieces:
            return EventType.PRIORITY_CHANGE, TargetType.PIECE, piece_id
        shop = max(
            state.shops.values(),
            key=lambda item: (len(item.queued_job_ids) + len(item.blocked_job_ids), item.risk_score),
        )
        return EventType.LOGISTICS_BACKLOG, TargetType.SHOP, shop.id
    if source_event.type == EventType.ECHO_RECOMMENDATION:
        shop = max(
            state.shops.values(),
            key=lambda item: (len(item.queued_job_ids) + len(item.blocked_job_ids), item.risk_score),
        )
        return EventType.LOGISTICS_BACKLOG, TargetType.SHOP, shop.id
    if source_event.type in {EventType.MISSING_MATERIAL, EventType.DELAYED_MATERIAL, EventType.SUPPLIER_ESCALATION}:
        if source_event.target_type == TargetType.JOB and source_event.target_id in state.jobs:
            job = state.jobs[source_event.target_id]
            return EventType.LOGISTICS_BACKLOG, TargetType.SHOP, job.shop_id
        return EventType.SUPPLIER_ESCALATION, source_event.target_type, source_event.target_id
    if source_event.type in {EventType.MACHINE_DOWN, EventType.TOOLING_DAMAGE}:
        return EventType.TOOLING_DAMAGE, source_event.target_type, source_event.target_id
    if source_event.type in {EventType.QUALITY_REWORK, EventType.REWORK_SPILLOVER}:
        return EventType.REWORK_SPILLOVER, TargetType.PIECE, _piece_id_for_event(state, source_event)
    if source_event.type in {EventType.INSPECTION_DELAY, EventType.CERTIFICATION_AUDIT}:
        return EventType.CERTIFICATION_AUDIT, TargetType.PIECE, _piece_id_for_event(state, source_event)
    if source_event.type in {EventType.ENGINEERING_HOLD, EventType.ENGINEERING_DATA_REVISION, EventType.PRIORITY_CHANGE}:
        return EventType.ENGINEERING_DATA_REVISION, TargetType.PIECE, _piece_id_for_event(state, source_event)
    if source_event.type in {EventType.WEATHER, EventType.FACILITY_OUTAGE, EventType.CREW_SHORTAGE, EventType.LOGISTICS_BACKLOG}:
        return EventType.CREW_SHORTAGE, source_event.target_type, source_event.target_id
    return EventType.LOGISTICS_BACKLOG, source_event.target_type, source_event.target_id

def _apply_risk_delta(state: SimulationState, card: DecisionCard, delta: int) -> None:
    """Apply a choice's risk delta to the most relevant jobs/entities."""
    for job in _jobs_for_card(state, card)[:8]:
        job.risk_score = max(0, min(100, job.risk_score + delta))
    for target_id in card.target_ids:
        if target_id in state.shops:
            state.shops[target_id].risk_score = max(0, min(100, state.shops[target_id].risk_score + delta))
        if target_id in state.pieces:
            state.pieces[target_id].risk_score = max(0, min(100, state.pieces[target_id].risk_score + delta))
