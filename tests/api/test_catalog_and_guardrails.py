from __future__ import annotations

import pytest

from echo_adventure.decision_web import DecisionWebTransition, generate_decision_web
from echo_adventure.decisions.cards import (
    _available_base_definitions,
    _build_choice,
    _format_job_list,
    _select_preplanned_follow_up_result,
    build_preplanned_decision_card,
    generate_daily_decision_cards,
    select_echo_choice_from_choices,
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
    assert card.echo_choice_id == select_echo_choice_from_choices(card.choices).id
    assert "subjob" not in f"{card.title} {card.description}".lower()
    assert "Job 1" not in card.description
    for choice in card.choices:
        assert set(choice.day_changes) <= {"JOB-01"}
        assert choice.score_delta == float(-sum(choice.day_changes.values()))
        assert choice.icon_key in SUPPORTED_CHOICE_ICON_KEYS
        delta = sum(choice.day_changes.values())
        assert abs(delta) <= (4 if definition.is_follow_up else 2)
        if definition.is_follow_up:
            assert trigger_delta + delta != 0

    last_job_state = initialize_state(scenario_from_durations(4))
    last_job = next(iter(last_job_state.jobs.values()))
    last_job_card = build_preplanned_decision_card(
        last_job_state,
        definition,
        last_job,
        [last_job],
        question_number=1,
        node_token="LASTJOB",
        trigger_delta=trigger_delta,
    )
    assert all(
        delta <= 0
        for choice in last_job_card.choices
        for delta in choice.day_changes.values()
    )

    outlier_state = initialize_state(scenario_from_durations(10, 3, 2))
    outlier = outlier_state.jobs["JOB-01"]
    outlier_card = build_preplanned_decision_card(
        outlier_state,
        definition,
        outlier,
        list(outlier_state.jobs.values()),
        question_number=1,
        node_token="OUTLIER",
        trigger_delta=trigger_delta,
    )
    assert all(set(choice.day_changes) <= {"JOB-01"} for choice in outlier_card.choices)
    if definition.id == "weather":
        assert any(
            delta > 0
            for choice in outlier_card.choices
            for delta in choice.day_changes.values()
        )

    if definition.alternate_results:
        expected_titles = {
            definition.title,
            *(result.title for result in definition.alternate_results),
        }
        selected_titles = set()
        for seed in range(1, 33):
            varied_state = initialize_state(scenario_from_durations(4, 5, 6, seed=seed))
            selected = _select_preplanned_follow_up_result(
                varied_state,
                definition,
                varied_state.jobs["JOB-01"],
                question_number=1,
                trigger_delta=trigger_delta,
            )
            selected_titles.add(selected.title)
        assert selected_titles == expected_titles


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


def test_echo_applies_and_advances_one_optimal_daily_step() -> None:
    config = small_config(
        job_count=2,
        min_job_duration_days=3,
        max_job_duration_days=3,
        max_campaign_day=6,
        seed=909,
    )
    scenario = generate_scenario(config)
    web = generate_decision_web(scenario, config)
    state = initialize_state(scenario)
    root = web.node(web.root_node_id)

    transition = apply_omniscient_choice(state, web, web.root_node_id)

    assert state.decision_cards[root.card.id] is root.card
    assert len(state.decision_history) == 1
    assert state.decision_history[0].actor == "ECHO"
    assert state.decision_history[0].aligned_with_echo is True
    assert state.pending_follow_ups == []
    assert transition is root.transitions[root.optimal_choice_id]
    assert transition.advances_day is True

    next_node_id = advance_omniscient_day(state, transition)

    assert next_node_id == transition.next_node_id
    assert state.current_day == 2
    assert next_node_id is not None
    web.assert_runtime_matches(state, next_node_id)


def test_echo_guardrails_reject_completed_non_daily_overtime_and_early_terminal_states() -> None:
    config = small_config(job_count=2, min_job_duration_days=2, max_job_duration_days=3, max_campaign_day=6)
    scenario = generate_scenario(config)
    web = generate_decision_web(scenario, config)
    completed = initialize_state(scenario)
    for job_id in completed.jobs:
        complete_job(completed, job_id)
    with pytest.raises(RuntimeError, match="cannot choose after completing"):
        apply_omniscient_choice(completed, web, web.root_node_id)

    state = initialize_state(scenario_from_durations(3))
    with pytest.raises(RuntimeError, match="cannot advance before"):
        advance_omniscient_day(
            state,
            DecisionWebTransition(None, advances_day=False),
        )
    with pytest.raises(RuntimeError, match="crossed the runtime-generation boundary"):
        advance_omniscient_day(
            state,
            DecisionWebTransition(None, advances_day=True, enters_overtime=True),
        )
    with pytest.raises(RuntimeError, match="terminal web edge before completing"):
        advance_omniscient_day(
            state,
            DecisionWebTransition(None, advances_day=True),
        )
