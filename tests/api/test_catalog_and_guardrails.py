from __future__ import annotations

import pytest

from echo_adventure.decision_web import DecisionWebTransition, generate_decision_web
from echo_adventure.decisions.cards import (
    _available_base_definitions,
    _build_choice,
    _format_job_list,
    build_preplanned_decision_card,
    generate_daily_decision_cards,
    select_echo_choice,
)
from echo_adventure.decisions.definitions import (
    BASE_DEFINITIONS,
    DEFINITIONS_BY_ID,
    SUPPORTED_CHOICE_ICON_KEYS,
)
from echo_adventure.echo import advance_omniscient_day, apply_omniscient_choice
from echo_adventure.scenario_generator import generate_scenario
from echo_adventure.simulation import complete_job, initialize_state

from .helpers import scenario_from_durations, small_config


@pytest.mark.parametrize(
    "definition",
    DEFINITIONS_BY_ID.values(),
    ids=DEFINITIONS_BY_ID,
)
def test_every_catalog_definition_builds_a_truthful_preplanned_card(definition) -> None:
    state = initialize_state(scenario_from_durations(4, 5, 6))
    targets = list(state.jobs.values())
    trigger_delta = 2 if definition.is_follow_up else 0

    card = build_preplanned_decision_card(
        state,
        definition,
        targets[0],
        targets,
        question_number=1,
        node_token="CATALOG",
        trigger_delta=trigger_delta,
    )

    assert card.definition_id == definition.id
    assert card.primary_job_id == "JOB-01"
    assert card.echo_choice_id == select_echo_choice(card).id
    assert "subjob" not in f"{card.title} {card.description}".lower()
    for choice in card.choices:
        assert set(choice.day_changes) <= {"JOB-01"}
        assert choice.score_delta == float(-sum(choice.day_changes.values()))
        assert choice.icon_key in SUPPORTED_CHOICE_ICON_KEYS
        assert "Schedule effect:" in choice.description
        assert "subjob" not in choice.description.lower()
        delta = sum(choice.day_changes.values())
        assert abs(delta) <= (4 if definition.is_follow_up else 2)
        if definition.is_follow_up:
            assert trigger_delta + delta != 0


@pytest.mark.parametrize(
    "definition",
    DEFINITIONS_BY_ID.values(),
    ids=DEFINITIONS_BY_ID,
)
def test_every_catalog_choice_builds_bounded_runtime_job_day_effects(definition) -> None:
    targets = list(scenario_from_durations(5, 5, 5).jobs.values())
    trigger_delta = -2 if definition.is_follow_up else 0

    for index, catalog_choice in enumerate(definition.choices, start=1):
        choice = _build_choice(
            definition,
            catalog_choice,
            targets,
            index,
            trigger_delta=trigger_delta,
        )
        assert set(choice.day_changes) <= {job.id for job in targets}
        assert 0 <= len(choice.day_changes) <= 3
        assert choice.score_delta == float(-sum(choice.day_changes.values()))
        assert choice.icon_key in SUPPORTED_CHOICE_ICON_KEYS
        assert all(abs(delta) <= 3 for delta in choice.day_changes.values())
        if definition.is_follow_up:
            assert trigger_delta + sum(choice.day_changes.values()) != 0


def test_daily_generation_handles_completed_work_and_exhausted_definition_pool() -> None:
    config = small_config()
    state = initialize_state(generate_scenario(config))
    for job_id in state.jobs:
        complete_job(state, job_id)

    assert generate_daily_decision_cards(state, config) == []

    active_state = initialize_state(generate_scenario(config))
    used = {definition.id for definition in BASE_DEFINITIONS}
    assert _available_base_definitions(active_state, used) == []
    assert _format_job_list([]) == ""


def test_echo_guardrails_reject_completed_non_daily_overtime_and_early_terminal_states() -> None:
    config = small_config(job_count=2, min_job_duration_days=2, max_job_duration_days=3, max_campaign_day=6)
    scenario = generate_scenario(config)
    web = generate_decision_web(scenario, config)
    completed = initialize_state(scenario)
    for job_id in completed.jobs:
        complete_job(completed, job_id)
    with pytest.raises(RuntimeError, match="cannot choose after completing"):
        apply_omniscient_choice(completed, web, web.root_node_id)

    state = initialize_state(scenario_from_durations(2))
    with pytest.raises(RuntimeError, match="cannot advance before"):
        advance_omniscient_day(
            state,
            DecisionWebTransition("choice-1", None, advances_day=False),
        )
    with pytest.raises(RuntimeError, match="crossed the runtime-generation boundary"):
        advance_omniscient_day(
            state,
            DecisionWebTransition("choice-1", None, advances_day=True, enters_overtime=True),
        )
    with pytest.raises(RuntimeError, match="terminal web edge before completing"):
        advance_omniscient_day(
            state,
            DecisionWebTransition("choice-1", None, advances_day=True),
        )
