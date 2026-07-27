from __future__ import annotations

import builtins
from dataclasses import replace
from io import StringIO
import sys
import threading
from types import SimpleNamespace

import pytest

from echo_adventure.api import server as server_module
from echo_adventure.api import session as session_module
from echo_adventure.api.automation import (
    AUTOMATION_STRATEGIES,
    AutomationContext,
    ChoiceOutcome,
    preplanned_choice_outcome,
    reachable_preplanned_days,
    select_preplanned_choice,
    select_runtime_choice,
    validate_automation_strategy,
)
from echo_adventure.api.developer import (
    _card_has_source,
    _catalog_possibilities,
    _future_job_day_change_payload,
    _job_label as developer_job_label,
    _pending_job_id,
    _state_has_source,
    _unscheduled_follow_up,
    _variant_signature,
    inspect_preplanned_follow_up,
    inspect_runtime_follow_up,
)
from echo_adventure.api.payloads import (
    _chart_decision_payload,
    _choice_payload,
    _echo_comparison_state,
)
from echo_adventure.api.review import (
    ReviewMixin,
    _format_applied_changes,
    _format_day_count,
)
from echo_adventure.api.server import _initialization_status, _parse_optional_seed
from echo_adventure.decision_web import (
    DecisionWeb,
    DecisionWebNode,
    DecisionWebState,
    DecisionWebTransition,
    _completed_mask,
    _has_follow_up,
    _preplanned_follow_up_occurs,
)
from echo_adventure.decisions.cards import (
    _build_final_assembly_choice,
    _choice_follow_ups,
    _event_identity,
    _format_job_list,
    _preplanned_deltas,
    _remove_delays,
    _simplify_language,
    _source_choice_label,
    generate_daily_decision_cards,
    generate_final_assembly_cards,
)
from echo_adventure.decisions.definitions import (
    BASE_DEFINITIONS,
    DEFINITIONS_BY_ID,
    FOLLOW_UP_DEFINITIONS,
    CatalogChoice,
    DecisionDefinition,
    FollowUpEdge,
)
from echo_adventure.decisions.effects import follow_up_occurs
from echo_adventure.enums import JobStatus
from echo_adventure.models import (
    DecisionCard,
    DecisionChoice,
    DecisionFollowUp,
    DecisionRecord,
)
from echo_adventure.simulation import initialize_state

from .helpers import make_card, make_choice, scenario_from_durations, small_config


def _web_node(
    node_id: str,
    *,
    day: int,
    choices: list[DecisionChoice] | None = None,
    transitions: dict[str, DecisionWebTransition] | None = None,
    optimal_choice_id: str | None = None,
    optimal_completion_day: int = 4,
    optimal_future_score: float = 0.0,
    state: DecisionWebState | None = None,
    card: DecisionCard | None = None,
) -> tuple[str, DecisionWebNode]:
    node_choices = choices or [make_choice("choice-1")]
    node_card = card or make_card(
        *node_choices,
        echo_choice_id=optimal_choice_id or node_choices[0].id,
    )
    return (
        node_id,
        DecisionWebNode(
            state=state or DecisionWebState(day, 0, (max(1, 5 - day),), 0),
            card=node_card,
            transitions=transitions or {},
            optimal_choice_id=optimal_choice_id or node_choices[0].id,
            optimal_completion_day=optimal_completion_day,
            optimal_future_score=optimal_future_score,
        ),
    )


def _automation_web() -> tuple[DecisionWeb, dict[str, DecisionChoice]]:
    choices = {
        "continue": make_choice("continue", score=1.25),
        "overtime": make_choice("overtime", score=-2),
        "complete": make_choice("complete", score=3),
    }
    root_id, root = _web_node(
        "ROOT",
        day=1,
        choices=list(choices.values()),
        transitions={
            "continue": DecisionWebTransition("DAY-2", True),
            "overtime": DecisionWebTransition(
                None,
                True,
                enters_overtime=True,
            ),
            "complete": DecisionWebTransition(
                None,
                True,
                completion_day=2,
            ),
        },
        optimal_choice_id="complete",
        optimal_completion_day=2,
        optimal_future_score=3,
    )
    finish = make_choice("finish", score=0.5)
    day_two_id, day_two = _web_node(
        "DAY-2",
        day=2,
        choices=[finish],
        transitions={
            "finish": DecisionWebTransition(None, True, completion_day=4),
        },
        optimal_choice_id="finish",
        optimal_completion_day=4,
        optimal_future_score=0.5,
    )
    return (
        DecisionWeb(
            root_node_id=root_id,
            nodes={root_id: root, day_two_id: day_two},
            question_counts={1: 1, 2: 1},
            optimal_completion_day=2,
            optimal_unfinished_job_days=0,
            generation_attempt=0,
        ),
        choices,
    )


