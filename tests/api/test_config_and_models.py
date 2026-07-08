from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from echo_adventure.config import (
    BalancePreset,
    CapacityProfile,
    DecisionProfile,
    DisruptionProfile,
    EchoProfile,
    GameConfig,
    WorkloadProfile,
    _validate_config,
    resolve_seed,
)
from echo_adventure.enums import JobStatus, WorkCenterStatus

from .helpers import make_state


class ConfigTests(unittest.TestCase):
    def test_balance_preset_flattens_profile_groups(self):
        preset = BalancePreset(
            workload=WorkloadProfile(total_days=2, piece_count=3, min_jobs_per_piece=1, max_jobs_per_piece=2),
            capacity=CapacityProfile(shop_count=4, min_workcenters_per_shop=1, max_workcenters_per_shop=2),
            disruptions=DisruptionProfile(min_base_events=0, max_base_events=1),
            decisions=DecisionProfile(min_decisions_per_day=1, max_decisions_per_day=2),
            echo=EchoProfile(echo_choice_lookahead_days=1),
        )

        flattened = preset.to_config_kwargs()

        self.assertEqual(flattened["total_days"], 2)
        self.assertEqual(flattened["shop_count"], 4)
        self.assertEqual(flattened["max_base_events"], 1)
        self.assertEqual(flattened["echo_choice_lookahead_days"], 1)

    def test_for_preset_resolves_demo_and_rejects_unknown_names(self):
        config = GameConfig.for_preset("demo", seed=77)

        self.assertEqual(config.seed, 77)
        self.assertEqual(config.total_days, 8)
        self.assertEqual(config.deadline_shift, 24)
        self.assertEqual(config.date_range_label, "December 23 to December 30")
        self.assertEqual(config.deadline_date_label, "December 30")
        self.assertEqual(config.date_label_for_shift(4), "December 24")
        self.assertEqual(config.work_period_label_for_shift(4), "December 24, Morning")
        with self.assertRaisesRegex(ValueError, "Unknown game preset"):
            GameConfig.for_preset("missing")

    def test_resolve_seed_uses_provided_seed_or_system_random(self):
        self.assertEqual(resolve_seed(123), 123)

        with patch("echo_adventure.config.random.SystemRandom") as system_random:
            system_random.return_value.randint.return_value = 456789

            self.assertEqual(resolve_seed(None), 456789)

        system_random.return_value.randint.assert_called_once_with(100_000, 999_999_999)

    def test_validate_config_rejects_invalid_values(self):
        base = GameConfig.for_preset("normal", seed=1)
        cases = [
            (replace(base, total_days=0), "total_days must be at least 1"),
            (replace(base, day_cycle_duration_ms=0), "day_cycle_duration_ms must be at least 1"),
            (replace(base, min_base_events=-1), "min_base_events cannot be negative"),
            (replace(base, min_jobs_per_piece=4, max_jobs_per_piece=3), "minimum subjobs per job"),
            (replace(base, transport_delay_probability=1.01), "transport_delay_probability must be between"),
            (replace(base, setup_time_choices=()), "setup_time_choices cannot be empty"),
            (replace(base, setup_time_choices=(-1,)), "setup_time_choices cannot contain negative"),
            (replace(base, end_date="2026-12-22"), "end_date must be on or after start_date"),
            (replace(base, end_date="2026-12-31"), "total_days must match"),
            (replace(base, work_period_labels=()), "work_period_labels cannot be empty"),
            (
                replace(
                    base,
                    completion_rework_probability=0.5,
                    min_completion_rework_shifts=0,
                    max_completion_rework_shifts=0,
                ),
                "completion rework shifts must be positive",
            ),
        ]

        for config, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    _validate_config("unit", config)


