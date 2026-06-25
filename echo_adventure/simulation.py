"""Core shift/day advancement logic for a scheduler-controlled run."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass

from .enums import JobStatus, WorkCenterStatus
from .events import refresh_event_state
from .metrics import calculate_snapshot, update_state_metrics
from .models import MetricSnapshot, Scenario, SimulationState
from .schedulers.base import Scheduler


@dataclass
class DayResult:
    """Summary of one in-game day after all shifts are processed."""

    completed_job_ids: list[str]
    notes: list[str]
    start_snapshot: MetricSnapshot
    end_snapshot: MetricSnapshot


def initialize_state(scenario: Scenario, shifts_per_day: int) -> SimulationState:
    """Deep-copy a scenario into mutable state for one scheduler."""
    state = SimulationState(
        scenario_id=scenario.scenario_id,
        seed=scenario.seed,
        deadline_shift=scenario.deadline_shift,
        shifts_per_day=shifts_per_day,
        shops=copy.deepcopy(scenario.shops),
        workcenters=copy.deepcopy(scenario.workcenters),
        pieces=copy.deepcopy(scenario.pieces),
        jobs=copy.deepcopy(scenario.jobs),
        event_timeline=copy.deepcopy(scenario.event_timeline),
        decision_cards=copy.deepcopy(scenario.decision_cards),
        daily_decision_roots=copy.deepcopy(scenario.daily_decision_roots),
        daily_decision_counts=copy.deepcopy(scenario.daily_decision_counts),
    )
    update_state_metrics(state)
    return state


def advance_day(state: SimulationState, scheduler: Scheduler) -> DayResult:
    """Let a scheduler plan, then process up to one day's worth of shifts."""
    update_state_metrics(state)
    start_snapshot = calculate_snapshot(state)
    completed_before = set(state.completed_jobs)
    notes_start = len(state.daily_notes)
    # Day-level planning can react to active disruptions and warnings before
    # individual shift processing starts.
    scheduler.plan_day(state, _known_events(state))

    for _ in range(state.shifts_per_day):
        if state.final_item_completed or state.current_shift >= state.deadline_shift:
            break
        advance_shift(state, scheduler)

    update_state_metrics(state)
    end_snapshot = calculate_snapshot(state)
    state.metric_history.append(end_snapshot)
    completed_today = sorted(state.completed_jobs - completed_before)
    notes = state.daily_notes[notes_start:]
    return DayResult(
        completed_job_ids=completed_today,
        notes=notes,
        start_snapshot=start_snapshot,
        end_snapshot=end_snapshot,
    )


def advance_shift(state: SimulationState, scheduler: Scheduler) -> None:
    """Advance one shift in event, planning, work, queue-aging order."""
    state.current_shift += 1
    # Events are applied before planning so schedulers see fresh downtime,
    # blocks, and warnings when assigning or resequencing work.
    refresh_event_state(state)
    update_state_metrics(state)
    scheduler.plan_shift(state)
    _start_available_jobs(state)
    _process_workcenters(state)
    _age_queues(state)
    update_state_metrics(state)


def complete_job(state: SimulationState, job_id: str) -> None:
    """Complete a job, unless completion inspection creates rework."""
    job = state.jobs[job_id]
    if _maybe_require_completion_rework(state, job):
        return
    job.status = JobStatus.COMPLETE
    job.completed_shift = state.current_shift
    job.remaining_duration_shifts = 0
    job.block_reason = None
    state.completed_jobs.add(job_id)
    state.blocked_jobs.discard(job_id)
    state.remove_job_from_queues(job_id)
    for wc in state.workcenters.values():
        if wc.current_job_id == job_id:
            wc.current_job_id = None
            wc.status = WorkCenterStatus.AVAILABLE
    state.daily_notes.append(f"Completed {job_id}.")
    _complete_project_if_ready(state)


