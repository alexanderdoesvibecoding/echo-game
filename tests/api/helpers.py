from __future__ import annotations

from dataclasses import replace

from echo_adventure.config import GameConfig
from echo_adventure.enums import DecisionType
from echo_adventure.models import (
    DecisionCard,
    DecisionChoice,
    DecisionFollowUp,
    Job,
    Scenario,
)


def small_config(**overrides: object) -> GameConfig:
    values: dict[str, object] = {
        "start_date": "2026-07-01",
        "job_count": 3,
        "min_job_duration_days": 2,
        "max_job_duration_days": 4,
        "min_decisions_per_day": 1,
        "max_decisions_per_day": 1,
        "max_campaign_day": 8,
        "day_cycle_duration_ms": 100,
        "daily_summary_counter_duration_ms": 50,
        "seed": 123,
    }
    values.update(overrides)
    return GameConfig(**values)


def scenario_from_durations(*durations: int, seed: int = 123) -> Scenario:
    jobs = {
        f"JOB-{index:02d}": Job(
            id=f"JOB-{index:02d}",
            name=f"Job {index}",
            initial_duration_days=duration,
            remaining_days=duration,
        )
        for index, duration in enumerate(durations, start=1)
    }
    return Scenario(scenario_id=f"SCN-{seed:06d}", seed=seed, jobs=jobs)


def make_choice(
    choice_id: str,
    *,
    changes: dict[str, int] | None = None,
    score: float = 0.0,
    follow_ups: tuple[DecisionFollowUp, ...] = (),
    icon: str = "adjust",
) -> DecisionChoice:
    return DecisionChoice(
        id=choice_id,
        label=f"Choice {choice_id}",
        description=f"Description {choice_id}",
        day_changes=dict(changes or {}),
        score_delta=score,
        icon_key=icon,
        follow_ups=follow_ups,
    )


def make_card(
    *choices: DecisionChoice,
    echo_choice_id: str | None = None,
    primary_job_id: str = "JOB-01",
    definition_id: str = "unit-decision",
) -> DecisionCard:
    card_choices = list(choices or (make_choice("choice-1"),))
    return DecisionCard(
        id="DEC-D001-Q01-UNIT-unit-decision",
        day=1,
        type=DecisionType.NEUTRAL,
        title="Unit decision",
        description="Choose a schedule response.",
        target_ids=[primary_job_id],
        choices=card_choices,
        echo_choice_id=echo_choice_id or card_choices[0].id,
        context_label="Job 1",
        definition_id=definition_id,
        primary_job_id=primary_job_id,
    )


def config_with_seed(config: GameConfig, seed: int) -> GameConfig:
    return replace(config, seed=seed)
