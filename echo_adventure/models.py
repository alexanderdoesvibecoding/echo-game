"""Dataclasses for the generated scenario and mutable simulation state."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .enums import (
    DecisionType,
    EventType,
    JobStatus,
    PieceStatus,
    TargetType,
    WorkCenterStatus,
)


@dataclass
class Shop:
    """A manufacturing shop that owns workcenters and roll-up metrics."""

    id: str
    name: str
    capabilities: list[str]
    workcenter_ids: list[str]
    active_job_ids: list[str] = field(default_factory=list)
    queued_job_ids: list[str] = field(default_factory=list)
    blocked_job_ids: list[str] = field(default_factory=list)
    completed_job_ids: list[str] = field(default_factory=list)
    utilization: float = 0.0
    idle_time: int = 0
    risk_score: float = 0.0


@dataclass
class WorkCenter:
    """A machine/station that can process queued jobs matching capabilities."""

    id: str
    shop_id: str
    name: str
    capabilities: list[str]
    efficiency: float
    status: WorkCenterStatus = WorkCenterStatus.AVAILABLE
    current_job_id: str | None = None
    queue: list[str] = field(default_factory=list)
    downtime_remaining: int = 0
    blocked_reason: str | None = None

    @property
    def load(self) -> int:
        """Return queued-plus-running load for scheduling comparisons."""
        return len(self.queue) + (1 if self.current_job_id else 0)

    @property
    def is_disrupted(self) -> bool:
        """Return whether this workcenter is unavailable due to a disruption."""
        return self.status in {
            WorkCenterStatus.DOWN,
            WorkCenterStatus.BLOCKED,
            WorkCenterStatus.WEATHER_IMPACTED,
        }


def least_loaded_workcenter(
    candidates: Iterable[WorkCenter],
    preferred_shop_id: str,
) -> WorkCenter | None:
    """Return the lowest-load workcenter, preferring a shop only as a tiebreaker."""
    candidate_list = list(candidates)
    if not candidate_list:
        return None
    return min(
        candidate_list,
        key=lambda wc: (
            wc.load,
            0 if wc.shop_id == preferred_shop_id else 1,
            wc.id,
        ),
    )


@dataclass
class PuzzlePiece:
    """A product/puzzle piece made complete by finishing its subjobs."""

    id: str
    name: str
    job_ids: list[str]
    status: PieceStatus = PieceStatus.NOT_STARTED
    completed_job_count: int = 0
    total_job_count: int = 0
    risk_score: float = 0.0
    estimated_completion_shift: int = 0
    completed: bool = False


@dataclass
class Job:
    """A schedulable unit of work with dependencies and routing options."""

    id: str
    piece_id: str
    shop_id: str
    required_capability: str
    candidate_workcenter_ids: list[str]
    assigned_workcenter_id: str | None
    base_duration_shifts: int
    remaining_duration_shifts: int
    setup_time_shifts: int
    transport_delay_shifts: int
    dependency_ids: list[str]
    dependent_job_ids: list[str] = field(default_factory=list)
    status: JobStatus = JobStatus.NOT_READY
    priority: int = 50
    due_shift: int = 90
    risk_score: float = 0.0
    critical_path: bool = False
    block_reason: str | None = None
    started_once: bool = False
    completed_shift: int | None = None
    queue_time: int = 0
    rework_count: int = 0

    planned_completion_rework_shifts: int = 0
    completion_rework_consumed: bool = False

    @property
    def planned_duration(self) -> int:
        """Return the initial duration before workcenter efficiency is applied."""
        return self.base_duration_shifts + self.setup_time_shifts + self.transport_delay_shifts

    @property
    def is_complete(self) -> bool:
        """Return whether the job is fully complete."""
        return self.status == JobStatus.COMPLETE

    @property
    def is_blocked(self) -> bool:
        """Return whether the job is blocked by status or an active reason."""
        return self.status == JobStatus.BLOCKED or self.block_reason is not None


def build_pending_job(
    *,
    id: str,
    piece_id: str,
    shop_id: str,
    required_capability: str,
    candidate_workcenter_ids: list[str],
    base_duration_shifts: int,
    dependency_ids: list[str],
    priority: int,
    due_shift: int,
    risk_score: float,
    setup_time_shifts: int = 0,
    transport_delay_shifts: int = 0,
    remaining_duration_shifts: int | None = None,
) -> Job:
    """Build an unassigned not-ready job with standard runtime defaults."""
    planned_duration = base_duration_shifts + setup_time_shifts + transport_delay_shifts
    return Job(
        id=id,
        piece_id=piece_id,
        shop_id=shop_id,
        required_capability=required_capability,
        candidate_workcenter_ids=list(candidate_workcenter_ids),
        assigned_workcenter_id=None,
        base_duration_shifts=base_duration_shifts,
        remaining_duration_shifts=(
            planned_duration
            if remaining_duration_shifts is None
            else remaining_duration_shifts
        ),
        setup_time_shifts=setup_time_shifts,
        transport_delay_shifts=transport_delay_shifts,
        dependency_ids=list(dependency_ids),
        status=JobStatus.NOT_READY,
        priority=priority,
        due_shift=due_shift,
        risk_score=risk_score,
    )


@dataclass
class Event:
    """A disruption, warning, or follow-on risk in the scenario timeline."""

    id: str
    type: EventType
    target_type: TargetType
    target_id: str
    start_shift: int
    duration_shifts: int
    severity: int
    has_advance_warning: bool
    warning_shift: int | None
    description: str
    effects: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    started: bool = False
    parent_event_id: str | None = None
    chain_depth: int = 0

    @property
    def end_shift(self) -> int:
        """Return the first shift at which the event should be resolved."""
        return self.start_shift + self.duration_shifts


@dataclass
class DecisionChoice:
    """One selectable player response and its immediate scoring effects."""

    id: str
    label: str
    description: str
    immediate_effects: dict[str, Any]
    risk_effect: int
    reschedule_effect: int
    next_card_id: str | None = None
    future_unlock_card_ids: list[str] = field(default_factory=list)
    branch_tags_added: list[str] = field(default_factory=list)
    score_delta: float = 0.0


@dataclass
class DecisionCard:
    """A player decision prompt tied to the campaign graph and shop state."""

    id: str
    day: int
    type: DecisionType
    title: str
    description: str
    target_ids: list[str]
    severity: int
    choices: list[DecisionChoice]
    echo_choice_id: str | None = None
    required_tags: list[str] = field(default_factory=list)
    excluded_tags: list[str] = field(default_factory=list)
    campaign_priority: int = 100


@dataclass
class DecisionRecord:
    """A persisted audit entry for a player or ECHO decision."""

    day: int
    card_id: str
    card_title: str
    actor: str
    choice_id: str
    choice_label: str
    echo_choice_id: str | None
    echo_choice_label: str | None
    aligned_with_echo: bool
    note: str


@dataclass
class DecisionProgress:
    """Progress through a day's fixed number of decision questions."""

    day: int
    total_questions: int
    answered_questions: int
    visible_cards: int
    open_card_ids: list[str]


