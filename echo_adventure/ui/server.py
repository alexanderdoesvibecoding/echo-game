"""Local browser UI server for ECHO Adventure."""

from __future__ import annotations

import argparse
import copy
import json
import math
import threading
from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from ..config import GameConfig, resolve_seed
from ..decisions import apply_choice, generate_decision_cards
from ..enums import JobStatus, TargetType, WorkCenterStatus
from ..metrics import calculate_snapshot, day_shift, update_state_metrics
from ..models import DecisionCard, DecisionChoice, Event, MetricSnapshot, SimulationState
from ..scenario_generator import generate_scenario
from ..schedulers.automated import AutomatedScheduler
from ..schedulers.manual import ManualScheduler
from ..simulation import DayResult, advance_day, initialize_state
from .view import INDEX_HTML


# GameSession is the stateful bridge between stateless HTTP requests and the
# mutable simulation engine. One process hosts one active session at a time.
class GameSession:
    """Owns one playable browser run and its hidden automated benchmark run.

    The browser server is threaded, so every public mutation/read takes the
    session lock. The player and automated states are initialized from the same
    scenario so the final reveal compares scheduling policy, not scenario luck.
    """

    def __init__(
        self,
        seed: int | None = None,
        demo: bool = False,
        settings: dict[str, Any] | None = None,
        mode: str | None = None,
    ) -> None:
        # RLock allows helper methods called inside locked public methods to
        # safely reuse the same lock if the implementation grows later.
        self.lock = threading.RLock()
        # Resolve random seeds immediately so the UI can always display and
        # replay the exact generated scenario.
        self.seed = resolve_seed(seed)
        self.demo = demo
        base_config = GameConfig.demo(seed=self.seed) if demo else GameConfig(seed=self.seed)
        self.config = _apply_config_settings(base_config, settings or {})
        self.mode = mode or ("demo" if demo else "normal")
        # Both schedulers share a scenario but mutate independent state copies.
        self.scenario = generate_scenario(self.config)
        self.player_state = initialize_state(self.scenario, self.config.shifts_per_day)
        self.automated_state = initialize_state(self.scenario, self.config.shifts_per_day)
        # Manual scheduler reflects player-driven priorities; automated is the
        # hidden ECHO benchmark revealed at the end.
        self.manual_scheduler = ManualScheduler()
        self.automated_scheduler = AutomatedScheduler()
        # Cards/choices are tracked at the session layer because they are a UI
        # interaction contract layered over the underlying simulation state.
        self.current_cards: list[DecisionCard] = []
        self.applied_choices: dict[str, str] = {}
        self.choice_notes: list[str] = []
        self.last_result: DayResult | None = None
        self._ensure_cards()

    def state_payload(self) -> dict[str, Any]:
        """Return the complete JSON model needed by the browser dashboard."""
        with self.lock:
            # Metrics can be invalidated by choices and event handling, so they
            # are refreshed every time the browser asks for state.
            update_state_metrics(self.player_state)
            self._ensure_cards()
            snapshot = calculate_snapshot(self.player_state)
            game_over = self._game_over()
            # Keep payload fields deliberately flat and table-oriented. The
            # frontend is plain JavaScript, so it benefits from data shaped
            # close to the rows and panels it renders.
            payload: dict[str, Any] = {
                "seed": self.seed,
                "mode": self.mode,
                "settings": _settings_payload(self.config),
                "scenarioId": self.scenario.scenario_id,
                "gameOver": game_over,
                "day": self.player_state.current_day,
                "shift": self.player_state.current_shift,
                "shiftLabel": day_shift(max(1, self.player_state.current_shift), self.config.shifts_per_day),
                "deadlineLabel": day_shift(self.player_state.deadline_shift, self.config.shifts_per_day),
                "snapshot": _snapshot_payload(snapshot, self.config.shifts_per_day),
                "overview": self._overview(snapshot),
                "shops": self._shops_payload(),
                "dailyCalendar": self._daily_calendar_payload(),
                "pieces": self._pieces_payload(),
                "workcenters": self._workcenters_payload(),
                "criticalPath": self._critical_path_payload(),
                "risks": self._risk_payload(),
                "decisions": [_card_payload(card, self.applied_choices.get(card.id)) for card in self.current_cards],
                "appliedChoices": self.choice_notes[-6:],
                "lastSummary": self._summary_payload(),
            }
            if game_over:
                # The automated state is lazy-finished only when it is needed
                # for the final reveal, keeping normal requests cheap.
                self._finish_automated()
                payload["finalReveal"] = self._final_payload()
            return payload

    def apply_choice(self, card_id: str, choice_id: str) -> dict[str, Any]:
        """Apply one response to one active decision card."""
        with self.lock:
            # Guard all invalid interaction states server-side. The browser also
            # disables buttons, but the server is the rule authority.
            if self._game_over():
                raise ValueError("The run has already ended.")
            self._ensure_cards()
            card = next((candidate for candidate in self.current_cards if candidate.id == card_id), None)
            if not card:
                raise ValueError("Decision card is no longer active.")
            if card.id in self.applied_choices:
                raise ValueError("That decision already has a selected response.")
            choice = next((candidate for candidate in card.choices if candidate.id == choice_id), None)
            if not choice:
                raise ValueError("Choice is not valid for that decision.")
            # Decision effects can mutate current queues and future event
            # chains. The returned note is the human-readable audit trail.
            note = apply_choice(self.player_state, card, choice)
            self.applied_choices[card.id] = choice.id
            self.choice_notes.append(f"{card.title}: {choice.label}. {note}")
            return {"note": note, "allDecisionsMade": self.ready_to_advance()}

    def advance_day(self) -> dict[str, Any]:
        """Advance both player and benchmark simulations by one in-game day."""
        with self.lock:
            if self._game_over():
                self._finish_automated()
                return {"summary": self._summary_payload(), "gameOver": True}
            self._ensure_cards()
            if not self.ready_to_advance():
                raise ValueError("Select a response for all decisions before advancing the day.")
            # Daily notes are scoped to the just-advanced day. Choice notes are
            # kept separately until the day is committed, then reset with cards.
            self.player_state.daily_notes.clear()
            self.last_result = advance_day(self.player_state, self.manual_scheduler)
            # The automated scheduler advances silently alongside the player so
            # it faces the same random event timeline.
            advance_day(self.automated_state, self.automated_scheduler)
            # A new day means fresh decision cards and no selected choices.
            self.current_cards = []
            self.applied_choices = {}
            self.choice_notes = []
            if self._game_over():
                self._finish_automated()
            else:
                self._ensure_cards()
            return {"summary": self._summary_payload(), "gameOver": self._game_over()}

    def ready_to_advance(self) -> bool:
        """Return whether every current daily decision has a selected choice."""
        return len(self.current_cards) == 0 or all(card.id in self.applied_choices for card in self.current_cards)

    def _ensure_cards(self) -> None:
        if self.current_cards or self._game_over():
            return
        # Cards are generated lazily so a fresh state payload always has the
        # current day's required decisions, including newly visible warnings.
        self.current_cards = generate_decision_cards(self.player_state, self.player_state.current_day, self.config)

    def _game_over(self) -> bool:
        """The run ends at project completion or the configured deadline."""
        return self.player_state.final_item_completed or self.player_state.current_shift >= self.player_state.deadline_shift

    def _finish_automated(self) -> None:
        # The benchmark is hidden during play. At game over, fast-forward it
        # through the same deadline so the reveal has a complete comparison.
        while self.automated_state.current_shift < self.automated_state.deadline_shift and not self.automated_state.final_item_completed:
            self.automated_state.daily_notes.clear()
            advance_day(self.automated_state, self.automated_scheduler)

    def _overview(self, snapshot: MetricSnapshot) -> dict[str, Any]:
        """Build the compact header/overview payload for the dashboard."""
        # Active and warning counts are pulled from event ids tracked on state;
        # the event objects contain the display text and severity details.
        active = [event for event in self.player_state.event_timeline if event.id in self.player_state.active_events]
        warnings = [event for event in self.player_state.event_timeline if event.id in self.player_state.known_warnings]
        bottlenecks = self.player_state.get_bottleneck_shops(3)
        return {
            "activeDisruptions": len(active),
            "knownWarnings": len(warnings),
            "bottlenecks": [shop.name for shop in bottlenecks],
            "projectedCompletion": day_shift(snapshot.projected_completion_shift, self.config.shifts_per_day),
            "finalComplete": self.player_state.final_item_completed,
            "completion": day_shift(self.player_state.completion_shift or 0, self.config.shifts_per_day)
            if self.player_state.completion_shift
            else None,
        }

    def _shops_payload(self) -> list[dict[str, Any]]:
        """Return one row per shop for the Shops operating-board table."""
        return [
            {
                "id": shop.id,
                "name": shop.name,
                "active": len(shop.active_job_ids),
                "queued": len(shop.queued_job_ids),
                "blocked": len(shop.blocked_job_ids),
                "completed": len(shop.completed_job_ids),
                "utilization": round(shop.utilization, 3),
                "idle": shop.idle_time,
                "risk": round(shop.risk_score, 1),
                "highestRiskPiece": _highest_risk_piece(self.player_state, shop.id),
                "bottleneck": len(shop.queued_job_ids) + len(shop.blocked_job_ids) >= 5,
                "event": _shop_event_label(self.player_state, shop.id),
            }
            for shop in self.player_state.shops.values()
        ]

    def _pieces_payload(self) -> list[dict[str, Any]]:
        """Return top-level job rows plus nested subjob rows for drill-down modals."""
        pieces = []
        # Highest-risk jobs are listed first in the payload; the browser later
        # sorts by internal id for the default table, but risk ordering is still
        # useful to callers and future views.
        for piece in sorted(self.player_state.pieces.values(), key=lambda item: (-item.risk_score, item.id)):
            blocked = sum(1 for job_id in piece.job_ids if self.player_state.jobs[job_id].is_blocked)
            critical = any(self.player_state.jobs[job_id].critical_path for job_id in piece.job_ids)
            last_job = self.player_state.jobs[piece.job_ids[-1]] if piece.job_ids else None
            piece_jobs: list[dict[str, Any]] = []
            for job_id in piece.job_ids:
                job = self.player_state.jobs[job_id]
                # Resolve display names here so the frontend does not need to
                # join subjobs back to shops/workcenters.
                wc = self.player_state.workcenters.get(job.assigned_workcenter_id) if job.assigned_workcenter_id else None
                shop = self.player_state.shops.get(job.shop_id)
                piece_jobs.append(
                    {
                        "id": job.id,
                        "status": job.status.value,
                        "shop": shop.name if shop else job.shop_id,
                        "workcenter": wc.id if wc else "-",
                        "capability": job.required_capability,
                        "remaining": job.remaining_duration_shifts,
                        "planned": job.planned_duration,
                        "due": day_shift(job.due_shift, self.config.shifts_per_day),
                        "blocked": job.is_blocked,
                        "blockReason": job.block_reason or "",
                        "critical": job.critical_path,
                        "rework": job.rework_count > 0 or job.status == JobStatus.REWORK_REQUIRED,
                    }
                )
            pieces.append(
                {
                    "id": piece.id,
                    "displayId": _piece_display_id(piece.id),
                    "name": piece.name,
                    "status": piece.status.value,
                    "completed": piece.completed_job_count,
                    "total": piece.total_job_count,
                    "progress": round(piece.percent_complete, 3),
                    "blocked": blocked,
                    "critical": critical,
                    "dueDate": day_shift(last_job.due_shift, self.config.shifts_per_day) if last_job else "-",
                    "risk": round(piece.risk_score, 1),
                    "jobs": piece_jobs,
                }
            )
        return pieces

    def _workcenters_payload(self) -> dict[str, list[dict[str, Any]]]:
        """Return workcenter rows grouped by shop id for the Workcenters tab."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        for shop in self.player_state.shops.values():
            rows = []
            for wc_id in shop.workcenter_ids:
                wc = self.player_state.workcenters[wc_id]
                current = wc.current_job_id
                current_job = self.player_state.jobs.get(current) if current else None
                next_job = self.player_state.jobs.get(wc.queue[0]) if wc.queue else None
                # Rework flags are calculated for current/next subjobs separately
                # so the UI can add a compact red marker next to subjob ids.
                rows.append(
                    {
                        "id": wc.id,
                        "name": wc.name,
                        "status": wc.status.value,
                        "current": current or "-",
                        "currentRework": bool(
                            current_job
                            and (current_job.rework_count > 0 or current_job.status == JobStatus.REWORK_REQUIRED)
                        ),
                        "remaining": current_job.remaining_duration_shifts if current_job else "-",
                        "queue": len(wc.queue),
                        "next": wc.queue[0] if wc.queue else "-",
                        "nextRework": bool(
                            next_job and (next_job.rework_count > 0 or next_job.status == JobStatus.REWORK_REQUIRED)
                        ),
                        "capability": ", ".join(cap.replace("_", " ") for cap in wc.capabilities[:2]),
                        "down": wc.downtime_remaining or "-",
                    }
                )
            grouped[shop.id] = rows
        return grouped

    def _daily_calendar_payload(self) -> dict[str, Any]:
        """Return a non-mutating preview of jobs scheduled across today's shifts."""
        preview = copy.deepcopy(self.player_state)
        update_state_metrics(preview)
        known_events = [
            event
            for event in preview.event_timeline
            if event.id in preview.known_warnings or event.id in preview.active_events
        ]
        ManualScheduler().plan_day(preview, known_events)

        day = preview.current_day
        day_start_shift = (day - 1) * self.config.shifts_per_day
        shifts: list[dict[str, Any]] = [
            {
                "index": shift_index + 1,
                "label": f"Shift {shift_index + 1}",
                "dayLabel": day_shift(day_start_shift + shift_index + 1, self.config.shifts_per_day),
                "jobs": [],
            }
            for shift_index in range(self.config.shifts_per_day)
        ]
        active_by_wc: dict[str, str | None] = {}
        remaining_by_wc: dict[str, int] = {}
        status_by_wc: dict[str, str] = {}
        queues_by_wc = {wc.id: list(wc.queue) for wc in preview.workcenters.values()}

        for wc in preview.workcenters.values():
            if wc.current_job_id and wc.current_job_id in preview.jobs and wc.status == WorkCenterStatus.BUSY:
                active_by_wc[wc.id] = wc.current_job_id
                remaining_by_wc[wc.id] = max(1, preview.jobs[wc.current_job_id].remaining_duration_shifts)
                status_by_wc[wc.id] = "Running"
            else:
                active_by_wc[wc.id] = None
                remaining_by_wc[wc.id] = 0
                status_by_wc[wc.id] = ""

        for shift in shifts:
            for shop in preview.shops.values():
                for wc_id in shop.workcenter_ids:
                    wc = preview.workcenters[wc_id]
                    job_id = active_by_wc[wc.id]
                    if job_id is None:
                        if wc.status not in {WorkCenterStatus.AVAILABLE, WorkCenterStatus.IDLE}:
                            continue
                        job_id = _next_calendar_job(preview, wc, queues_by_wc[wc.id])
                        if job_id is None:
                            continue
                        active_by_wc[wc.id] = job_id
                        remaining_by_wc[wc.id] = _calendar_duration(preview.jobs[job_id], wc)
                        status_by_wc[wc.id] = "Scheduled"

                    job = preview.jobs[job_id]
                    shift["jobs"].append(
                        _calendar_job_payload(
                            preview,
                            job,
                            wc,
                            shop.name,
                            status_by_wc[wc.id],
                            remaining_by_wc[wc.id],
                        )
                    )
                    remaining_by_wc[wc.id] = max(0, remaining_by_wc[wc.id] - 1)
                    if remaining_by_wc[wc.id] == 0:
                        active_by_wc[wc.id] = None
                        status_by_wc[wc.id] = ""

        return {
            "day": day,
            "label": f"Day {day}",
            "shifts": shifts,
        }

    def _critical_path_payload(self) -> list[dict[str, Any]]:
        """Return critical-path rows capped for a readable dashboard table."""
        rows = []
        for job in self.player_state.get_critical_path_jobs()[:18]:
            wc = self.player_state.workcenters.get(job.assigned_workcenter_id) if job.assigned_workcenter_id else None
            shop = self.player_state.shops.get(job.shop_id)
            # Slack is recalculated for display from current shift and remaining
            # work so it reflects choices/events made earlier in the same day.
            slack = job.due_shift - self.player_state.current_shift - max(0, job.remaining_duration_shifts)
            rows.append(
                {
                    "id": job.id,
                    "shop": shop.name if shop else job.shop_id,
                    "workcenter": wc.id if wc else "-",
                    "remaining": job.remaining_duration_shifts,
                    "slack": slack,
                    "block": job.block_reason or "-",
                    "impact": _piece_display_id(job.piece_id),
                    "risk": round(job.risk_score, 1),
                    "rework": job.rework_count > 0 or job.status == JobStatus.REWORK_REQUIRED,
                }
            )
        return rows

    def _risk_payload(self) -> list[dict[str, Any]]:
        """Return active warnings/disruptions plus blocked subjobs for risk review."""
        rows = []
        for event in self.player_state.event_timeline:
            if event.id not in self.player_state.active_events and event.id not in self.player_state.known_warnings:
                continue
            # Source identifies event-chain ancestry. It is "-" for base
            # timeline events and an event id for follow-on/cascade events.
            status = "Active" if event.id in self.player_state.active_events else "Warning"
            shifts = max(0, event.end_shift - self.player_state.current_shift) if status == "Active" else max(0, event.start_shift - self.player_state.current_shift)
            rows.append(
                {
                    "status": status,
                    "id": event.id,
                    "type": event.type.value,
                    "affected": _event_target_name(self.player_state, event),
                    "severity": event.severity,
                    "shifts": shifts,
                    "response": _response_category(event.type.value),
                    "source": event.parent_event_id or "-",
                    "rework": bool(
                        event.target_id in self.player_state.jobs
                        and self.player_state.jobs[event.target_id].rework_count > 0
                    ),
                }
            )
        for job in self.player_state.get_blocked_jobs()[:12]:
            # Blocked subjobs are shown alongside events because they require the
            # same scheduling attention even when they are not event objects.
            rows.append(
                {
                    "status": "Blocked",
                    "id": job.id,
                    "type": "Subjob block",
                    "affected": _piece_display_id(job.piece_id),
                    "severity": round(job.risk_score, 1),
                    "shifts": "-",
                    "response": "mitigation recommended",
                    "source": "-",
                    "rework": job.rework_count > 0 or job.status == JobStatus.REWORK_REQUIRED,
                }
            )
        return rows

    def _summary_payload(self) -> dict[str, Any] | None:
        """Return the latest end-of-day summary, if a day has advanced."""
        if not self.last_result:
            return None
        snapshot = self.last_result.end_snapshot
        return {
            "completedToday": len(self.last_result.completed_job_ids),
            "jobsRemaining": snapshot.jobs_remaining,
            "piecesCompleted": snapshot.pieces_completed,
            "jobsLate": snapshot.jobs_late,
            "reschedules": snapshot.reschedules,
            "cost": round(snapshot.cost, 1),
            "utilization": round(snapshot.utilization, 3),
            "idleTime": snapshot.idle_time,
            "risk": round(snapshot.schedule_risk, 1),
            "projectedCompletion": day_shift(snapshot.projected_completion_shift, self.config.shifts_per_day),
            "notes": self.last_result.notes[-10:],
        }

    def _final_payload(self) -> dict[str, Any]:
        """Return the final player-vs-ECHO comparison payload."""
        player_snapshot = calculate_snapshot(self.player_state)
        automated_snapshot = calculate_snapshot(self.automated_state)
        return {
            "player": _snapshot_payload(player_snapshot, self.config.shifts_per_day, self.player_state),
            "automated": _snapshot_payload(automated_snapshot, self.config.shifts_per_day, self.automated_state),
            "explanation": [
                "ECHO continuously reprioritized critical-path work instead of waiting for daily manual decisions.",
                "It used alternate capable workcenters when queue pressure or downtime threatened slack.",
                "It reacted to warnings by pulling forward unaffected work and reducing bottleneck idle time.",
                "It avoided unnecessary preemption while still resequencing around blocked subjobs quickly.",
                "Those behaviors reduced cascading delay, cost pressure, and end-of-run schedule risk.",
            ],
        }


