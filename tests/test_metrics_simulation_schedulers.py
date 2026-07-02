from __future__ import annotations

import unittest

from echo_adventure.enums import EventType, JobStatus, TargetType, WorkCenterStatus
from echo_adventure.metrics import (
    calculate_final_score,
    calculate_schedule_risk,
    calculate_snapshot,
    day_shift,
    recalculate_critical_path,
    score_decision_path_differentiator,
    shop_utilization,
    update_state_metrics,
)
from echo_adventure.models import Event
from echo_adventure.schedulers.automated import AutomatedScheduler
from echo_adventure.schedulers.base import downstream_count
from echo_adventure.schedulers.manual import ManualScheduler
from echo_adventure.simulation import (
    _age_queues,
    _known_events,
    _start_available_jobs,
    advance_day,
    advance_shift,
    complete_job,
    initialize_state,
    prepare_day,
)

from .helpers import make_card, make_event, make_scenario, make_state


class RecordingScheduler:
    name = "recording"

    def __init__(self) -> None:
        self.day_events: list[Event] = []
        self.shift_calls = 0

    def plan_day(self, state, known_events):
        self.day_events = list(known_events)

    def plan_shift(self, state):
        self.shift_calls += 1


class MetricsTests(unittest.TestCase):
    def test_update_state_metrics_refreshes_job_piece_and_shop_statuses(self):
        state = make_state(update_metrics=False)

        update_state_metrics(state)

        self.assertEqual(state.jobs["JOB-01-001"].status, JobStatus.READY)
        self.assertEqual(state.jobs["JOB-01-002"].status, JobStatus.NOT_READY)
        self.assertEqual(state.pieces["PIECE-01"].status.value, "Not Started")
        self.assertEqual(state.shops["SHOP-A"].idle_time, 2)

    def test_calculate_snapshot_counts_late_behind_and_utilization(self):
        state = make_state()
        state.current_shift = 8
        state.jobs["JOB-01-001"].status = JobStatus.COMPLETE
        state.jobs["JOB-01-001"].completed_shift = 6
        state.completed_jobs.add("JOB-01-001")
        state.busy_shift_count = 3
        state.available_shift_count = 4
        update_state_metrics(state)

        snapshot = calculate_snapshot(state)

        self.assertEqual(snapshot.jobs_completed, 1)
        self.assertGreaterEqual(snapshot.jobs_behind_schedule, 1)
        self.assertEqual(snapshot.jobs_late, 1)
        self.assertEqual(snapshot.utilization, 0.75)
        self.assertFalse(snapshot.deadline_met)

    def test_schedule_risk_is_bounded_and_capped_after_completion(self):
        state = make_state()
        state.current_shift = 11
        state.active_events = ["EVT-1", "EVT-2"]
        for job in state.jobs.values():
            job.block_reason = "blocked"
            job.critical_path = True

        risk = calculate_schedule_risk(state, projected_completion_shift=99)
        self.assertGreaterEqual(risk, 0.0)
        self.assertLessEqual(risk, 100.0)

        state.final_item_completed = True
        self.assertLessEqual(calculate_schedule_risk(state, projected_completion_shift=99), 8.0)

    def test_critical_path_marks_longest_remaining_chain(self):
        state = make_state()

        projected = recalculate_critical_path(state)
        critical_ids = {job.id for job in state.jobs.values() if job.critical_path}

        self.assertGreater(projected, state.current_shift)
        self.assertIn("JOB-02-001", critical_ids)
        self.assertEqual(downstream_count(state, state.jobs["JOB-01-001"]), 1)

    def test_final_score_includes_deterministic_decision_path_component(self):
        state = make_state()
        state.decision_path = ["CARD-1:A", "CARD-2:B"]
        state.decision_path_signature = "12345678abcdef00"
        state.decision_path_score_delta = 1.5

        differentiator = score_decision_path_differentiator(state)
        score = calculate_final_score(state)

        self.assertEqual(differentiator, round(1.5 + (int("12345678", 16) % 2500) / 100.0, 2))
        self.assertIsInstance(score, float)

    def test_day_shift_formats_boundaries(self):
        self.assertEqual(day_shift(0, 3), "Day 1, Shift 1")
        self.assertEqual(day_shift(1, 3), "Day 1, Shift 1")
        self.assertEqual(day_shift(4, 3), "Day 2, Shift 1")

    def test_shop_utilization_handles_empty_shop(self):
        state = make_state()
        state.shops["EMPTY"] = state.shops["SHOP-A"].__class__(
            id="EMPTY",
            name="Empty",
            capabilities=[],
            workcenter_ids=[],
        )

        self.assertEqual(shop_utilization(state, "EMPTY"), 0.0)


