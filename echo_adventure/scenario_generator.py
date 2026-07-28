"""Generate one starter job plus the configured flat-job duration range."""

from __future__ import annotations

import random

from .config import GameConfig
from .models import Job, Scenario


_STARTER_JOB_DURATION_DAYS = 3
_MIN_JOB_COUNT_FOR_STARTER = 3


def generate_scenario(config: GameConfig) -> Scenario:
    """Generate a deterministic set of jobs, including the early starter job."""
    # A private RNG makes scenario generation reproducible without perturbing
    # randomness used by callers or other concurrently generated sessions.
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
    # Ordinary durations are generated first so starter selection is a stable,
    # explicit exception to the configured duration range.
    _assign_starter_job(jobs, config)
    scenario = Scenario(
        seed=config.seed or 0,
        jobs=jobs,
    )
    validate_scenario(scenario, config)
    return scenario


def _weighted_duration(rng: random.Random, config: GameConfig) -> int:
    """Favor short jobs while keeping every configured duration possible."""
    durations = list(range(config.min_job_duration_days, config.max_job_duration_days + 1))
    # Harmonic weights bias the puzzle toward early completions without ever
    # assigning a zero probability to a longer configured duration.
    weights = [1.0 / (offset + 1) for offset in range(len(durations))]
    return rng.choices(durations, weights=weights, k=1)[0]


def _assign_starter_job(jobs: dict[str, Job], config: GameConfig) -> None:
    """Shorten one deterministic job in games large enough for an early piece."""
    if (
        len(jobs) < _MIN_JOB_COUNT_FOR_STARTER
        or config.min_job_duration_days <= _STARTER_JOB_DURATION_DAYS
    ):
        return
    # The shortest generated job changes the least; the ID tie-break preserves
    # the same starter for repeated runs with the same seed.
    starter = min(
        jobs.values(),
        key=lambda job: (job.initial_duration_days, job.id),
    )
    starter.initial_duration_days = _STARTER_JOB_DURATION_DAYS
    starter.remaining_days = _STARTER_JOB_DURATION_DAYS
    starter.is_starter_job = True


def validate_scenario(scenario: Scenario, config: GameConfig) -> None:
    """Reject scenarios that violate configured job and starter invariants."""
    if len(scenario.jobs) != config.job_count:
        raise ValueError(f"Scenario must contain exactly {config.job_count} jobs.")
    starter_jobs = [job for job in scenario.jobs.values() if job.is_starter_job]
    if len(starter_jobs) > 1:
        raise ValueError("Scenario cannot contain more than one starter job.")
    for job in scenario.jobs.values():
        # The one marked starter is the only legal below-minimum job.
        if job.is_starter_job:
            if (
                job.initial_duration_days != _STARTER_JOB_DURATION_DAYS
                or job.initial_duration_days > config.max_job_duration_days
            ):
                raise ValueError(
                    f"{job.id} starter duration must be {_STARTER_JOB_DURATION_DAYS} days."
                )
            continue
        if not config.min_job_duration_days <= job.initial_duration_days <= config.max_job_duration_days:
            raise ValueError(f"{job.id} duration is outside the configured range.")