class SimulationStateModelTests(unittest.TestCase):
    def test_job_properties_and_current_day_boundaries(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]

        self.assertEqual(job.planned_duration, 3)
        self.assertFalse(job.is_complete)
        self.assertFalse(job.is_blocked)

        job.status = JobStatus.COMPLETE
        self.assertTrue(job.is_complete)
        job.status = JobStatus.READY
        job.block_reason = "blocked for test"
        self.assertTrue(job.is_blocked)

        self.assertEqual(state.current_day, 1)
        state.current_shift = 3
        self.assertEqual(state.current_day, 2)
        state.current_shift = 99
        self.assertEqual(state.current_day, 4)

    def test_dependency_ready_blocked_and_critical_path_helpers(self):
        state = make_state()

        ready_ids = {job.id for job in state.get_ready_jobs()}
        self.assertEqual(ready_ids, {"JOB-01-001", "JOB-02-001"})
        self.assertFalse(state.is_dependency_complete("JOB-01-002"))

        state.jobs["JOB-01-001"].status = JobStatus.COMPLETE
        state.completed_jobs.add("JOB-01-001")
        self.assertTrue(state.is_dependency_complete("JOB-01-002"))
        ready_ids = {job.id for job in state.get_ready_jobs()}
        self.assertIn("JOB-01-002", ready_ids)

        state.jobs["JOB-02-001"].block_reason = "blocked"
        blocked = state.get_blocked_jobs()
        self.assertEqual([job.id for job in blocked], ["JOB-02-001"])

        critical_ids = [job.id for job in state.get_critical_path_jobs()]
        self.assertTrue(critical_ids)
        self.assertLessEqual(
            state.jobs[critical_ids[0]].due_shift,
            state.jobs[critical_ids[-1]].due_shift,
        )

    def test_workcenter_and_bottleneck_helpers_filter_and_sort(self):
        state = make_state()
        state.workcenters["WC-A1"].current_job_id = "JOB-01-001"
        state.workcenters["WC-A1"].status = WorkCenterStatus.BUSY
        state.workcenters["WC-B1"].status = WorkCenterStatus.DOWN
        state.shops["SHOP-A"].queued_job_ids = ["A"]
        state.shops["SHOP-B"].queued_job_ids = ["B"]
        state.shops["SHOP-B"].blocked_job_ids = ["C"]
        state.shops["SHOP-A"].risk_score = 80
        state.shops["SHOP-B"].risk_score = 5

        cutting = state.get_available_workcenters("cutting")
        self.assertEqual(cutting, [])
        all_available = {wc.id for wc in state.get_available_workcenters()}
        self.assertEqual(all_available, {"WC-A2", "WC-B2"})
        self.assertEqual(state.get_bottleneck_shops(limit=1)[0].id, "SHOP-B")

    def test_remove_and_clear_queue_helpers(self):
        state = make_state()
        state.workcenters["WC-A1"].queue = ["JOB-01-001", "JOB-02-001", "JOB-01-001"]
        state.shops["SHOP-A"].queued_job_ids = ["JOB-01-001", "JOB-02-001"]

        state.remove_job_from_queues("JOB-01-001")

        self.assertEqual(state.workcenters["WC-A1"].queue, ["JOB-02-001"])
        self.assertEqual(state.shops["SHOP-A"].queued_job_ids, ["JOB-02-001"])

        state.workcenters["WC-A1"].current_job_id = "JOB-02-001"
        state.workcenters["WC-A1"].status = WorkCenterStatus.DOWN
        self.assertTrue(state.clear_job_from_current_workcenters("JOB-02-001"))
        self.assertIsNone(state.workcenters["WC-A1"].current_job_id)
        self.assertEqual(state.workcenters["WC-A1"].status, WorkCenterStatus.DOWN)

    def test_assign_job_rejects_incompatible_workcenter_and_queues_compatible_job(self):
        state = make_state()

        self.assertFalse(state.assign_job("JOB-01-002", "WC-A1"))
        self.assertIsNone(state.jobs["JOB-01-002"].assigned_workcenter_id)

        self.assertTrue(state.assign_job("JOB-01-001", "WC-A1"))
        self.assertEqual(state.jobs["JOB-01-001"].status, JobStatus.QUEUED)
        self.assertEqual(state.workcenters["WC-A1"].queue, ["JOB-01-001"])

    def test_assign_job_moving_active_work_adds_disruption_and_reschedules(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]
        state.assign_job(job.id, "WC-A1")
        state.workcenters["WC-A1"].queue.clear()
        state.workcenters["WC-A1"].current_job_id = job.id
        state.workcenters["WC-A1"].status = WorkCenterStatus.BUSY
        job.status = JobStatus.RUNNING
        job.remaining_duration_shifts = 2

        self.assertTrue(state.assign_job(job.id, "WC-B1", front=True))

        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertEqual(job.remaining_duration_shifts, 3)
        self.assertEqual(job.assigned_workcenter_id, "WC-B1")
        self.assertEqual(state.workcenters["WC-B1"].queue, [job.id])
        self.assertEqual(state.reschedule_count, 2)
        self.assertIn("moved while active", state.daily_notes[-1])

    def test_preempt_current_job_interrupts_running_work_for_incoming_job(self):
        state = make_state()
        current = state.jobs["JOB-01-001"]
        incoming = state.jobs["JOB-02-001"]
        current.status = JobStatus.RUNNING
        current.assigned_workcenter_id = "WC-A1"
        current.remaining_duration_shifts = 2
        incoming.status = JobStatus.READY
        state.workcenters["WC-A1"].current_job_id = current.id
        state.workcenters["WC-A1"].status = WorkCenterStatus.BUSY

        self.assertTrue(state.preempt_current_job("WC-A1", incoming.id))

        self.assertEqual(current.status, JobStatus.QUEUED)
        self.assertEqual(current.remaining_duration_shifts, 3)
        self.assertEqual(incoming.assigned_workcenter_id, "WC-A1")
        self.assertEqual(state.workcenters["WC-A1"].queue[:2], [incoming.id, current.id])
        self.assertIn("preempted", state.daily_notes[-1])

    def test_preempt_current_job_rejects_invalid_states(self):
        state = make_state()

        self.assertFalse(state.preempt_current_job("WC-A1", "JOB-01-001"))

        state.workcenters["WC-A1"].current_job_id = "JOB-01-001"
        state.jobs["JOB-01-001"].status = JobStatus.QUEUED
        self.assertFalse(state.preempt_current_job("WC-A1", "JOB-02-001"))


if __name__ == "__main__":
    unittest.main()