@pytest.mark.parametrize("strategy", sorted(AUTOMATION_STRATEGIES))
def test_automation_strategy_validation_accepts_every_supported_value(
    strategy: str,
) -> None:
    assert validate_automation_strategy(strategy) == strategy


@pytest.mark.parametrize(
    "strategy",
    [None, 1, True, "", "ECHO", "slowest"],
)
def test_automation_strategy_validation_rejects_every_other_shape(
    strategy: object,
) -> None:
    with pytest.raises(ValueError, match="Unknown automated strategy"):
        validate_automation_strategy(strategy)


def test_preplanned_choice_selection_and_outcomes_cover_all_edge_types() -> None:
    web, choices = _automation_web()
    context = AutomationContext(seed=19, start_token="unit-start")

    assert select_preplanned_choice(
        web,
        "ROOT",
        "echo",
        context,
        max_campaign_day=8,
    ).id == "complete"
    assert select_preplanned_choice(
        web,
        "ROOT",
        "first",
        context,
        max_campaign_day=8,
    ).id == "continue"
    assert select_preplanned_choice(
        web,
        "ROOT",
        "last",
        context,
        max_campaign_day=8,
    ).id == "complete"
    assert (
        select_preplanned_choice(
            web,
            "ROOT",
            "random",
            context,
            max_campaign_day=8,
        )
        == select_preplanned_choice(
            web,
            "ROOT",
            "random",
            context,
            max_campaign_day=8,
        )
    )
    assert preplanned_choice_outcome(
        web,
        "ROOT",
        choices["continue"],
        max_campaign_day=8,
    ) == ChoiceOutcome(4, 1.75, True)
    assert preplanned_choice_outcome(
        web,
        "ROOT",
        choices["overtime"],
        max_campaign_day=8,
    ) == ChoiceOutcome(8, -2.0, False)
    assert preplanned_choice_outcome(
        web,
        "ROOT",
        choices["complete"],
        max_campaign_day=8,
    ) == ChoiceOutcome(2, 3.0, True)

    with pytest.raises(ValueError, match="Unsupported automated strategy"):
        select_preplanned_choice(
            web,
            "ROOT",
            "unsupported",
            context,
            max_campaign_day=8,
        )

    web.node("ROOT").optimal_choice_id = "missing"
    with pytest.raises(RuntimeError, match="not present"):
        select_preplanned_choice(
            web,
            "ROOT",
            "echo",
            context,
            max_campaign_day=8,
        )


def test_runtime_choice_selection_handles_player_only_and_last_job_safety() -> None:
    state = initialize_state(scenario_from_durations(4))
    context = AutomationContext(seed=7, start_token="runtime")
    delay_one = make_choice("delay-one", changes={"JOB-01": 1}, score=10)
    delay_two = make_choice("delay-two", changes={"JOB-01": 2}, score=-10)
    card = make_card(delay_one, delay_two, echo_choice_id="delay-two")
    card.player_only = True

    assert select_runtime_choice(state, card, "echo", context).id == "delay-two"

    card.player_only = False
    assert select_runtime_choice(state, card, "worst", context).id == "delay-one"

    with pytest.raises(ValueError, match="Unsupported automated strategy"):
        select_runtime_choice(state, card, "unsupported", context)

    card.echo_choice_id = "missing"
    card.player_only = True
    with pytest.raises(RuntimeError, match="not present"):
        select_runtime_choice(state, card, "echo", context)


def test_reachable_preplanned_days_supports_pending_edges_and_detects_cycles() -> None:
    web, _ = _automation_web()
    context = AutomationContext(seed=5, start_token="walk")

    assert reachable_preplanned_days(
        web,
        "ROOT",
        "first",
        context,
        current_day=1,
        max_campaign_day=8,
    ) == [2]
    assert reachable_preplanned_days(
        web,
        "ROOT",
        "first",
        context,
        current_day=1,
        max_campaign_day=8,
        pending_transition=DecisionWebTransition("DAY-2", True),
    ) == [2]
    assert reachable_preplanned_days(
        web,
        "ROOT",
        "last",
        context,
        current_day=1,
        max_campaign_day=8,
    ) == []

    loop_choice = make_choice("loop")
    loop_id, loop_node = _web_node(
        "LOOP",
        day=1,
        choices=[loop_choice],
        transitions={"loop": DecisionWebTransition("LOOP", False)},
        optimal_choice_id="loop",
    )
    loop_web = DecisionWeb(
        root_node_id=loop_id,
        nodes={loop_id: loop_node},
        question_counts={1: 1},
        optimal_completion_day=2,
        optimal_unfinished_job_days=0,
        generation_attempt=0,
    )
    with pytest.raises(RuntimeError, match="cycle at LOOP"):
        reachable_preplanned_days(
            loop_web,
            "LOOP",
            "echo",
            context,
            current_day=1,
            max_campaign_day=8,
        )


