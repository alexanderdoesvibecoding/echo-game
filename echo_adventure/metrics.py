"""Derived metric, status, risk, and critical-path calculations."""

from __future__ import annotations

from functools import lru_cache

from .enums import JobStatus, PieceStatus, WorkCenterStatus
from .models import Job, MetricSnapshot, SimulationState


def update_state_metrics(state: SimulationState) -> None:
    """Refresh all derived status fields and roll-up risk metrics on state."""
    # Several modules mutate jobs, workcenters, and events directly. This pass
    # re-derives display/status fields so schedulers and renderers agree.
    _refresh_job_statuses(state)
    projected = recalculate_critical_path(state)
    _refresh_piece_statuses(state)
    _refresh_shop_statuses(state)
    risk = calculate_schedule_risk(state, projected)
    for shop in state.shops.values():
        shop.risk_score = min(100.0, shop.risk_score + risk * 0.08)


def calculate_snapshot(state: SimulationState) -> MetricSnapshot:
    """Return a point-in-time metric snapshot without storing it on state."""
    projected = recalculate_critical_path(state)
    risk = calculate_schedule_risk(state, projected)
    jobs_completed = len(state.completed_jobs)
    total_jobs = len(state.jobs)
    jobs_late = sum(
        1
        for job in state.jobs.values()
        if job.completed_shift is not None and job.completed_shift > job.due_shift
    )
    pieces_completed = sum(1 for piece in state.pieces.values() if piece.ready_for_integration)
    utilization = (
        state.busy_shift_count / state.available_shift_count
        if state.available_shift_count
        else 0.0
    )
    return MetricSnapshot(
        shift=state.current_shift,
        day=state.current_day,
        pieces_completed=pieces_completed,
        jobs_completed=jobs_completed,
        jobs_remaining=max(0, total_jobs - jobs_completed),
        jobs_late=jobs_late,
        utilization=utilization,
        idle_time=state.idle_time,
        reschedules=state.reschedule_count,
        cost=state.cost,
        schedule_risk=risk,
        projected_completion_shift=projected,
        final_item_completed=state.final_item_completed,
        deadline_met=state.final_item_completed and (state.completion_shift or 9999) <= state.deadline_shift,
    )


def calculate_schedule_risk(state: SimulationState, projected_completion_shift: int | None = None) -> float:
    """Estimate deadline risk from slack, blockers, queues, and disruptions."""
    if projected_completion_shift is None:
        projected_completion_shift = recalculate_critical_path(state)
    slack = state.deadline_shift - projected_completion_shift
    late_jobs = sum(
        1
        for job in state.jobs.values()
        if (job.completed_shift and job.completed_shift > job.due_shift)
        or (not job.is_complete and state.current_shift > job.due_shift)
    )
    blocked_critical = sum(1 for job in state.jobs.values() if job.critical_path and job.is_blocked)
    queued_pressure = sum(max(0, len(wc.queue) - 2) for wc in state.workcenters.values())
    down_centers = sum(
        1
        for wc in state.workcenters.values()
        if wc.status in {WorkCenterStatus.DOWN, WorkCenterStatus.BLOCKED, WorkCenterStatus.WEATHER_IMPACTED}
    )
    remaining_jobs = sum(1 for job in state.jobs.values() if not job.is_complete)
    completed_pieces = sum(1 for piece in state.pieces.values() if piece.ready_for_integration)
    integration_gap = max(0, 15 - completed_pieces) * (1.0 if state.current_shift > 30 else 0.45)
    slack_risk = max(0, 22 - slack) * 0.9
    work_risk = max(0.0, remaining_jobs / max(1, state.deadline_shift - state.current_shift)) * 3.5
    # This is a heuristic score, not a probability model. It intentionally
    # blends schedule slack with operational symptoms the player can affect.
    risk = (
        slack_risk
        + late_jobs * 2.6
        + blocked_critical * 6.0
        + queued_pressure * 0.8
        + down_centers * 1.4
        + len(state.active_events) * 3.5
        + len(state.known_warnings) * 2.0
        + integration_gap
        + work_risk
    )
    if state.final_item_completed:
        risk = min(risk, 8.0)
    return max(0.0, min(100.0, risk))


def recalculate_critical_path(state: SimulationState) -> int:
    """Mark critical jobs and return the projected final completion shift."""
    for job in state.jobs.values():
        job.critical_path = False

    @lru_cache(maxsize=None)
    def remaining_path(job_id: str) -> int:
        """Return remaining downstream work from this job through dependents."""
        job = state.jobs[job_id]
        if job.status == JobStatus.COMPLETE:
            own = 0
        elif job.status == JobStatus.RUNNING:
            own = max(1, job.remaining_duration_shifts)
        elif job.block_reason:
            own = max(1, job.remaining_duration_shifts) + 3
        else:
            own = max(1, job.remaining_duration_shifts)
        if not job.dependent_job_ids:
            return own
        return own + max(remaining_path(dep_id) for dep_id in job.dependent_job_ids if dep_id in state.jobs)

    incomplete = [job for job in state.jobs.values() if not job.is_complete]
    if not incomplete:
        return state.completion_shift or state.current_shift
    scored = [(remaining_path(job.id), job) for job in incomplete]
    max_path = max(score for score, _job in scored)
    threshold = max(1, int(max_path * 0.72))
    for score, job in scored:
        # Jobs near the longest path, with low slack, or representing final
        # integration are all treated as critical-path attention targets.
        slack = state.deadline_shift - (state.current_shift + score)
        if score >= threshold or slack <= 10 or job.id == state.final_integration_job:
            job.critical_path = True
        job.risk_score = _job_risk(job, slack)
    return state.current_shift + max_path


