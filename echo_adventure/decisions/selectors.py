"""Selectors for jobs, events, targets, and workcenters affected by decisions."""

from __future__ import annotations

from ..enums import EventType, JobStatus, TargetType, WorkCenterStatus
from ..models import DecisionCard, Event, Job, SimulationState, WorkCenter

def _visible_events(state: SimulationState) -> list[Event]:
    """Return active/warned events ordered by urgency for card generation."""
    ids = list(dict.fromkeys(state.active_events + state.known_warnings))
    events = [event for event in state.event_timeline if event.id in ids and not event.resolved]
    return sorted(
        events,
        key=lambda event: (
            0 if event.type == EventType.UNEXPECTED_JOB else 1,
            0 if event.id in state.active_events else 1,
            -event.severity,
            event.start_shift,
        ),
    )

def _event_by_id(state: SimulationState, event_id: str | None) -> Event | None:
    """Find an event by id, tolerating missing ids from generic cards."""
    if not event_id:
        return None
    return next((event for event in state.event_timeline if event.id == event_id), None)

def _jobs_for_card(
    state: SimulationState,
    card: DecisionCard,
    fallback_limit: int = 5,
) -> list[Job]:
    """Expand a card's targets into concrete affected jobs."""
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
        jobs = state.get_critical_path_jobs()[:fallback_limit] or state.get_ready_jobs()[:fallback_limit]
    live_jobs = list({job.id: job for job in jobs if not job.is_complete}.values())
    if not live_jobs:
        live_jobs = state.get_critical_path_jobs()[:fallback_limit] or state.get_ready_jobs()[:fallback_limit]
    return sorted(
        live_jobs,
        key=lambda job: (job.critical_path, job.risk_score, job.priority),
        reverse=True,
    )

def _jobs_for_event(state: SimulationState, event: Event) -> list[Job]:
    """Expand an event target into concrete affected jobs."""
    piece_id = event.effects.get("unexpected_piece_id")
    if piece_id in state.pieces:
        return [state.jobs[job_id] for job_id in state.pieces[piece_id].job_ids if job_id in state.jobs]
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
    """Return the least-loaded capable workcenter for a reroute."""
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

def _alternate_routing_jobs(state: SimulationState) -> list[Job]:
    """Find risky jobs with usable alternate workcenters."""
    candidates = [
        job
        for job in state.jobs.values()
        if not job.is_complete
        and len(job.candidate_workcenter_ids) > 1
        and (job.critical_path or job.risk_score > 40)
        and _best_alternate_workcenter(state, job) is not None
    ]
    return sorted(candidates, key=lambda job: (job.critical_path, job.risk_score, job.priority), reverse=True)

def _handoff_risk_job(state: SimulationState) -> Job | None:
    """Find a dependency handoff where shops differ and timing is tight."""
    candidates: list[Job] = []
    for job in state.jobs.values():
        if job.is_complete or not job.dependency_ids:
            continue
        upstream_shops = {
            state.jobs[dep_id].shop_id
            for dep_id in job.dependency_ids
            if dep_id in state.jobs and state.jobs[dep_id].shop_id != job.shop_id
        }
        if not upstream_shops:
            continue
        slack = job.due_shift - state.current_shift - job.remaining_duration_shifts
        if job.critical_path or slack <= 8 or job.risk_score >= 35:
            candidates.append(job)
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda job: (job.critical_path, job.risk_score, -job.due_shift, job.priority),
        reverse=True,
    )[0]

def _quality_triage_job(state: SimulationState) -> Job | None:
    """Find work where preventive quality attention could change the day."""
    quality_capabilities = {
        "inspection",
        "metrology",
        "certification",
        "alignment",
        "calibration",
        "finishing",
    }
    candidates = [
        job
        for job in state.jobs.values()
        if not job.is_complete
        and (
            job.rework_count > 0
            or job.status == JobStatus.REWORK_REQUIRED
            or job.required_capability in quality_capabilities
            or job.risk_score >= 45
        )
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda job: (job.rework_count, job.status == JobStatus.REWORK_REQUIRED, job.critical_path, job.risk_score),
        reverse=True,
    )[0]

def _has_idle_opportunity(state: SimulationState) -> bool:
    """Return whether open workcenters and ready jobs coexist."""
    return bool(state.get_ready_jobs()) and bool(state.get_available_workcenters())

def _events_related(state: SimulationState, source: Event, candidate: Event) -> bool:
    """Return whether two events touch the same job, piece, or shop context."""
    if source.target_id == candidate.target_id:
        return True
    source_jobs = _jobs_for_event(state, source)
    candidate_jobs = _jobs_for_event(state, candidate)
    if source_jobs and candidate_jobs:
        source_job_ids = {job.id for job in source_jobs}
        candidate_job_ids = {job.id for job in candidate_jobs}
        if source_job_ids & candidate_job_ids:
            return True
        source_piece_ids = {job.piece_id for job in source_jobs}
        candidate_piece_ids = {job.piece_id for job in candidate_jobs}
        if source_piece_ids & candidate_piece_ids:
            return True
        source_shop_ids = {job.shop_id for job in source_jobs}
        candidate_shop_ids = {job.shop_id for job in candidate_jobs}
        if source_shop_ids & candidate_shop_ids:
            return True
    if source.target_type == TargetType.SHOP and candidate.target_type == TargetType.SHOP:
        return source.target_id == candidate.target_id
    return False

def _piece_id_for_event(state: SimulationState, event: Event) -> str:
    """Resolve the piece id most closely associated with an event."""
    if event.target_type == TargetType.PIECE and event.target_id in state.pieces:
        return event.target_id
    if event.target_type == TargetType.JOB and event.target_id in state.jobs:
        return state.jobs[event.target_id].piece_id
    jobs = _jobs_for_event(state, event)
    if jobs:
        return jobs[0].piece_id
    return next(iter(state.pieces))