def _scheduled_follow_up_web(
    *,
    target_definition_id: str = "narrow-drift-found",
) -> tuple[DecisionWeb, DecisionChoice]:
    trigger = make_choice("choice-1")
    trigger_card = make_card(trigger, definition_id="calibration-drift")
    root_id, root = _web_node(
        "SOURCE",
        day=1,
        choices=[trigger],
        card=trigger_card,
        transitions={"choice-1": DecisionWebTransition("WAITING", True)},
    )
    pending_state = DecisionWebState(
        2,
        0,
        (3,),
        0,
        pending_definition_id=target_definition_id,
        pending_job_index=0,
        pending_available_day=3,
        pending_trigger_delta=1,
        pending_source_day=1,
        pending_source_definition_id="calibration-drift",
        pending_source_choice_id="choice-1",
    )
    waiting_card = make_card(make_choice("wait"))
    waiting_id, waiting = _web_node(
        "WAITING",
        day=2,
        state=pending_state,
        card=waiting_card,
        transitions={
            "continue": DecisionWebTransition("FOLLOW-UP", True),
            "cancel": DecisionWebTransition(None, True, enters_overtime=True),
        },
    )
    follow_up_card = replace(
        make_card(
            make_choice("resolve", changes={"JOB-01": -1}),
            definition_id=target_definition_id,
        ),
        title="Resolved variant",
        event_scope="follow-up",
        follow_up_source_day=1,
        follow_up_source_definition_id="calibration-drift",
        follow_up_source_choice_id="choice-1",
    )
    follow_up_state = replace(pending_state, day=3)
    follow_up_id, follow_up = _web_node(
        "FOLLOW-UP",
        day=3,
        state=follow_up_state,
        card=follow_up_card,
    )
    return (
        DecisionWeb(
            root_node_id=root_id,
            nodes={
                root_id: root,
                waiting_id: waiting,
                follow_up_id: follow_up,
            },
            question_counts={1: 1, 2: 1, 3: 1},
            optimal_completion_day=4,
            optimal_unfinished_job_days=0,
            generation_attempt=0,
        ),
        trigger,
    )


def test_preplanned_follow_up_inspection_reports_variants_and_cancellation() -> None:
    web, trigger = _scheduled_follow_up_web()
    jobs = scenario_from_durations(4).jobs

    result = inspect_preplanned_follow_up(
        web,
        "SOURCE",
        trigger,
        jobs,
        lambda day: f"Date {day}",
    )

    assert result["mode"] == "preplanned"
    assert result["scheduled"] is True
    assert result["target"]["definitionId"] == "narrow-drift-found"
    assert result["target"]["jobLabel"] == "Job 1"
    assert result["target"]["delayDays"] == 2
    assert result["earliestDay"] == 3
    assert result["earliestDate"] == "Date 3"
    assert result["possibleDays"] == [3]
    assert result["possibleDates"] == ["Date 3"]
    assert result["canceledOnSomeContinuations"] is True
    assert result["variants"][0]["title"] == "Resolved variant"
    assert result["variants"][0]["possibleDays"] == [3]
    assert result["variants"][0]["choices"][0]["jobDayChanges"][0] == {
        "jobId": "JOB-01",
        "jobLabel": "Job 1",
        "jobName": "Job 1",
        "days": -1,
        "applies": True,
        "remainingBefore": 3,
        "remainingAfter": 2,
    }


def test_preplanned_and_runtime_follow_up_inspection_handles_unscheduled_edges() -> None:
    web, choices = _automation_web()
    jobs = scenario_from_durations(3).jobs
    assert inspect_preplanned_follow_up(
        web,
        "ROOT",
        choices["complete"],
        jobs,
        str,
    ) == _unscheduled_follow_up("preplanned")

    unknown_follow_up = DecisionFollowUp("missing-definition", 1.0, 2)
    choice = make_choice("unknown", follow_ups=(unknown_follow_up,))
    card = make_card(choice, primary_job_id="JOB-99")
    runtime = inspect_runtime_follow_up(
        initialize_state(scenario_from_durations(3)),
        card,
        choice,
    )
    assert runtime["scheduled"] is False
    assert runtime["targets"][0]["title"] == "missing-definition"
    assert runtime["targets"][0]["jobName"] == "JOB-99"
    assert runtime["targets"][0]["possibilities"] == []

    card.player_only = True
    assert inspect_runtime_follow_up(
        initialize_state(scenario_from_durations(3)),
        card,
        choice,
    ) == {
        "mode": "player-only",
        "scheduled": False,
        "targets": [],
        "note": "Final-assembly choices do not schedule follow-ups.",
    }


