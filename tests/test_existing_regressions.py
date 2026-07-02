from dataclasses import replace
import threading
import unittest
from unittest.mock import patch

from echo_adventure import echo as echo_policy
from echo_adventure.config import GameConfig
from echo_adventure.decisions import select_echo_choice
from echo_adventure.enums import DecisionType, EventType, JobStatus, TargetType
from echo_adventure.events import apply_event_start, resolve_event
from echo_adventure.metrics import update_state_metrics
from echo_adventure.models import DecisionCard, DecisionChoice, Event
from echo_adventure.scenario_generator import generate_scenario
from echo_adventure.simulation import initialize_state
from echo_adventure.api.server import STATIC_ASSETS, GameSession, SessionStore
from echo_adventure.api.view import INDEX_HTML


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


class EchoForecastLoggingTests(unittest.TestCase):
    def test_forecast_exception_is_logged_before_heuristic_fallback(self):
        session = GameSession(seed=123)
        card = session.current_cards[0]

        with patch.object(echo_policy, "apply_choice", side_effect=RuntimeError("forecast boom")):
            with self.assertLogs("echo_adventure.echo", level="ERROR") as logs:
                choice = echo_policy.select_echo_choice_for_state(
                    session.player_state,
                    card,
                    session.config,
                    session.player_state.decision_cards,
                )

        self.assertIn(choice.id, [candidate.id for candidate in card.choices])
        self.assertTrue(any("ECHO forecast failed" in line for line in logs.output))
        self.assertTrue(any(card.id in line for line in logs.output))


class StaticViewAssetTests(unittest.TestCase):
    def test_index_html_references_external_static_assets(self):
        self.assertIn('/ui/styles.css', INDEX_HTML)
        self.assertIn('/ui/app.js', INDEX_HTML)
        self.assertNotIn('<style>', INDEX_HTML)
        self.assertNotIn('\n  <script>\n', INDEX_HTML)
        for _, asset_path in STATIC_ASSETS.values():
            self.assertTrue(asset_path.exists())

    def test_final_chart_renderer_uses_cumulative_scores_and_correct_answer_copy(self):
        source = STATIC_ASSETS["/ui/renderFinal.js"][1].read_text(encoding="utf-8")

        self.assertIn("playerCumulativeScore", source)
        self.assertIn("echoCumulativeScore", source)
        self.assertIn("Correct answer (ECHO)", source)
        self.assertIn("Your answer:", source)
        self.assertIn("cumulative decision score", source)
        self.assertNotIn("const playerImpact = decisionPoints.map", source)
        self.assertNotIn("Strategic path signature", source)


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
        self.assertEqual(point["questionText"], card.description)
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


class SessionStoreOwnershipTests(unittest.TestCase):
    def test_new_session_waits_for_in_flight_action_payload(self):
        store = SessionStore(seed=123)
        original_session = store.session
        card = original_session.current_cards[0]
        choice = card.choices[0]
        original_apply_choice = original_session.apply_choice
        entered_action = threading.Event()
        release_action = threading.Event()
        new_session_finished = threading.Event()
        results = {}

        def blocking_apply_choice(card_id: str, choice_id: str):
            entered_action.set()
            if not release_action.wait(timeout=2):
                raise AssertionError("Timed out waiting to release the blocked choice.")
            return original_apply_choice(card_id, choice_id)

        original_session.apply_choice = blocking_apply_choice

        def choose_in_thread():
            results["choice"] = store.choice_payload(card.id, choice.id)

        def start_new_run_in_thread():
            results["new"] = store.new_session_payload(seed=456)
            new_session_finished.set()

        choice_thread = threading.Thread(target=choose_in_thread)
        new_thread = threading.Thread(target=start_new_run_in_thread)

        choice_thread.start()
        self.assertTrue(entered_action.wait(timeout=2))
        new_thread.start()
        self.assertFalse(new_session_finished.wait(timeout=0.05))

        release_action.set()
        choice_thread.join(timeout=2)
        new_thread.join(timeout=2)

        self.assertFalse(choice_thread.is_alive())
        self.assertFalse(new_thread.is_alive())
        self.assertEqual(results["choice"]["seed"], 123)
        self.assertEqual(results["new"]["seed"], 456)
        self.assertEqual(store.state_payload()["seed"], 456)


