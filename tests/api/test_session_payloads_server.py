from __future__ import annotations

from dataclasses import replace
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from echo_adventure.api import session as session_module
from echo_adventure.api.payloads import _echo_comparison_state
from echo_adventure.api.server import GameRequestHandler, STATIC_ASSETS, _parse_optional_seed

from .helpers import small_config


def install_fast_session_config(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> None:
    def factory(seed: int | None = None):
        return small_config(seed=seed, **overrides)

    monkeypatch.setattr(session_module, "GameConfig", factory)


def play_to_completion(session: session_module.GameSession, first_choice_id: str | None = None) -> dict:
    first = True
    guard = 0
    while not session.player_state.final_item_completed:
        guard += 1
        assert guard < 100
        if session.current_cards:
            assert len(session.current_cards) == 1
            card = session.current_cards[0]
            choice_id = first_choice_id if first and first_choice_id else card.echo_choice_id
            session.apply_choice(card.id, choice_id)
            first = False
        elif session.ready_to_advance():
            session.advance_day()
        else:
            raise AssertionError("Unfinished session has neither a decision nor a ready workday.")
    return session.state_payload()["finalReveal"]


def test_initial_session_payload_matches_the_modern_browser_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fast_session_config(monkeypatch)
    session = session_module.GameSession(seed=404)

    payload = session.state_payload()

    assert payload["seed"] == 404
    assert payload["day"] == 1
    assert payload["currentDate"] == "July 1"
    assert payload["jobCount"] == 3
    assert payload["gameOver"] is False
    assert payload["finalAssembly"] is None
    assert payload["decisionProgress"] == {
        "completed": 0,
        "total": 1,
    }
    assert payload["decisions"][0]["eventId"]
    assert payload["decisions"][0]["eventScope"] in {
        "shared-day",
        "route-specific",
        "follow-up",
    }
    assert len(payload["livePuzzle"]["tiles"]) == 3
    assert set(payload["timelines"]) == {"player", "echo"}
    assert payload["lastSummary"] is None

    real_generate_decision_web = session_module.generate_decision_web
    generation_calls: list[tuple[int, float | None]] = []

    def controlled_generation(scenario, config, *, max_generation_seconds=None):
        generation_calls.append((scenario.seed, max_generation_seconds))
        if scenario.seed == 111:
            raise session_module.DecisionWebGenerationTimeout("timed out")
        return real_generate_decision_web(
            scenario,
            config,
            max_generation_seconds=max_generation_seconds,
        )

    random_seeds = iter((111, 222))
    monkeypatch.setattr(
        session_module,
        "resolve_seed",
        lambda requested: requested if requested is not None else next(random_seeds),
    )
    monkeypatch.setattr(
        session_module,
        "generate_decision_web",
        controlled_generation,
    )

    explicit = session_module.GameSession(seed=505)
    assert explicit.seed == 505
    assert generation_calls == [(505, None)]

    generation_calls.clear()
    random_session = session_module.GameSession()
    assert random_session.seed == random_session.scenario.seed == 222
    assert generation_calls == [(111, 15.0), (222, 15.0)]


def test_session_rejects_invalid_or_out_of_sequence_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fast_session_config(monkeypatch)
    session = session_module.GameSession(seed=405)
    card = session.current_cards[0]

    with pytest.raises(ValueError, match="before advancing"):
        session.advance_day()
    with pytest.raises(ValueError, match="no longer active"):
        session.apply_choice("missing", card.choices[0].id)
    with pytest.raises(ValueError, match="not valid"):
        session.apply_choice(card.id, "missing")

    session.apply_choice(card.id, card.choices[0].id)
    with pytest.raises(ValueError, match="no longer active|already"):
        session.apply_choice(card.id, card.choices[0].id)


def test_choice_and_advance_update_player_and_echo_once_per_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fast_session_config(monkeypatch)
    session = session_module.GameSession(seed=406)
    card = session.current_cards[0]
    choice = card.choices[0]

    session.apply_choice(card.id, choice.id)

    assert len(session.player_state.decision_history) == 1
    assert len(session.automated_state.decision_history) == 1
    assert session.questions_answered_today == 1
    assert session.current_cards == []

    session.advance_day()
    assert session.last_result is not None
    assert session.last_result.day == 1
    payload = session.state_payload()
    job_count = len(session.player_state.jobs)
    assert payload["lastSummary"]["previousJobsComplete"] == job_count - session.last_result.start_snapshot.jobs_remaining
    assert payload["lastSummary"]["jobsComplete"] == job_count - session.last_result.end_snapshot.jobs_remaining
    assert payload["lastSummary"]["previousJobsRemaining"] == session.last_result.start_snapshot.jobs_remaining
    assert payload["lastSummary"]["jobsRemaining"] == session.last_result.end_snapshot.jobs_remaining
    assert (
        payload["lastSummary"]["projectedCompletion"]
        == payload["timelines"]["player"]["projectedCompletion"]
    )
    expected_remaining_jobs = [
        {
            "name": job.name,
            "remainingDays": job.remaining_days,
        }
        for job in sorted(session.player_state.incomplete_jobs(), key=lambda job: job.id)
    ]
    assert payload["lastSummary"]["remainingJobs"] == expected_remaining_jobs
    assert session.player_state.current_day == 2
    assert session.automated_state.current_day == 2
    assert session.questions_answered_today == 0
    assert len(session.current_cards) == 1

    first_summary_remaining_jobs = payload["lastSummary"]["remainingJobs"]
    next_card = session.current_cards[0]
    session.apply_choice(next_card.id, next_card.choices[0].id)
    assert session.state_payload()["lastSummary"]["remainingJobs"] == first_summary_remaining_jobs


def test_multi_question_days_traverse_web_and_end_on_an_early_final_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fast_session_config(
        monkeypatch,
        min_decisions_per_day=2,
        max_decisions_per_day=2,
    )
    session = session_module.GameSession(seed=407)
    assert session.decision_total_today == 2
    first = session.current_cards[0]
    monkeypatch.setattr(session, "_should_start_final_assembly", lambda: True)

    session.apply_choice(first.id, first.echo_choice_id)

    assert session.questions_answered_today == 1
    assert session.pending_player_transition is None
    assert len(session.current_cards) == 1
    assert session.current_cards[0].id != first.id
    assert session.ready_to_advance() is False

    monkeypatch.setattr(session, "_should_start_final_assembly", lambda: False)
    second = session.current_cards[0]
    session.apply_choice(second.id, second.echo_choice_id)
    assert session.ready_to_advance() is True
    session.advance_day()
    assert session.player_state.current_day == 2
    assert session.automated_state.current_day == 2

    early_finish = session_module.GameSession(seed=11)
    for choice_id in ("choice-1", "choice-1", "choice-1", "choice-1"):
        card = early_finish.current_cards[0]
        early_finish.apply_choice(card.id, choice_id)
        if early_finish.ready_to_advance():
            early_finish.advance_day()

    assert early_finish.player_state.current_day == 3
    assert early_finish.questions_answered_today == 0
    assert early_finish.decision_total_today == 2
    final_card = early_finish.current_cards[0]
    in_progress_payload = early_finish.state_payload()

    assert in_progress_payload["timelines"]["player"]["displayCompletion"] == "July 3"
    assert in_progress_payload["timelines"]["player"]["progressPercent"] == 66.6667

    early_finish.apply_choice(final_card.id, "choice-2")

    payload = early_finish.state_payload()
    assert payload["gameOver"] is True
    assert payload["timelines"]["player"]["progressPercent"] == 100.0
    assert payload["decisionProgress"] == {"completed": 1, "total": 2}
    assert payload["decisions"] == []
    assert early_finish.player_state.jobs["JOB-03"].remaining_days == 0
    with pytest.raises(ValueError, match="already ended"):
        early_finish.apply_choice(final_card.id, "choice-2")


def test_exact_optimal_path_ties_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fast_session_config(monkeypatch)
    session = session_module.GameSession(seed=410)

    final = play_to_completion(session)

    assert final["review"]["outcome"] == "tied"
    assert "exact optimal path" in final["review"]["headline"]
    assert final["player"]["completionDay"] == final["automated"]["completionDay"]
    assert final["player"]["finalScore"] == final["automated"]["finalScore"]
    assert final["player"]["unfinishedJobDays"] == final["automated"]["unfinishedJobDays"]
    assert (
        final["automated"]["unfinishedJobDays"]
        == session.decision_web.optimal_unfinished_job_days
    )
    assert all(record.aligned_with_echo for record in session.player_state.decision_history)
    assert len(final["review"]["reasons"]) == 1
    assert "matched ECHO on all" in final["review"]["reasons"][0]
    assert len([final["review"]["headline"], *final["review"]["reasons"]]) <= 3

    with pytest.raises(ValueError, match="already ended"):
        session.apply_choice("finished", "finished")
    session.advance_day()
    assert session.state_payload()["gameOver"] is True


@pytest.mark.parametrize("seed", [402, 411])
def test_every_first_decision_divergence_loses_to_echo(
    monkeypatch: pytest.MonkeyPatch,
    seed: int,
) -> None:
    install_fast_session_config(monkeypatch)
    reference = session_module.GameSession(seed=seed)
    first_card = reference.current_cards[0]
    divergent_ids = [choice.id for choice in first_card.choices if choice.id != first_card.echo_choice_id]
    assert divergent_ids

    for divergent_id in divergent_ids:
        session = session_module.GameSession(seed=seed)
        final = play_to_completion(session, first_choice_id=divergent_id)
        assert final["review"]["outcome"] == "behind"
        assert (
            "prevailed" in final["review"]["headline"].lower()
            or "earlier" in final["review"]["headline"].lower()
            or "higher score" in final["review"]["headline"].lower()
            or "fewer unfinished" in final["review"]["headline"].lower()
        )
        assert any(not record.aligned_with_echo for record in session.player_state.decision_history)
        reasons = final["review"]["reasons"]
        assert reasons
        assert reasons[0].startswith("On day 1, question 1, choosing ")
        assert "instead of" in reasons[0]
        assert any(job.name in reasons[0] for job in session.player_state.jobs.values())
        assert len([final["review"]["headline"], *reasons]) <= 3
        if seed == 402:
            assert "same immediate job-day total" in reasons[0]


@pytest.mark.parametrize("seed", [421, 422, 423, 424, 425, 426])
def test_multi_seed_exact_paths_tie_and_every_first_divergence_loses(
    monkeypatch: pytest.MonkeyPatch,
    seed: int,
) -> None:
    install_fast_session_config(monkeypatch)
    exact = session_module.GameSession(seed=seed)
    exact_final = play_to_completion(exact)
    assert exact_final["review"]["outcome"] == "tied"

    first_card = session_module.GameSession(seed=seed).current_cards[0]
    divergent_ids = [choice.id for choice in first_card.choices if choice.id != first_card.echo_choice_id]
    for choice_id in divergent_ids:
        divergent = session_module.GameSession(seed=seed)
        final = play_to_completion(divergent, first_choice_id=choice_id)
        assert final["review"]["outcome"] == "behind"
        assert any(not record.aligned_with_echo for record in divergent.player_state.decision_history)


def test_slow_route_uses_one_player_only_final_assembly_batch_then_normal_workdays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fast_session_config(
        monkeypatch,
        job_count=2,
        min_job_duration_days=4,
        max_job_duration_days=4,
        max_campaign_day=5,
    )
    session = session_module.GameSession(seed=1)

    guard = 0
    while not session.player_final_assembly_started:
        guard += 1
        assert guard < 50
        if session.current_cards:
            card = session.current_cards[0]
            slowest = min(card.choices, key=lambda choice: (choice.score_delta, choice.id))
            session.apply_choice(card.id, slowest.id)
        elif session.ready_to_advance():
            session.advance_day()
        else:
            raise AssertionError("Slow route stalled before final assembly.")

    assert session.automated_state.final_item_completed
    assert len(session.player_state.incomplete_jobs()) == 1
    assert session.player_state.current_day >= (session.automated_state.completion_day or 0)
    assert session.final_assembly_cards
    assert all(card.player_only for card in session.final_assembly_cards)
    assert all(
        abs(delta) == 1
        for card in session.final_assembly_cards
        for choice in card.choices
        for delta in choice.day_changes.values()
    )
    projected_day = (
        session.player_state.current_day
        + session.player_state.incomplete_jobs()[0].remaining_days
        - 1
    )
    safe_removal_budget = projected_day - (session.automated_state.completion_day or 0) - 1
    accelerating_cards = sum(
        any(
            delta < 0
            for choice in card.choices
            for delta in choice.day_changes.values()
        )
        for card in session.final_assembly_cards
    )
    assert accelerating_cards <= max(0, safe_removal_budget)
    echo_history_count = len(session.automated_state.decision_history)

    while not session.player_final_assembly_locked and not session.player_state.final_item_completed:
        card = session.current_cards[0]
        slowest = min(card.choices, key=lambda choice: (choice.score_delta, choice.id))
        session.apply_choice(card.id, slowest.id)

    final_records = [
        record
        for record in session.player_state.decision_history
        if record.card_id.startswith("FINAL-")
    ]
    assert final_records
    assert all(record.aligned_with_echo is None for record in final_records)
    assert len(session.automated_state.decision_history) == echo_history_count

    if not session.player_state.final_item_completed:
        assert session.current_cards == []
        assert session.ready_to_advance()
        locked_payload = session.state_payload()
        assert locked_payload["dayCycleDurationMs"] == 2_000
        assert locked_payload["dailySummaryCounterDurationMs"] == 500
        remaining_before = session.player_state.incomplete_jobs()[0].remaining_days
        session.advance_day()
        if not session.player_state.final_item_completed:
            assert session.player_state.incomplete_jobs()[0].remaining_days == remaining_before - 1
            assert session.current_cards == []
            assert session.decision_total_today == 0

    while not session.player_state.final_item_completed:
        assert session.current_cards == []
        assert session.ready_to_advance()
        session.advance_day()

    final = session.state_payload()["finalReveal"]
    assert final["review"]["outcome"] == "behind"
    assert session.player_state.completion_day > session.automated_state.completion_day
    final_points = [
        point
        for point in final["completionHistory"]["decisionPoints"]
        if point["playerDecision"]
        and point["playerDecision"]["questionId"].startswith("FINAL-")
    ]
    assert final_points
    assert all(point["echoDecision"] is None for point in final_points)
    assert all(
        "echoPreferredChoice" not in point["playerDecision"]
        for point in final_points
    )


def test_final_payload_aligns_real_player_and_echo_histories(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fast_session_config(monkeypatch)
    session = session_module.GameSession(seed=412)
    first_card = session.current_cards[0]
    divergent = next(choice.id for choice in first_card.choices if choice.id != first_card.echo_choice_id)

    final = play_to_completion(session, first_choice_id=divergent)
    history = final["completionHistory"]

    assert history["decisionPoints"]
    first_point = history["decisionPoints"][0]
    assert first_point["playerDecision"]["choice"] == session.player_state.decision_history[0].choice_label
    assert first_point["echoDecision"]["choice"] == session.automated_state.decision_history[0].choice_label
    assert first_point["playerDecision"]["affectedLabel"].startswith("Job")
    assert first_point["playerDecision"]["echoSituationMatches"] is True
    assert first_point["playerDecision"]["echoEventMatches"] is True
    assert first_point["playerDecision"]["echoComparisonState"] == "same-context"
    assert first_point["playerDecision"]["echoPreferenceState"] == "same-context-different-choice"
    assert first_point["playerDecision"]["echoPreferenceBasis"] == (
        "completion-day-then-score-then-unfinished-work"
    )
    player_card = session.player_state.decision_cards[
        session.player_state.decision_history[0].card_id
    ]
    echo_card = session.automated_state.decision_cards[
        session.automated_state.decision_history[0].card_id
    ]
    assert _echo_comparison_state(player_card, echo_card) == "same-context"
    assert _echo_comparison_state(
        replace(player_card, event_id="shared-event", primary_job_id="JOB-01"),
        replace(echo_card, event_id="shared-event", primary_job_id="JOB-02"),
    ) == "same-event-different-context"
    assert _echo_comparison_state(
        replace(player_card, event_id="player-event"),
        replace(echo_card, event_id="echo-event"),
    ) == "different-events"


def test_timeline_stops_rescaling_after_echo_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fast_session_config(monkeypatch)
    session = session_module.GameSession(seed=413)
    final = play_to_completion(session)
    payload = session.state_payload()

    assert final["automated"]["completionDay"] is not None
    assert payload["timelines"]["echo"]["progressPercent"] == 100.0
    assert payload["timelines"]["echo"]["displayCompletion"] == final["automated"]["completion"]


def test_session_store_serializes_duplicate_concurrent_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fast_session_config(monkeypatch)
    store = session_module.SessionStore(seed=414)
    card = store.session.current_cards[0]
    choice = card.choices[0]
    barrier = threading.Barrier(2)
    results: list[tuple[str, object]] = []

    def choose_once() -> None:
        barrier.wait(timeout=2)
        try:
            results.append(("ok", store.choice_payload(card.id, choice.id)))
        except ValueError as exc:
            results.append(("error", str(exc)))

    threads = [threading.Thread(target=choose_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert [kind for kind, _ in results].count("ok") == 1
    assert [kind for kind, _ in results].count("error") == 1
    assert len(store.session.player_state.decision_history) == 1


@pytest.mark.parametrize("value, expected", [(None, None), ("", None), (" 007 ", 7), (42, 42), (-2, -2)])
def test_parse_optional_seed_accepts_supported_values(value: object, expected: int | None) -> None:
    assert _parse_optional_seed(value) == expected


@pytest.mark.parametrize("value", [True, False, 4.2, "4.2", "abc"])
def test_parse_optional_seed_rejects_non_integers(value: object) -> None:
    with pytest.raises(ValueError, match="Seed must be an integer"):
        _parse_optional_seed(value)


class HandlerHarness:
    def __init__(self, method: str, path: str, payload: object = None, raw_body: bytes | None = None):
        self.method = method
        self.path = path
        body = raw_body if raw_body is not None else (json.dumps(payload).encode() if payload is not None else b"")
        self.headers = {"content-length": str(len(body))}
        self.rfile = BytesIO(body)
        self.wfile = BytesIO()
        self.response_status = 0
        self.response_headers: dict[str, str] = {}

    def send_response(self, status: HTTPStatus) -> None:
        self.response_status = int(status)

    def send_header(self, name: str, value: str) -> None:
        self.response_headers[name.lower()] = value

    def end_headers(self) -> None:
        return None

    def body_json(self) -> dict:
        return json.loads(self.wfile.getvalue().decode())


def handler_type(store: object):
    return type("TestHandler", (HandlerHarness, GameRequestHandler), {"session_store": store})


def dispatch(handler: HandlerHarness) -> None:
    if handler.method == "GET":
        handler.do_GET()
    else:
        handler.do_POST()


def test_request_handler_routes_state_actions_html_and_not_found() -> None:
    class FakeStore:
        def state_payload(self):
            return {"route": "state"}

        def new_session_payload(self, seed=None):
            return {"route": "new", "seed": seed}

        def choice_payload(self, card_id, choice_id):
            return {"route": "choice", "ids": [card_id, choice_id]}

        def advance_payload(self):
            return {"route": "advance"}

    Handler = handler_type(FakeStore())
    cases = [
        (Handler("GET", "/api/state"), 200, {"route": "state"}),
        (Handler("POST", "/api/new", {"seed": "12"}), 200, {"route": "new", "seed": 12}),
        (Handler("POST", "/api/choice", {"cardId": "C", "choiceId": "A"}), 200, {"route": "choice", "ids": ["C", "A"]}),
        (Handler("POST", "/api/advance", {}), 200, {"route": "advance"}),
        (Handler("GET", "/missing"), 404, {"error": "Not found"}),
    ]
    for handler, status, payload in cases:
        dispatch(handler)
        assert handler.response_status == status
        assert handler.body_json() == payload

    root = Handler("GET", "/")
    dispatch(root)
    assert root.response_status == 200
    assert root.response_headers["content-type"].startswith("text/html")
    assert b"/ui/app.js" in root.wfile.getvalue()


def test_request_handler_reports_bad_input_and_serves_declared_static_assets() -> None:
    class FakeStore:
        def new_session_payload(self, seed=None):
            return {"seed": seed}

    Handler = handler_type(FakeStore())
    malformed = Handler("POST", "/api/new", raw_body=b'{"seed":')
    dispatch(malformed)
    assert malformed.response_status == 400
    assert "Expecting value" in malformed.body_json()["error"]

    bad_seed = Handler("POST", "/api/new", {"seed": True})
    dispatch(bad_seed)
    assert bad_seed.response_status == 400
    assert bad_seed.body_json() == {"error": "Seed must be an integer."}

    for path, (content_type, asset_path) in STATIC_ASSETS.items():
        handler = Handler("GET", path)
        dispatch(handler)
        assert handler.response_status == 200
        assert handler.response_headers["content-type"] == content_type
        assert int(handler.response_headers["content-length"]) == asset_path.stat().st_size


def test_live_http_server_supports_a_complete_exact_path_playthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fast_session_config(monkeypatch)
    store = session_module.SessionStore(seed=501)
    Handler = type("LiveTestHandler", (GameRequestHandler,), {"session_store": store})
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    def request_json(path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            f"{base_url}{path}",
            data=body,
            headers={"content-type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        with urlopen(request, timeout=3) as response:
            assert response.status == 200
            return json.loads(response.read().decode())

    try:
        with urlopen(f"{base_url}/", timeout=3) as response:
            assert response.status == 200
            assert b"/ui/app.js" in response.read()

        state = request_json("/api/state")
        assert state["seed"] == 501
        while not state["gameOver"]:
            if state["decisions"]:
                card = state["decisions"][0]
                echo_choice_id = store.session.current_cards[0].echo_choice_id
                state = request_json(
                    "/api/choice",
                    {"cardId": card["id"], "choiceId": echo_choice_id},
                )
            elif state["decisionProgress"]["completed"] == state["decisionProgress"]["total"]:
                state = request_json("/api/advance", {})
            else:
                raise AssertionError("Exact HTTP run has no decision or ready workday.")

        assert state["finalReveal"]["review"]["outcome"] == "tied"
        assert all(tile["completed"] for tile in state["livePuzzle"]["tiles"])

        state = request_json("/api/new", {"seed": 502})
        assert state["seed"] == 502
        assert state["day"] == 1
        assert state["gameOver"] is False
        first_card = store.session.current_cards[0]
        divergent_choice = next(
            choice.id for choice in first_card.choices if choice.id != first_card.echo_choice_id
        )
        first_decision = True
        while not state["gameOver"]:
            if state["decisions"]:
                card = state["decisions"][0]
                choice_id = (
                    divergent_choice
                    if first_decision
                    else store.session.current_cards[0].echo_choice_id
                )
                first_decision = False
                state = request_json(
                    "/api/choice",
                    {"cardId": card["id"], "choiceId": choice_id},
                )
            elif state["decisionProgress"]["completed"] == state["decisionProgress"]["total"]:
                state = request_json("/api/advance", {})
            else:
                raise AssertionError("Divergent HTTP run has no decision or ready workday.")
        assert state["finalReveal"]["review"]["outcome"] == "behind"

        bad_request = Request(
            f"{base_url}/api/new",
            data=json.dumps({"seed": True}).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(bad_request, timeout=3)
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert not thread.is_alive()
