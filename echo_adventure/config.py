"""Configuration profiles and seed handling for reproducible runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
import random

TOTAL_DAYS = 28
NORMAL_CAMPAIGN_START_DATE = "2026-07-01"
NORMAL_CAMPAIGN_END_DATE = "2026-07-15"
DEFAULT_WORK_PERIOD_LABELS = ("Morning", "Afternoon", "Night")
_MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


@dataclass(frozen=True)
class WorkloadProfile:
    """Scenario size and job-duration knobs for a preset."""

    total_days: int
    piece_count: int
    min_jobs_per_piece: int
    max_jobs_per_piece: int
    start_date: str = NORMAL_CAMPAIGN_START_DATE
    end_date: str | None = None
    min_job_duration_shifts: int = 1
    max_job_duration_shifts: int = 5
    setup_time_choices: tuple[int, ...] = (0, 0, 0, 1)
    transport_delay_probability: float = 0.35


@dataclass(frozen=True)
class CapacityProfile:
    """Shop and routing-capacity knobs for a preset."""

    shop_count: int = 9
    min_workcenters_per_shop: int = 1
    max_workcenters_per_shop: int = 5
    min_capable_workcenters_per_capability: int = 2
    min_candidate_workcenters_per_job: int = 2
    max_candidate_workcenters_per_job: int = 8
    max_alternate_workcenters_per_job: int = 3


@dataclass(frozen=True)
class DisruptionProfile:
    """Event and rework pressure knobs for a preset."""

    min_base_events: int = 10
    max_base_events: int = 15
    min_extra_quality_rework_events: int = 1
    max_extra_quality_rework_events: int = 5
    completion_rework_probability: float = 0.10
    min_completion_rework_shifts: int = 1
    max_completion_rework_shifts: int = 3


@dataclass(frozen=True)
class DecisionProfile:
    """Daily decision graph breadth and runtime visibility knobs."""

    min_decisions_per_day: int = 3
    max_decisions_per_day: int = 5
    max_campaign_decision_nodes: int = 900
    max_future_unlocks_per_choice: int = 4
    max_active_decision_cards_per_day: int = 5
    max_branch_variants_per_day: int = 12


@dataclass(frozen=True)
class EchoProfile:
    """Hidden benchmark policy knobs for ECHO's background play."""

    echo_choice_lookahead_days: int = 0
    echo_choice_projection_limit: int = 0


NO_RANDOM_DISRUPTION_PROFILE = DisruptionProfile(
    min_base_events=0,
    max_base_events=0,
    min_extra_quality_rework_events=0,
    max_extra_quality_rework_events=0,
    completion_rework_probability=0.0,
    min_completion_rework_shifts=0,
    max_completion_rework_shifts=0,
)


@dataclass(frozen=True)
class BalancePreset:
    """Named gameplay preset assembled from focused profile groups."""

    workload: WorkloadProfile
    capacity: CapacityProfile = CapacityProfile()
    disruptions: DisruptionProfile = DisruptionProfile()
    decisions: DecisionProfile = DecisionProfile()
    echo: EchoProfile = EchoProfile()

    def to_config_kwargs(self) -> dict[str, object]:
        """Flatten the profile groups into GameConfig keyword arguments."""
        values: dict[str, object] = {}
        for profile in (self.workload, self.capacity, self.disruptions, self.decisions, self.echo):
            values.update(asdict(profile))
        if values.get("end_date"):
            values["total_days"] = _inclusive_date_span(str(values["start_date"]), str(values["end_date"]))
        return values


GAME_PRESETS: dict[str, BalancePreset] = {
    "normal": BalancePreset(
        workload=WorkloadProfile(
            total_days=TOTAL_DAYS,
            start_date=NORMAL_CAMPAIGN_START_DATE,
            end_date=NORMAL_CAMPAIGN_END_DATE,
            piece_count=6,
            min_jobs_per_piece=5,
            max_jobs_per_piece=7,
            max_job_duration_shifts=2,
            setup_time_choices=(0,),
            transport_delay_probability=0.0,
        ),
        capacity=CapacityProfile(
            max_workcenters_per_shop=5,
            min_capable_workcenters_per_capability=3,
            min_candidate_workcenters_per_job=3,
            max_candidate_workcenters_per_job=8,
            max_alternate_workcenters_per_job=4,
        ),
        disruptions=NO_RANDOM_DISRUPTION_PROFILE,
        decisions=DecisionProfile(
            min_decisions_per_day=3,
            max_decisions_per_day=4,
            max_active_decision_cards_per_day=3,
        ),
    ),
}