@dataclass
class CampaignDecisionGraph:
    """Prebuilt campaign-wide decision graph and day indexes.

    Graph size is controlled at generation time by GameConfig limits. Runtime
    selection only filters these existing nodes by day, branch tags, and
    unlocked card ids; it does not create future cards.
    """

    root_card_ids: list[str] = field(default_factory=list)
    cards_by_day: dict[int, list[str]] = field(default_factory=dict)
    event_card_ids_by_day: dict[int, list[str]] = field(default_factory=dict)
    max_active_cards_per_day: int = 0


@dataclass
class MetricSnapshot:
    """Point-in-time roll-up metrics used for summaries and final comparison."""

    shift: int
    day: int
    pieces_completed: int
    jobs_completed: int
    jobs_remaining: int
    jobs_behind_schedule: int
    jobs_late: int
    utilization: float
    idle_time: int
    reschedules: int
    schedule_risk: float
    projected_completion_shift: int
    final_item_completed: bool
    deadline_met: bool


@dataclass
class Scenario:
    """Immutable generated scenario template before a scheduler mutates state."""

    scenario_id: str
    seed: int
    shops: dict[str, Shop]
    workcenters: dict[str, WorkCenter]
    pieces: dict[str, PuzzlePiece]
    jobs: dict[str, Job]
    event_timeline: list[Event]
    deadline_shift: int
    decision_cards: dict[str, DecisionCard] = field(default_factory=dict)
    campaign_decision_graph: CampaignDecisionGraph = field(default_factory=CampaignDecisionGraph)


