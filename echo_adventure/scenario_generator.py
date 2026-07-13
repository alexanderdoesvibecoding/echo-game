"""Generate twenty flat jobs with five-to-fifteen-day runtimes."""

from __future__ import annotations

import random

from .config import GameConfig
from .models import Job, Scenario


JOB_NAMES = (
    "Aster", "Beacon", "Cinder", "Delta", "Ember",
    "Flux", "Garnet", "Helio", "Ion", "Juniper",
    "Kestrel", "Lumen", "Mosaic", "Nimbus", "Orchid",
    "Pioneer", "Quasar", "Relay", "Solace", "Tangent",
)


def generate_scenario(config: GameConfig) -> Scenario:
    rng = random.Random(config.seed or 0)
    jobs: dict[str, Job] = {}
    for index in range(1, config.job_count + 1):
        job_id = f"JOB-{index:02d}"
        duration = rng.randint(config.min_job_duration_days, config.max_job_duration_days)
        base_name = JOB_NAMES[(index - 1) % len(JOB_NAMES)]
        name = base_name if index <= len(JOB_NAMES) else f"{base_name} {index}"
        jobs[job_id] = Job(
            id=job_id,
            name=f"Job {index:02d} - {name}",
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


def validate_scenario(scenario: Scenario, config: GameConfig) -> None:
    if len(scenario.jobs) != config.job_count:
        raise ValueError(f"Scenario must contain exactly {config.job_count} jobs.")
    for job in scenario.jobs.values():
        if not config.min_job_duration_days <= job.initial_duration_days <= config.max_job_duration_days:
            raise ValueError(f"{job.id} duration is outside the configured range.")
