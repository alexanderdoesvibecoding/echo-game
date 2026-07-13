"""Generate twenty flat jobs with five-to-fifteen-day runtimes."""

from __future__ import annotations

import random

from .config import GameConfig
from .models import Job, Scenario


def generate_scenario(config: GameConfig) -> Scenario:
    rng = random.Random(config.seed or 0)
    jobs: dict[str, Job] = {}
    for index in range(1, config.job_count + 1):
        job_id = f"JOB-{index:02d}"
        duration = _weighted_duration(rng, config)
        jobs[job_id] = Job(
            id=job_id,
            name=f"Job {index}",
            initial_duration_days=duration,
            remaining_days=duration,
        )
    scenario = Scenario(
        scenario_id=f"SCN-{(config.seed or 0) % 1_000_000:06d}",
        seed=config.seed or 0,
        jobs=jobs,
    )
    validate_scenario(scenario, config)
    return scenario


def _weighted_duration(rng: random.Random, config: GameConfig) -> int:
    """Favor short jobs while keeping every configured duration possible."""
    durations = list(range(config.min_job_duration_days, config.max_job_duration_days + 1))
    weights = [1.0 / (offset + 1) for offset in range(len(durations))]
    return rng.choices(durations, weights=weights, k=1)[0]


def validate_scenario(scenario: Scenario, config: GameConfig) -> None:
    if len(scenario.jobs) != config.job_count:
        raise ValueError(f"Scenario must contain exactly {config.job_count} jobs.")
    for job in scenario.jobs.values():
        if not config.min_job_duration_days <= job.initial_duration_days <= config.max_job_duration_days:
            raise ValueError(f"{job.id} duration is outside the configured range.")