def _maybe_require_completion_rework(state: SimulationState, job) -> bool:
    """Apply preassigned completion rework, if this job has a scenario defect."""
    if job.completion_rework_consumed:
        return False

    if job.planned_completion_rework_shifts <= 0:
        return False

    extra_shifts = job.planned_completion_rework_shifts
    job.completion_rework_consumed = True
    job.rework_count += 1
    job.status = JobStatus.REWORK_REQUIRED
    job.completed_shift = None
    job.remaining_duration_shifts = extra_shifts
    job.priority += 12
    job.risk_score = min(100.0, job.risk_score + 12 + extra_shifts * 3)
    job.queue_time = 0

    state.reschedule_count += 1
    state.completed_jobs.discard(job.id)
    state.remove_job_from_queues(job.id)

    for wc in state.workcenters.values():
        if wc.current_job_id == job.id:
            wc.current_job_id = None
            wc.status = WorkCenterStatus.AVAILABLE

    state.daily_notes.append(
        f"Quality rework flagged on {job.id}; added {extra_shifts} shift(s)."
    )
    return True


def _complete_project_if_ready(state: SimulationState) -> None:
    """Mark the run complete once every top-level job's subjobs are finished."""
    if state.final_item_completed:
        return
    if not all(
        all(state.jobs[job_id].status == JobStatus.COMPLETE for job_id in piece.job_ids)
        for piece in state.pieces.values()
    ):
        return
    state.final_item_completed = True
    state.completion_shift = state.current_shift
    state.daily_notes.append(f"All jobs completed at shift {state.current_shift}.")


def _start_available_jobs(state: SimulationState) -> None:
    """Move queued jobs onto idle workcenters when they are still valid."""
    for wc in state.workcenters.values():
        if wc.current_job_id:
            continue
        if wc.status not in {WorkCenterStatus.AVAILABLE, WorkCenterStatus.IDLE}:
            continue
        while wc.queue:
            job_id = wc.queue.pop(0)
            if job_id not in state.jobs:
                continue
            job = state.jobs[job_id]
            if job.status == JobStatus.COMPLETE:
                continue
            if job.block_reason or not state.is_dependency_complete(job_id):
                job.status = JobStatus.BLOCKED if job.block_reason else JobStatus.NOT_READY
                continue
            if job.required_capability not in wc.capabilities:
                continue
            if not job.started_once:
                # Duration is locked when the job starts, because reroutes and
                # workcenter efficiency should not keep re-scaling active work.
                planned = job.planned_duration
                adjusted = max(1, math.ceil(planned / max(0.2, wc.efficiency)))
                if wc.id != job.candidate_workcenter_ids[0]:
                    adjusted += 1
                job.remaining_duration_shifts = max(1, adjusted)
                job.started_once = True
            job.status = JobStatus.RUNNING
            job.assigned_workcenter_id = wc.id
            wc.current_job_id = job_id
            wc.status = WorkCenterStatus.BUSY
            break
        if wc.status == WorkCenterStatus.AVAILABLE:
            wc.status = WorkCenterStatus.IDLE


def _process_workcenters(state: SimulationState) -> None:
    """Consume one shift of capacity across all workcenters."""
    disrupted = {WorkCenterStatus.DOWN, WorkCenterStatus.BLOCKED, WorkCenterStatus.WEATHER_IMPACTED}
    for wc in state.workcenters.values():
        if wc.status in disrupted:
            state.idle_disrupted_time += 1
            continue
        state.available_shift_count += 1
        if wc.current_job_id:
            job = state.jobs[wc.current_job_id]
            if job.status == JobStatus.PAUSED:
                state.idle_blocked_time += 1
                continue
            state.busy_shift_count += 1
            job.remaining_duration_shifts -= 1
            if job.remaining_duration_shifts <= 0:
                complete_job(state, job.id)
        else:
            state.idle_time += 1
            if wc.queue:
                state.idle_blocked_time += 1
            if wc.status == WorkCenterStatus.BUSY:
                wc.status = WorkCenterStatus.AVAILABLE


def _age_queues(state: SimulationState) -> None:
    """Increment queue-time pressure for queued jobs."""
    queued: set[str] = set()
    for wc in state.workcenters.values():
        for job_id in wc.queue:
            if job_id in state.jobs and state.jobs[job_id].status == JobStatus.QUEUED:
                queued.add(job_id)
    for job_id in queued:
        state.jobs[job_id].queue_time += 1


def _known_events(state: SimulationState):
    """Return events the scheduler is allowed to know about today."""
    known = []
    for event in state.event_timeline:
        if event.id in state.known_warnings or event.id in state.active_events:
            known.append(event)
    return known
