"""Data models for the flat, day-based job simulation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import DecisionType, JobStatus


@dataclass
class Job:
    """One job and one matching submarine puzzle piece."""

    id: str
    name: str
    initial_duration_days: int
    remaining_days: int
    status: JobStatus = JobStatus.IN_PROGRESS
    completed_day: int | None = None

    @property
    def is_complete(self) -> bool:
        return self.status == JobStatus.COMPLETE


@dataclass(frozen=True)
class DecisionChoice:
    """A response whose only runtime effect is changing job days."""

    id: str
    label: str
    description: str
    day_changes: dict[str, int]
    score_delta: float


@dataclass
class DecisionCard:
    """A daily question about one job or a set of jobs."""

    id: str
    day: int
    type: DecisionType
    title: str
    description: str
    target_ids: list[str]
    choices: list[DecisionChoice]
    echo_choice_id: str
    context_label: str


@dataclass
class DecisionRecord:
    day: int
    card_id: str
    card_title: str
    actor: str
    choice_id: str
    choice_label: str
    echo_choice_id: str
    echo_choice_label: str
    aligned_with_echo: bool
    note: str
    score_delta: float
    cumulative_score: float


@dataclass(frozen=True)
class DecisionProgress:
    day: int
    total_questions: int
    answered_questions: int
    open_card_ids: list[str]


@dataclass(frozen=True)
class MetricSnapshot:
    day: int
    jobs_completed: int
    jobs_remaining: int
    total_remaining_days: int
    projected_completion_day: int
    final_item_completed: bool


@dataclass
class Scenario:
    scenario_id: str
    seed: int
    jobs: dict[str, Job]


@dataclass
class SimulationState:
    scenario_id: str
    seed: int
    jobs: dict[str, Job]
    current_day: int = 1
    completed_jobs: set[str] = field(default_factory=set)
    final_item_completed: bool = False
    completion_day: int | None = None
    daily_notes: list[str] = field(default_factory=list)
    metric_history: list[MetricSnapshot] = field(default_factory=list)
    decision_cards: dict[str, DecisionCard] = field(default_factory=dict)
    decision_history: list[DecisionRecord] = field(default_factory=list)
    decision_score: float = 0.0
    is_echo_benchmark: bool = False

    def incomplete_jobs(self) -> list[Job]:
        return [job for job in self.jobs.values() if not job.is_complete]
