"""Derived metrics for twenty independently progressing jobs."""

from __future__ import annotations

from .models import MetricSnapshot, SimulationState


def update_state_metrics(state: SimulationState) -> None:
    state.completed_jobs = {job.id for job in state.jobs.values() if job.is_complete}
    state.final_item_completed = len(state.completed_jobs) == len(state.jobs)
    if state.final_item_completed and state.completion_day is None:
        state.completion_day = state.current_day


def calculate_snapshot(state: SimulationState) -> MetricSnapshot:
    update_state_metrics(state)
    incomplete = state.incomplete_jobs()
    longest = max((max(0, job.remaining_days) for job in incomplete), default=0)
    projected = state.completion_day or state.current_day + max(0, longest - 1)
    return MetricSnapshot(
        day=state.current_day,
        jobs_completed=len(state.completed_jobs),
        jobs_remaining=len(incomplete),
        total_remaining_days=sum(max(0, job.remaining_days) for job in incomplete),
        projected_completion_day=projected,
        final_item_completed=state.final_item_completed,
    )


def calculate_final_score(state: SimulationState) -> float:
    return round(state.decision_score, 2)