class SimulationTests(unittest.TestCase):
    def test_initialize_state_deep_copies_scenario_and_unlocks_roots(self):
        source_state = make_state()
        source_state.decision_cards["ROOT"] = source_state.decision_cards.get("ROOT") or make_card("ROOT")
        source_state.campaign_decision_graph.root_card_ids = ["ROOT"]
        scenario = make_scenario(source_state)

        state = initialize_state(scenario, shifts_per_day=3)
        scenario.jobs["JOB-01-001"].priority = 1

        self.assertNotEqual(state.jobs["JOB-01-001"].priority, scenario.jobs["JOB-01-001"].priority)
        self.assertEqual(state.unlocked_decision_card_ids, {"ROOT"})

    def test_prepare_day_passes_only_known_events_to_scheduler(self):
        state = make_state()
        warned = make_event("EVT-W", start_shift=4)
        active = make_event("EVT-A", start_shift=1)
        hidden = make_event("EVT-H", start_shift=8)
        state.event_timeline = [warned, active, hidden]
        state.known_warnings = [warned.id]
        state.active_events = [active.id]
        scheduler = RecordingScheduler()

        snapshot = prepare_day(state, scheduler)

        self.assertEqual(snapshot.shift, 0)
        self.assertEqual({event.id for event in scheduler.day_events}, {"EVT-W", "EVT-A"})

    def test_advance_shift_applies_warning_then_start_then_resolution(self):
        state = make_state()
        event = make_event(
            "EVT-1",
            event_type=EventType.MISSING_MATERIAL,
            target_type=TargetType.JOB,
            target_id="JOB-01-001",
            start_shift=2,
            duration_shifts=1,
            has_advance_warning=True,
            warning_shift=1,
        )
        state.event_timeline = [event]
        scheduler = RecordingScheduler()

        advance_shift(state, scheduler)
        self.assertIn(event.id, state.known_warnings)
        self.assertIn("Warning received", state.daily_notes[-1])

        advance_shift(state, scheduler)
        self.assertIn(event.id, state.active_events)
        self.assertEqual(state.jobs["JOB-01-001"].status, JobStatus.BLOCKED)

        advance_shift(state, scheduler)
        self.assertTrue(event.resolved)
        self.assertNotIn(event.id, state.active_events)
        self.assertIsNone(state.jobs["JOB-01-001"].block_reason)

    def test_start_available_jobs_locks_duration_with_efficiency_and_route_penalty(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]
        state.assign_job(job.id, "WC-B1")
        state.workcenters["WC-B1"].queue = [job.id]

        _start_available_jobs(state)

        self.assertEqual(job.status, JobStatus.RUNNING)
        self.assertEqual(job.assigned_workcenter_id, "WC-B1")
        self.assertEqual(job.remaining_duration_shifts, 5)
        self.assertTrue(job.started_once)

    def test_age_queues_increments_each_queued_job_once(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]
        job.status = JobStatus.QUEUED
        state.workcenters["WC-A1"].queue = [job.id, job.id]

        _age_queues(state)

        self.assertEqual(job.queue_time, 1)

    def test_complete_job_requires_preplanned_rework_once_then_completes(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]
        job.status = JobStatus.RUNNING
        job.planned_completion_rework_shifts = 2
        state.workcenters["WC-A1"].current_job_id = job.id
        state.workcenters["WC-A1"].status = WorkCenterStatus.BUSY

        complete_job(state, job.id)

        self.assertEqual(job.status, JobStatus.REWORK_REQUIRED)
        self.assertEqual(job.remaining_duration_shifts, 2)
        self.assertTrue(job.completion_rework_consumed)
        self.assertNotIn(job.id, state.completed_jobs)

        complete_job(state, job.id)

        self.assertEqual(job.status, JobStatus.COMPLETE)
        self.assertIn(job.id, state.completed_jobs)

    def test_complete_job_marks_project_complete_when_final_subjob_finishes(self):
        state = make_state()
        for job_id, job in state.jobs.items():
            if job_id == "JOB-02-002":
                continue
            job.status = JobStatus.COMPLETE
            job.completed_shift = 2
            state.completed_jobs.add(job_id)
        last = state.jobs["JOB-02-002"]
        last.status = JobStatus.RUNNING
        state.current_shift = 5

        complete_job(state, last.id)

        self.assertTrue(state.final_item_completed)
        self.assertEqual(state.completion_shift, 5)
        self.assertIn("All jobs completed", state.daily_notes[-1])

    def test_advance_day_stops_at_deadline(self):
        state = make_state()
        state.current_shift = 11
        scheduler = RecordingScheduler()

        result = advance_day(state, scheduler)

        self.assertEqual(state.current_shift, 12)
        self.assertEqual(result.end_snapshot.shift, 12)
        self.assertEqual(scheduler.shift_calls, 1)

    def test_known_events_returns_active_and_warned_events(self):
        state = make_state()
        active = make_event("EVT-A")
        warned = make_event("EVT-W")
        state.event_timeline = [active, warned, make_event("EVT-H")]
        state.active_events = [active.id]
        state.known_warnings = [warned.id]

        self.assertEqual({event.id for event in _known_events(state)}, {"EVT-A", "EVT-W"})


