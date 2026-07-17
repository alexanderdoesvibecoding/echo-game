from __future__ import annotations

import copy

import pytest

from echo_adventure.decision_web import generate_decision_web
from echo_adventure.decisions.cards import (
    _avoid_exact_cancellation,
    _day_changes,
    generate_daily_decision_cards,
    select_echo_choice_from_choices,
)
from echo_adventure.decisions.definitions import (
    BASE_DEFINITIONS,
    DEFINITIONS_BY_ID,
    FOLLOW_UP_DEFINITIONS,
    SUPPORTED_CHOICE_ICON_KEYS,
)
from echo_adventure.decisions.effects import apply_choice
from echo_adventure.models import DecisionFollowUp, PendingFollowUp
from echo_adventure.scenario_generator import generate_scenario
from echo_adventure.simulation import initialize_state

from .helpers import make_card, make_choice, scenario_from_durations, small_config


def test_catalog_is_large_unique_and_has_valid_choice_icons() -> None:
    assert len(DEFINITIONS_BY_ID) >= 70
    assert len(DEFINITIONS_BY_ID) == len(BASE_DEFINITIONS) + len(FOLLOW_UP_DEFINITIONS)
    assert all(not definition.is_follow_up for definition in BASE_DEFINITIONS)
    assert all(definition.is_follow_up for definition in FOLLOW_UP_DEFINITIONS)

    for definition in DEFINITIONS_BY_ID.values():
        assert len(definition.choices) >= 1
        icons = [choice.icon_key for choice in definition.choices]
        assert len(icons) == len(set(icons))
        assert set(icons) <= SUPPORTED_CHOICE_ICON_KEYS


@pytest.mark.parametrize(
    "score, expected",
    [
        (0.0, {}),
        (0.14, {}),
        (0.2, {"JOB-01": -1}),
        (-0.2, {"JOB-01": 1}),
        (2.0, {"JOB-01": -1, "JOB-02": -1, "JOB-03": -1}),
    ],
)
def test_schedule_scores_become_bounded_explicit_day_changes(score: float, expected: dict[str, int]) -> None:
    jobs = list(scenario_from_durations(3, 3, 3).jobs.values())
    assert _day_changes(score, jobs) == expected


def test_inverse_follow_up_never_exactly_cancels_the_trigger() -> None:
    assert _avoid_exact_cancellation({"JOB-01": -2}, 2, "JOB-01") == {"JOB-01": -3}
    assert _avoid_exact_cancellation({"JOB-01": -1}, 2, "JOB-01") == {"JOB-01": -1}


def test_echo_choice_has_a_stable_tiebreak() -> None:
    choices = [
        make_choice("choice-1", score=2),
        make_choice("choice-2", score=2),
        make_choice("choice-3", score=1),
    ]
    assert select_echo_choice_from_choices(choices).id == "choice-2"


def test_apply_choice_changes_only_unfinished_known_jobs_and_records_score() -> None:
    state = initialize_state(scenario_from_durations(2, 3))
    state.jobs["JOB-02"].remaining_days = 0
    state.jobs["JOB-02"].status = state.jobs["JOB-02"].status.COMPLETE
    choice = make_choice(
        "choice-1",
        changes={"JOB-01": -3, "JOB-02": 5, "MISSING": 8},
        score=2.25,
    )
    card = make_card(choice)

    apply_choice(state, card, choice, actor="player")

    assert state.jobs["JOB-01"].remaining_days == -1
    assert state.jobs["JOB-02"].remaining_days == 0
    assert state.decision_score == 2.25
    record = state.decision_history[0]
    assert (record.actor, record.aligned_with_echo) == ("player", True)
    assert record.cumulative_score == 2.25


def test_apply_choice_schedules_each_valid_follow_up_at_most_once() -> None:
    state = initialize_state(scenario_from_durations(3))
    follow_up_id = FOLLOW_UP_DEFINITIONS[0].id
    follow_up = DecisionFollowUp(follow_up_id, probability=1.0, delay_days=2)
    choice = make_choice("choice-1", changes={"JOB-01": 1}, follow_ups=(follow_up, follow_up))
    card = make_card(choice, definition_id="trigger")

    apply_choice(state, card, choice, actor="player")
    apply_choice(state, card, choice, actor="player")

    assert state.pending_follow_ups == [
        PendingFollowUp(follow_up_id, "JOB-01", available_day=3, trigger_delta=1)
    ]


def test_daily_card_generation_is_deterministic_varied_and_free_of_subjob_copy() -> None:
    config = small_config(min_decisions_per_day=3, max_decisions_per_day=3)
    scenario = generate_scenario(config)
    first_state = initialize_state(scenario)
    second_state = initialize_state(copy.deepcopy(scenario))

    first = generate_daily_decision_cards(first_state, config)
    second = generate_daily_decision_cards(second_state, config)

    assert first == second
    assert len(first) == 3
    assert len({card.definition_id for card in first}) == 3
    assert len({card.primary_job_id for card in first}) == 3
    assert all(card.echo_choice_id in {choice.id for choice in card.choices} for card in first)
    assert "subjob" not in " ".join(
        [part for card in first for part in (card.title, card.description)]
    ).lower()

    last_job_state = initialize_state(scenario_from_durations(2))
    last_job_cards = generate_daily_decision_cards(
        last_job_state,
        config,
    )
    assert last_job_cards
    assert all(
        delta <= 0
        for card in last_job_cards
        for choice in card.choices
        for delta in choice.day_changes.values()
    )