def test_developer_inspection_helpers_cover_source_and_completed_job_boundaries() -> None:
    state = DecisionWebState(
        3,
        0,
        (0, 4),
        1,
        pending_definition_id="later",
        pending_job_index=1,
        pending_source_day=1,
        pending_source_definition_id="source",
        pending_source_choice_id="choice-2",
    )
    source = (1, "source", "choice-2")
    jobs = scenario_from_durations(2, 4).jobs
    card = replace(
        make_card(make_choice("choice-1")),
        event_scope="follow-up",
        follow_up_source_day=1,
        follow_up_source_definition_id="source",
        follow_up_source_choice_id="choice-2",
    )

    assert _state_has_source(state, source)
    assert _state_has_source(state, source, target_definition_id="later")
    assert not _state_has_source(state, source, target_definition_id="other")
    assert _card_has_source(card, source)
    assert not _card_has_source(replace(card, event_scope="route-specific"), source)
    assert _pending_job_id(state, jobs) == "JOB-02"
    assert _pending_job_id(replace(state, pending_job_index=99), jobs) == ""
    assert _variant_signature(card)[0] == card.definition_id
    assert _future_job_day_change_payload(state, jobs, "JOB-01", -3) == {
        "jobId": "JOB-01",
        "jobLabel": "Job 1",
        "jobName": "Job 1",
        "days": -3,
        "applies": False,
        "remainingBefore": 0,
        "remainingAfter": 0,
    }
    assert developer_job_label("") == ""
    assert developer_job_label("JOB-09") == "Job 9"

    definition = next(
        item for item in FOLLOW_UP_DEFINITIONS if item.alternate_results
    )
    possibilities = _catalog_possibilities(definition)
    assert possibilities[0]["kind"] == "catalog"
    assert any(item["kind"] == "alternate" for item in possibilities)
    assert all(
        choice["effectNote"] == "Effect determined when follow-up appears"
        for possibility in possibilities
        for choice in possibility["choices"]
    )


class _ReviewHarness(ReviewMixin):
    pass


def _review_harness(
    *,
    player_day: int,
    echo_day: int,
    player_score: float,
    echo_score: float,
    player_unfinished: int,
    echo_unfinished: int,
    aligned: bool,
) -> _ReviewHarness:
    player_choice = make_choice("player-choice", score=-1)
    echo_choice = make_choice("echo-choice", score=1)
    card = make_card(
        player_choice,
        echo_choice,
        echo_choice_id=echo_choice.id,
    )
    player_record = DecisionRecord(
        day=1,
        card_id=card.id,
        card_title=card.title,
        actor="player",
        choice_label=echo_choice.label if aligned else player_choice.label,
        echo_choice_label=echo_choice.label,
        aligned_with_echo=aligned,
        applied_day_changes={"JOB-01": 1},
        score_delta=echo_choice.score_delta if aligned else player_choice.score_delta,
        cumulative_score=player_score,
    )
    echo_record = replace(
        player_record,
        actor="ECHO",
        choice_label=echo_choice.label,
        aligned_with_echo=True,
        score_delta=echo_choice.score_delta,
        cumulative_score=echo_score,
    )
    jobs = scenario_from_durations(2).jobs
    harness = _ReviewHarness()
    harness.config = small_config(max_campaign_day=8)
    harness.player_state = SimpleNamespace(
        completion_day=player_day,
        current_day=player_day,
        decision_history=[player_record],
        decision_cards={card.id: card},
        decision_score=player_score,
        cumulative_unfinished_job_days=player_unfinished,
        jobs=jobs,
    )
    harness.automated_state = SimpleNamespace(
        completion_day=echo_day,
        current_day=echo_day,
        decision_history=[echo_record],
        decision_cards={card.id: card},
        decision_score=echo_score,
        cumulative_unfinished_job_days=echo_unfinished,
        jobs=jobs,
    )
    return harness


@pytest.mark.parametrize(
    (
        "values",
        "expected_outcome",
        "headline_fragment",
    ),
    [
        (
            (4, 4, 2.0, 2.0, 10, 10, True),
            "tied",
            "exact optimal path",
        ),
        (
            (6, 4, 2.0, 2.0, 10, 10, False),
            "behind",
            "2 days earlier",
        ),
        (
            (4, 4, 1.0, 2.0, 10, 10, False),
            "behind",
            "higher score",
        ),
        (
            (4, 4, 2.0, 2.0, 11, 10, False),
            "behind",
            "1 fewer unfinished job-day",
        ),
        (
            (4, 4, 2.0, 2.0, 10, 10, False),
            "behind",
            "routes diverged",
        ),
    ],
)
def test_final_review_classifies_every_permitted_outcome(
    values: tuple[int, int, float, float, int, int, bool],
    expected_outcome: str,
    headline_fragment: str,
) -> None:
    review = _review_harness(
        player_day=values[0],
        echo_day=values[1],
        player_score=values[2],
        echo_score=values[3],
        player_unfinished=values[4],
        echo_unfinished=values[5],
        aligned=values[6],
    )._final_review_payload()

    assert review["outcome"] == expected_outcome
    assert headline_fragment in review["headline"]
    assert 3 <= len(review["reasons"]) <= 5