@dataclass
class SimulationState:
    """Mutable runtime state for one scheduler's version of a scenario."""

    scenario_id: str
    seed: int
    deadline_shift: int
    shifts_per_day: int
    shops: dict[str, Shop]
    workcenters: dict[str, WorkCenter]
    pieces: dict[str, PuzzlePiece]
    jobs: dict[str, Job]
    event_timeline: list[Event]
    decision_cards: dict[str, DecisionCard] = field(default_factory=dict)
    campaign_decision_graph: CampaignDecisionGraph = field(default_factory=CampaignDecisionGraph)
    unlocked_decision_card_ids: set[str] = field(default_factory=set)
    campaign_branch_tags: set[str] = field(default_factory=set)
    campaign_branch_tag_order: dict[str, int] = field(default_factory=dict)
    campaign_selected_choices: dict[str, str] = field(default_factory=dict)
    decision_path: list[str] = field(default_factory=list)
    decision_path_signature: str = ""
    decision_path_score_delta: float = 0.0
    max_schedule_risk_seen: float = 0.0
    current_shift: int = 0
    active_events: list[str] = field(default_factory=list)
    known_warnings: list[str] = field(default_factory=list)
    completed_jobs: set[str] = field(default_factory=set)
    blocked_jobs: set[str] = field(default_factory=set)
    reschedule_count: int = 0
    metric_history: list[MetricSnapshot] = field(default_factory=list)
    final_item_completed: bool = False
    completion_shift: int | None = None
    busy_shift_count: int = 0
    available_shift_count: int = 0
    idle_time: int = 0
    idle_blocked_time: int = 0
    idle_disrupted_time: int = 0
    daily_notes: list[str] = field(default_factory=list)
    decision_history: list[DecisionRecord] = field(default_factory=list)

    @property
    def current_day(self) -> int:
        """Return the one-based day number, capped at the deadline day."""
        return min(((self.current_shift) // self.shifts_per_day) + 1, self.deadline_shift // self.shifts_per_day)

    def is_dependency_complete(self, job_id: str) -> bool:
        """Return whether every predecessor for a job is in completed_jobs."""
        job = self.jobs[job_id]
        return all(dep_id in self.completed_jobs for dep_id in job.dependency_ids)

    def get_ready_jobs(self) -> list[Job]:
        """Return jobs that can be queued without violating dependencies."""
        ready: list[Job] = []
        for job in self.jobs.values():
            if job.status in {
                JobStatus.COMPLETE,
                JobStatus.RUNNING,
                JobStatus.QUEUED,
            }:
                continue
            if job.block_reason:
                continue
            if self.is_dependency_complete(job.id):
                ready.append(job)
        return ready

    def get_blocked_jobs(self) -> list[Job]:
        """Return jobs currently blocked by disruptions or explicit reasons."""
        return [job for job in self.jobs.values() if job.block_reason or job.status == JobStatus.BLOCKED]

    def get_critical_path_jobs(self) -> list[Job]:
        """Return incomplete critical-path jobs ordered by urgency."""
        return sorted(
            [job for job in self.jobs.values() if job.critical_path and not job.is_complete],
            key=lambda job: (job.due_shift, -job.priority),
        )

    def get_available_workcenters(self, capability: str | None = None) -> list[WorkCenter]:
        """Return idle/open workcenters, optionally filtered by capability."""
        centers = [
            wc
            for wc in self.workcenters.values()
            if wc.status in {WorkCenterStatus.AVAILABLE, WorkCenterStatus.IDLE}
            and wc.current_job_id is None
        ]
        if capability:
            centers = [wc for wc in centers if capability in wc.capabilities]
        return centers

    def get_bottleneck_shops(self, limit: int = 3) -> list[Shop]:
        """Return shops with the highest queued/blocked pressure."""
        return sorted(
            self.shops.values(),
            key=lambda shop: (len(shop.queued_job_ids) + len(shop.blocked_job_ids) * 2, shop.risk_score),
            reverse=True,
        )[:limit]

    def all_pieces_ready(self) -> bool:
        """Return whether every puzzle piece has completed its required jobs."""
        return all(piece.completed for piece in self.pieces.values())

    def remove_job_from_queues(self, job_id: str) -> None:
        """Remove a job from every workcenter/shop queue that may reference it."""
        for wc in self.workcenters.values():
            if job_id in wc.queue:
                wc.queue = [queued_id for queued_id in wc.queue if queued_id != job_id]
        for shop in self.shops.values():
            if job_id in shop.queued_job_ids:
                shop.queued_job_ids = [queued_id for queued_id in shop.queued_job_ids if queued_id != job_id]

    def clear_job_from_current_workcenters(self, job_id: str, except_workcenter_id: str | None = None) -> bool:
        """Remove a job from active workcenter slots outside the given target.

        Disrupted workcenters keep their disrupted status/reason. The job is
        being moved, not repairing the old workcenter.
        """
        cleared = False

        for old_wc in self.workcenters.values():
            if old_wc.id == except_workcenter_id or old_wc.current_job_id != job_id:
                continue

            old_wc.current_job_id = None
            cleared = True

            if not old_wc.is_disrupted:
                old_wc.status = WorkCenterStatus.AVAILABLE

        return cleared

    def assign_job(self, job_id: str, workcenter_id: str, front: bool = False) -> bool:
        """Assign or reassign a job to a workcenter queue.

        Returns False when the target workcenter cannot perform the job's
        required capability. Reassignments intentionally add reschedule
        pressure because queue churn is part of the game balance.
        """
        job = self.jobs[job_id]
        wc = self.workcenters[workcenter_id]
        if job.required_capability not in wc.capabilities:
            return False
        old_assignment = job.assigned_workcenter_id
        moving_to_new_workcenter = old_assignment != workcenter_id

        self.clear_job_from_current_workcenters(job_id, except_workcenter_id=workcenter_id)

        if job.status in {JobStatus.RUNNING, JobStatus.PAUSED} and moving_to_new_workcenter:
            # Moving active/paused work is allowed, but it removes the job from
            # the old station and adds one shift to represent teardown/restart
            # disruption. If the old station is down/blocked/weather impacted,
            # its disruption state remains in place.
            job.status = JobStatus.QUEUED
            job.remaining_duration_shifts += 1
            self.reschedule_count += 1
            self.daily_notes.append(f"{job.id} was moved while active; one shift of disruption was added.")
        if old_assignment and old_assignment != workcenter_id:
            self.reschedule_count += 1
        self.remove_job_from_queues(job_id)
        job.assigned_workcenter_id = workcenter_id
        if job.status not in {JobStatus.RUNNING, JobStatus.COMPLETE}:
            job.status = JobStatus.QUEUED
        if job_id not in wc.queue and wc.current_job_id != job_id:
            if front:
                wc.queue.insert(0, job_id)
            else:
                wc.queue.append(job_id)
        return True

    def preempt_current_job(self, workcenter_id: str, incoming_job_id: str) -> bool:
        """Interrupt a running job and put a higher-priority job at the front."""
        wc = self.workcenters[workcenter_id]
        current_id = wc.current_job_id
        if not current_id or current_id == incoming_job_id:
            return False
        current_job = self.jobs[current_id]
        if current_job.status != JobStatus.RUNNING:
            return False
        current_job.status = JobStatus.QUEUED
        current_job.remaining_duration_shifts += 1
        wc.current_job_id = None
        wc.status = WorkCenterStatus.AVAILABLE
        wc.queue.insert(0, current_id)
        self.reschedule_count += 1
        self.daily_notes.append(f"{current_id} was preempted on {wc.name}; one shift of disruption was added.")
        return self.assign_job(incoming_job_id, workcenter_id, front=True)
