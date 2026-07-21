"""Derived metrics for twenty independently progressing jobs."""

from __future__ import annotations

from .models import MetricSnapshot, SimulationState


def daily_progress_days(remaining_days: list[int]) -> list[int]:
    """Return smooth per-job progress, accelerating an outlier or final job."""
    if not remaining_days:
        return []
    if len(remaining_days) == 1:
        return [min(2, remaining_days[0])]

    ordered = sorted(remaining_days, reverse=True)
    longest, next_longest = ordered[:2]
    return [
        3 if days == longest and longest > next_longest + 2 else 1
        for days in remaining_days
    ]


def projected_workdays(remaining_days: list[int]) -> int:
    """Forecast completion using the same smooth daily progression rules."""
    forecast = [max(0, days) for days in remaining_days if days > 0]
    workdays = 0
    while forecast:
        progress = daily_progress_days(forecast)
        forecast = [
            days - progress_days
            for days, progress_days in zip(forecast, progress, strict=True)
            if days - progress_days > 0
        ]
        workdays += 1
    return workdays


def update_state_metrics(state: SimulationState) -> None:
    state.completed_jobs = {job.id for job in state.jobs.values() if job.is_complete}
    state.final_item_completed = len(state.completed_jobs) == len(state.jobs)
    if state.final_item_completed and state.completion_day is None:
        state.completion_day = state.current_day


def calculate_snapshot(state: SimulationState) -> MetricSnapshot:
    update_state_metrics(state)
    incomplete = state.incomplete_jobs()
    remaining = [max(0, job.remaining_days) for job in incomplete]
    workdays_remaining = projected_workdays(remaining)
    projected = state.completion_day or state.current_day + max(0, workdays_remaining - 1)
    return MetricSnapshot(
        jobs_remaining=len(incomplete),
        total_remaining_days=sum(max(0, job.remaining_days) for job in incomplete),
        projected_completion_day=projected,
        final_item_completed=state.final_item_completed,
    )
