"""Hidden ECHO benchmark scheduler with proactive routing heuristics."""

from __future__ import annotations

from ..enums import EventType, JobStatus, TargetType, WorkCenterStatus
from ..metrics import recalculate_critical_path, update_state_metrics
from ..models import Event, Job, SimulationState, WorkCenter
from .base import Scheduler, downstream_count


class AutomatedScheduler(Scheduler):
    """Scheduler that continuously optimizes for slack and downstream unlocks."""

    name = "automated"

    def plan_day(self, state: SimulationState, known_events: list[Event]) -> None:
        """React to known disruptions before shift-level queue assignment."""
        update_state_metrics(state)
        self._respond_to_known_events(state, known_events)
        self.plan_shift(state)

    def plan_shift(self, state: SimulationState) -> None:
        """Reorder queues and assign/preempt jobs using benchmark heuristics."""
        update_state_metrics(state)
        recalculate_critical_path(state)
        self._clean_and_reorder_queues(state)
        ready_jobs = sorted(state.get_ready_jobs(), key=lambda job: self._job_score(state, job), reverse=True)
        for job in ready_jobs:
            if job.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETE}:
                continue
            wc = self._best_workcenter(state, job)
            if not wc:
                continue
            if wc.current_job_id and self._should_preempt(state, job, wc):
                state.preempt_current_job(wc.id, job.id)
            else:
                state.assign_job(job.id, wc.id, front=job.critical_path or job.priority >= 85)
        self._clean_and_reorder_queues(state)

    def _respond_to_known_events(self, state: SimulationState, known_events: list[Event]) -> None:
        """Adjust priorities/routes for warnings and active disruptions."""
        for event in known_events:
            if event.type == EventType.DELAYED_MATERIAL and event.target_id in state.jobs:
                target = state.jobs[event.target_id]
                for dep_id in target.dependent_job_ids:
                    if dep_id in state.jobs:
                        state.jobs[dep_id].priority += 4
                if not target.is_complete and state.is_dependency_complete(target.id):
                    target.priority += 12
            elif event.type == EventType.WEATHER and event.target_type == TargetType.SHOP:
                for job in state.jobs.values():
                    if job.shop_id != event.target_id and not job.is_complete:
                        if job.critical_path:
                            job.priority += 6
                    elif job.shop_id == event.target_id and state.is_dependency_complete(job.id):
                        job.priority += 3
            elif event.type in {EventType.MACHINE_DOWN, EventType.FACILITY_OUTAGE}:
                affected_wcs = []
                if event.target_type == TargetType.WORKCENTER:
                    affected_wcs = [event.target_id]
                elif event.target_type == TargetType.SHOP and event.target_id in state.shops:
                    affected_wcs = state.shops[event.target_id].workcenter_ids
                for wc_id in affected_wcs:
                    if wc_id not in state.workcenters:
                        continue
                    wc = state.workcenters[wc_id]
                    moving = list(wc.queue)
                    if wc.current_job_id:
                        moving.append(wc.current_job_id)
                    for job_id in moving:
                        # ECHO only moves critical work out of disrupted areas;
                        # routine work absorbs the queue churn instead.
                        if job_id in state.jobs and state.jobs[job_id].critical_path:
                            alt = self._best_workcenter(state, state.jobs[job_id], exclude={wc_id})
                            if alt:
                                state.assign_job(job_id, alt.id, front=True)

    def _clean_and_reorder_queues(self, state: SimulationState) -> None:
        """Remove invalid queue entries and sort remaining jobs by score."""
        for wc in state.workcenters.values():
            clean_queue = [
                job_id
                for job_id in wc.queue
                if job_id in state.jobs
                and state.jobs[job_id].status != JobStatus.COMPLETE
                and not state.jobs[job_id].block_reason
                and state.is_dependency_complete(job_id)
            ]
            clean_queue.sort(key=lambda job_id: self._job_score(state, state.jobs[job_id], wc), reverse=True)
            if clean_queue != wc.queue:
                if wc.queue:
                    state.reschedule_count += 1
                wc.queue = clean_queue

    def _best_workcenter(
        self,
        state: SimulationState,
        job: Job,
        exclude: set[str] | None = None,
    ) -> WorkCenter | None:
        """Choose the highest-scoring capable workcenter for a job."""
        exclude = exclude or set()
        candidates = [
            state.workcenters[wc_id]
            for wc_id in job.candidate_workcenter_ids
            if wc_id in state.workcenters
            and wc_id not in exclude
            and job.required_capability in state.workcenters[wc_id].capabilities
            and state.workcenters[wc_id].status
            not in {WorkCenterStatus.DOWN, WorkCenterStatus.BLOCKED, WorkCenterStatus.WEATHER_IMPACTED}
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda wc: self._assignment_score(state, job, wc))

    def _assignment_score(self, state: SimulationState, job: Job, wc: WorkCenter) -> float:
        """Score a job/workcenter pairing for queue assignment decisions."""
        # Higher scores favor urgent, critical, high-unlock jobs on efficient
        # low-queue workcenters, while still charging for cross-shop movement.
        queue_penalty = len(wc.queue) * 9 + (8 if wc.current_job_id else 0)
        shop_bonus = 4 if wc.shop_id == job.shop_id else -2
        efficiency_bonus = wc.efficiency * 12
        unlock_bonus = downstream_count(state, job) * 1.8
        critical_bonus = 30 if job.critical_path else 0
        slack = job.due_shift - state.current_shift - max(1, job.remaining_duration_shifts)
        slack_bonus = max(0, 20 - slack) * 2.2
        return (
            job.priority
            + critical_bonus
            + slack_bonus
            + unlock_bonus
            + efficiency_bonus
            + shop_bonus
            - queue_penalty
            - job.transport_delay_shifts
            - job.setup_time_shifts
        )

    def _job_score(self, state: SimulationState, job: Job, wc: WorkCenter | None = None) -> float:
        """Score a job independently, with optional workcenter context."""
        slack = job.due_shift - state.current_shift - max(1, job.remaining_duration_shifts)
        score = job.priority + downstream_count(state, job) * 2.5
        if job.critical_path:
            score += 42
        score += max(0, 24 - slack) * 2.8
        score -= job.queue_time * 0.6
        if job.block_reason:
            score -= 100
        if wc:
            score += wc.efficiency * 5 - len(wc.queue) * 3
        return score

    def _should_preempt(self, state: SimulationState, job: Job, wc: WorkCenter) -> bool:
        """Return whether replacing current work is worth the disruption."""
        if not wc.current_job_id:
            return False
        if not (job.critical_path or job.priority >= 88):
            return False
        current = state.jobs[wc.current_job_id]
        if current.critical_path and current.due_shift <= job.due_shift:
            return False
        gain = self._job_score(state, job, wc) - self._job_score(state, current, wc)
        return gain > 38 and job.remaining_duration_shifts <= max(8, current.remaining_duration_shifts + 3)