def test_due_follow_up_is_prioritized_and_stale_follow_ups_are_discarded() -> None:
    config = small_config()
    state = initialize_state(generate_scenario(config))
    due_id = FOLLOW_UP_DEFINITIONS[0].id
    state.pending_follow_ups = [
        PendingFollowUp(due_id, "JOB-01", available_day=1, trigger_delta=2),
        PendingFollowUp("missing", "JOB-02", available_day=1),
        PendingFollowUp(due_id, "MISSING", available_day=1),
    ]

    cards = generate_daily_decision_cards(state, config)

    assert cards[0].definition_id == due_id
    assert cards[0].primary_job_id == "JOB-01"
    assert state.pending_follow_ups == []
    assert due_id in state.shown_follow_up_decision_ids
    assert all(sum(choice.day_changes.values()) != -2 for choice in cards[0].choices)


@pytest.fixture(scope="module")
def solved_web_bundle():
    config = small_config(job_count=2, min_job_duration_days=2, max_job_duration_days=3, max_campaign_day=6, seed=818)
    scenario = generate_scenario(config)
    return config, scenario, generate_decision_web(scenario, config)


def test_decision_web_is_deterministic_and_every_node_is_fully_solved(solved_web_bundle) -> None:
    config, scenario, web = solved_web_bundle
    duplicate = generate_decision_web(scenario, config)

    assert web == duplicate
    assert web.optimal_completion_day < config.max_campaign_day
    assert any(
        transition.completion_day is not None
        for node in web.nodes.values()
        for transition in node.transitions.values()
    )
    for node in web.nodes.values():
        assert set(node.transitions) == {choice.id for choice in node.card.choices}
        assert node.card.echo_choice_id == node.optimal_choice_id
        assert node.optimal_choice_id in node.transitions
        expected = []
        choices = {choice.id: choice for choice in node.card.choices}
        for choice_id, transition in node.transitions.items():
            if transition.completion_day is not None:
                completion_day, future_score = transition.completion_day, 0.0
            elif transition.enters_overtime:
                completion_day, future_score = config.max_campaign_day, 0.0
            else:
                successor = web.node(transition.next_node_id)
                completion_day, future_score = successor.optimal_completion_day, successor.optimal_future_score
            expected.append((completion_day, round(choices[choice_id].score_delta + future_score, 2), choice_id))
        assert min(expected, key=lambda candidate: (candidate[0], -candidate[1], candidate[2])) == (
            node.optimal_completion_day,
            node.optimal_future_score,
            node.optimal_choice_id,
        )


def test_decision_web_detects_runtime_drift(solved_web_bundle) -> None:
    _, scenario, web = solved_web_bundle
    state = initialize_state(scenario)
    web.assert_runtime_matches(state, web.root_node_id)

    state.jobs["JOB-01"].remaining_days += 1
    with pytest.raises(RuntimeError, match="diverged"):
        web.assert_runtime_matches(state, web.root_node_id)


def test_optimal_route_never_enters_overtime(solved_web_bundle) -> None:
    _, _, web = solved_web_bundle
    node_id = web.root_node_id

    while node_id is not None:
        node = web.node(node_id)
        transition = node.transitions[node.optimal_choice_id]
        assert transition.enters_overtime is False
        node_id = transition.next_node_id


@pytest.mark.parametrize("seed", [31, 32, 33, 34, 35])
def test_every_route_through_a_small_web_respects_echo_objective_order(seed: int) -> None:
    """Exhaust every bounded route, not merely ECHO's selected traversal."""
    config = small_config(
        job_count=1,
        min_job_duration_days=2,
        max_job_duration_days=2,
        max_campaign_day=4,
        seed=seed,
    )
    scenario = generate_scenario(config)
    web = generate_decision_web(scenario, config)
    routes: list[tuple[int, float, tuple[str, ...]]] = []

    def visit(node_id: str, score: float, path: tuple[str, ...]) -> None:
        node = web.node(node_id)
        choices = {choice.id: choice for choice in node.card.choices}
        for choice_id, transition in node.transitions.items():
            next_score = round(score + choices[choice_id].score_delta, 2)
            next_path = (*path, choice_id)
            if transition.completion_day is not None:
                routes.append((transition.completion_day, next_score, next_path))
            elif transition.enters_overtime:
                routes.append((config.max_campaign_day, next_score, next_path))
            else:
                assert transition.next_node_id is not None
                visit(transition.next_node_id, next_score, next_path)

    visit(web.root_node_id, 0.0, ())
    assert routes
    globally_best = min(routes, key=lambda route: (route[0], -route[1], route[2]))

    echo_path: list[str] = []
    node_id: str | None = web.root_node_id
    while node_id is not None:
        node = web.node(node_id)
        echo_path.append(node.optimal_choice_id)
        transition = node.transitions[node.optimal_choice_id]
        node_id = transition.next_node_id

    optimal_score = web.node(web.root_node_id).optimal_future_score
    assert globally_best == (web.optimal_completion_day, optimal_score, tuple(echo_path))
    for completion_day, score, path in routes:
        if path == tuple(echo_path):
            continue
        assert (
            completion_day > web.optimal_completion_day
            or (completion_day == web.optimal_completion_day and score < optimal_score)
            or (
                completion_day == web.optimal_completion_day
                and score == optimal_score
                and path > tuple(echo_path)
            )
        )
