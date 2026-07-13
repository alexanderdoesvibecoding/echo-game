"""Configuration and calendar helpers for the jobs-only game."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import random


_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


@dataclass(frozen=True)
class GameConfig:
    """The small set of knobs that define a run."""

    start_date: str = "2026-07-01"
    job_count: int = 20
    min_job_duration_days: int = 5
    max_job_duration_days: int = 15
    min_decisions_per_day: int = 2
    max_decisions_per_day: int = 4
    day_cycle_duration_ms: int = 8000
    daily_summary_counter_duration_ms: int = 1200
    seed: int | None = None

    @property
    def schedule_start(self) -> date:
        try:
            return date.fromisoformat(self.start_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("start_date must use YYYY-MM-DD format.") from exc

    def date_label_for_day(self, day: int) -> str:
        """Return the calendar label for any one-based game day."""
        value = self.schedule_start + timedelta(days=max(1, int(day or 1)) - 1)
        return f"{_MONTH_NAMES[value.month - 1]} {value.day}"

    @classmethod
    def for_preset(cls, preset: str, seed: int | None = None) -> "GameConfig":
        if preset not in {"normal", "demo"}:
            raise ValueError(f"Unknown game preset: {preset}")
        config = cls(seed=seed)
        _validate_config(config)
        return config


def resolve_seed(seed: int | None) -> int:
    if seed is not None:
        return seed
    return random.SystemRandom().randint(100_000, 999_999_999)


def _validate_config(config: GameConfig) -> None:
    for field in (
        "job_count",
        "min_job_duration_days",
        "max_job_duration_days",
        "min_decisions_per_day",
        "max_decisions_per_day",
        "day_cycle_duration_ms",
        "daily_summary_counter_duration_ms",
    ):
        if int(getattr(config, field)) < 1:
            raise ValueError(f"{field} must be at least 1.")
    if config.min_job_duration_days > config.max_job_duration_days:
        raise ValueError("Minimum job duration cannot exceed maximum job duration.")
    if config.min_decisions_per_day > config.max_decisions_per_day:
        raise ValueError("Minimum daily decisions cannot exceed maximum daily decisions.")
    config.schedule_start
