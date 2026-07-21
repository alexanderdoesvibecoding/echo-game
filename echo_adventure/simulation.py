"""Daily progression for all incomplete jobs, accelerated for the final job."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from .enums import JobStatus
from .metrics import calculate_snapshot, daily_progress_days, update_state_metrics
from .models import MetricSnapshot, Scenario, SimulationState


@dataclass
class DayResult:
    day: int
    completed_job_ids: list[str]
    notes: list[str]
    start_snapshot: MetricSnapshot
    end_snapshot: MetricSnapshot


def initialize_state(scenario: Scenario) -> SimulationState:
    state = SimulationState(
        seed=scenario.seed,
        jobs=copy.deepcopy(scenario.jobs),
    )
    update_state_metrics(state)
    return state


def complete_job(state: SimulationState, job_id: str) -> None:
    job = state.jobs[job_id]
    if job.is_complete:
        return
    job.remaining_days = 0
    job.status = JobStatus.COMPLETE
    job.completed_day = state.current_day
    state.completed_jobs.add(job.id)
    state.daily_notes.append(f"{job.name} completed.")
    update_state_metrics(state)


def advance_day(state: SimulationState) -> DayResult:
    """Advance work, finishing the sole remaining job within two workdays."""
    day = state.current_day
    state.daily_notes.clear()
    start_snapshot = calculate_snapshot(state)
    state.cumulative_unfinished_job_days += start_snapshot.total_remaining_days
    completed_before = set(state.completed_jobs)

    incomplete = list(state.incomplete_jobs())
    progress = daily_progress_days([job.remaining_days for job in incomplete])
    for job, progress_days in zip(incomplete, progress, strict=True):
        job.remaining_days = max(0, job.remaining_days - progress_days)
        if job.remaining_days == 0:
            complete_job(state, job.id)

    update_state_metrics(state)
    end_snapshot = calculate_snapshot(state)
    completed_today = sorted(state.completed_jobs - completed_before)
    result = DayResult(
        day=day,
        completed_job_ids=completed_today,
        notes=list(state.daily_notes),
        start_snapshot=start_snapshot,
        end_snapshot=end_snapshot,
    )
    if not state.final_item_completed:
        state.current_day += 1
    return result
