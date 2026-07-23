from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

from echo_adventure.decision_web import (
    _JOB_TARGET_SCHEDULE_LENGTH,
    _JOB_TARGET_WINDOW_PATTERN,
    _DecisionWebBuilder,
    _target_window_index,
    DecisionWeb,
    DecisionWebGenerationTimeout,
    DecisionWebNode,
    DecisionWebState,
    generate_decision_web,
)
from echo_adventure.api.developer import (
    inspect_preplanned_follow_up,
    inspect_runtime_follow_up,
)
from echo_adventure.decisions.cards import (
    _avoid_exact_cancellation,
    _day_changes,
    generate_daily_decision_cards,
    generate_final_assembly_cards,
    select_echo_choice_for_state,
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
    assert {
        definition.id
        for definition in BASE_DEFINITIONS
        if definition.shared_across_routes
    } == {
        "weather",
        "safety-drill",
        "access-badge-failure",
        "network-folder-offline",
        "cleanliness-breach",
        "shop-air-pressure-dip",
        "waste-container-full",
        "vendor-rep-on-site",
        "shift-overlap-bonus",
        "off-peak-utility-slot",
    }

    for definition in DEFINITIONS_BY_ID.values():
        assert len(definition.choices) >= 1
        result_choices = (
            definition.choices,
            *(result.choices for result in definition.alternate_results),
        )
        for choices in result_choices:
            assert len(choices) == len(definition.choices)
            icons = [choice.icon_key for choice in choices]
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

    state = initialize_state(scenario_from_durations(5))
    outcome_choices = [
        make_choice("choice-1", changes={"JOB-01": -3}, score=-2),
        make_choice("choice-2", changes={}, score=5),
    ]
    assert select_echo_choice_for_state(state, outcome_choices).id == "choice-1"


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

    assert state.jobs["JOB-01"].remaining_days == 0
    assert state.jobs["JOB-01"].is_complete
    assert state.jobs["JOB-02"].remaining_days == 0
    later_choice = make_choice("choice-2", changes={"JOB-01": 5})
    apply_choice(state, make_card(later_choice), later_choice, actor="player")
    assert state.jobs["JOB-01"].remaining_days == 0
    assert state.decision_score == 2.25
    record = state.decision_history[0]
    assert (record.actor, record.aligned_with_echo) == ("player", True)
    assert record.applied_day_changes == {"JOB-01": -3}
    assert record.cumulative_score == 2.25
    assert state.decision_history[1].applied_day_changes == {}


def test_apply_choice_schedules_each_valid_follow_up_at_most_once() -> None:
    state = initialize_state(scenario_from_durations(3))
    follow_up_id = FOLLOW_UP_DEFINITIONS[0].id
    follow_up = DecisionFollowUp(follow_up_id, probability=1.0, delay_days=2)
    choice = make_choice("choice-1", changes={"JOB-01": 1}, follow_ups=(follow_up, follow_up))
    card = make_card(choice, definition_id="trigger")

    diagnostics = inspect_runtime_follow_up(state, card, choice)
    assert diagnostics["mode"] == "runtime"
    assert diagnostics["scheduled"] is True
    assert [target["definitionId"] for target in diagnostics["targets"] if target["scheduled"]] == [
        follow_up_id,
    ]
    assert all(
        target["effectNote"] == "Effect determined when follow-up appears"
        for target in diagnostics["targets"]
    )
    assert diagnostics["targets"][0]["possibilities"]

    apply_choice(state, card, choice, actor="player")
    apply_choice(state, card, choice, actor="player")

    assert state.pending_follow_ups == [
        PendingFollowUp(
            follow_up_id,
            "JOB-01",
            available_day=3,
            trigger_delta=1,
            source_day=1,
            source_definition_id="trigger",
            source_choice_id="choice-1",
        )
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
    assert all("Today's affected job is" not in card.description for card in first)

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

    outlier_state = initialize_state(scenario_from_durations(10, 3, 2, seed=1))
    outlier_cards = generate_daily_decision_cards(outlier_state, config)
    outlier_card = next(card for card in outlier_cards if card.primary_job_id == "JOB-01")
    assert any(
        delta > 0
        for choice in outlier_card.choices
        for delta in choice.day_changes.values()
    )

    final_state = initialize_state(scenario_from_durations(4))
    final_state.pending_follow_ups = [
        PendingFollowUp(
            "narrow-drift-found",
            "JOB-01",
            available_day=1,
            trigger_delta=1,
            source_day=1,
            source_definition_id="calibration-drift",
            source_choice_id="choice-1",
        )
    ]
    final_cards = generate_final_assembly_cards(
        final_state,
        config,
        maximum_total_days_removed=2,
    )
    assert len(final_cards) == 3
    assert final_cards[0].definition_id == "narrow-drift-found"
    assert final_cards[0].follow_up_source_title == "Measurements may be unreliable"
    assert final_cards[0].follow_up_source_choice_label == "Recalibrate now"
    assert all(card.player_only for card in final_cards)
    assert all(card.primary_job_id == "JOB-01" for card in final_cards)
    assert all("Only Job 1 remains" in card.description for card in final_cards)
    assert all(
        abs(delta) == 1
        for card in final_cards
        for choice in card.choices
        for delta in choice.day_changes.values()
    )
    assert any(
        delta < 0
        for card in final_cards
        for choice in card.choices
        for delta in choice.day_changes.values()
    )
    assert any(
        delta > 0
        for card in final_cards
        for choice in card.choices
        for delta in choice.day_changes.values()
    )
    assert all(any(not choice.day_changes for choice in card.choices) for card in final_cards)
    assert all(
        "keeps the current date" not in choice.label and "adds 1 day" not in choice.label
        for card in final_cards
        for choice in card.choices
    )
    assert all(
        not choice.follow_ups
        for card in final_cards
        for choice in card.choices
    )
    assert final_state.pending_follow_ups == []

    final_choice = final_cards[0].choices[0]
    apply_choice(final_state, final_cards[0], final_choice, actor="player")
    assert final_state.decision_history[-1].aligned_with_echo is None
    assert final_state.decision_history[-1].echo_choice_label is None


def test_due_follow_up_is_prioritized_and_stale_follow_ups_are_discarded() -> None:
    config = small_config()
    state = initialize_state(generate_scenario(config))
    due_id = FOLLOW_UP_DEFINITIONS[0].id
    state.pending_follow_ups = [
        PendingFollowUp(
            due_id,
            "JOB-01",
            available_day=1,
            trigger_delta=2,
            source_day=1,
            source_definition_id="calibration-drift",
            source_choice_id="choice-1",
        ),
        PendingFollowUp("missing", "JOB-02", available_day=1),
        PendingFollowUp(due_id, "MISSING", available_day=1),
    ]

    cards = generate_daily_decision_cards(state, config)

    assert cards[0].definition_id == due_id
    assert cards[0].primary_job_id == "JOB-01"
    assert cards[0].event_scope == "follow-up"
    assert cards[0].follow_up_source_title == "Measurements may be unreliable"
    assert cards[0].follow_up_source_choice_label == "Recalibrate now"
    assert "Job 1" not in cards[0].description
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
    builder = _DecisionWebBuilder(scenario, config, generation_attempt=0)
    retry_builder = _DecisionWebBuilder(scenario, config, generation_attempt=1)

    assert web == duplicate
    assert web.generation_attempt == duplicate.generation_attempt
    assert web.optimal_completion_day < config.max_campaign_day
    with pytest.raises(ValueError, match="greater than zero"):
        generate_decision_web(scenario, config, max_generation_seconds=0)
    with patch(
        "echo_adventure.decision_web.time.monotonic",
        side_effect=(100.0, 116.0),
    ):
        with pytest.raises(DecisionWebGenerationTimeout, match="seed 818"):
            generate_decision_web(
                scenario,
                config,
                max_generation_seconds=15,
            )
    assert _JOB_TARGET_WINDOW_PATTERN == (2, 1)
    assert len(builder.job_target_schedule) == _JOB_TARGET_SCHEDULE_LENGTH
    assert builder.job_target_schedule == retry_builder.job_target_schedule
    assert all(
        set(builder.job_target_schedule[start : start + len(builder.job_ids)])
        == set(builder.job_ids)
        for start in range(0, _JOB_TARGET_SCHEDULE_LENGTH, len(builder.job_ids))
    )
    expected_window_indexes = (0, 0, 1, 2, 2, 3, 4, 4, 5, 6, 6, 7)
    assert tuple(_target_window_index(day) for day in range(1, 13)) == expected_window_indexes
    incomplete = list(initialize_state(scenario).incomplete_jobs())
    assert tuple(
        builder._select_scheduled_job(day, incomplete).id
        for day in range(1, 13)
    ) == tuple(builder.job_target_schedule[index] for index in expected_window_indexes)
    assert builder._select_scheduled_job(301, incomplete).id == builder.job_target_schedule[0]

    day_one_target = builder.job_target_schedule[0]
    incomplete_after_target = [job for job in incomplete if job.id != day_one_target]
    expected_advanced_target = next(
        job_id
        for job_id in builder.job_target_schedule[1:]
        if job_id in {job.id for job in incomplete_after_target}
    )
    assert builder._select_scheduled_job(1, incomplete_after_target).id == expected_advanced_target

    multi_question_config = small_config(
        job_count=2,
        min_job_duration_days=2,
        max_job_duration_days=3,
        min_decisions_per_day=2,
        max_decisions_per_day=2,
        max_campaign_day=6,
        seed=818,
    )
    multi_question_builder = _DecisionWebBuilder(
        scenario,
        multi_question_config,
        generation_attempt=0,
    )
    remaining = tuple(scenario.jobs[job_id].remaining_days for job_id in builder.job_ids)
    first_card = multi_question_builder._build_card(
        DecisionWebState(1, 0, remaining, 0),
        "NODE-UNIT-1",
    )
    second_card = multi_question_builder._build_card(
        DecisionWebState(1, 1, remaining, 0),
        "NODE-UNIT-2",
    )
    assert first_card.primary_job_id == second_card.primary_job_id == day_one_target

    pending_job_index = 1 - builder.job_index[day_one_target]
    multi_question_builder.base_schedule[(1, 1)] = DEFINITIONS_BY_ID[
        "handoff-window-missed"
    ]
    pending_card = multi_question_builder._build_card(
        DecisionWebState(
            1,
            1,
            remaining,
            0,
            pending_definition_id=FOLLOW_UP_DEFINITIONS[0].id,
            pending_job_index=pending_job_index,
            pending_available_day=1,
            pending_trigger_delta=1,
            pending_source_day=1,
            pending_source_definition_id="calibration-drift",
            pending_source_choice_id="choice-1",
        ),
        "NODE-UNIT-FOLLOW-UP",
    )
    assert pending_card.primary_job_id == builder.job_ids[pending_job_index]
    assert pending_card.event_scope == "follow-up"
    assert pending_card.follow_up_source_day == 1
    assert pending_card.follow_up_source_title == "Measurements may be unreliable"
    assert pending_card.follow_up_source_choice_label == "Recalibrate now"

    shared_pending_state = DecisionWebState(
        1,
        1,
        remaining,
        0,
        pending_definition_id=FOLLOW_UP_DEFINITIONS[0].id,
        pending_job_index=pending_job_index,
        pending_available_day=1,
        pending_trigger_delta=1,
        pending_source_day=1,
        pending_source_definition_id="calibration-drift",
        pending_source_choice_id="choice-1",
    )
    multi_question_builder.base_schedule[(1, 1)] = DEFINITIONS_BY_ID[
        "access-badge-failure"
    ]
    shared_card = multi_question_builder._build_card(
        shared_pending_state,
        "NODE-UNIT-SHARED",
    )
    assert shared_card.definition_id == "access-badge-failure"
    assert shared_card.event_scope == "shared-day"

    delayed_choice = make_choice(
        "choice-1",
        follow_ups=(DecisionFollowUp(FOLLOW_UP_DEFINITIONS[0].id, 1.0, 1),),
    )
    delayed_card = make_card(
        delayed_choice,
        primary_job_id=builder.job_ids[pending_job_index],
        definition_id="calibration-drift",
    )
    delayed_transition = multi_question_builder._build_transition(
        DecisionWebState(1, 0, remaining, 0),
        "NODE-UNIT-DELAYED",
        delayed_card,
        delayed_choice,
    )
    delayed_state = multi_question_builder.nodes[
        delayed_transition.next_node_id
    ].state
    assert delayed_state.pending_available_day == 2
    assert delayed_state.pending_source_day == 1
    assert delayed_state.pending_source_definition_id == "calibration-drift"
    assert delayed_state.pending_source_choice_id == "choice-1"

    delayed_root_state = DecisionWebState(1, 0, remaining, 0)
    multi_question_builder.nodes["NODE-UNIT-DELAYED"] = DecisionWebNode(
        state=delayed_root_state,
        card=delayed_card,
        transitions={delayed_choice.id: delayed_transition},
    )
    inspection_web = DecisionWeb(
        root_node_id="NODE-UNIT-DELAYED",
        nodes=multi_question_builder.nodes,
        question_counts=multi_question_builder.question_counts,
        optimal_completion_day=0,
        optimal_unfinished_job_days=0,
        generation_attempt=multi_question_builder.generation_attempt,
    )
    forward = inspect_preplanned_follow_up(
        inspection_web,
        "NODE-UNIT-DELAYED",
        delayed_choice,
        scenario.jobs,
        config.date_label_for_day,
    )
    assert forward["scheduled"] is True
    assert forward["target"]["definitionId"] == FOLLOW_UP_DEFINITIONS[0].id
    assert forward["target"]["delayDays"] == 1
    assert forward["possibleDays"]
    assert forward["earliestDay"] == min(forward["possibleDays"])
    assert forward["variants"]
    assert all(
        variant["definitionId"] == FOLLOW_UP_DEFINITIONS[0].id
        for variant in forward["variants"]
    )
    assert all(
        {
            "jobId",
            "jobLabel",
            "jobName",
            "days",
            "remainingBefore",
            "remainingAfter",
        }
        <= change.keys()
        for variant in forward["variants"]
        for variant_choice in variant["choices"]
        for change in variant_choice["jobDayChanges"]
    )

    non_longest_scenario = scenario_from_durations(10, 3, 2, seed=1)
    non_longest_config = small_config(
        job_count=3,
        min_job_duration_days=2,
        max_job_duration_days=10,
        max_campaign_day=11,
        seed=1,
    )
    non_longest_builder = _DecisionWebBuilder(
        non_longest_scenario,
        non_longest_config,
        generation_attempt=0,
    )
    non_longest_target = non_longest_builder._select_scheduled_job(
        1,
        list(non_longest_scenario.jobs.values()),
    )
    assert non_longest_target.id == "JOB-02"
    assert non_longest_target.remaining_days < max(
        job.remaining_days for job in non_longest_scenario.jobs.values()
    )
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
            choice_remaining = list(node.state.remaining_days)
            choice_completed_mask = node.state.completed_mask
            for job_id, delta in choices[choice_id].day_changes.items():
                index = builder.job_index[job_id]
                if not choice_completed_mask & (1 << index):
                    choice_remaining[index] += delta
                    if choice_remaining[index] <= 0:
                        choice_remaining[index] = 0
                        choice_completed_mask |= 1 << index
            if transition.advances_day and transition.next_node_id is not None:
                successor_state = web.node(transition.next_node_id).state
                assert successor_state.remaining_days == tuple(
                    remaining_days
                    if choice_completed_mask & (1 << index)
                    else max(0, remaining_days - 1)
                    for index, remaining_days in enumerate(choice_remaining)
                )
            if transition.completion_day is not None:
                completion_day, future_score, future_unfinished_job_days = (
                    transition.completion_day,
                    0.0,
                    0,
                )
            elif transition.enters_overtime:
                completion_day, future_score, future_unfinished_job_days = (
                    config.max_campaign_day,
                    0.0,
                    0,
                )
            else:
                successor = web.node(transition.next_node_id)
                completion_day = successor.optimal_completion_day
                future_score = successor.optimal_future_score
                future_unfinished_job_days = successor.optimal_future_unfinished_job_days
            expected.append(
                (
                    completion_day,
                    round(choices[choice_id].score_delta + future_score, 2),
                    transition.unfinished_job_days + future_unfinished_job_days,
                    choice_id,
                )
            )
        assert min(
            expected,
            key=lambda candidate: (candidate[0], -candidate[1], candidate[2], candidate[3]),
        ) == (
            node.optimal_completion_day,
            node.optimal_future_score,
            node.optimal_future_unfinished_job_days,
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
    routes: list[tuple[int, float, int, tuple[str, ...]]] = []

    def visit(
        node_id: str,
        score: float,
        unfinished_job_days: int,
        path: tuple[str, ...],
    ) -> None:
        node = web.node(node_id)
        choices = {choice.id: choice for choice in node.card.choices}
        for choice_id, transition in node.transitions.items():
            next_score = round(score + choices[choice_id].score_delta, 2)
            next_unfinished_job_days = (
                unfinished_job_days + transition.unfinished_job_days
            )
            next_path = (*path, choice_id)
            if transition.completion_day is not None:
                routes.append(
                    (
                        transition.completion_day,
                        next_score,
                        next_unfinished_job_days,
                        next_path,
                    )
                )
            elif transition.enters_overtime:
                routes.append(
                    (
                        config.max_campaign_day,
                        next_score,
                        next_unfinished_job_days,
                        next_path,
                    )
                )
            else:
                assert transition.next_node_id is not None
                visit(
                    transition.next_node_id,
                    next_score,
                    next_unfinished_job_days,
                    next_path,
                )

    visit(web.root_node_id, 0.0, 0, ())
    assert routes
    globally_best = min(
        routes,
        key=lambda route: (route[0], -route[1], route[2], route[3]),
    )

    echo_path: list[str] = []
    node_id: str | None = web.root_node_id
    while node_id is not None:
        node = web.node(node_id)
        echo_path.append(node.optimal_choice_id)
        transition = node.transitions[node.optimal_choice_id]
        node_id = transition.next_node_id

    optimal_score = web.node(web.root_node_id).optimal_future_score
    assert globally_best == (
        web.optimal_completion_day,
        optimal_score,
        web.optimal_unfinished_job_days,
        tuple(echo_path),
    )
    for completion_day, score, unfinished_job_days, path in routes:
        if path == tuple(echo_path):
            continue
        assert (
            completion_day > web.optimal_completion_day
            or (completion_day == web.optimal_completion_day and score < optimal_score)
            or (
                completion_day == web.optimal_completion_day
                and score == optimal_score
                and unfinished_job_days > web.optimal_unfinished_job_days
            )
            or (
                completion_day == web.optimal_completion_day
                and score == optimal_score
                and unfinished_job_days == web.optimal_unfinished_job_days
                and path > tuple(echo_path)
            )
        )
