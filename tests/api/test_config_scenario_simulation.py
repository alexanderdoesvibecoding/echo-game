from __future__ import annotations

import random
from unittest.mock import patch

import pytest

from echo_adventure.config import GameConfig, resolve_seed
from echo_adventure.enums import JobStatus
from echo_adventure.metrics import calculate_snapshot
from echo_adventure.scenario_generator import _weighted_duration, generate_scenario, validate_scenario
from echo_adventure.scoring import public_score, public_score_delta
from echo_adventure.simulation import advance_day, complete_job, initialize_state

from .helpers import scenario_from_durations, small_config


def test_config_defaults_describe_the_twenty_job_game() -> None:
    config = GameConfig(seed=7)

    assert config.job_count == 20
    assert (config.min_job_duration_days, config.max_job_duration_days) == (5, 15)
    assert (config.min_decisions_per_day, config.max_decisions_per_day) == (2, 3)
    assert config.max_campaign_day == 25
    assert config.day_cycle_duration_ms == 6000


def test_calendar_labels_are_one_based_and_cross_month_boundaries() -> None:
    config = small_config(start_date="2026-07-31")

    assert config.date_label_for_day(0) == "July 31"
    assert config.date_label_for_day(1) == "July 31"
    assert config.date_label_for_day(2) == "August 1"


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"job_count": 0}, "job_count must be at least 1"),
        ({"min_job_duration_days": 0}, "min_job_duration_days must be at least 1"),
        ({"max_job_duration_days": 0}, "max_job_duration_days must be at least 1"),
        ({"min_decisions_per_day": 0}, "min_decisions_per_day must be at least 1"),
        ({"max_decisions_per_day": 0}, "max_decisions_per_day must be at least 1"),
        ({"max_campaign_day": 0}, "max_campaign_day must be at least 1"),
        ({"day_cycle_duration_ms": 0}, "day_cycle_duration_ms must be at least 1"),
        (
            {"daily_summary_counter_duration_ms": 0},
            "daily_summary_counter_duration_ms must be at least 1",
        ),
        ({"min_job_duration_days": 5, "max_job_duration_days": 4}, "Minimum job duration"),
        ({"min_decisions_per_day": 3, "max_decisions_per_day": 2}, "Minimum daily decisions"),
        ({"max_job_duration_days": 9, "max_campaign_day": 8}, "Campaign horizon"),
        ({"start_date": "July 1"}, "YYYY-MM-DD"),
    ],
)
def test_config_rejects_invalid_values(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        small_config(**overrides)


def test_resolve_seed_preserves_explicit_values_and_uses_system_random() -> None:
    assert resolve_seed(0) == 0
    assert resolve_seed(-15) == -15

    with patch("echo_adventure.config.random.SystemRandom") as system_random:
        system_random.return_value.randint.return_value = 456789
        assert resolve_seed(None) == 456789
        system_random.return_value.randint.assert_called_once_with(100_000, 999_999_999)


def test_public_score_is_bounded_monotonic_symmetric_and_reports_exact_deltas() -> None:
    raw_scores = [-1_000_000, -10, -2, 0, 2, 10, 1_000_000]
    scores = [public_score(raw_score) for raw_score in raw_scores]

    assert scores == sorted(scores)
    assert scores[0] == 0.0
    assert scores[-1] == 100.0
    assert public_score(-10) == 25.0
    assert public_score(0) == 50.0
    assert public_score(10) == 75.0
    assert public_score(-2) + public_score(2) == 100.0
    assert public_score_delta(0, 2) == 8.33
    assert public_score_delta(2, 0) == -8.33
    assert public_score_delta(-2, 2) == 16.67


def test_scenario_generation_is_deterministic_and_within_bounds() -> None:
    config = small_config(job_count=8, seed=2026)

    first = generate_scenario(config)
    second = generate_scenario(config)

    assert first == second
    assert list(first.jobs) == [f"JOB-{index:02d}" for index in range(1, 9)]
    assert all(job.name == f"Job {index}" for index, job in enumerate(first.jobs.values(), start=1))
    assert all(config.min_job_duration_days <= job.remaining_days <= config.max_job_duration_days for job in first.jobs.values())


def test_weighted_generation_favors_shorter_values_without_excluding_the_range() -> None:
    config = small_config(min_job_duration_days=2, max_job_duration_days=6, max_campaign_day=8)
    rng = random.Random(12)
    values = [_weighted_duration(rng, config) for _ in range(5_000)]

    assert set(values) == {2, 3, 4, 5, 6}
    assert sum(values) / len(values) < 4


def test_scenario_validation_rejects_wrong_count_and_out_of_range_duration() -> None:
    config = small_config(job_count=2)
    wrong_count = scenario_from_durations(2)
    with pytest.raises(ValueError, match="exactly 2 jobs"):
        validate_scenario(wrong_count, config)

    wrong_duration = scenario_from_durations(2, 7)
    with pytest.raises(ValueError, match="outside the configured range"):
        validate_scenario(wrong_duration, config)


def test_initialization_deep_copies_jobs_and_builds_initial_metrics() -> None:
    scenario = scenario_from_durations(1, 2, 3)

    state = initialize_state(scenario)

    assert state.jobs == scenario.jobs
    assert state.jobs is not scenario.jobs
    state.jobs["JOB-01"].remaining_days = 99
    assert scenario.jobs["JOB-01"].remaining_days == 1
    snapshot = calculate_snapshot(state)
    assert snapshot.jobs_remaining == 3
    assert snapshot.total_remaining_days == 104
    assert snapshot.projected_completion_day == 99


def test_job_completion_property_and_incomplete_job_filter_follow_status() -> None:
    state = initialize_state(scenario_from_durations(1, 2))

    assert state.jobs["JOB-01"].is_complete is False
    assert [job.id for job in state.incomplete_jobs()] == ["JOB-01", "JOB-02"]

    complete_job(state, "JOB-01")

    assert state.jobs["JOB-01"].is_complete is True
    assert [job.id for job in state.incomplete_jobs()] == ["JOB-02"]


def test_advance_day_ticks_every_unfinished_job_once_and_records_summary() -> None:
    state = initialize_state(scenario_from_durations(1, 2, 3))

    result = advance_day(state)

    assert result.day == 1
    assert result.completed_job_ids == ["JOB-01"]
    assert result.notes == ["Job 1 completed."]
    assert [job.remaining_days for job in state.jobs.values()] == [0, 1, 2]
    assert state.current_day == 2
    assert result.start_snapshot.total_remaining_days == 6
    assert result.end_snapshot.total_remaining_days == 3
    assert result.end_snapshot.projected_completion_day == 3
    assert result.end_snapshot == calculate_snapshot(state)
    assert state.cumulative_unfinished_job_days == 6

    outlier_state = initialize_state(scenario_from_durations(4, 7, 16))
    advance_day(outlier_state)
    assert [job.remaining_days for job in outlier_state.jobs.values()] == [3, 6, 15]


def test_complete_job_is_idempotent_and_final_job_advances_one_day_at_a_time() -> None:
    state = initialize_state(scenario_from_durations(1, 9))

    complete_job(state, "JOB-01")
    complete_job(state, "JOB-01")
    assert state.daily_notes == ["Job 1 completed."]
    assert state.jobs["JOB-01"].completed_day == 1

    for expected_remaining in range(8, 0, -1):
        advance_day(state)
        assert state.final_item_completed is False
        assert state.jobs["JOB-02"].remaining_days == expected_remaining
    advance_day(state)
    assert state.final_item_completed is True
    assert state.completion_day == 9
    assert state.current_day == 9


def test_snapshot_projection_uses_the_longest_unfinished_duration() -> None:
    state = initialize_state(scenario_from_durations(2, 5))
    state.current_day = 4

    snapshot = calculate_snapshot(state)

    assert snapshot.projected_completion_day == 8
    assert snapshot.total_remaining_days == 7
    state.jobs["JOB-01"].status = JobStatus.COMPLETE
    state.jobs["JOB-01"].remaining_days = 0
    final_job_snapshot = calculate_snapshot(state)
    assert final_job_snapshot.jobs_remaining == 1
    assert final_job_snapshot.projected_completion_day == 8


def test_completed_snapshot_keeps_the_original_completion_day() -> None:
    state = initialize_state(scenario_from_durations(1))
    complete_job(state, "JOB-01")
    state.current_day = 9

    snapshot = calculate_snapshot(state)

    assert snapshot.jobs_remaining == 0
    assert snapshot.total_remaining_days == 0
    assert snapshot.projected_completion_day == 1
    assert snapshot.final_item_completed is True
    assert state.completion_day == 1
