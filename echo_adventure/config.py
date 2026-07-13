"""Configuration profiles and seed handling for reproducible runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import random

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
class GameConfig:
    """Tunable game/scenario parameters shared by the UI and tests."""

    total_days: int = 15
    shifts_per_day: int = 3
    start_date: str = "2026-07-01"
    end_date: str | None = None
    work_period_labels: tuple[str, ...] = ("Morning", "Afternoon", "Night")
    piece_count: int = 6
    shop_count: int = 9
    min_workcenters_per_shop: int = 1
    max_workcenters_per_shop: int = 5
    min_decisions_per_day: int = 3
    max_decisions_per_day: int = 4
    min_jobs_per_piece: int = 5
    max_jobs_per_piece: int = 7
    min_job_duration_shifts: int = 1
    max_job_duration_shifts: int = 2
    setup_time_choices: tuple[int, ...] = (0,)
    transport_delay_probability: float = 0.0
    min_capable_workcenters_per_capability: int = 3
    min_candidate_workcenters_per_job: int = 3
    max_candidate_workcenters_per_job: int = 8
    max_alternate_workcenters_per_job: int = 4
    min_base_events: int = 0
    max_base_events: int = 0
    min_extra_quality_rework_events: int = 0
    max_extra_quality_rework_events: int = 0
    completion_rework_probability: float = 0.0
    min_completion_rework_shifts: int = 0
    max_completion_rework_shifts: int = 0
    max_campaign_decision_nodes: int = 900
    max_future_unlocks_per_choice: int = 4
    max_active_decision_cards_per_day: int = 3
    max_branch_variants_per_day: int = 12
    echo_choice_lookahead_days: int = 0
    echo_choice_projection_limit: int = 0
    day_cycle_duration_ms: int = 8000
    daily_summary_counter_duration_ms: int = 1800
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
        day, _ = self._position_for_shift(shift)
        return self.date_label_for_day(day)

    def work_period_label_for_shift(self, shift: int | None) -> str:
        """Return the calendar date and named work period for an internal shift."""
        day, period_index = self._position_for_shift(shift)
        period = (
            self.work_period_labels[period_index]
            if period_index < len(self.work_period_labels)
            else f"Work period {period_index + 1}"
        )
        return f"{self.date_label_for_day(day)}, {period}"

    def _position_for_shift(self, shift: int | None) -> tuple[int, int]:
        """Return the one-based day and zero-based work period for a shift."""
        safe_shift = max(1, int(shift or 1))
        day = ((safe_shift - 1) // self.shifts_per_day) + 1
        period_index = (safe_shift - 1) % self.shifts_per_day
        return day, period_index

    @classmethod
    def for_preset(
        cls,
        preset: str,
        seed: int | None = None,
    ) -> "GameConfig":
        """Return a validated config for a supported game preset."""
        if preset not in {"normal", "demo"}:
            raise ValueError(f"Unknown game preset: {preset}")
        config = cls(seed=seed)
        _validate_config("normal", config)
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
        "daily_summary_counter_duration_ms",
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
