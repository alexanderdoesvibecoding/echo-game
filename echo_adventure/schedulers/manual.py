"""Player-side scheduler used after daily manual decisions are applied."""

from __future__ import annotations

from ..enums import JobStatus, WorkCenterStatus
from ..metrics import update_state_metrics
from ..models import Event, Job, SimulationState, WorkCenter
from .base import Scheduler


class ManualScheduler(Scheduler):
    """A conservative scheduler that fills queues by priority and due date."""

    name = "manual"

    def plan_day(self, state: SimulationState, known_events: list[Event]) -> None:
        """Refresh metrics and make an initial queueing pass for the day."""
        update_state_metrics(state)
        self.plan_shift(state)

    def plan_shift(self, state: SimulationState) -> None:
        """Assign ready jobs into compatible queues without aggressive churn."""
        update_state_metrics(state)
        ready_jobs = sorted(
            state.get_ready_jobs(),
            key=lambda job: (-job.priority, job.due_shift, job.queue_time, job.id),
        )
        for job in ready_jobs:
            if job.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETE}:
                continue
            wc = self._choose_workcenter(state, job)
            if wc:
                state.assign_job(job.id, wc.id)

    def _choose_workcenter(self, state: SimulationState, job: Job) -> WorkCenter | None:
        """Prefer the existing assignment, then the shortest viable queue."""
        if job.assigned_workcenter_id:
            assigned = state.workcenters[job.assigned_workcenter_id]
            if assigned.status not in {
                WorkCenterStatus.DOWN,
                WorkCenterStatus.BLOCKED,
                WorkCenterStatus.WEATHER_IMPACTED,
            }:
                return assigned
            return None
        primary = [
            state.workcenters[wc_id]
            for wc_id in job.candidate_workcenter_ids
            if wc_id in state.workcenters
            and state.workcenters[wc_id].shop_id == job.shop_id
            and state.workcenters[wc_id].status
            not in {WorkCenterStatus.DOWN, WorkCenterStatus.BLOCKED, WorkCenterStatus.WEATHER_IMPACTED}
        ]
        candidates = primary or [
            state.workcenters[wc_id]
            for wc_id in job.candidate_workcenter_ids
            if wc_id in state.workcenters
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
        )