def test_final_review_rejects_a_route_that_would_surpass_echo() -> None:
    harness = _review_harness(
        player_day=3,
        echo_day=4,
        player_score=3,
        echo_score=2,
        player_unfinished=5,
        echo_unfinished=6,
        aligned=False,
    )
    with pytest.raises(RuntimeError, match="surpassed"):
        harness._final_review_payload()


@pytest.mark.parametrize(
    ("player_choice_score", "expected"),
    [
        (-1.0, "cost 2 job-days"),
        (2.0, "saved 1 job-day more immediately"),
        (1.0, "same immediate job-day total"),
    ],
)
def test_review_turning_point_explains_positive_negative_and_neutral_deltas(
    player_choice_score: float,
    expected: str,
) -> None:
    harness = _review_harness(
        player_day=5,
        echo_day=4,
        player_score=player_choice_score,
        echo_score=1,
        player_unfinished=10,
        echo_unfinished=9,
        aligned=False,
    )
    card = next(iter(harness.player_state.decision_cards.values()))
    card.choices[0] = replace(card.choices[0], score_delta=player_choice_score)
    record = replace(
        harness.player_state.decision_history[0],
        score_delta=player_choice_score,
        cumulative_score=player_choice_score,
    )

    sentence = harness._decision_driver_sentence(record, 2)

    assert expected in sentence
    assert "question 2" in sentence
    assert "added 1 day to Job 1" in sentence


def test_review_helpers_format_counts_changes_and_overtime_fallback() -> None:
    jobs = scenario_from_durations(2, 3, 4).jobs
    assert _format_day_count(1) == "1 job-day"
    assert _format_day_count(1.5) == "1.5 job-days"
    assert _format_day_count(2) == "2 job-days"
    assert _format_applied_changes({}, jobs) == "made no direct job-day change"
    assert _format_applied_changes({"JOB-01": -1}, jobs) == (
        "removed 1 day from Job 1"
    )
    assert _format_applied_changes(
        {"JOB-01": 1, "JOB-02": -2},
        jobs,
    ) == "added 1 day to Job 1 and removed 2 days from Job 2"
    assert _format_applied_changes(
        {"JOB-01": 1, "JOB-02": -2, "MISSING": 3},
        jobs,
    ) == (
        "added 1 day to Job 1, removed 2 days from Job 2, "
        "and added 3 days to MISSING"
    )

    harness = _review_harness(
        player_day=9,
        echo_day=4,
        player_score=0,
        echo_score=1,
        player_unfinished=10,
        echo_unfinished=9,
        aligned=False,
    )
    overtime = replace(
        harness.player_state.decision_history[0],
        day=8,
        card_id="missing-card",
    )
    reasons = harness._outcome_driver_reasons(
        [overtime],
        comparable_record_count=1,
        identical_optimal_path=False,
        player_day=9,
        echo_day=4,
        aligned=0,
    )
    assert reasons[0].startswith("Your route required 1 overtime question")


def test_payload_helpers_preserve_fallback_context_and_optional_diagnostics() -> None:
    choice = make_choice("choice-1")
    assert _choice_payload(choice) == {
        "id": "choice-1",
        "label": "Choice choice-1",
        "icon": "adjust",
    }
    assert _choice_payload(choice, developer={})["developer"] == {}

    record = DecisionRecord(
        day=2,
        card_id="missing-card",
        card_title="Recorded title",
        actor="player",
        choice_label="Recorded choice",
        echo_choice_label="ECHO choice",
        aligned_with_echo=False,
        applied_day_changes={},
        score_delta=0,
        cumulative_score=0,
    )
    fallback = _chart_decision_payload(
        record,
        None,
        position=2,
        include_echo_preference=True,
        echo_comparison_state="different-events",
    )
    assert fallback["questionText"] == "Recorded title"
    assert fallback["affectedLabel"] == "-"
    assert fallback["eventId"] == "missing-card"
    assert fallback["echoPreferredChoice"] == "ECHO choice"
    assert fallback["echoPreferenceState"] == "different-events-different-choice"

    card = replace(
        make_card(choice),
        follow_up_source_day=1,
        follow_up_source_definition_id="source",
        follow_up_source_title="Source title",
        follow_up_source_choice_id="choice-2",
        follow_up_source_choice_label="Source choice",
    )
    enriched = _chart_decision_payload(
        replace(record, card_id=card.id, choice_label=choice.label),
        card,
        position=1,
        include_echo_preference=True,
        echo_comparison_state="same-context",
    )
    assert "followUpSource" not in enriched
    assert enriched["echoPreferenceState"] == "same-context-same-choice"
    assert _echo_comparison_state(None, card) == "different-events"


