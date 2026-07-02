from __future__ import annotations

from io import BytesIO
import json
import unittest

from echo_adventure.api.payloads import (
    _card_payload,
    _choice_by_id,
    _choice_payload,
    _decision_progress_payload,
    _job_queue_wait,
    _piece_completion_shift,
    _piece_display_id,
    _piece_due_shift,
    _piece_projected_completion_shift,
    _snapshot_payload,
)
from echo_adventure.api.review import ReviewMixin, _job_was_late
from echo_adventure.api.server import GameRequestHandler, _parse_optional_seed
from echo_adventure.enums import JobStatus
from echo_adventure.metrics import day_shift
from echo_adventure.metrics import calculate_snapshot, update_state_metrics
from echo_adventure.models import DecisionProgress

from .helpers import make_card, make_choice, make_state, unit_config


class PayloadHelperTests(unittest.TestCase):
    def test_snapshot_payload_includes_score_fields_when_state_is_supplied(self):
        state = make_state()
        state.decision_path = ["CARD:A"]
        state.decision_path_signature = "abcdef1234567890"
        snapshot = calculate_snapshot(state)

        payload = _snapshot_payload(snapshot, shifts_per_day=3, state=state)

        self.assertEqual(payload["shift"], snapshot.shift)
        self.assertEqual(payload["projectedCompletion"], day_shift(snapshot.projected_completion_shift, 3))
        self.assertIn("finalScore", payload)
        self.assertEqual(payload["decisionPathSignature"], "abcdef1234567890")

    def test_card_choice_and_progress_payload_helpers_are_json_ready(self):
        selected = make_choice("B", effect_type="wait", risk_effect=2, reschedule_effect=1)
        card = make_card("CARD", choices=[make_choice("A"), selected])
        progress = DecisionProgress(day=2, total_questions=3, answered_questions=1, visible_cards=2, open_card_ids=["B"])

        self.assertIs(_choice_by_id(card, "B"), selected)
        self.assertIsNone(_choice_by_id(card, "missing"))
        self.assertEqual(_choice_payload(selected)["riskEffect"], 2)
        self.assertEqual(_card_payload(card, selected_choice="B")["selectedChoice"], "B")
        self.assertEqual(
            _decision_progress_payload(progress),
            {"day": 2, "completed": 1, "total": 3, "visibleCards": 2, "openCardIds": ["B"]},
        )

    def test_piece_display_and_projection_helpers_cover_completion_and_queue_wait(self):
        state = make_state()
        piece = state.pieces["PIECE-01"]
        job = state.jobs["JOB-01-001"]
        job.status = JobStatus.QUEUED
        job.assigned_workcenter_id = "WC-A1"
        state.workcenters["WC-A1"].current_job_id = "JOB-02-001"
        state.workcenters["WC-A1"].queue = ["OTHER", job.id]

        self.assertEqual(_piece_display_id("PIECE-09"), "Job 09")
        self.assertEqual(_piece_due_shift(state, piece), 7)
        self.assertEqual(_job_queue_wait(state, job.id), 2)
        self.assertGreater(_piece_projected_completion_shift(state, piece), state.current_shift)
        self.assertIsNone(_piece_completion_shift(state, piece))

        for job_id in piece.job_ids:
            state.jobs[job_id].status = JobStatus.COMPLETE
            state.jobs[job_id].completed_shift = 4 if job_id.endswith("001") else 6
        self.assertEqual(_piece_completion_shift(state, piece), 6)
        self.assertEqual(_piece_projected_completion_shift(state, piece), 6)


