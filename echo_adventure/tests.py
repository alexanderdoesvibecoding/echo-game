import unittest

from echo_adventure.config import GameConfig
from echo_adventure.decisions import select_echo_choice
from echo_adventure.enums import DecisionType
from echo_adventure.models import DecisionCard, DecisionChoice
from echo_adventure.scenario_generator import generate_scenario
from echo_adventure.ui.server import GameSession


class DeterministicDecisionGenerationTests(unittest.TestCase):
    def test_echo_static_choice_reads_full_reachable_tree(self):
        root = DecisionCard(
            id="ROOT",
            day=1,
            type=DecisionType.CRITICAL_PATH,
            title="Root",
            description="Root",
            target_ids=[],
            severity=1,
            choices=[
                DecisionChoice(
                    id="1",
                    label="Looks good now",
                    description="Looks good now",
                    immediate_effects={"type": "echo_recommendation"},
                    risk_effect=0,
                    reschedule_effect=0,
                    next_card_id="CHILD",
                ),
                DecisionChoice(
                    id="2",
                    label="Safer path",
                    description="Safer path",
                    immediate_effects={"type": "echo_recommendation"},
                    risk_effect=1,
                    reschedule_effect=0,
                ),
            ],
        )
        child = DecisionCard(
            id="CHILD",
            day=2,
            type=DecisionType.CRITICAL_PATH,
            title="Child",
            description="Child",
            target_ids=[],
            severity=1,
            choices=[
                DecisionChoice(
                    id="1",
                    label="Grandchild path",
                    description="Grandchild path",
                    immediate_effects={"type": "echo_recommendation"},
                    risk_effect=0,
                    reschedule_effect=0,
                    next_card_id="GRANDCHILD",
                )
            ],
        )
        grandchild = DecisionCard(
            id="GRANDCHILD",
            day=3,
            type=DecisionType.CRITICAL_PATH,
            title="Grandchild",
            description="Grandchild",
            target_ids=[],
            severity=1,
            choices=[
                DecisionChoice(
                    id="1",
                    label="Hidden bad tail",
                    description="Hidden bad tail",
                    immediate_effects={"type": "wait"},
                    risk_effect=10,
                    reschedule_effect=0,
                )
            ],
        )

        graph = {card.id: card for card in (root, child, grandchild)}

        self.assertEqual(select_echo_choice(root, graph).id, "2")


class FinalDecisionGraphPayloadTests(unittest.TestCase):
    def test_decision_chart_payload_includes_player_and_echo_choice_details(self):
        session = GameSession(seed=123)
        card = session.current_cards[0]
        choice = card.choices[0]

        session.apply_choice(card.id, choice.id)

        points = session._decision_chart_payload()
        self.assertEqual(len(points), 1)
        point = points[0]
        self.assertEqual(point["sequence"], 1)
        self.assertEqual(point["day"], card.day)
        self.assertEqual(point["questionId"], card.id)
        self.assertEqual(point["questionTitle"], card.title)
        self.assertEqual(point["playerChoice"], choice.label)
        self.assertIn(point["echoChoice"], [candidate.label for candidate in card.choices])
        self.assertIn("playerDelta", point)
        self.assertIn("echoDelta", point)
        self.assertIn("playerCumulativeScore", point)
        self.assertIn("echoCumulativeScore", point)
        self.assertIn("affectedLabel", point)

    def test_decision_chart_payload_handles_no_decisions(self):
        session = GameSession(seed=123)

        self.assertEqual(session._decision_chart_payload(), [])


class ScenarioDueDateGenerationTests(unittest.TestCase):
    def test_piece_due_dates_spread_across_configured_total_days(self):
        scenario = generate_scenario(_due_date_test_config(total_days=8, seed=2468))
        due_days = _piece_due_days(scenario, shifts_per_day=3)

        self.assertEqual(len(due_days), 6)
        self.assertTrue(all(1 <= due_day <= 8 for due_day in due_days.values()))
        self.assertGreater(len(set(due_days.values())), 1)
        self.assertLess(min(due_days.values()), 5)
        self.assertGreater(max(due_days.values()), 6)
        self.assertTrue(any(due_day < 8 for due_day in due_days.values()))
        self.assertTrue(all(1 <= job.due_shift <= scenario.deadline_shift for job in scenario.jobs.values()))

    def test_piece_due_dates_adapt_to_longer_total_days(self):
        scenario = generate_scenario(_due_date_test_config(total_days=15, seed=2468))
        due_days = _piece_due_days(scenario, shifts_per_day=3)

        self.assertEqual(len(due_days), 6)
        self.assertTrue(all(1 <= due_day <= 15 for due_day in due_days.values()))
        self.assertTrue(any(due_day < 15 for due_day in due_days.values()))
        self.assertTrue(all(job.due_shift <= scenario.deadline_shift for job in scenario.jobs.values()))


class ShiftProgressionPayloadTests(unittest.TestCase):
    def test_live_snapshot_updates_by_shift_before_day_summary(self):
        session = GameSession(seed=123)
        initial = session.state_payload()

        session.advance_shift()
        shifted = session.state_payload()

        self.assertEqual(shifted["snapshot"]["shift"], initial["snapshot"]["shift"] + 1)
        self.assertEqual(shifted["day"], initial["day"])
        self.assertIsNone(session.last_result)

        while not session.ready_to_advance():
            open_card = next(card for card in session.current_cards if card.id not in session.applied_choices)
            session.apply_choice(open_card.id, open_card.choices[0].id)

        session.advance_day()

        self.assertIsNotNone(session.last_result)
        self.assertEqual(session.last_result.start_snapshot.shift, initial["snapshot"]["shift"])
        self.assertEqual(session.last_result.end_snapshot.shift, initial["snapshot"]["shift"] + session.config.shifts_per_day)


def _due_date_test_config(total_days: int, seed: int) -> GameConfig:
    return GameConfig(
        total_days=total_days,
        shifts_per_day=3,
        piece_count=6,
        min_jobs_per_piece=2,
        max_jobs_per_piece=2,
        max_job_duration_shifts=2,
        setup_time_choices=(0,),
        transport_delay_probability=0.0,
        min_base_events=0,
        max_base_events=0,
        min_extra_quality_rework_events=0,
        max_extra_quality_rework_events=0,
        completion_rework_probability=0.0,
        min_completion_rework_shifts=0,
        max_completion_rework_shifts=0,
        min_decisions_per_day=1,
        max_decisions_per_day=1,
        max_active_decision_cards_per_day=1,
        max_campaign_decision_nodes=40,
        max_campaign_branch_depth=2,
        max_future_unlocks_per_choice=1,
        max_branch_variants_per_day=2,
        seed=seed,
    )


def _piece_due_days(scenario, shifts_per_day: int) -> dict[str, int]:
    due_days = {}
    for piece in scenario.pieces.values():
        piece_due_shifts = {scenario.jobs[job_id].due_shift for job_id in piece.job_ids}
        if len(piece_due_shifts) != 1:
            raise AssertionError(f"{piece.id} should have one shared due shift.")
        due_shift = piece_due_shifts.pop()
        due_days[piece.id] = ((due_shift - 1) // shifts_per_day) + 1
    return due_days


if __name__ == "__main__":
    unittest.main()
