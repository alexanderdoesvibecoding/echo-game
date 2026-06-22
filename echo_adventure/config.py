"""Configuration defaults and seed handling for reproducible runs."""

from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class GameConfig:
    """Tunable game/scenario parameters shared by the UI and tests."""

    total_days: int = 15
    shifts_per_day: int = 3
    piece_count: int = 15
    shop_count: int = 10
    min_workcenters_per_shop: int = 1
    max_workcenters_per_shop: int = 5
    min_decisions_per_day: int = 1
    max_decisions_per_day: int = 5
    min_jobs_per_piece: int = 5
    max_jobs_per_piece: int = 10
    min_job_duration_shifts: int = 1
    max_job_duration_shifts: int = 4
    setup_time_choices: tuple[int, ...] = (0, 0, 1)
    transport_delay_probability: float = 0.65
    min_base_events: int = 22
    max_base_events: int = 30
    min_extra_quality_rework_events: int = 5
    max_extra_quality_rework_events: int = 8
    seed: int | None = None
    use_color: bool = True
    debug: bool = False

    @property
    def deadline_shift(self) -> int:
        """Convert the day-based deadline into the simulation's shift clock."""
        return self.total_days * self.shifts_per_day

    @classmethod
    def demo(cls, seed: int | None = None, use_color: bool = True, debug: bool = False) -> "GameConfig":
        """Return a short scenario that can be completed in one sitting."""
        return cls(
            total_days=5,
            piece_count=5,
            min_decisions_per_day=1,
            max_decisions_per_day=2,
            min_jobs_per_piece=3,
            max_jobs_per_piece=5,
            max_job_duration_shifts=5,
            setup_time_choices=(0,),
            transport_delay_probability=0.0,
            min_base_events=0,
            max_base_events=0,
            min_extra_quality_rework_events=0,
            max_extra_quality_rework_events=1,
            seed=seed,
            use_color=use_color,
            debug=debug,
        )


def resolve_seed(seed: int | None) -> int:
    """Return a provided seed or generate one suitable for replaying a run."""
    if seed is not None:
        return seed
    return random.SystemRandom().randint(100_000, 999_999_999)
