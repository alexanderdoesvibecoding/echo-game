"""Data models for the flat, day-based job simulation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import JobStatus


@dataclass
class Job:
    """One job and one matching submarine puzzle piece."""

    id: str
    name: str
    initial_duration_days: int
    remaining_days: int
    status: JobStatus = JobStatus.IN_PROGRESS
    completed_day: int | None = None
    is_starter_job: bool = False

    @property
    def is_complete(self) -> bool:
        """Report whether this job has reached its terminal state."""
        return self.status == JobStatus.COMPLETE


@dataclass(frozen=True)
class DecisionFollowUp:
    """One possible later definition unlocked by a selected response."""

    definition_id: str
    probability: float
    delay_days: int


@dataclass(frozen=True)
class DecisionChoice:
    """A response whose only runtime effect is changing job days."""

    id: str
    label: str
    day_changes: dict[str, int]
    score_delta: float
    icon_key: str
    follow_ups: tuple[DecisionFollowUp, ...] = ()


@dataclass
class DecisionCard:
    """A daily question about one job or a set of jobs."""

    id: str
    title: str
    description: str
    choices: list[DecisionChoice]
    echo_choice_id: str
    context_label: str
    definition_id: str = ""
    primary_job_id: str = ""
    player_only: bool = False
    event_id: str = ""
    event_scope: str = "route-specific"
    follow_up_source_day: int | None = None
    follow_up_source_definition_id: str = ""
    follow_up_source_title: str = ""
    follow_up_source_choice_id: str = ""
    follow_up_source_choice_label: str = ""


@dataclass(frozen=True)
class PendingFollowUp:
    """A definition waiting to revisit the still-active originating job."""

    definition_id: str
    job_id: str
    available_day: int
    trigger_delta: int = 0
    source_day: int | None = None
    source_definition_id: str = ""
    source_choice_id: str = ""


@dataclass
class DecisionRecord:
    """Record one actor's choice and its resulting schedule and score effects."""
    day: int
    card_id: str
    card_title: str
    actor: str
    choice_label: str
    echo_choice_label: str | None
    aligned_with_echo: bool | None
    applied_day_changes: dict[str, int]
    score_delta: float
    cumulative_score: float


@dataclass(frozen=True)
class MetricSnapshot:
    """Capture the aggregate schedule metrics at one point in time."""
    jobs_remaining: int
    total_remaining_days: int
    projected_completion_day: int
    final_item_completed: bool


@dataclass
class Scenario:
    """Bundle a resolved seed with its generated starting jobs."""
    seed: int
    jobs: dict[str, Job]


@dataclass
class SimulationState:
    """Hold all mutable simulation and decision state for one actor."""
    seed: int
    jobs: dict[str, Job]
    current_day: int = 1
    completed_jobs: set[str] = field(default_factory=set)
    final_item_completed: bool = False
    completion_day: int | None = None
    daily_notes: list[str] = field(default_factory=list)
    decision_cards: dict[str, DecisionCard] = field(default_factory=dict)
    decision_history: list[DecisionRecord] = field(default_factory=list)
    decision_score: float = 0.0
    cumulative_unfinished_job_days: int = 0
    shown_follow_up_decision_ids: set[str] = field(default_factory=set)
    pending_follow_ups: list[PendingFollowUp] = field(default_factory=list)

    def incomplete_jobs(self) -> list[Job]:
        """Return unfinished jobs in their stable scenario order."""
        return [job for job in self.jobs.values() if not job.is_complete]
