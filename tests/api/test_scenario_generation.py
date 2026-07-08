from __future__ import annotations

import unittest

from echo_adventure.scenario_generator import SHOP_BLUEPRINTS, generate_scenario, validate_scenario

from .helpers import make_scenario, make_state, piece_due_days, unit_config


class ScenarioGenerationCoverageTests(unittest.TestCase):
    def test_capability_coverage_and_candidate_routes_are_playable(self):
        config = unit_config(
            total_days=6,
            shop_count=9,
            piece_count=5,
            min_workcenters_per_shop=2,
            max_workcenters_per_shop=2,
            min_capable_workcenters_per_capability=3,
            min_candidate_workcenters_per_job=2,
            max_candidate_workcenters_per_job=5,
            max_campaign_decision_nodes=80,
            max_branch_variants_per_day=4,
            seed=202,
        )

        scenario = generate_scenario(config)
        expected_capabilities = {
            capability
            for zero_index in range(config.shop_count)
            for capability in SHOP_BLUEPRINTS[zero_index % len(SHOP_BLUEPRINTS)][1]
        }

        for capability in expected_capabilities:
            with self.subTest(capability=capability):
                capable = [
                    workcenter
                    for workcenter in scenario.workcenters.values()
                    if capability in workcenter.capabilities
                ]
                self.assertGreaterEqual(
                    len(capable),
                    min(config.min_capable_workcenters_per_capability, len(scenario.workcenters)),
                )

        for job in scenario.jobs.values():
            with self.subTest(job=job.id):
                self.assertGreaterEqual(len(job.candidate_workcenter_ids), config.min_candidate_workcenters_per_job)
                self.assertLessEqual(len(job.candidate_workcenter_ids), config.max_candidate_workcenters_per_job)
                self.assertTrue(
                    all(
                        job.required_capability in scenario.workcenters[workcenter_id].capabilities
                        for workcenter_id in job.candidate_workcenter_ids
                    )
                )

    def test_due_dates_spread_across_total_days_and_calendar_ranges(self):
        cases = [
            unit_config(
                total_days=3,
                start_date="2027-02-01",
                end_date="2027-02-03",
                piece_count=4,
                max_campaign_decision_nodes=50,
                seed=303,
            ),
            unit_config(
                total_days=9,
                start_date="2028-06-10",
                end_date="2028-06-18",
                piece_count=7,
                max_campaign_decision_nodes=90,
                seed=404,
            ),
        ]

        for config in cases:
            with self.subTest(total_days=config.total_days, start=config.start_date):
                scenario = generate_scenario(config)
                due_days = piece_due_days(scenario, config.shifts_per_day)

                self.assertEqual(len(due_days), config.piece_count)
                self.assertTrue(all(1 <= due_day <= config.total_days for due_day in due_days.values()))
                self.assertGreater(len(set(due_days.values())), 1)
                self.assertTrue(any(due_day < config.total_days for due_day in due_days.values()))
                self.assertEqual(config.date_label_for_shift(scenario.deadline_shift), config.deadline_date_label)
                self.assertTrue(
                    all(1 <= job.due_shift <= scenario.deadline_shift for job in scenario.jobs.values())
                )


class ScenarioValidationTests(unittest.TestCase):
    def test_validate_scenario_rejects_dependency_cycles(self):
        state = make_state()
        state.jobs["JOB-01-001"].dependency_ids = ["JOB-01-002"]
        state.jobs["JOB-01-002"].dependency_ids = ["JOB-01-001"]
        scenario = make_scenario(state)
        config = unit_config(piece_count=2, shop_count=2, min_jobs_per_piece=2, max_jobs_per_piece=2)

        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_scenario(scenario, config)

    def test_validate_scenario_rejects_jobs_without_capable_routes(self):
        state = make_state()
        state.jobs["JOB-01-001"].candidate_workcenter_ids = []
        scenario = make_scenario(state)
        config = unit_config(piece_count=2, shop_count=2, min_jobs_per_piece=2, max_jobs_per_piece=2)

        with self.assertRaisesRegex(ValueError, "no capable workcenter"):
            validate_scenario(scenario, config)


if __name__ == "__main__":
    unittest.main()