class SchedulerTests(unittest.TestCase):
    def test_manual_scheduler_assigns_ready_jobs_by_priority_and_due_date(self):
        state = make_state()

        ManualScheduler().plan_shift(state)

        self.assertEqual(state.jobs["JOB-02-001"].status, JobStatus.QUEUED)
        self.assertEqual(state.jobs["JOB-02-001"].assigned_workcenter_id, "WC-B1")
        self.assertEqual(state.jobs["JOB-01-001"].assigned_workcenter_id, "WC-A1")

    def test_manual_scheduler_avoids_disrupted_existing_assignment(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]
        job.assigned_workcenter_id = "WC-A1"
        state.workcenters["WC-A1"].status = WorkCenterStatus.DOWN

        ManualScheduler().plan_shift(state)

        self.assertEqual(job.assigned_workcenter_id, "WC-A1")
        self.assertNotIn(job.id, state.workcenters["WC-A1"].queue)

    def test_automated_scheduler_reacts_to_known_material_and_weather_events(self):
        state = make_state()
        delayed = make_event(
            "EVT-MAT",
            event_type=EventType.DELAYED_MATERIAL,
            target_type=TargetType.JOB,
            target_id="JOB-01-001",
        )
        weather = make_event(
            "EVT-WX",
            event_type=EventType.WEATHER,
            target_type=TargetType.SHOP,
            target_id="SHOP-A",
        )
        state.jobs["JOB-01-001"].critical_path = True
        before_target = state.jobs["JOB-01-001"].priority
        before_dependent = state.jobs["JOB-01-002"].priority

        AutomatedScheduler()._respond_to_known_events(state, [delayed, weather])

        self.assertGreater(state.jobs["JOB-01-001"].priority, before_target)
        self.assertGreater(state.jobs["JOB-01-002"].priority, before_dependent)

    def test_automated_scheduler_cleans_reorders_and_rebalances_queues(self):
        state = make_state()
        scheduler = AutomatedScheduler()
        urgent = state.jobs["JOB-02-001"]
        routine = state.jobs["JOB-01-001"]
        blocked = state.jobs["JOB-01-002"]
        urgent.status = JobStatus.QUEUED
        routine.status = JobStatus.QUEUED
        blocked.status = JobStatus.QUEUED
        blocked.block_reason = "blocked"
        urgent.assigned_workcenter_id = "WC-B1"
        routine.assigned_workcenter_id = "WC-B1"
        state.workcenters["WC-B1"].queue = [blocked.id, routine.id, urgent.id]

        scheduler._clean_and_reorder_queues(state)

        self.assertNotIn(blocked.id, state.workcenters["WC-B1"].queue)
        self.assertEqual(state.workcenters["WC-B1"].queue[0], urgent.id)
        self.assertGreater(state.reschedule_count, 0)

        state.workcenters["WC-A1"].queue = []
        state.workcenters["WC-A1"].status = WorkCenterStatus.IDLE
        urgent.queue_time = 3
        scheduler._rebalance_queued_jobs(state)

        self.assertEqual(urgent.assigned_workcenter_id, "WC-A1")

    def test_automated_scheduler_preemption_requires_large_gain(self):
        state = make_state()
        scheduler = AutomatedScheduler()
        current = state.jobs["JOB-01-001"]
        incoming = state.jobs["JOB-02-001"]
        current.status = JobStatus.RUNNING
        current.critical_path = False
        current.priority = 60
        current.remaining_duration_shifts = 8
        incoming.priority = 98
        incoming.critical_path = True
        incoming.remaining_duration_shifts = 2
        state.workcenters["WC-A1"].current_job_id = current.id

        self.assertTrue(scheduler._should_preempt(state, incoming, state.workcenters["WC-A1"]))

        incoming.critical_path = False
        incoming.priority = 70
        self.assertFalse(scheduler._should_preempt(state, incoming, state.workcenters["WC-A1"]))


if __name__ == "__main__":
    unittest.main()
