from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import json
import threading
import unittest

from echo_adventure.api.payloads import (
    PayloadMixin,
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
from echo_adventure.api.server import GameRequestHandler, STATIC_ASSETS, SessionStore, _parse_optional_seed
from echo_adventure.enums import JobStatus
from echo_adventure.metrics import calculate_snapshot, update_state_metrics
from echo_adventure.models import DecisionProgress, DecisionRecord

from .helpers import make_card, make_choice, make_state, unit_config


class PayloadHelperTests(unittest.TestCase):
    def test_state_payload_exposes_day_cycle_duration_from_config(self):
        harness = PayloadHarness(unit_config(day_cycle_duration_ms=12345), make_state())

        payload = harness.state_payload()

        self.assertEqual(payload["dayCycleDurationMs"], 12345)
        self.assertEqual(payload["snapshot"]["jobsCompletedToday"], 0)

    def test_state_payload_counts_live_subjobs_completed_today(self):
        state = make_state()
        state.jobs["JOB-01-001"].status = JobStatus.COMPLETE
        state.jobs["JOB-01-001"].completed_shift = 1
        state.completed_jobs.add("JOB-01-001")
        harness = PayloadHarness(unit_config(), state)
        harness.day_start_snapshot = object()

        payload = harness.state_payload()

        self.assertEqual(payload["snapshot"]["jobsCompletedToday"], 1)

    def test_state_payload_includes_live_submarine_puzzle(self):
        state = make_state()
        state.current_shift = 2
        for job_id in ("JOB-01-001", "JOB-01-002"):
            state.jobs[job_id].status = JobStatus.COMPLETE
            state.jobs[job_id].completed_shift = 2
            state.completed_jobs.add(job_id)
        harness = PayloadHarness(unit_config(), state)
        harness.day_start_snapshot = object()
        harness.day_start_shift = 0

        payload = harness.state_payload()
        puzzle = payload["livePuzzle"]
        completed_tile = next(tile for tile in puzzle["tiles"] if tile["id"] == "PIECE-01")

        self.assertEqual(puzzle["completed"], 1)
        self.assertEqual(puzzle["completedToday"], 1)
        self.assertTrue(completed_tile["completed"])
        self.assertTrue(completed_tile["newlyCompleted"])

    def test_snapshot_payload_includes_score_fields_when_state_is_supplied(self):
        state = make_state()
        state.decision_path = ["CARD:A"]
        state.decision_path_signature = "abcdef1234567890"
        state.decision_path_score_delta = 2.75
        snapshot = calculate_snapshot(state)

        config = unit_config()

        payload = _snapshot_payload(snapshot, shifts_per_day=3, state=state, config=config)

        self.assertEqual(payload["shift"], snapshot.shift)
        self.assertEqual(payload["projectedCompletion"], config.date_label_for_shift(snapshot.projected_completion_shift))
        self.assertEqual(payload["date"], config.date_label_for_day(snapshot.day))
        self.assertEqual(payload["finalScore"], 2.75)
        self.assertNotIn("decisionPathSignature", payload)
        self.assertNotIn("decisionPathDifferentiator", payload)

    def test_snapshot_payload_includes_max_schedule_risk_from_history(self):
        state = make_state()
        snapshot = calculate_snapshot(state)
        state.metric_history.append(replace(snapshot, schedule_risk=42.2))
        state.max_schedule_risk_seen = 51.4

        payload = _snapshot_payload(snapshot, shifts_per_day=3, state=state)

        self.assertEqual(payload["scheduleRisk"], round(snapshot.schedule_risk, 1))
        self.assertEqual(payload["maxScheduleRisk"], 51.4)

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

    def test_final_review_payload_omits_decision_match_audit(self):
        player = make_state()
        automated = make_state()
        player.decision_history.append(
            DecisionRecord(
                day=1,
                card_id="CARD-1",
                card_title="Unit Card",
                actor="player",
                choice_id="A",
                choice_label="A choice",
                echo_choice_id="A",
                echo_choice_label="A choice",
                aligned_with_echo=True,
                note="Recorded elsewhere.",
            )
        )
        update_state_metrics(player)
        update_state_metrics(automated)
        harness = ReviewHarness(unit_config(), player, automated)

        review = harness._final_review_payload(calculate_snapshot(player), calculate_snapshot(automated))

        self.assertFalse(any("matched ECHO" in reason for reason in review["reasons"]))

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


class PayloadHarness(PayloadMixin):
    def __init__(self, config, player_state):
        self.lock = threading.RLock()
        self.seed = config.seed
        self.config = config
        self.player_state = player_state
        self.current_cards = []
        self.applied_choices = {}
        self.choice_notes = []
        self.last_result = None
        self.last_summary_past_due_jobs = None
        self.last_summary_puzzle = None
        self.day_start_snapshot = None
        self.day_completed_before = set()
        self.day_start_shift = None

    def _ensure_cards(self):
        return None

    def _game_over(self):
        return False


class ServerHelperTests(unittest.TestCase):
    def test_parse_optional_seed_accepts_empty_values_and_rejects_non_integer(self):
        self.assertIsNone(_parse_optional_seed(None))
        self.assertIsNone(_parse_optional_seed(""))
        self.assertIsNone(_parse_optional_seed("   "))
        self.assertEqual(_parse_optional_seed(" 007 "), 7)
        self.assertEqual(_parse_optional_seed(42), 42)
        self.assertEqual(_parse_optional_seed("42"), 42)
        for bad_seed in ("abc", "4.2", 4.2, True, False):
            with self.subTest(seed=bad_seed):
                with self.assertRaisesRegex(ValueError, "Seed must be an integer"):
                    _parse_optional_seed(bad_seed)

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

            def skip_to_end_payload(self):
                return {"route": "skip-to-end"}

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
        self.assert_json_handler_response(
            handler_type("POST", "/api/test/skip-to-end"),
            200,
            {"route": "skip-to-end"},
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

    def test_request_handler_rejects_malformed_json_and_unknown_post_routes(self):
        class FakeStore:
            def new_session_payload(self, seed=None):
                return {"route": "new", "seed": seed}

        handler_type = type("FakeHandler", (HandlerHarness, GameRequestHandler), {"session_store": FakeStore()})

        malformed = handler_type("POST", "/api/new", raw_body=b'{"seed":')
        malformed.do_POST()
        self.assertEqual(malformed.response_status, 400)
        self.assertIn("Expecting value", json.loads(malformed.body_text())["error"])

        self.assert_json_handler_response(
            handler_type("POST", "/api/missing", {}),
            404,
            {"error": "Not found"},
        )

    def test_static_asset_mime_types_and_missing_static_paths(self):
        handler_type = type("FakeHandler", (HandlerHarness, GameRequestHandler), {"session_store": object()})

        for path, (expected_type, asset_path) in STATIC_ASSETS.items():
            with self.subTest(path=path):
                handler = handler_type("GET", path)
                handler.do_GET()
                self.assertEqual(handler.response_status, 200)
                self.assertEqual(handler.header("content-type"), expected_type)
                self.assertEqual(int(handler.header("content-length")), asset_path.stat().st_size)

        missing = handler_type("GET", "/ui/missing.js")
        missing.do_GET()
        self.assertEqual(missing.response_status, 404)
        self.assertEqual(json.loads(missing.body_text()), {"error": "Not found"})

    def test_concurrent_duplicate_choices_apply_once(self):
        store = SessionStore(seed=123)
        card = store.session.current_cards[0]
        choice = card.choices[0]
        start = threading.Barrier(2)
        results = []

        def choose_once():
            start.wait(timeout=2)
            try:
                results.append(("ok", store.choice_payload(card.id, choice.id)))
            except ValueError as exc:
                results.append(("error", str(exc)))

        threads = [threading.Thread(target=choose_once) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual([kind for kind, _ in results].count("ok"), 1)
        self.assertEqual([kind for kind, _ in results].count("error"), 1)
        error_message = next(payload for kind, payload in results if kind == "error")
        self.assertTrue(
            "already" in error_message
            or "no longer active" in error_message
        )
        with store.lock:
            self.assertEqual(store.session.applied_choices.get(card.id), choice.id)
            player_records = [
                record
                for record in store.session.player_state.decision_history
                if record.actor == "player" and record.card_id == card.id
            ]
        self.assertEqual(len(player_records), 1)

    def assert_json_handler_response(self, handler, expected_status, expected_payload):
        if handler.method == "GET":
            handler.do_GET()
        else:
            handler.do_POST()
        self.assertEqual(handler.response_status, expected_status)
        self.assertEqual(json.loads(handler.body_text()), expected_payload)


class HandlerHarness:
    def __init__(self, method, path, payload=None, raw_body=None):
        self.method = method
        self.path = path
        if raw_body is not None:
            body = raw_body
        elif payload is not None:
            body = json.dumps(payload).encode("utf-8")
        else:
            body = b""
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