class ReviewMixinTests(unittest.TestCase):
    def test_final_review_payload_explains_win_against_failed_benchmark(self):
        player = make_state()
        automated = make_state()
        for job in player.jobs.values():
            job.status = JobStatus.COMPLETE
            job.completed_shift = 8
            player.completed_jobs.add(job.id)
        player.final_item_completed = True
        player.completion_shift = 8
        automated.current_shift = automated.deadline_shift
        update_state_metrics(player)
        update_state_metrics(automated)
        harness = ReviewHarness(unit_config(), player, automated)

        review = harness._final_review_payload(calculate_snapshot(player), calculate_snapshot(automated))

        self.assertEqual(review["outcome"], "won")
        self.assertIn("You won", review["headline"])
        self.assertTrue(any("beat the benchmark" in reason for reason in review["reasons"]))

    def test_loss_reasons_include_incomplete_late_blocked_and_rework_pressure(self):
        player = make_state()
        automated = make_state()
        player.current_shift = player.deadline_shift
        player.jobs["JOB-01-001"].due_shift = 1
        player.jobs["JOB-01-001"].critical_path = True
        player.jobs["JOB-01-001"].block_reason = "blocked"
        player.jobs["JOB-02-001"].rework_count = 1
        update_state_metrics(player)
        update_state_metrics(automated)
        harness = ReviewHarness(unit_config(), player, automated)

        reasons = harness._loss_reasons(calculate_snapshot(player), calculate_snapshot(automated))

        self.assertTrue(any("incomplete" in reason for reason in reasons))
        self.assertTrue(any("late" in reason for reason in reasons))
        self.assertTrue(any("blocked" in reason for reason in reasons))
        self.assertTrue(any("Quality/rework" in reason for reason in reasons))
        self.assertTrue(_job_was_late(player, player.jobs["JOB-01-001"]))


class ReviewHarness(ReviewMixin):
    def __init__(self, config, player_state, automated_state):
        self.config = config
        self.player_state = player_state
        self.automated_state = automated_state


class ServerHelperTests(unittest.TestCase):
    def test_parse_optional_seed_accepts_empty_values_and_rejects_non_integer(self):
        self.assertIsNone(_parse_optional_seed(None))
        self.assertIsNone(_parse_optional_seed(""))
        self.assertEqual(_parse_optional_seed("42"), 42)
        with self.assertRaisesRegex(ValueError, "Seed must be an integer"):
            _parse_optional_seed("abc")

    def test_request_handler_routes_json_html_static_and_errors(self):
        class FakeStore:
            def state_payload(self):
                return {"route": "state"}

            def new_session_payload(self, seed=None):
                return {"route": "new", "seed": seed}

            def choice_payload(self, card_id, choice_id):
                raise ValueError(f"bad choice {card_id}/{choice_id}")

            def shift_payload(self):
                return {"route": "shift"}

            def advance_payload(self):
                return {"route": "advance"}

        handler_type = type("FakeHandler", (HandlerHarness, GameRequestHandler), {"session_store": FakeStore()})

        self.assert_json_handler_response(handler_type("GET", "/api/state"), 200, {"route": "state"})
        self.assert_json_handler_response(
            handler_type("POST", "/api/new", {"seed": "123"}),
            200,
            {"route": "new", "seed": 123},
        )
        self.assert_json_handler_response(
            handler_type("POST", "/api/choice", {"cardId": "C", "choiceId": "X"}),
            400,
            {"error": "bad choice C/X"},
        )
        self.assert_json_handler_response(handler_type("GET", "/missing"), 404, {"error": "Not found"})

        html = handler_type("GET", "/")
        html.do_GET()
        self.assertEqual(html.response_status, 200)
        self.assertIn("text/html", html.header("content-type"))
        self.assertIn("/ui/app.js", html.body_text())

        static = handler_type("GET", "/ui/html.js")
        static.do_GET()
        self.assertEqual(static.response_status, 200)
        self.assertIn("application/javascript", static.header("content-type"))
        self.assertIn("escapeHtml", static.body_text())

    def assert_json_handler_response(self, handler, expected_status, expected_payload):
        if handler.method == "GET":
            handler.do_GET()
        else:
            handler.do_POST()
        self.assertEqual(handler.response_status, expected_status)
        self.assertEqual(json.loads(handler.body_text()), expected_payload)


class HandlerHarness:
    def __init__(self, method, path, payload=None):
        self.method = method
        self.path = path
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        self.headers = {"content-length": str(len(body))}
        self.rfile = BytesIO(body)
        self.wfile = BytesIO()
        self.response_status = None
        self.response_headers = {}

    def send_response(self, status):
        self.response_status = int(status)

    def send_header(self, name, value):
        self.response_headers[name.lower()] = value

    def end_headers(self):
        return None

    def header(self, name):
        return self.response_headers.get(name.lower(), "")

    def body_text(self):
        return self.wfile.getvalue().decode("utf-8")


if __name__ == "__main__":
    unittest.main()
