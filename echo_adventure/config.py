from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class GameConfig:
    total_days: int = 15
    shifts_per_day: int = 3
    piece_count: int = 15
    shop_count: int = 10
    min_workcenters_per_shop: int = 1
    max_workcenters_per_shop: int = 7
    min_decisions_per_day: int = 1
    max_decisions_per_day: int = 5
    min_jobs_per_piece: int = 5
    max_jobs_per_piece: int = 10
    min_extra_quality_rework_events: int = 5
    max_extra_quality_rework_events: int = 8
    seed: int | None = None
    use_color: bool = True
    debug: bool = False

    @property
    def deadline_shift(self) -> int:
        return self.total_days * self.shifts_per_day


def resolve_seed(seed: int | None) -> int:
    if seed is not None:
        return seed
    return random.SystemRandom().randint(100_000, 999_999_999)
