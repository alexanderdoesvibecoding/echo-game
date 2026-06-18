from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Event, Job, SimulationState, WorkCenter


class Scheduler(ABC):
    name: str = "scheduler"

    @abstractmethod
    def plan_day(self, state: SimulationState, known_events: list[Event]) -> None:
        """Apply day-level planning for a runtime state."""

    @abstractmethod
    def plan_shift(self, state: SimulationState) -> None:
        """Fill open workcenter slots and maintain queues before a shift advances."""


def usable_workcenter(wc: WorkCenter) -> bool:
    from ..enums import WorkCenterStatus

    return wc.status in {WorkCenterStatus.AVAILABLE, WorkCenterStatus.IDLE, WorkCenterStatus.BUSY} or (
        wc.status.value == "Busy" and wc.current_job_id is not None
    )


def downstream_count(state: SimulationState, job: Job) -> int:
    seen: set[str] = set()
    stack = list(job.dependent_job_ids)
    while stack:
        job_id = stack.pop()
        if job_id in seen or job_id not in state.jobs:
            continue
        seen.add(job_id)
        stack.extend(state.jobs[job_id].dependent_job_ids)
    return len(seen)