def test_decision_card_helpers_cover_empty_final_and_follow_up_boundaries() -> None:
    completed = initialize_state(scenario_from_durations(1))
    completed.jobs["JOB-01"].status = JobStatus.COMPLETE
    completed.completed_jobs.add("JOB-01")
    completed.final_item_completed = True
    completed.completion_day = 1
    assert generate_daily_decision_cards(completed, small_config()) == []

    with pytest.raises(ValueError, match="exactly one unfinished job"):
        generate_final_assembly_cards(
            initialize_state(scenario_from_durations(2, 3)),
            small_config(),
        )

    job = scenario_from_durations(4).jobs["JOB-01"]
    neutral = CatalogChoice("Neutral", (), 1.0, "wait")
    assert _build_final_assembly_choice(
        neutral,
        job,
        1,
        1.0,
        1.0,
        allow_acceleration=True,
    ).day_changes == {}
    assert _build_final_assembly_choice(
        neutral,
        job,
        1,
        1.0,
        -1.0,
        allow_acceleration=True,
    ).day_changes == {"JOB-01": -1}
    assert _build_final_assembly_choice(
        replace(neutral, score_delta=-1.0),
        job,
        2,
        1.0,
        -1.0,
        allow_acceleration=False,
    ).day_changes == {"JOB-01": 1}
    assert _remove_delays({"JOB-01": 2, "JOB-02": -1, "JOB-03": 0}) == {
        "JOB-02": -1,
    }


def test_decision_definition_helpers_preserve_semantics_and_safe_labels() -> None:
    base = next(
        item for item in BASE_DEFINITIONS if not item.shared_across_routes
    )
    follow_up = FOLLOW_UP_DEFINITIONS[0]
    jobs = list(scenario_from_durations(4, 4).jobs.values())
    base_deltas = _preplanned_deltas(base, jobs, trigger_delta=0)
    follow_up_deltas = _preplanned_deltas(follow_up, jobs, trigger_delta=1)
    assert len(base_deltas) == len(base.choices)
    assert all(abs(delta) <= 2 for delta in base_deltas)
    assert len(follow_up_deltas) == len(follow_up.choices)
    assert -1 not in follow_up_deltas

    duplicate = FollowUpEdge("target", 0.75, 0)
    definition = DecisionDefinition(
        id="unit",
        title="Unit",
        description="Unit",
        choices=(
            CatalogChoice("Choice", (duplicate,), 1, "adjust"),
        ),
        unavoidable_follow_up_edges=(
            FollowUpEdge("target", 1.0, -5),
        ),
    )
    follow_ups = _choice_follow_ups(definition, definition.choices[0])
    assert follow_ups == (DecisionFollowUp("target", 1.0, 1),)
    assert _has_follow_up(definition)
    assert not _has_follow_up(
        replace(definition, choices=(replace(definition.choices[0], follow_up_edges=()),), unavoidable_follow_up_edges=())
    )

    primary = jobs[0]
    shared = next(item for item in BASE_DEFINITIONS if item.shared_across_routes)
    assert _event_identity(2, 1, shared, primary)[0] == "shared-day"
    assert _event_identity(2, 1, base, primary)[0] == "route-specific"
    assert _event_identity(
        3,
        2,
        follow_up,
        primary,
        source_day=1,
        source_definition_id="source",
    ) == (
        "follow-up",
        f"FOLLOW-D001-source-{primary.id}-{follow_up.id}",
    )
    assert _source_choice_label("missing", "choice-1") == ""
    assert _source_choice_label(base.id, "bad") == ""
    assert _source_choice_label(base.id, "choice-999") == ""
    assert _simplify_language("Subjobs and a subjob") == "Jobs and a job"
    assert _format_job_list([]) == ""
    assert _format_job_list(["A"]) == "A"
    assert _format_job_list(["A", "B"]) == "A and B"
    assert _format_job_list(["A", "B", "C"]) == "A, B, and C"