def shop_utilization(state: SimulationState, shop_id: str) -> float:
    """Return current active-workcenter utilization for one shop."""
    shop = state.shops[shop_id]
    if not shop.workcenter_ids:
        return 0.0
    busy = 0
    for wc_id in shop.workcenter_ids:
        wc = state.workcenters[wc_id]
        if wc.status == WorkCenterStatus.BUSY or wc.current_job_id:
            busy += 1
    return busy / len(shop.workcenter_ids)


def _job_risk(job: Job, slack: int) -> float:
    """Score an individual incomplete job's schedule risk."""
    risk = 0.0
    if slack < 0:
        risk += 65
    else:
        risk += max(0, 35 - slack) * 1.2
    if job.block_reason:
        risk += 20
    if job.status == JobStatus.QUEUED:
        risk += min(12, job.queue_time * 0.8)
    risk += max(0, job.priority - 65) * 0.35
    return max(0.0, min(100.0, risk))


def _refresh_job_statuses(state: SimulationState) -> None:
    """Refresh dependency-driven job statuses without disturbing active work."""
    for job in state.jobs.values():
        if job.status == JobStatus.COMPLETE:
            continue
        if job.block_reason:
            job.status = JobStatus.BLOCKED
            state.blocked_jobs.add(job.id)
            continue
        state.blocked_jobs.discard(job.id)
        if job.status in {JobStatus.RUNNING, JobStatus.QUEUED, JobStatus.PAUSED, JobStatus.REWORK_REQUIRED}:
            continue
        if job.id == state.final_integration_job and not state.all_pieces_ready():
            job.status = JobStatus.NOT_READY
        elif state.is_dependency_complete(job.id):
            job.status = JobStatus.READY
        else:
            job.status = JobStatus.NOT_READY


def _refresh_piece_statuses(state: SimulationState) -> None:
    """Roll job statuses up into each puzzle piece's status and risk."""
    for piece in state.pieces.values():
        completed = sum(1 for job_id in piece.job_ids if state.jobs[job_id].status == JobStatus.COMPLETE)
        blocked = sum(1 for job_id in piece.job_ids if state.jobs[job_id].is_blocked)
        piece.completed_job_count = completed
        piece.total_job_count = len(piece.job_ids)
        incomplete_jobs = [state.jobs[job_id] for job_id in piece.job_ids if not state.jobs[job_id].is_complete]
        piece.risk_score = (
            max((job.risk_score for job in incomplete_jobs), default=0.0)
            + blocked * 4
            + max(0, state.current_shift - min((job.due_shift for job in incomplete_jobs), default=state.deadline_shift)) * 0.5
        )
        piece.risk_score = min(100.0, piece.risk_score)
        piece.estimated_completion_shift = max(
            [state.jobs[job_id].due_shift for job_id in piece.job_ids if not state.jobs[job_id].is_complete]
            or [state.current_shift]
        )
        if completed == piece.total_job_count:
            piece.ready_for_integration = True
            piece.status = PieceStatus.INTEGRATED if piece.integrated else PieceStatus.READY_FOR_INTEGRATION
        elif blocked:
            piece.status = PieceStatus.BLOCKED
        elif completed == 0:
            piece.status = PieceStatus.NOT_STARTED
        elif piece.risk_score >= 65:
            piece.status = PieceStatus.AT_RISK
        else:
            piece.status = PieceStatus.IN_PROGRESS
    if state.final_item_completed:
        for piece in state.pieces.values():
            piece.integrated = True
            piece.status = PieceStatus.INTEGRATED


def _refresh_shop_statuses(state: SimulationState) -> None:
    """Roll job/workcenter state up into shop queues, utilization, and risk."""
    for shop in state.shops.values():
        shop.active_job_ids = []
        shop.queued_job_ids = []
        shop.blocked_job_ids = []
        shop.completed_job_ids = []
        shop.idle_time = 0
        for job in state.jobs.values():
            if job.shop_id != shop.id:
                continue
            if job.status == JobStatus.COMPLETE:
                shop.completed_job_ids.append(job.id)
            elif job.status == JobStatus.RUNNING:
                shop.active_job_ids.append(job.id)
            elif job.status == JobStatus.QUEUED:
                shop.queued_job_ids.append(job.id)
            elif job.is_blocked:
                shop.blocked_job_ids.append(job.id)
        shop.utilization = shop_utilization(state, shop.id)
        shop.idle_time = sum(
            1
            for wc_id in shop.workcenter_ids
            if state.workcenters[wc_id].status in {WorkCenterStatus.AVAILABLE, WorkCenterStatus.IDLE}
            and not state.workcenters[wc_id].current_job_id
        )
        shop.risk_score = min(
            100.0,
            len(shop.queued_job_ids) * 1.5
            + len(shop.blocked_job_ids) * 4
            + max((state.jobs[job_id].risk_score for job_id in shop.queued_job_ids + shop.blocked_job_ids), default=0.0),
        )


def day_shift(shift: int, shifts_per_day: int = 3) -> str:
    """Format a one-based shift number as a day/shift label."""
    if shift <= 0:
        return "Day 1, Shift 1"
    day = ((shift - 1) // shifts_per_day) + 1
    in_day = ((shift - 1) % shifts_per_day) + 1
    return f"Day {day}, Shift {in_day}"