@dataclass(frozen=True)
class GameConfig:
    """Tunable game/scenario parameters shared by the UI and tests."""

    total_days: int = 15
    shifts_per_day: int = 3
    start_date: str = NORMAL_CAMPAIGN_START_DATE
    end_date: str | None = None
    work_period_labels: tuple[str, ...] = DEFAULT_WORK_PERIOD_LABELS
    piece_count: int = 15
    shop_count: int = 9
    min_workcenters_per_shop: int = 1
    max_workcenters_per_shop: int = 5
    min_decisions_per_day: int = 3
    max_decisions_per_day: int = 5
    min_jobs_per_piece: int = 5
    max_jobs_per_piece: int = 10
    min_job_duration_shifts: int = 1
    max_job_duration_shifts: int = 5
    setup_time_choices: tuple[int, ...] = (0, 0, 0, 1)
    transport_delay_probability: float = 0.35
    min_capable_workcenters_per_capability: int = 2
    min_candidate_workcenters_per_job: int = 2
    max_candidate_workcenters_per_job: int = 8
    max_alternate_workcenters_per_job: int = 3
    min_base_events: int = 10
    max_base_events: int = 15
    min_extra_quality_rework_events: int = 1
    max_extra_quality_rework_events: int = 5
    completion_rework_probability: float = 0.10
    min_completion_rework_shifts: int = 1
    max_completion_rework_shifts: int = 3
    max_campaign_decision_nodes: int = 900
    max_future_unlocks_per_choice: int = 4
    max_active_decision_cards_per_day: int = 5
    max_branch_variants_per_day: int = 12
    echo_choice_lookahead_days: int = 0
    echo_choice_projection_limit: int = 0
    day_cycle_duration_ms: int = 8000
    seed: int | None = None

    @property
    def deadline_shift(self) -> int:
        """Convert the day-based deadline into the simulation's shift clock."""
        return self.total_days * self.shifts_per_day

    @property
    def schedule_start(self) -> date:
        """Return the configured campaign start date."""
        return _parse_config_date("start_date", self.start_date)

    @property
    def schedule_end(self) -> date:
        """Return the configured campaign deadline date."""
        if self.end_date:
            return _parse_config_date("end_date", self.end_date)
        return self.schedule_start + timedelta(days=self.total_days - 1)

    @property
    def deadline_date_label(self) -> str:
        """Return the player-facing deadline date."""
        return _format_calendar_date(self.schedule_end)

    @property
    def date_range_label(self) -> str:
        """Return the full configured campaign date range."""
        start = _format_calendar_date(self.schedule_start)
        end = self.deadline_date_label
        return start if start == end else f"{start} to {end}"

    def date_label_for_day(self, day: int) -> str:
        """Return the calendar date for a one-based simulation day."""
        safe_day = max(1, min(self.total_days, int(day or 1)))
        return _format_calendar_date(self.schedule_start + timedelta(days=safe_day - 1))

    def date_label_for_shift(self, shift: int | None) -> str:
        """Return only the calendar date for an internal shift."""
        safe_shift = max(1, int(shift or 1))
        day = ((safe_shift - 1) // self.shifts_per_day) + 1
        return self.date_label_for_day(day)

    def work_period_label_for_shift(self, shift: int | None) -> str:
        """Return the calendar date and named work period for an internal shift."""
        safe_shift = max(1, int(shift or 1))
        day = ((safe_shift - 1) // self.shifts_per_day) + 1
        period_index = (safe_shift - 1) % self.shifts_per_day
        period = (
            self.work_period_labels[period_index]
            if period_index < len(self.work_period_labels)
            else f"Work period {period_index + 1}"
        )
        return f"{self.date_label_for_day(day)}, {period}"

    @classmethod
    def for_preset(
        cls,
        preset: str,
        seed: int | None = None,
    ) -> "GameConfig":
        """Return a config built from one editable game preset."""
        if preset == "demo":
            preset = "normal"
        values = GAME_PRESETS.get(preset)
        if values is None:
            raise ValueError(f"Unknown game preset: {preset}")
        config = cls(seed=seed, **values.to_config_kwargs())
        _validate_config(preset, config)
        return config


def resolve_seed(seed: int | None) -> int:
    """Return a provided seed or generate one suitable for replaying a run."""
    if seed is not None:
        return seed
    return random.SystemRandom().randint(100_000, 999_999_999)


def _parse_config_date(field: str, value: str) -> date:
    """Parse an ISO date configured in this module."""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD format.") from exc


def _inclusive_date_span(start_date: str, end_date: str) -> int:
    """Return the number of calendar days in an inclusive date range."""
    start = _parse_config_date("start_date", start_date)
    end = _parse_config_date("end_date", end_date)
    span = (end - start).days + 1
    if span < 1:
        raise ValueError("end_date must be on or after start_date.")
    return span


def _format_calendar_date(value: date) -> str:
    """Format dates without platform-specific strftime flags."""
    return f"{_MONTH_NAMES[value.month - 1]} {value.day}"


def _validate_config(preset: str, config: GameConfig) -> None:
    """Fail fast when an edited preset has an impossible size range."""
    positive_fields = [
        "total_days",
        "shifts_per_day",
        "piece_count",
        "shop_count",
        "min_decisions_per_day",
        "max_decisions_per_day",
        "min_job_duration_shifts",
        "max_job_duration_shifts",
        "min_jobs_per_piece",
        "max_jobs_per_piece",
        "min_workcenters_per_shop",
        "max_workcenters_per_shop",
        "min_capable_workcenters_per_capability",
        "min_candidate_workcenters_per_job",
        "max_candidate_workcenters_per_job",
        "day_cycle_duration_ms",
    ]
    for field in positive_fields:
        if int(getattr(config, field)) < 1:
            raise ValueError(f"{preset} preset {field} must be at least 1.")

    if len(config.work_period_labels) < 1:
        raise ValueError(f"{preset} preset work_period_labels cannot be empty.")

    non_negative_fields = [
        "min_base_events",
        "max_base_events",
        "min_extra_quality_rework_events",
        "max_extra_quality_rework_events",
        "min_completion_rework_shifts",
        "max_completion_rework_shifts",
        "max_campaign_decision_nodes",
        "max_future_unlocks_per_choice",
        "max_active_decision_cards_per_day",
        "max_branch_variants_per_day",
        "max_alternate_workcenters_per_job",
        "echo_choice_lookahead_days",
        "echo_choice_projection_limit",
    ]
    for field in non_negative_fields:
        if int(getattr(config, field)) < 0:
            raise ValueError(f"{preset} preset {field} cannot be negative.")

    ordered_ranges = [
        ("min_jobs_per_piece", "max_jobs_per_piece", "subjobs per job"),
        ("min_workcenters_per_shop", "max_workcenters_per_shop", "work centers per shop"),
        ("min_candidate_workcenters_per_job", "max_candidate_workcenters_per_job", "candidate work centers per subjob"),
        ("min_decisions_per_day", "max_decisions_per_day", "decisions per day"),
        ("min_job_duration_shifts", "max_job_duration_shifts", "job duration"),
        ("min_base_events", "max_base_events", "base events"),
        (
            "min_extra_quality_rework_events",
            "max_extra_quality_rework_events",
            "extra quality rework events",
        ),
        ("min_completion_rework_shifts", "max_completion_rework_shifts", "completion rework"),
    ]
    for minimum, maximum, label in ordered_ranges:
        if int(getattr(config, minimum)) > int(getattr(config, maximum)):
            raise ValueError(f"{preset} preset minimum {label} cannot exceed maximum {label}.")

    for field in ("transport_delay_probability", "completion_rework_probability"):
        probability = float(getattr(config, field))
        if probability < 0.0 or probability > 1.0:
            raise ValueError(f"{preset} preset {field} must be between 0.0 and 1.0.")

    if not config.setup_time_choices:
        raise ValueError(f"{preset} preset setup_time_choices cannot be empty.")
    if any(choice < 0 for choice in config.setup_time_choices):
        raise ValueError(f"{preset} preset setup_time_choices cannot contain negative values.")

    schedule_start = _parse_config_date("start_date", config.start_date)
    schedule_end = config.schedule_end
    if schedule_end < schedule_start:
        raise ValueError(f"{preset} preset end_date must be on or after start_date.")
    if config.end_date:
        date_span = (schedule_end - schedule_start).days + 1
        if date_span != config.total_days:
            raise ValueError(
                f"{preset} preset total_days must match the inclusive start_date/end_date range ({date_span})."
            )

    if config.completion_rework_probability > 0 and config.max_completion_rework_shifts < 1:
        raise ValueError(
            f"{preset} preset completion rework shifts must be positive when completion rework is enabled."
        )