def test_follow_up_rolls_are_deterministic_and_clamp_probability_bounds() -> None:
    state = initialize_state(scenario_from_durations(3))
    choice = make_choice("choice-1")
    card = make_card(choice)
    assert follow_up_occurs(state, card, choice, "later", -100) is False
    assert follow_up_occurs(state, card, choice, "later", 100) is True
    assert (
        follow_up_occurs(state, card, choice, "later", 0.5)
        == follow_up_occurs(state, card, choice, "later", 0.5)
    )
    assert _preplanned_follow_up_occurs(
        state.seed,
        card,
        choice,
        "later",
        -100,
        0,
    ) is False
    assert _preplanned_follow_up_occurs(
        state.seed,
        card,
        choice,
        "later",
        100,
        0,
    ) is True

    state.jobs["JOB-01"].status = JobStatus.COMPLETE
    assert _completed_mask(state) == 1


class _Output(StringIO):
    def __init__(self, *, interactive: bool = False) -> None:
        super().__init__()
        self.interactive = interactive

    def isatty(self) -> bool:
        return self.interactive


def test_initialization_status_reports_success_but_not_false_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _Output()
    monkeypatch.setattr(server_module.sys, "stdout", output)
    with _initialization_status():
        pass
    assert output.getvalue() == "Initializing...\n✓ Initialized\n"

    failed_output = _Output()
    monkeypatch.setattr(server_module.sys, "stdout", failed_output)
    with pytest.raises(RuntimeError, match="failed"):
        with _initialization_status():
            raise RuntimeError("failed")
    assert failed_output.getvalue() == "Initializing...\n"


def test_interactive_initialization_status_starts_and_joins_animation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _Output(interactive=True)
    events: list[str] = []

    class FakeThread:
        def __init__(self, *, target, daemon):
            assert callable(target)
            assert daemon is True

        def start(self) -> None:
            events.append("start")

        def join(self) -> None:
            events.append("join")

    monkeypatch.setattr(server_module.sys, "stdout", output)
    monkeypatch.setattr(server_module.threading, "Thread", FakeThread)
    with _initialization_status():
        pass

    assert events == ["start", "join"]
    assert output.getvalue().endswith("\r               \r✓ Initialized\n")


@pytest.mark.parametrize("interrupt", [False, True])
def test_run_ui_server_owns_and_closes_its_server(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    interrupt: bool,
) -> None:
    created: list[object] = []

    class FakeServer:
        def __init__(self, address, handler):
            self.address = address
            self.handler = handler
            self.closed = False
            created.append(self)

        def serve_forever(self) -> None:
            if interrupt:
                raise KeyboardInterrupt

        def server_close(self) -> None:
            self.closed = True

    fake_store = SimpleNamespace(dev_mode=True)
    monkeypatch.setattr(server_module, "SessionStore", lambda **kwargs: fake_store)
    monkeypatch.setattr(server_module, "ThreadingHTTPServer", FakeServer)

    server_module.run_ui_server(
        seed=12,
        host="localhost",
        port=9999,
        dev_mode=True,
    )

    assert len(created) == 1
    server = created[0]
    assert server.address == ("localhost", 9999)
    assert server.handler.session_store is fake_store
    assert server.closed is True
    output = capsys.readouterr().out
    assert "ECHO Adventure UI running at http://localhost:9999" in output
    assert ("ECHO Adventure stopped." in output) is interrupt


def test_request_handler_defensive_paths_and_seed_conversion() -> None:
    from .test_session_payloads_server import HandlerHarness, dispatch, handler_type

    class Store:
        dev_mode = False

        def advance_payload(self):
            raise RuntimeError("boom")

    Handler = handler_type(Store())
    empty = Handler("POST", "/api/new")
    assert empty._read_json() == {}
    assert empty.log_message("ignored") is None

    unknown_post = Handler("POST", "/missing", {})
    dispatch(unknown_post)
    assert unknown_post.response_status == 404

    failed = Handler("POST", "/api/advance", {})
    dispatch(failed)
    assert failed.response_status == 500
    assert failed.body_json() == {"error": "Server error: boom"}

    class IntegerLike:
        def __int__(self) -> int:
            return 17

    class BadInteger:
        def __int__(self) -> int:
            raise OverflowError

    assert _parse_optional_seed(IntegerLike()) == 17
    with pytest.raises(ValueError, match="Seed must be an integer"):
        _parse_optional_seed(BadInteger())


def test_process_memory_probes_cover_linux_unknown_and_peak_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_module.sys, "platform", "linux")
    monkeypatch.setattr(
        builtins,
        "open",
        lambda *args, **kwargs: StringIO("100 7 0 0"),
    )
    monkeypatch.setattr(session_module.os, "sysconf", lambda name: 4096)
    assert session_module._process_current_rss_bytes() == 7 * 4096

    monkeypatch.setattr(
        builtins,
        "open",
        lambda *args, **kwargs: StringIO("malformed"),
    )
    assert session_module._process_current_rss_bytes() is None

    monkeypatch.setattr(session_module.sys, "platform", "other")
    assert session_module._process_current_rss_bytes() is None

    fake_resource = SimpleNamespace(
        RUSAGE_SELF=0,
        getrusage=lambda who: SimpleNamespace(ru_maxrss=123),
    )
    monkeypatch.setitem(sys.modules, "resource", fake_resource)
    monkeypatch.setattr(session_module.sys, "platform", "linux")
    assert session_module._process_peak_rss_bytes() == 123 * 1024
    monkeypatch.setattr(session_module.sys, "platform", "darwin")
    assert session_module._process_peak_rss_bytes() == 123


