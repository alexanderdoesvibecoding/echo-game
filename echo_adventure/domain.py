"""Runtime maintenance for decision-driven manufacturing resources."""

from __future__ import annotations

from .enums import JobStatus, ResourceStatus, WorkCenterStatus
from .models import Job, SimulationState


def refresh_domain_constraints(state: SimulationState) -> list[str]:
    """Advance finite-resource holds and return releasable completed job ids."""
    current = state.current_shift
    releasable: list[str] = []

    for worker in state.workers.values():
        if not worker.available and worker.unavailable_until < current:
            worker.available = True
            worker.unavailable_until = 0
            worker.fatigue = max(0, worker.fatigue - 1)

    for resource in state.shared_resources.values():
        if resource.unavailable_until and resource.unavailable_until < current:
            resource.unavailable_until = 0
            if resource.status in {ResourceStatus.UNAVAILABLE, ResourceStatus.HELD, ResourceStatus.NEEDS_REVIEW}:
                resource.status = ResourceStatus.AVAILABLE
            resource.available_capacity = max(resource.available_capacity, resource.capacity)
            if resource.condition in {"held", "offline", "blocked"}:
                resource.condition = "ready"

    for document in state.documents.values():
        if document.unavailable_until and document.unavailable_until < current:
            document.unavailable_until = 0
            document.available = True

    for wc in state.workcenters.values():
        if wc.decision_downtime_until >= current and wc.decision_downtime_reason:
            wc.downtime_remaining = max(1, wc.decision_downtime_until - current + 1)
            reason = wc.decision_downtime_reason
            wc.blocked_reason = f"Decision: {reason}"
            wc.status = (
                WorkCenterStatus.WEATHER_IMPACTED
                if reason == "weather"
                else WorkCenterStatus.DOWN
                if reason == "down"
                else WorkCenterStatus.BLOCKED
            )
            if wc.current_job_id and wc.current_job_id in state.jobs:
                state.jobs[wc.current_job_id].status = JobStatus.PAUSED
            continue
        if wc.decision_downtime_reason:
            wc.decision_downtime_reason = None
            wc.decision_downtime_until = 0
            if wc.blocked_reason and wc.blocked_reason.startswith("Decision:"):
                wc.blocked_reason = None
                wc.downtime_remaining = 0
                if wc.current_job_id:
                    state.jobs[wc.current_job_id].status = JobStatus.RUNNING
                    wc.status = WorkCenterStatus.BUSY
                else:
                    wc.status = WorkCenterStatus.AVAILABLE

    for job in state.jobs.values():
        if job.is_complete:
            continue
        if job.block_reason == "Decision: waiting on manufacturing resource" and job_domain_ready(state, job):
            job.block_reason = None
            state.blocked_jobs.discard(job.id)
            job.status = JobStatus.READY if state.is_dependency_complete(job.id) else JobStatus.NOT_READY
        if job.decision_block_reason and job.decision_blocked_until >= current:
            job.block_reason = f"Decision: {job.decision_block_reason}"
            job.status = JobStatus.BLOCKED
            state.blocked_jobs.add(job.id)
        elif job.decision_block_reason:
            job.decision_block_reason = None
            job.decision_blocked_until = 0
            if job.block_reason and job.block_reason.startswith("Decision:"):
                job.block_reason = None
            state.blocked_jobs.discard(job.id)
            job.status = JobStatus.READY if state.is_dependency_complete(job.id) else JobStatus.NOT_READY

        if job.acceptance_hold and job.acceptance_hold_until < current:
            job.acceptance_hold = False
            job.acceptance_hold_until = 0
            if job.document_id and job.document_id in state.documents:
                document = state.documents[job.document_id]
                document.held_job_ids = [job_id for job_id in document.held_job_ids if job_id != job.id]
            if job.block_reason and job.block_reason.startswith("Decision: acceptance"):
                job.block_reason = None
                state.blocked_jobs.discard(job.id)
            if job.remaining_duration_shifts <= 0:
                releasable.append(job.id)

    return releasable


def job_domain_ready(state: SimulationState, job: Job) -> bool:
    """Return whether real worker/material/document/resource constraints permit a start."""
    if job.worker_id and (worker := state.workers.get(job.worker_id)):
        if not worker.available or job.required_capability not in worker.skills:
            return False
    if job.material_id and not job.material_consumed and (stock := state.material_stocks.get(job.material_id)):
        if not stock.verified or stock.quantity <= 0:
            return False
    if job.document_id and (document := state.documents.get(job.document_id)):
        if not document.available or not document.approved:
            return False
    if job.fixture_id and (fixture := state.shared_resources.get(job.fixture_id)):
        if not fixture.certified or fixture.status in {ResourceStatus.UNAVAILABLE, ResourceStatus.HELD}:
            return False
    for resource_id in job.support_resource_ids:
        resource = state.shared_resources.get(resource_id)
        if resource and resource.status == ResourceStatus.UNAVAILABLE:
            return False
    return True


def claim_job_resources(state: SimulationState, job: Job) -> None:
    """Reserve consumable and reusable resources when a job begins."""
    if job.material_id and not job.material_consumed and (stock := state.material_stocks.get(job.material_id)):
        stock.quantity = max(0, stock.quantity - 1)
        job.material_consumed = True
        if job.id not in stock.reserved_job_ids:
            stock.reserved_job_ids.append(job.id)
    if job.worker_id and (worker := state.workers.get(job.worker_id)):
        worker.assigned_job_id = job.id
    for resource_id in [job.fixture_id, *job.support_resource_ids]:
        if not resource_id or resource_id not in state.shared_resources:
            continue
        resource = state.shared_resources[resource_id]
        if job.id not in resource.holder_job_ids:
            resource.holder_job_ids.append(job.id)


def release_job_resources(state: SimulationState, job: Job) -> None:
    """Release reusable resources after completion."""
    if job.worker_id and (worker := state.workers.get(job.worker_id)) and worker.assigned_job_id == job.id:
        worker.assigned_job_id = None
    for resource_id in [job.fixture_id, *job.support_resource_ids]:
        if not resource_id or resource_id not in state.shared_resources:
            continue
        resource = state.shared_resources[resource_id]
        resource.holder_job_ids = [job_id for job_id in resource.holder_job_ids if job_id != job.id]