class ScenarioDueDateGenerationTests(unittest.TestCase):
    def test_extra_quality_rework_events_do_not_require_base_events(self):
        config = replace(
            _due_date_test_config(total_days=8, seed=2468),
            min_extra_quality_rework_events=2,
            max_extra_quality_rework_events=2,
        )

        scenario = generate_scenario(config)
        rework_events = [
            event
            for event in scenario.event_timeline
            if event.type == EventType.QUALITY_REWORK
        ]

        self.assertEqual(len(rework_events), 2)

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


class EventResolutionTests(unittest.TestCase):
    def test_overlapping_job_blocks_keep_job_blocked_until_all_resolve(self):
        config = _due_date_test_config(total_days=8, seed=2468)
        state = initialize_state(generate_scenario(config), config.shifts_per_day)
        job = next(job for job in state.jobs.values() if not job.dependency_ids)
        first_event = Event(
            id="EVT-A",
            type=EventType.MISSING_MATERIAL,
            target_type=TargetType.JOB,
            target_id=job.id,
            start_shift=1,
            duration_shifts=5,
            severity=1,
            has_advance_warning=False,
            warning_shift=None,
            description="First blocker",
        )
        second_event = Event(
            id="EVT-B",
            type=EventType.INSPECTION_DELAY,
            target_type=TargetType.JOB,
            target_id=job.id,
            start_shift=2,
            duration_shifts=5,
            severity=1,
            has_advance_warning=False,
            warning_shift=None,
            description="Second blocker",
        )
        state.event_timeline.extend([first_event, second_event])

        apply_event_start(state, first_event)
        apply_event_start(state, second_event)
        self.assertEqual(job.status, JobStatus.BLOCKED)
        self.assertIn(second_event.id, job.block_reason or "")

        resolve_event(state, second_event)
        self.assertEqual(job.status, JobStatus.BLOCKED)
        self.assertIn(first_event.id, job.block_reason or "")
        self.assertIn(job.id, state.blocked_jobs)

        resolve_event(state, first_event)
        self.assertEqual(job.status, JobStatus.READY)
        self.assertIsNone(job.block_reason)
        self.assertNotIn(job.id, state.blocked_jobs)


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

    def test_summary_puzzle_does_not_change_after_midday_progress(self):
        session = GameSession(seed=123)

        while not session.ready_to_advance():
            open_card = next(card for card in session.current_cards if card.id not in session.applied_choices)
            session.apply_choice(open_card.id, open_card.choices[0].id)
        session.advance_day()

        original_puzzle = session.state_payload()["lastSummary"]["puzzle"]
        incomplete_piece_ids = [tile["id"] for tile in original_puzzle["tiles"] if not tile["completed"]]
        self.assertGreater(len(incomplete_piece_ids), 1)

        future_shift = session.last_result.end_snapshot.shift + 1
        target_piece = session.player_state.pieces[incomplete_piece_ids[0]]
        session.player_state.current_shift = future_shift
        for job_id in target_piece.job_ids:
            job = session.player_state.jobs[job_id]
            job.status = JobStatus.COMPLETE
            job.completed_shift = future_shift
            job.remaining_duration_shifts = 0
            job.block_reason = None
            session.player_state.completed_jobs.add(job_id)
            session.player_state.remove_job_from_queues(job_id)
        update_state_metrics(session.player_state)

        refreshed_puzzle = session.state_payload()["lastSummary"]["puzzle"]
        self.assertEqual(refreshed_puzzle, original_puzzle)

    def test_summary_past_due_jobs_do_not_change_after_later_progress(self):
        session = GameSession(seed=123)

        while not session.ready_to_advance():
            open_card = next(card for card in session.current_cards if card.id not in session.applied_choices)
            session.apply_choice(open_card.id, open_card.choices[0].id)
        session.advance_day()

        original_past_due = session.state_payload()["lastSummary"]["pastDueJobs"]
        target_job = next(job for job in session.player_state.jobs.values() if not job.is_complete)
        session.player_state.current_shift = min(
            session.player_state.deadline_shift - 1,
            session.last_result.end_snapshot.shift + session.config.shifts_per_day,
        )
        target_job.due_shift = 1
        target_job.remaining_duration_shifts = 7
        update_state_metrics(session.player_state)

        refreshed_past_due = session.state_payload()["lastSummary"]["pastDueJobs"]
        self.assertEqual(refreshed_past_due, original_past_due)


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