def _fast_session(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dev_mode: bool = True,
) -> session_module.GameSession:
    monkeypatch.setattr(
        session_module,
        "GameConfig",
        lambda seed=None: small_config(seed=seed),
    )
    return session_module.GameSession(seed=909, dev_mode=dev_mode)


@pytest.mark.parametrize("target", [True, False, 2.5, "2", [], {}])
def test_session_skip_target_rejects_non_integer_values(
    monkeypatch: pytest.MonkeyPatch,
    target: object,
) -> None:
    session = _fast_session(monkeypatch)
    with pytest.raises(ValueError, match="integer or null"):
        session._validate_skip_target(target)


def test_session_skip_target_and_reachability_respect_run_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _fast_session(monkeypatch)
    assert session._validate_skip_target(None) is None
    assert session._validate_skip_target(2) == 2
    with pytest.raises(ValueError, match="later than"):
        session._validate_skip_target(1)

    assert session.reachable_days_by_strategy()
    session.player_in_overtime = True
    assert session.reachable_days_by_strategy() == {}
    session.player_in_overtime = False
    session.player_final_assembly_started = True
    assert session.reachable_days_by_strategy() == {}

    standard = _fast_session(monkeypatch, dev_mode=False)
    assert standard.reachable_days_by_strategy() == {}


def test_session_ready_to_advance_covers_each_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _fast_session(monkeypatch)
    assert session.ready_to_advance() is False
    session.questions_answered_today = session.decision_total_today
    session.pending_player_transition = DecisionWebTransition("next", True)
    assert session.ready_to_advance() is True

    session.player_in_overtime = True
    session.pending_player_transition = None
    session.overtime_ready_to_advance = False
    assert session.ready_to_advance() is False
    session.overtime_ready_to_advance = True
    assert session.ready_to_advance() is True

    session.player_final_assembly_started = True
    session.player_final_assembly_locked = False
    assert session.ready_to_advance() is False
    session.player_final_assembly_locked = True
    assert session.ready_to_advance() is True


def test_session_internal_guards_fail_loudly_on_impossible_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _fast_session(monkeypatch)
    with pytest.raises(RuntimeError, match="slot mismatch"):
        session._apply_echo_choice(2)

    session.pending_echo_transition = DecisionWebTransition("next", True)
    with pytest.raises(RuntimeError, match="no unapplied decision"):
        session._apply_echo_choice(1)

    session.pending_echo_transition = None
    session.echo_choices_applied_today = 0
    session.decision_total_today = 1
    with pytest.raises(RuntimeError, match="not applied every expected"):
        session._advance_echo_day()

    session.echo_choices_applied_today = 1
    with pytest.raises(RuntimeError, match="no daily transition"):
        session._advance_echo_day()

    monkeypatch.setattr(
        session_module,
        "generate_daily_decision_cards",
        lambda state, config: [],
    )
    with pytest.raises(RuntimeError, match="produced no questions"):
        session._start_overtime_day()

    session.automated_state.final_item_completed = True
    session.automated_state.completion_day = None
    with pytest.raises(RuntimeError, match="outside its player endgame"):
        session._start_final_assembly()

    session.automated_state.final_item_completed = False
    session.echo_node_id = None
    session.pending_echo_transition = None
    with pytest.raises(RuntimeError, match="ended before completing"):
        session._finish_automated()


def test_session_store_delegates_advance_and_protects_skip() -> None:
    calls: list[object] = []

    class FakeSession:
        def advance_day(self) -> None:
            calls.append("advance")

        def skip(self, strategy, target_day) -> None:
            calls.append(("skip", strategy, target_day))

        def state_payload(self) -> dict[str, object]:
            return {"calls": list(calls)}

    store = session_module.SessionStore.__new__(session_module.SessionStore)
    store.lock = threading.RLock()
    store.session = FakeSession()
    store.dev_mode = False
    assert store.advance_payload() == {"calls": ["advance"]}
    with pytest.raises(ValueError, match="Developer mode is not enabled"):
        store.skip_payload("echo")

    store.dev_mode = True
    assert store.skip_payload("last", 3) == {
        "calls": ["advance", ("skip", "last", 3)],
    }