class GameRequestHandler(BaseHTTPRequestHandler):
    """Small JSON/HTML request handler for the local-only browser app."""

    # The dynamically-created subclass in run_ui_server attaches a GameSession
    # here so every request handler instance shares the same current run.
    session: GameSession

    def do_GET(self) -> None:
        """Serve the shell HTML or the current JSON state."""
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(INDEX_HTML)
        elif parsed.path == "/api/state":
            self._send_json(self.session.state_payload())
        else:
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        """Handle state-changing UI actions."""
        parsed = urlparse(self.path)
        try:
            # This intentionally tiny API mirrors the UI's workflow:
            # create/read a run, apply decisions, then advance days.
            if parsed.path == "/api/new":
                data = self._read_json()
                seed = data.get("seed")
                if seed in ("", None):
                    seed = None
                else:
                    seed = int(seed)
                mode = str(data.get("mode", "normal")).lower()
                settings = data.get("settings")
                type(self).session = GameSession(
                    seed=seed,
                    demo=mode == "demo",
                    settings=settings if isinstance(settings, dict) else None,
                    mode=mode if mode in {"normal", "demo", "custom"} else None,
                )
                self._send_json(type(self).session.state_payload())
            elif parsed.path == "/api/choice":
                data = self._read_json()
                result = self.session.apply_choice(str(data.get("cardId", "")), str(data.get("choiceId", "")))
                state = self.session.state_payload()
                state["action"] = result
                self._send_json(state)
            elif parsed.path == "/api/advance":
                result = self.session.advance_day()
                state = self.session.state_payload()
                state["advance"] = result
                self._send_json(state)
            else:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - defensive local server path
            self._send_json({"error": f"Server error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy per-request logs; the UI is local and stateful, and
        # request spam makes terminal output harder to use while developing.
        return

    def _read_json(self) -> dict[str, Any]:
        """Read a JSON request body, treating empty bodies as empty objects."""
        length = int(self.headers.get("content-length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        """Serialize and send a JSON response with explicit length headers."""
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        """Send the inline HTML shell."""
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_ui_server(seed: int | None = None, host: str = "127.0.0.1", port: int = 8765, demo: bool = False) -> None:
    """Start the local browser UI server."""
    # A fresh handler subclass lets us attach a mutable class-level session
    # without modifying BaseHTTPRequestHandler itself.
    handler = type("SessionHandler", (GameRequestHandler,), {})
    handler.session = GameSession(seed=seed, demo=demo)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}"
    mode_label = "demo" if demo else "normal"
    print(f"ECHO Adventure UI running at {url} ({mode_label} mode)")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for running only the browser UI server."""
    parser = argparse.ArgumentParser(description="Run the local ECHO Adventure browser UI.")
    parser.add_argument("--seed", type=int, help="Run a reproducible scenario seed.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for the local UI server.")
    parser.add_argument("--port", type=int, default=8765, help="Port for the local UI server.")
    parser.add_argument("--demo", action="store_true", help="Start with the short five-day demo scenario.")
    args = parser.parse_args(argv)
    run_ui_server(seed=args.seed, host=args.host, port=args.port, demo=args.demo)


def _snapshot_payload(snapshot: MetricSnapshot, shifts_per_day: int, state: SimulationState | None = None) -> dict[str, Any]:
    """Convert a MetricSnapshot into frontend-friendly camelCase fields."""
    completion_shift = state.completion_shift if state else None
    return {
        "shift": snapshot.shift,
        "day": snapshot.day,
        "piecesCompleted": snapshot.pieces_completed,
        "jobsCompleted": snapshot.jobs_completed,
        "jobsRemaining": snapshot.jobs_remaining,
        "jobsLate": snapshot.jobs_late,
        "utilization": round(snapshot.utilization, 3),
        "idleTime": snapshot.idle_time,
        "reschedules": snapshot.reschedules,
        "cost": round(snapshot.cost, 1),
        "scheduleRisk": round(snapshot.schedule_risk, 1),
        "projectedCompletionShift": snapshot.projected_completion_shift,
        "projectedCompletion": day_shift(snapshot.projected_completion_shift, shifts_per_day),
        "finalItemCompleted": snapshot.final_item_completed,
        "deadlineMet": snapshot.deadline_met,
        "completion": day_shift(completion_shift, shifts_per_day) if completion_shift else None,
    }


def _apply_config_settings(config: GameConfig, settings: dict[str, Any]) -> GameConfig:
    """Apply user-entered new-run settings to a preset config."""
    values: dict[str, int] = {}
    bounds = {
        "total_days": (1, 90),
        "piece_count": (1, 30),
        "min_jobs_per_piece": (1, 20),
        "max_jobs_per_piece": (1, 20),
    }
    for key, (minimum, maximum) in bounds.items():
        if key not in settings or settings[key] in ("", None):
            continue
        try:
            value = int(settings[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key.replace('_', ' ').title()} must be a whole number.") from exc
        if value < minimum or value > maximum:
            raise ValueError(f"{key.replace('_', ' ').title()} must be between {minimum} and {maximum}.")
        values[key] = value
    min_jobs = values.get("min_jobs_per_piece", config.min_jobs_per_piece)
    max_jobs = values.get("max_jobs_per_piece", config.max_jobs_per_piece)
    if min_jobs > max_jobs:
                raise ValueError("Minimum subjobs per job cannot be greater than maximum subjobs per job.")
    return replace(config, **values)


def _settings_payload(config: GameConfig) -> dict[str, int]:
    """Return editable new-run settings for the browser modal."""
    return {
        "totalDays": config.total_days,
        "pieceCount": config.piece_count,
        "minJobsPerPiece": config.min_jobs_per_piece,
        "maxJobsPerPiece": config.max_jobs_per_piece,
    }


def _card_payload(card: DecisionCard, selected_choice: str | None) -> dict[str, Any]:
    """Convert a decision card into the shape rendered by the modal UI."""
    return {
        "id": card.id,
        "type": card.type.value,
        "title": card.title,
        "description": card.description,
        "severity": card.severity,
        "selectedChoice": selected_choice,
        "choices": [_choice_payload(choice) for choice in card.choices],
    }


def _choice_payload(choice: DecisionChoice) -> dict[str, Any]:
    """Convert a decision choice while preserving simulation effect hints."""
    return {
        "id": choice.id,
        "label": choice.label,
        "description": choice.description,
        "riskEffect": choice.risk_effect,
        "costEffect": choice.cost_effect,
        "rescheduleEffect": choice.reschedule_effect,
    }


def _next_calendar_job(state: SimulationState, wc, queue: list[str]) -> str | None:
    """Pop the next queue job that could actually start on this workcenter."""
    while queue:
        job_id = queue.pop(0)
        if job_id not in state.jobs:
            continue
        job = state.jobs[job_id]
        if job.status in {JobStatus.COMPLETE, JobStatus.CANCELLED}:
            continue
        if job.block_reason or not state.is_dependency_complete(job_id):
            continue
        if job.required_capability not in wc.capabilities:
            continue
        return job_id
    return None


def _calendar_duration(job, wc) -> int:
    """Estimate how many shifts a queued job will occupy on the chosen workcenter."""
    if job.started_once:
        return max(1, job.remaining_duration_shifts)
    duration = max(1, math.ceil(job.planned_duration / max(0.2, wc.efficiency)))
    if wc.id != job.candidate_workcenter_ids[0]:
        duration += 1
    return duration


def _calendar_job_payload(
    state: SimulationState,
    job,
    wc,
    shop_name: str,
    status: str,
    remaining: int,
) -> dict[str, Any]:
    """Convert one scheduled subjob occurrence into a daily calendar card."""
    piece = state.pieces.get(job.piece_id)
    return {
        "id": job.id,
        "piece": _piece_display_id(job.piece_id),
        "pieceName": piece.name if piece else "Project",
        "shop": shop_name,
        "workcenter": wc.id,
        "workcenterName": wc.name,
        "capability": job.required_capability.replace("_", " "),
        "status": status,
        "remaining": max(1, remaining),
        "due": day_shift(job.due_shift, state.shifts_per_day),
        "late": state.current_shift > job.due_shift,
        "critical": job.critical_path,
        "risk": round(job.risk_score, 1),
        "rework": job.rework_count > 0 or job.status == JobStatus.REWORK_REQUIRED,
    }


def _highest_risk_piece(state: SimulationState, shop_id: str) -> str:
    """Return a compact highest-risk job label for one shop row."""
    piece_scores: dict[str, float] = {}
    for job in state.jobs.values():
        if job.shop_id == shop_id and job.piece_id in state.pieces and not job.is_complete:
            piece_scores[job.piece_id] = max(piece_scores.get(job.piece_id, 0.0), job.risk_score)
    if not piece_scores:
        return "-"
    piece_id = max(piece_scores, key=piece_scores.get)
    return f"{_piece_display_id(piece_id)} ({piece_scores[piece_id]:.0f})"


def _piece_display_id(piece_id: str) -> str:
    """Convert an internal piece id into the player-facing top-level job label."""
    suffix = piece_id.split("-")[-1] if piece_id else ""
    return f"Job {suffix}" if suffix else "Job"


def _shop_event_label(state: SimulationState, shop_id: str) -> str:
    """Return active event labels affecting a shop or its workcenters."""
    labels = []
    for event in state.event_timeline:
        if event.id not in state.active_events:
            continue
        if event.target_id == shop_id:
            labels.append(event.type.value)
        elif event.target_id in state.workcenters and state.workcenters[event.target_id].shop_id == shop_id:
            labels.append(event.type.value)
    return ", ".join(labels[:2])


def _event_target_name(state: SimulationState, event: Event) -> str:
    """Resolve an event target id into a human-readable UI label."""
    if event.target_type == TargetType.SHOP and event.target_id in state.shops:
        return state.shops[event.target_id].name
    if event.target_type == TargetType.WORKCENTER and event.target_id in state.workcenters:
        return state.workcenters[event.target_id].name
    if event.target_type == TargetType.PIECE and event.target_id in state.pieces:
        return state.pieces[event.target_id].name
    if event.target_type == TargetType.JOB and event.target_id in state.jobs:
        return event.target_id
    return event.target_id


def _response_category(event_type: str) -> str:
    """Map event display text to the broad response hint shown in risk rows."""
    lower = event_type.lower()
    if "weather" in lower or "facility" in lower:
        return "pre-stage or shift unaffected work"
    if "material" in lower or "supplier" in lower or "logistics" in lower:
        return "resequence or expedite"
    if "machine" in lower or "workcenter" in lower or "tooling" in lower:
        return "reroute or protect critical path"
    if "crew" in lower:
        return "split capacity or protect critical subjobs"
    if "rework" in lower:
        return "contain quality impact"
    if "inspection" in lower or "engineering" in lower or "certification" in lower:
        return "mitigation recommended"
    return "priority review"
