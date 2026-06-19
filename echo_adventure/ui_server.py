"""Local browser UI for ECHO Adventure.

This module intentionally keeps the browser UI self-contained: the HTTP API,
session state, and inline HTML/CSS/JS all live here. The simulation and decision
logic remain in their own modules; this file translates those domain objects
into small JSON payloads that the dashboard can render.
"""

from __future__ import annotations

import argparse
import json
import threading
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import GameConfig, resolve_seed
from .decisions import apply_choice, generate_decision_cards
from .enums import JobStatus, TargetType, WorkCenterStatus
from .metrics import calculate_snapshot, day_shift, update_state_metrics
from .models import DecisionCard, DecisionChoice, Event, Job, MetricSnapshot, SimulationState
from .scenario_generator import generate_scenario
from .schedulers.automated import AutomatedScheduler
from .schedulers.manual import ManualScheduler
from .simulation import DayResult, advance_day, initialize_state


# GameSession is the stateful bridge between stateless HTTP requests and the
# mutable simulation engine. One process hosts one active session at a time.
class GameSession:
    """Owns one playable browser run and its hidden automated benchmark run.

    The browser server is threaded, so every public mutation/read takes the
    session lock. The player and automated states are initialized from the same
    scenario so the final reveal compares scheduling policy, not scenario luck.
    """

    def __init__(self, seed: int | None = None) -> None:
        # RLock allows helper methods called inside locked public methods to
        # safely reuse the same lock if the implementation grows later.
        self.lock = threading.RLock()
        # Resolve random seeds immediately so the UI can always display and
        # replay the exact generated scenario.
        self.seed = resolve_seed(seed)
        self.config = GameConfig(seed=self.seed)
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
                "scenarioId": self.scenario.scenario_id,
                "gameOver": game_over,
                "day": self.player_state.current_day,
                "shift": self.player_state.current_shift,
                "shiftLabel": day_shift(max(1, self.player_state.current_shift), self.config.shifts_per_day),
                "deadlineLabel": "Day 30, Shift 3",
                "snapshot": _snapshot_payload(snapshot, self.config.shifts_per_day),
                "overview": self._overview(snapshot),
                "shops": self._shops_payload(),
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
        """The run ends at final completion or the configured deadline."""
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
        """Return piece rows plus nested job rows for piece drill-down modals."""
        pieces = []
        # Highest-risk pieces are listed first in the payload; the browser later
        # sorts by piece id for the default table, but risk ordering is still
        # useful to callers and future views.
        for piece in sorted(self.player_state.pieces.values(), key=lambda item: (-item.risk_score, item.id)):
            blocked = sum(1 for job_id in piece.job_ids if self.player_state.jobs[job_id].is_blocked)
            critical = any(self.player_state.jobs[job_id].critical_path for job_id in piece.job_ids)
            piece_jobs: list[dict[str, Any]] = []
            for job_id in piece.job_ids:
                job = self.player_state.jobs[job_id]
                # Resolve display names here so the frontend does not need to
                # join jobs back to shops/workcenters.
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
                    "name": piece.name,
                    "status": piece.status.value,
                    "completed": piece.completed_job_count,
                    "total": piece.total_job_count,
                    "progress": round(piece.percent_complete, 3),
                    "blocked": blocked,
                    "critical": critical,
                    "estimated": day_shift(piece.estimated_completion_shift, self.config.shifts_per_day),
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
                # Rework flags are calculated for current/next jobs separately
                # so the UI can add a compact red marker next to job ids.
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
                    "impact": "Final integration" if job.id == self.player_state.final_integration_job else job.piece_id,
                    "risk": round(job.risk_score, 1),
                    "rework": job.rework_count > 0 or job.status == JobStatus.REWORK_REQUIRED,
                }
            )
        return rows

    def _risk_payload(self) -> list[dict[str, Any]]:
        """Return active warnings/disruptions plus blocked jobs for risk review."""
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
            # Blocked jobs are shown alongside events because they require the
            # same scheduling attention even when they are not event objects.
            rows.append(
                {
                    "status": "Blocked",
                    "id": job.id,
                    "type": "Job block",
                    "affected": job.piece_id,
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
                "It avoided unnecessary preemption while still resequencing around blocked jobs quickly.",
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
                type(self).session = GameSession(seed=seed)
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


def run_ui_server(seed: int | None = None, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start the local browser UI server."""
    # A fresh handler subclass lets us attach a mutable class-level session
    # without modifying BaseHTTPRequestHandler itself.
    handler = type("SessionHandler", (GameRequestHandler,), {})
    handler.session = GameSession(seed=seed)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}"
    print(f"ECHO Adventure UI running at {url}")
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
    args = parser.parse_args(argv)
    run_ui_server(seed=args.seed, host=args.host, port=args.port)


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


def _highest_risk_piece(state: SimulationState, shop_id: str) -> str:
    """Return a compact highest-risk piece label for one shop row."""
    piece_scores: dict[str, float] = {}
    for job in state.jobs.values():
        if job.shop_id == shop_id and job.piece_id in state.pieces and not job.is_complete:
            piece_scores[job.piece_id] = max(piece_scores.get(job.piece_id, 0.0), job.risk_score)
    if not piece_scores:
        return "-"
    piece_id = max(piece_scores, key=piece_scores.get)
    return f"{piece_id} ({piece_scores[piece_id]:.0f})"


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
        return "split capacity or protect critical jobs"
    if "rework" in lower:
        return "contain quality impact"
    if "inspection" in lower or "engineering" in lower or "certification" in lower:
        return "mitigation recommended"
    return "priority review"


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ECHO Adventure Operations UI</title>
  <style>
    :root {
      --bg: #f6f7f4;
      --panel: #ffffff;
      --ink: #202524;
      --muted: #66706d;
      --line: #d9ded8;
      --teal: #167c78;
      --teal-dark: #0d5552;
      --amber: #b7791f;
      --red: #b33a3a;
      --green: #2f7d46;
      --violet: #6c5aa7;
      --shadow: 0 14px 32px rgba(32, 37, 36, 0.08);
    }

    html[data-theme="dark"] {
      --bg: #0f1419;
      --panel: #1a202a;
      --ink: #f0f3f5;
      --muted: #a5b0b8;
      --line: #3a4352;
      --shadow: 0 14px 32px rgba(0, 0, 0, 0.4);
    }

    html[data-theme="dark"] header {
      background: rgba(15, 20, 25, 0.95);
    }

    html[data-theme="dark"] h1,
    html[data-theme="dark"] h2,
    html[data-theme="dark"] h3 {
      color: #ffffff;
    }

    html[data-theme="dark"] input,
    html[data-theme="dark"] select,
    html[data-theme="dark"] button {
      background: #1a202a;
      color: #f0f3f5;
      border-color: #3a4352;
    }

    html[data-theme="dark"] button.primary {
      background: #167c78;
      color: #ffffff;
      border-color: #167c78;
    }

    html[data-theme="dark"] button.primary:hover {
      background: #0d5552;
      border-color: #0d5552;
    }

    html[data-theme="dark"] button:disabled {
      opacity: 0.48;
    }

    html[data-theme="dark"] option {
      background: #1a202a;
      color: #f0f3f5;
    }

    html[data-theme="dark"] .badge {
      background: #2a3543;
      color: #a5b0b8;
    }

    html[data-theme="dark"] .badge.good {
      background: #1a3a2a;
      color: #5dd99f;
    }

    html[data-theme="dark"] .badge.warn {
      background: #3a2a1a;
      color: #f0ad4e;
    }

    html[data-theme="dark"] .badge.danger {
      background: #3a1a1a;
      color: #ff6b6b;
    }

    html[data-theme="dark"] .badge.info {
      background: #1a2a3a;
      color: #5dd9e0;
    }

    html[data-theme="dark"] table,
    html[data-theme="dark"] th,
    html[data-theme="dark"] td {
      border-color: #3a4352;
    }

    html[data-theme="dark"] th {
      background: #1a202a;
      color: #a5b0b8;
    }

    html[data-theme="dark"] .section-head {
      background: #252d38;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .tabbar button {
      background: #1a202a;
      color: #a5b0b8;
    }

    html[data-theme="dark"] .tabbar button.active {
      background: #2a3543;
      border-bottom-color: #2a3543;
      color: #5dd9e0;
    }

    html[data-theme="dark"] .decision {
      background: #1a202a;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .decision.done {
      border-color: #2a5a3a;
      background: #1a2f1f;
    }

    html[data-theme="dark"] .decision-head {
      border-color: #3a4352;
    }

    html[data-theme="dark"] .choice {
      background: #252d38;
      border-color: #3a4352;
      color: #f0f3f5;
    }

    html[data-theme="dark"] .choice.selected {
      background: #2a5a3a;
      border-color: #5dd99f;
    }

    html[data-theme="dark"] .modal {
      background: #1a202a;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .reveal-panel {
      background: #1a202a;
      border-color: #3a4352;
    }

    html[data-theme="dark"] .error {
      background: #2a1a1a;
      border-color: #5a3a3a;
      color: #ff9999;
    }

    html[data-theme="dark"] .metric {
      background: #252d38;
      border-color: #3a4352;
      color: #f0f3f5;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.4;
    }

    header {
      position: sticky;
      top: 0;
      z-index: 20;
      background: rgba(246, 247, 244, 0.94);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(12px);
    }

    .topbar {
      display: grid;
      grid-template-columns: minmax(240px, 1fr) auto;
      gap: 18px;
      align-items: center;
      padding: 16px 22px;
    }

    h1, h2, h3 { margin: 0; letter-spacing: 0; }
    h1 { font-size: 20px; font-weight: 760; }
    h2 { font-size: 15px; font-weight: 760; }
    h3 { font-size: 13px; font-weight: 760; color: var(--muted); text-transform: uppercase; }
    .subtle { color: var(--muted); }
    .controls { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; align-items: center; }
    input, select, button {
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }
    input { width: 132px; padding: 0 10px; }
    select { min-width: 210px; padding: 0 8px; }
    button {
      padding: 0 12px;
      cursor: pointer;
      font-weight: 650;
    }
    button.primary { background: var(--teal); color: #fff; border-color: var(--teal); }
    button.primary:hover { background: var(--teal-dark); }
    button:disabled { opacity: 0.48; cursor: not-allowed; }

    main {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 16px;
      padding: 16px 22px 28px;
      max-width: 1600px;
      margin: 0 auto;
    }

    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    section { overflow: visible; }
    .section-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 13px 15px;
      border-bottom: 1px solid var(--line);
      background: #fbfcf9;
    }

    .grid { display: grid; gap: 16px; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(6, minmax(120px, 1fr));
      gap: 10px;
      padding: 14px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 11px;
      background: #fff;
      min-height: 74px;
    }
    .metric strong {
      display: block;
      font-size: 22px;
      line-height: 1.1;
      margin-top: 6px;
    }

    .progress {
      width: 100%;
      height: 8px;
      border-radius: 99px;
      background: #e6ebe6;
      overflow: hidden;
      margin-top: 8px;
    }
    .bar { height: 100%; background: var(--teal); width: 0; }
    .bar.warn { background: var(--amber); }
    .bar.danger { background: var(--red); }
    .bar.good { background: var(--green); }

    .tabbar {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 10px 14px 0;
    }
    .tabbar button {
      height: 32px;
      border-radius: 6px 6px 0 0;
      background: #f0f3ef;
      display: inline-flex;
      align-items: center;
    }
    .tabbar button.active {
      background: #fff;
      border-bottom-color: #fff;
      color: var(--teal-dark);
    }
    .view { display: none; padding: 14px; }
    .view.active { display: block; }
    .view-controls {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 13px;
    }
    th, td {
      padding: 8px 7px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
      background: #fbfcf9;
    }
    tr:last-child td { border-bottom: none; }
    .table-wrap { max-height: 520px; overflow: auto; border: 1px solid var(--line); border-radius: 8px; }

    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 7px;
      border-radius: 999px;
      background: #eef2ee;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .badge.good { background: #e7f3eb; color: var(--green); }
    .badge.warn { background: #fbf0da; color: var(--amber); }
    .badge.danger { background: #f8e4e4; color: var(--red); }
    .badge.info { background: #e7f1f1; color: var(--teal-dark); }

    .link-button {
      appearance: none;
      border: none;
      background: none;
      color: var(--teal-dark);
      text-decoration: underline;
      cursor: pointer;
      padding: 0;
      font: inherit;
    }
    .link-button:hover {
      color: var(--primary);
    }

    .decision {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }
    .decision.done { border-color: #b8d8c2; background: #fbfffc; }
    .decision-head { padding: 11px; border-bottom: 1px solid var(--line); }
    .decision-title { display: flex; justify-content: space-between; gap: 10px; align-items: start; }
    .choice {
      display: block;
      width: calc(100% - 20px);
      height: auto;
      min-height: 44px;
      margin: 8px 10px;
      padding: 9px;
      text-align: left;
      border-radius: 6px;
    }
    .choice.selected { border-color: var(--green); background: #eef8f0; }
    .choice small { display: block; color: var(--muted); margin-top: 3px; }
    .decision-modal {
      max-width: 680px;
    }
    .modal-titlebar {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 12px;
    }
    .icon-button {
      width: 34px;
      padding: 0;
      font-size: 20px;
      line-height: 1;
    }

    .split {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 12px;
      padding: 14px;
    }
    .reveal-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }
    .notes {
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
    }
    .status-line {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      margin-top: 6px;
    }
    .hidden { display: none !important; }
    .error {
      margin: 0 22px;
      padding: 10px 12px;
      border: 1px solid #e4b3b3;
      background: #fff2f2;
      color: #8d2525;
      border-radius: 8px;
    }

    @media (max-width: 1120px) {
      main { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: repeat(3, minmax(120px, 1fr)); }
    }
    @media (max-width: 680px) {
      .topbar { grid-template-columns: 1fr; }
      .controls { justify-content: flex-start; }
      main { padding: 12px; }
      .metrics, .split { grid-template-columns: 1fr; }
      table { min-width: 720px; }
    }
    /* Modal overlay for end-of-day summary */
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(16,20,18,0.45);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 60;
      padding: 24px;
    }
    .modal-overlay.active { display: flex; }
    .modal {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 18px;
      max-width: 820px;
      width: 100%;
      box-shadow: 0 30px 60px rgba(8,10,9,0.4);
    }
    .modal .modal-body { max-height: 60vh; overflow: auto; margin-bottom: 12px; }
    .modal .modal-footer { display:flex; justify-content:flex-end; gap:8px; }
    .modal h3 { margin-top: 0; }
    .welcome-copy {
      display: grid;
      gap: 10px;
      margin: 8px 0 4px;
      color: var(--muted);
    }
    .welcome-copy p {
      margin: 0;
    }
    .welcome-copy ul {
      margin: 0;
      padding-left: 20px;
    }
    .welcome-copy li {
      margin: 6px 0;
    }
    .rework-flag {
      display: inline-block;
      width: 8px;
      height: 8px;
      margin-left: 6px;
      border-radius: 50%;
      background: var(--red);
      box-shadow: 0 0 0 2px rgba(179, 58, 58, 0.14);
      vertical-align: middle;
    }
    .info-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-style: italic;
      color: var(--muted);
      cursor: help;
      font-size: 11px;
      font-weight: bold;
      margin-left: 4px;
      position: relative;
      z-index: 10;
      width: 16px;
      height: 16px;
      border: 1.5px solid var(--ink);
      border-radius: 50%;
    }
    .info-icon:hover::after {
      content: attr(data-tooltip);
      position: absolute;
      bottom: 125%;
      left: 50%;
      transform: translateX(-50%);
      background: var(--panel);
      color: var(--ink);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 12px;
      font-size: 13px;
      font-style: normal;
      font-weight: 600;
      opacity: 1;
      white-space: nowrap;
      z-index: 100000;
      box-shadow: 0 10px 24px rgba(0, 0, 0, 0.24);
    }
    .tabbar .info-icon:hover::after {
      width: min(280px, 70vw);
      white-space: normal;
      line-height: 1.3;
      text-align: left;
    }
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div>
        <h1>Advanced Manufacturing Yard Schedule</h1>
        <div class="status-line">
          <span class="badge" id="dayBadge">Day</span>
          <span class="badge warn" id="decisionProgress">Decisions</span>
        </div>
      </div>
      <div class="controls">
        <button id="themeToggle" title="Toggle dark mode" style="width:36px;padding:0;display:flex;align-items:center;justify-content:center;font-size:18px;">🌙</button>
        <input id="seedInput" inputmode="numeric" placeholder="Seed">
        <button id="newRunBtn">New Run</button>
        <button id="decisionBtn">Daily Decisions</button>
        <button id="advanceBtn" class="primary" disabled>End Day</button>
      </div>
    </div>
    <div id="error" class="error hidden"></div>
  </header>

  <main>
    <div class="grid">
      <section>
        <div class="section-head">
          <div>
            <h2>Project Position</h2>
            <div class="subtle" id="projectedText">Projected completion</div>
          </div>
          <span class="badge" id="runStateBadge">In progress</span>
        </div>
        <div class="metrics" id="metrics"></div>
      </section>

      <section>
        <div class="section-head">
          <h2>Operating Board</h2>
        </div>
        <div class="tabbar">
          <button data-tab="shops" class="active">Shops<span class="info-icon" data-tooltip="Shows queue pressure, blocked work, utilization, idle time, shop risk, and active disruptions by shop.">i</span></button>
          <button data-tab="pieces">Pieces<span class="info-icon" data-tooltip="Shows each puzzle piece's completion progress, blocked job count, critical-path exposure, estimated completion, and risk.">i</span></button>
          <button data-tab="workcenters">Workcenters<span class="info-icon" data-tooltip="Shows the selected shop's machines or stations, current job, queue depth, next job, capability, and downtime.">i</span></button>
          <button data-tab="critical">Critical Path<span class="info-icon" data-tooltip="Shows jobs most likely to control the final completion date, including slack, blockers, downstream impact, and risk.">i</span></button>
          <button data-tab="risks">Risk Register<span class="info-icon" data-tooltip="Shows active disruptions, warnings, and blocked jobs that need schedule response or mitigation.">i</span></button>
        </div>
        <div id="shops" class="view active"><div class="table-wrap"><table id="shopsTable"></table></div></div>
        <div id="pieces" class="view"><div class="table-wrap"><table id="piecesTable"></table></div></div>
        <div id="workcenters" class="view">
          <div class="view-controls">
            <select id="shopSelect" aria-label="Select shop"></select>
          </div>
          <div class="table-wrap"><table id="workcentersTable"></table></div>
        </div>
        <div id="critical" class="view"><div class="table-wrap"><table id="criticalTable"></table></div></div>
        <div id="risks" class="view"><div class="table-wrap"><table id="risksTable"></table></div></div>
      </section>

      <section id="summarySection" class="hidden">
        <div class="section-head"><h2>End-of-Day Summary</h2></div>
        <div class="split">
          <div class="reveal-panel" id="summaryMetrics"></div>
          <div class="reveal-panel"><h3>Notable Consequences</h3><ul class="notes" id="summaryNotes"></ul></div>
        </div>
      </section>

      <section id="finalSection" class="hidden">
        <div class="section-head">
          <div>
            <h2>Final Operational Comparison</h2>
            <div class="subtle">The silent benchmark is revealed only after the run ends.</div>
          </div>
        </div>
        <div class="split">
          <div class="reveal-panel"><h3>Metric Comparison</h3><table id="finalTable"></table></div>
          <div class="reveal-panel"><h3>Outcome Drivers</h3><ul class="notes" id="finalNotes"></ul></div>
        </div>
      </section>
    </div>

  </main>

  <div id="welcomeModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="welcomeModalTitle">
    <div class="modal">
      <h1 id="welcomeModalTitle">Welcome</h1>
      <div class="welcome-copy">
        <p>You are managing a manufacturing schedule under disruption. Each day, inspect the operating board, read the active risks, and choose how the yard should respond.</p>
        <p>Your goal is to get every puzzle piece ready for final integration before the Day 15 deadline while balancing cost, reschedules, utilization, and schedule risk.</p>
        <ul>
          <li>Review shops, workcenters, pieces, the critical path, and the risk register.</li>
          <li>Answer the daily decision cards to resequence, reroute, expedite, or protect critical work.</li>
          <li>End the day to see the consequences of your choices and move the schedule forward.</li>
        </ul>
      </div>
      <div class="modal-footer">
        <button id="closeWelcomeBtn" class="primary" onclick="closeWelcomeModal()">Start</button>
      </div>
    </div>
  </div>

  <div id="decisionModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="decisionModalTitle">
    <div class="modal decision-modal">
      <div class="modal-titlebar">
        <div>
          <h1 id="decisionModalTitle">Daily Decisions</h1>
          <div class="subtle" id="decisionModalSubtitle"></div>
        </div>
        <button id="closeDecisionBtn" class="icon-button" title="Dismiss decisions" onclick="dismissDecisionModal()">×</button>
      </div>
      <div class="modal-body" id="decisionModalBody"></div>
      <div class="modal-footer" id="decisionModalFooter"></div>
    </div>
  </div>

  <script>
    let state = null;
    let activeTab = "shops";
    // Client-side modal state is intentionally local. The server remains the
    // source of truth for the run, decisions, and day advancement rules.
    let welcomeModalVisible = false;
    let decisionModalVisible = false;
    let dismissedDecisionKey = null;
    const welcomeStorageKey = "echoAdventureWelcomeSeen";

    const $ = (id) => document.getElementById(id);
    const fmtPct = (value) => `${Math.round((value || 0) * 100)}%`;
    const fmtNum = (value) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });

    async function api(path, options = {}) {
      // All API endpoints return JSON, including errors. Throwing here keeps
      // button handlers small and centralizes user-facing error display.
      const response = await fetch(path, {
        headers: { "content-type": "application/json" },
        ...options
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Request failed");
      return data;
    }

    function showError(message) {
      const box = $("error");
      if (!message) {
        box.classList.add("hidden");
        box.textContent = "";
        return;
      }
      box.textContent = message;
      box.classList.remove("hidden");
    }

    async function loadState() {
      try {
        state = await api("/api/state");
        showError("");
        render();
      } catch (error) {
        showError(error.message);
      }
    }

    async function newRun() {
      try {
        const seed = $("seedInput").value.trim();
        state = await api("/api/new", {
          method: "POST",
          body: JSON.stringify({ seed })
        });
        pendingChoice = null;
        dismissedDecisionKey = null;
        decisionModalVisible = false;
        showError("");
        render();
      } catch (error) {
        showError(error.message);
      }
    }

    async function choose(cardId, choiceId) {
      try {
        state = await api("/api/choice", {
          method: "POST",
          body: JSON.stringify({ cardId, choiceId })
        });
        pendingChoice = null;
        dismissedDecisionKey = null;
        decisionModalVisible = true;
        showError("");
        render();
      } catch (error) {
        showError(error.message);
      }
    }

    let pendingAdvanceState = null;

    async function prepareAdvanceDay() {
      // The button should already be disabled until all decisions are complete,
      // but this guard keeps direct console calls and stale UI state honest.
      if (!readyToAdvance()) {
        openDecisionModal();
        return;
      }
      try {
        const nextState = await api("/api/advance", { method: "POST", body: "{}" });
        showError("");
        pendingAdvanceState = nextState;
        if (nextState.finalReveal) {
          state = nextState;
          pendingAdvanceState = null;
          finalModalVisible = true;
          modalVisible = false;
        } else {
          modalVisible = true;
          finalModalVisible = false;
        }
        decisionModalVisible = false;
        pieceModalVisible = false;
        render();
      } catch (error) {
        showError(error.message);
      }
    }

    function commitAdvanceDay() {
      if (!pendingAdvanceState) {
        return;
      }
      state = pendingAdvanceState;
      pendingAdvanceState = null;
      modalVisible = false;
      render();
    }

    let modalVisible = false;
    let finalModalVisible = false;
    let pieceModalVisible = false;
    let activePieceId = null;
    let pendingChoice = null;

    function openPieceModal(pieceId) {
      activePieceId = pieceId;
      modalVisible = false;
      finalModalVisible = false;
      decisionModalVisible = false;
      pieceModalVisible = true;
      render();
    }

    function closePieceModal() {
      pieceModalVisible = false;
      render();
    }

    function closeFinalModal() {
      finalModalVisible = false;
      render();
    }

    function render() {
      if (!state) return;
      $("dayBadge").textContent = state.shiftLabel;
      $("projectedText").textContent = `Projected completion: ${state.overview.projectedCompletion}`;
      $("runStateBadge").textContent = state.gameOver ? "Run complete" : "In progress";
      $("runStateBadge").className = `badge ${state.gameOver ? "good" : "info"}`;

      renderMetrics();
      renderShopOptions();
      renderTables();
      renderDecisions();
      renderSummary();
      renderSummaryModal();
      renderFinal();
      renderPieceModal();
      renderWelcomeModal();
      maybeAutoOpenDecisionModal();
      renderDecisionModal();
      // Auto-open final modal if run finished.
      if (state.finalReveal && !finalModalVisible) finalModalVisible = true;
      renderFinalModal();
    }

    function selectedDecisionCount() {
      return state ? state.decisions.filter(card => card.selectedChoice).length : 0;
    }

    function readyToAdvance() {
      return Boolean(state && !state.gameOver && selectedDecisionCount() === state.decisions.length);
    }

    function decisionPromptKey() {
      if (!state) return "";
      const nextCard = state.decisions.find(card => !card.selectedChoice);
      // A dismissed decision modal should stay dismissed only until the next
      // unresolved card appears or the day's completion state changes.
      return `${state.day}:${selectedDecisionCount()}:${nextCard ? nextCard.id : "complete"}`;
    }

    function maybeAutoOpenDecisionModal() {
      // Decisions should be "in your face" when they need attention, but not
      // fight with other modals or reopen immediately after the user dismisses.
      if (!state || state.gameOver || welcomeModalVisible || finalModalVisible || modalVisible || pieceModalVisible) {
        return;
      }
      const hasOpenDecision = state.decisions.some(card => !card.selectedChoice);
      if (hasOpenDecision && dismissedDecisionKey !== decisionPromptKey()) {
        decisionModalVisible = true;
      }
    }

    function openDecisionModal() {
      if (!state || state.gameOver) return;
      dismissedDecisionKey = null;
      decisionModalVisible = true;
      renderDecisionModal();
    }

    function dismissDecisionModal() {
      dismissedDecisionKey = decisionPromptKey();
      decisionModalVisible = false;
      renderDecisionModal();
    }

    function submitDecision(cardId) {
      if (!pendingChoice) return;
      choose(cardId, pendingChoice);
    }

    function renderWelcomeModal() {
      const overlay = document.getElementById("welcomeModalOverlay");
      if (!overlay) return;
      overlay.classList.toggle("active", welcomeModalVisible);
    }

    function closeWelcomeModal() {
      welcomeModalVisible = false;
      localStorage.setItem(welcomeStorageKey, "true");
      renderWelcomeModal();
      maybeAutoOpenDecisionModal();
      renderDecisionModal();
    }

    function renderSummaryModal() {
      const payload = pendingAdvanceState || state;
      const summary = payload.lastSummary;
      const overlay = document.getElementById("summaryModalOverlay");
      const body = document.getElementById("summaryModalBody");
      const notes = document.getElementById("summaryModalNotes");
      if (!overlay || !body || !notes) return;
      if (!summary || !modalVisible) {
        overlay.classList.remove("active");
        return;
      }
      // The day has already been simulated on the server, but the summary modal
      // lets the player read consequences before committing that state locally.
      overlay.classList.add("active");
      body.innerHTML = `
        <table>
          <tbody>
            <tr><td>Jobs completed today</td><td>${summary.completedToday}</td></tr>
            <tr><td>Jobs remaining</td><td>${summary.jobsRemaining}</td></tr>
            <tr><td>Pieces ready</td><td>${summary.piecesCompleted}/${state.pieces.length}</td></tr>
            <tr><td>Jobs late</td><td>${summary.jobsLate}</td></tr>
            <tr><td>Cost</td><td>${fmtNum(summary.cost)}</td></tr>
            <tr><td>Risk</td><td>${Math.round(summary.risk)}/100</td></tr>
            <tr><td>Projected completion</td><td>${summary.projectedCompletion}</td></tr>
          </tbody>
        </table>
      `;
      body.scrollTop = 0;
      notes.innerHTML = (summary.notes || []).map(note => `<li>${escapeHtml(note)}</li>`).join("") || "<li>No notable notes recorded.</li>";
    }

    function renderFinalModal() {
      const final = state.finalReveal;
      const overlay = document.getElementById("finalModalOverlay");
      const body = document.getElementById("finalModalBody");
      const notes = document.getElementById("finalModalNotes");
      if (!overlay || !body || !notes) return;
      if (!final || !finalModalVisible) {
        overlay.classList.remove("active");
        return;
      }
      overlay.classList.add("active");
      const p = final.player;
      const a = final.automated;
      body.innerHTML = `
        <table>
          <tbody>
            <tr><td>Deadline met</td><td>${p.deadlineMet ? "Yes" : "No"}</td><td>${a.deadlineMet ? "Yes" : "No"}</td></tr>
            <tr><td>Final item completed</td><td>${p.finalItemCompleted ? "Yes" : "No"}</td><td>${a.finalItemCompleted ? "Yes" : "No"}</td></tr>
            <tr><td>Completion</td><td>${p.completion || "Not complete"}</td><td>${a.completion || "Not complete"}</td></tr>
            <tr><td>Pieces ready</td><td>${p.piecesCompleted}</td><td>${a.piecesCompleted}</td></tr>
            <tr><td>Jobs completed</td><td>${p.jobsCompleted}</td><td>${a.jobsCompleted}</td></tr>
            <tr><td>Jobs late</td><td>${p.jobsLate}</td><td>${a.jobsLate}</td></tr>
            <tr><td>Utilization</td><td>${fmtPct(p.utilization)}</td><td>${fmtPct(a.utilization)}</td></tr>
            <tr><td>Idle time</td><td>${p.idleTime}</td><td>${a.idleTime}</td></tr>
            <tr><td>Reschedules</td><td>${p.reschedules}</td><td>${a.reschedules}</td></tr>
            <tr><td>Cost</td><td>${fmtNum(p.cost)}</td><td>${fmtNum(a.cost)}</td></tr>
            <tr><td>Schedule risk</td><td>${Math.round(p.scheduleRisk)}</td><td>${Math.round(a.scheduleRisk)}</td></tr>
          </tbody>
        </table>
      `;
      body.scrollTop = 0;
      notes.innerHTML = (final.explanation || []).map(note => `<li>${escapeHtml(note)}</li>`).join("");
    }

    function renderPieceModal() {
      const overlay = document.getElementById("pieceModalOverlay");
      const body = document.getElementById("pieceModalBody");
      if (!overlay || !body) return;
      const piece = state.pieces.find(item => item.id === activePieceId);
      if (!piece || !pieceModalVisible) {
        overlay.classList.remove("active");
        return;
      }
      overlay.classList.add("active");
      const blockedCount = piece.jobs.filter(job => job.blocked).length;
      const criticalCount = piece.jobs.filter(job => job.critical).length;
      body.innerHTML = `
        <div style="margin-bottom: 16px;">
          <h3>${escapeHtml(piece.name)}</h3>
          <p class="subtle">${escapeHtml(piece.id)}</p>
          <table>
            <tbody>
              <tr><td>Status</td><td>${escapeHtml(piece.status)}</td></tr>
              <tr><td>Progress</td><td>${fmtPct(piece.progress)}</td></tr>
              <tr><td>Jobs complete</td><td>${piece.completed}/${piece.total}</td></tr>
              <tr><td>Jobs blocked</td><td>${blockedCount}</td></tr>
              <tr><td>Critical jobs</td><td>${criticalCount}</td></tr>
              <tr><td>Estimated completion</td><td>${escapeHtml(piece.estimated)}</td></tr>
              <tr><td>Risk</td><td>${Math.round(piece.risk)}</td></tr>
            </tbody>
          </table>
        </div>
        <h4>Subjobs</h4>
        <table>
          <thead>
            <tr>
              <th>Job</th>
              <th>Status</th>
              <th>Shop</th>
              <th>Workcenter</th>
              <th>Capability</th>
              <th>Remaining</th>
              <th>Due</th>
              <th>Blocked</th>
            </tr>
          </thead>
          <tbody>
            ${piece.jobs.map(job => `
              <tr>
                <td>${jobLabel(job.id, job.rework)}</td>
                <td>${escapeHtml(job.status)}</td>
                <td>${escapeHtml(job.shop)}</td>
                <td>${escapeHtml(job.workcenter)}</td>
                <td>${escapeHtml(job.capability)}</td>
                <td>${escapeHtml(job.remaining)}</td>
                <td>${escapeHtml(job.due)}</td>
                <td>${job.blocked ? "Yes" : ""}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
      body.scrollTop = 0;
    }

    function renderMetrics() {
      const snap = state.snapshot;
      const metrics = [
        ["Pieces Ready", `${snap.piecesCompleted}/${state.pieces.length}`, snap.piecesCompleted / state.pieces.length, "good", "How many puzzle pieces are complete and ready to assemble."],
        ["Jobs Complete", fmtNum(snap.jobsCompleted), snap.jobsCompleted / Math.max(1, snap.jobsCompleted + snap.jobsRemaining), "good", "Total jobs finished out of all required work."],
        ["Jobs Late", fmtNum(snap.jobsLate), Math.min(1, snap.jobsLate / 20), snap.jobsLate > 0 ? "warn" : "good", "Number of jobs that have missed their target completion date."],
        ["Utilization", fmtPct(snap.utilization), snap.utilization, "info", "How busy your workcenters are (0% = idle, 100% = fully busy)."],
        ["Cost", fmtNum(snap.cost), Math.min(1, snap.cost / 28000), "warn", "Total additional costs from rescheduling, expediting, and resolving issues."],
        ["Schedule Risk", `${Math.round(snap.scheduleRisk)}/100`, snap.scheduleRisk / 100, snap.scheduleRisk > 70 ? "danger" : snap.scheduleRisk > 40 ? "warn" : "good", "Overall probability of missing the deadline (0 = safe, 100 = critical)."]
      ];
      $("metrics").innerHTML = metrics.map(([label, value, pct, tone, tooltip]) => `
        <div class="metric">
          <span class="subtle">${label}<span class="info-icon" data-tooltip="${escapeHtml(tooltip)}">i</span></span>
          <strong>${value}</strong>
          <div class="progress"><div class="bar ${tone}" style="width:${Math.max(0, Math.min(1, pct)) * 100}%"></div></div>
        </div>
      `).join("");
    }

    function renderShopOptions() {
      const select = $("shopSelect");
      const current = select.value || state.shops[0]?.id;
      // Preserve the selected shop across refreshes unless a new run no longer
      // contains that shop id.
      select.innerHTML = state.shops.map(shop => `<option value="${shop.id}">${shop.name}</option>`).join("");
      select.value = state.shops.some(shop => shop.id === current) ? current : state.shops[0]?.id;
    }

    function renderTables() {
      // Tables are rebuilt from the latest state payload. This is simple and
      // adequate for the small local dashboard; no client-side cache is needed.
      table($("shopsTable"), ["Shop", "Active", "Queued", "Blocked", "Complete", "Util.", "Idle", "Risk", "Risk Piece", "Event"], state.shops.map(shop => [
        shop.name,
        shop.active,
        shop.queued,
        shop.blocked,
        shop.completed,
        fmtPct(shop.utilization),
        shop.idle,
        badge(Math.round(shop.risk), shop.risk > 70 ? "danger" : shop.risk > 40 ? "warn" : "info"),
        shop.highestRiskPiece,
        shop.event || "-"
      ]));

      table($("piecesTable"), ["Piece", "Status", "Progress", "Jobs", "Blocked", "Critical", "Est.", "Risk"], state.pieces.sort((a, b) => {
        const numA = parseInt(a.id.replace(/\D/g, '')) || 0;
        const numB = parseInt(b.id.replace(/\D/g, '')) || 0;
        return numA - numB;
      }).map(piece => [
        `<button class="link-button" onclick="openPieceModal('${piece.id}')">${escapeHtml(piece.id)}</button>`,
        badge(piece.status, piece.status.includes("Risk") || piece.status.includes("Blocked") ? "warn" : piece.status.includes("Ready") ? "good" : "info"),
        progressCell(piece.progress),
        `${piece.completed}/${piece.total}`,
        piece.blocked,
        piece.critical ? "Yes" : "",
        piece.estimated,
        Math.round(piece.risk)
      ]));

      const shopId = $("shopSelect").value || state.shops[0]?.id;
      table($("workcentersTable"), ["Workcenter", "Status", "Current", "Remain", "Queue", "Next", "Capability", "Down"], (state.workcenters[shopId] || []).map(wc => [
        wc.id,
        badge(wc.status, wc.status === "Busy" ? "info" : wc.status === "Idle" || wc.status === "Available" ? "good" : "danger"),
        jobLabel(wc.current, wc.currentRework),
        wc.remaining,
        wc.queue,
        jobLabel(wc.next, wc.nextRework),
        wc.capability,
        wc.down
      ]));

      table($("criticalTable"), ["Job", "Shop", "WC", "Remain", "Slack", "Block", "Impact", "Risk"], state.criticalPath.map(job => [
        jobLabel(job.id, job.rework),
        job.shop,
        job.workcenter,
        job.remaining,
        badge(job.slack, job.slack < 0 ? "danger" : job.slack < 8 ? "warn" : "info"),
        job.block,
        job.impact,
        Math.round(job.risk)
      ]));

      table($("risksTable"), ["Status", "ID", "Risk", "Affected", "Severity", "Shifts", "Source", "Response"], state.risks.map(risk => [
        badge(risk.status, risk.status === "Active" || risk.status === "Blocked" ? "danger" : "warn"),
        jobLabel(risk.id, risk.rework),
        risk.type,
        risk.affected,
        risk.severity,
        risk.shifts,
        risk.source || "-",
        risk.response
      ]));
    }

    function renderDecisions() {
      const chosenCount = state.decisions.filter(card => card.selectedChoice).length;
      const totalCount = state.decisions.length;
      const remainingCount = Math.max(0, totalCount - chosenCount);
      const progress = $("decisionProgress");
      const decisionBtn = $("decisionBtn");
      const advanceBtn = $("advanceBtn");

      if (state.gameOver) {
        progress.textContent = "Run complete";
        progress.className = "badge good";
        decisionBtn.disabled = true;
        advanceBtn.disabled = true;
        return;
      }

      progress.textContent = `${chosenCount}/${totalCount} decisions`;
      progress.className = `badge ${remainingCount ? "warn" : "good"}`;
      decisionBtn.disabled = false;
      decisionBtn.textContent = remainingCount ? `Daily Decisions (${remainingCount})` : "Daily Decisions";
      advanceBtn.disabled = !readyToAdvance();
    }

    function renderDecisionModal() {
      const overlay = $("decisionModalOverlay");
      const subtitle = $("decisionModalSubtitle");
      const body = $("decisionModalBody");
      const footer = $("decisionModalFooter");
      if (!overlay || !subtitle || !body || !footer) return;

      if (!state || !decisionModalVisible || state.gameOver) {
        overlay.classList.remove("active");
        return;
      }

      const chosenCount = selectedDecisionCount();
      const totalCount = state.decisions.length;
      const nextCard = state.decisions.find(card => !card.selectedChoice);
      overlay.classList.add("active");
      subtitle.textContent = `${chosenCount}/${totalCount} responses selected`;

      if (nextCard) {
        // Only one open card is shown at a time. Submitting it asks the server
        // for the updated state, which may expose the next required card.
        body.innerHTML = `
          <div class="decision">
            <div class="decision-head">
              <div class="decision-title">
                <div>
                  <h2>${escapeHtml(nextCard.title)}</h2>
                  <div class="subtle">${escapeHtml(nextCard.type)} | Severity ${nextCard.severity}</div>
                </div>
                <span class="badge warn">Open</span>
              </div>
              <p>${escapeHtml(nextCard.description)}</p>
            </div>
            ${nextCard.choices.map(choice => `
              <button class="choice ${pendingChoice === choice.id ? "selected" : ""}" onclick="pendingChoice='${choice.id}';renderDecisionModal()">
                <strong>${escapeHtml(choice.label)}</strong>
                <small>${escapeHtml(choice.description)}</small>
              </button>
            `).join("")}
          </div>
        `;
        footer.innerHTML = `
          <button onclick="dismissDecisionModal()">Dismiss</button>
          <button ${!pendingChoice ? "disabled" : ""} class="primary" onclick="submitDecision('${nextCard.id}')">Submit</button>
        `;
        return;
      }

      body.innerHTML = `
        <div class="reveal-panel">
          <h3>All choices made for today.</h3>
          <div class="subtle">End the day to process the schedule and reveal the daily consequences.</div>
        </div>
      `;
      footer.innerHTML = `
        <button onclick="dismissDecisionModal()">Dismiss</button>
        <button class="primary" onclick="prepareAdvanceDay()">End Day</button>
      `;
    }

    function renderSummary() {
      const summary = state.lastSummary;
      $("summarySection").classList.toggle("hidden", !summary);
      if (!summary) return;
      $("summaryMetrics").innerHTML = `
        <h3>Day Result</h3>
        <table>
          <tbody>
            <tr><td>Jobs completed today</td><td>${summary.completedToday}</td></tr>
            <tr><td>Jobs remaining</td><td>${summary.jobsRemaining}</td></tr>
            <tr><td>Pieces ready</td><td>${summary.piecesCompleted}/${state.pieces.length}</td></tr>
            <tr><td>Jobs late</td><td>${summary.jobsLate}</td></tr>
            <tr><td>Cost</td><td>${fmtNum(summary.cost)}</td></tr>
            <tr><td>Risk</td><td>${Math.round(summary.risk)}/100</td></tr>
            <tr><td>Projected completion</td><td>${summary.projectedCompletion}</td></tr>
          </tbody>
        </table>
      `;
      $("summaryNotes").innerHTML = (summary.notes || []).map(note => `<li>${escapeHtml(note)}</li>`).join("") || "<li>No notable notes recorded.</li>";
    }

    function renderFinal() {
      const final = state.finalReveal;
      $("finalSection").classList.toggle("hidden", !final);
      if (!final) return;
      const p = final.player;
      const a = final.automated;
      table($("finalTable"), ["Metric", "Player", "ECHO"], [
        ["Deadline met", p.deadlineMet ? "Yes" : "No", a.deadlineMet ? "Yes" : "No"],
        ["Final item completed", p.finalItemCompleted ? "Yes" : "No", a.finalItemCompleted ? "Yes" : "No"],
        ["Completion", p.completion || "Not complete", a.completion || "Not complete"],
        ["Pieces ready", p.piecesCompleted, a.piecesCompleted],
        ["Jobs completed", p.jobsCompleted, a.jobsCompleted],
        ["Jobs late", p.jobsLate, a.jobsLate],
        ["Utilization", fmtPct(p.utilization), fmtPct(a.utilization)],
        ["Idle time", p.idleTime, a.idleTime],
        ["Reschedules", p.reschedules, a.reschedules],
        ["Cost", fmtNum(p.cost), fmtNum(a.cost)],
        ["Schedule risk", Math.round(p.scheduleRisk), Math.round(a.scheduleRisk)]
      ]);
      $("finalNotes").innerHTML = final.explanation.map(note => `<li>${escapeHtml(note)}</li>`).join("");
    }

    function table(el, headers, rows) {
      el.innerHTML = `
        <thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead>
        <tbody>${rows.length ? rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${headers.length}">No rows</td></tr>`}</tbody>
      `;
    }

    function progressCell(value) {
      return `<div>${fmtPct(value)}</div><div class="progress"><div class="bar good" style="width:${Math.max(0, Math.min(1, value)) * 100}%"></div></div>`;
    }

    function badge(value, tone) {
      return `<span class="badge ${tone || ""}">${escapeHtml(String(value))}</span>`;
    }

    function jobLabel(value, hasRework) {
      const label = escapeHtml(String(value || "-"));
      if (!hasRework || label === "-") return label;
      // Rework is a visual flag, not a separate table column, so dense boards
      // can still be scanned without widening every job table.
      return `${label}<span class="rework-flag" title="Rework required or completed" aria-label="Rework"></span>`;
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
    }

    document.querySelectorAll(".tabbar button").forEach(button => {
      button.addEventListener("click", () => {
        activeTab = button.dataset.tab;
        document.querySelectorAll(".tabbar button").forEach(item => item.classList.toggle("active", item.dataset.tab === activeTab));
        document.querySelectorAll(".view").forEach(view => view.classList.toggle("active", view.id === activeTab));
      });
    });

    $("shopSelect").addEventListener("change", renderTables);
    $("newRunBtn").addEventListener("click", newRun);
    $("decisionBtn").addEventListener("click", openDecisionModal);
    $("advanceBtn").addEventListener("click", prepareAdvanceDay);
    document.addEventListener("click", (e) => {
      const summaryOverlay = document.getElementById("summaryModalOverlay");
      const finalOverlay = document.getElementById("finalModalOverlay");
      const pieceOverlay = document.getElementById("pieceModalOverlay");
      const welcomeOverlay = document.getElementById("welcomeModalOverlay");
      const decisionOverlay = document.getElementById("decisionModalOverlay");
      if (e.target && e.target.id === "closeWelcomeBtn") {
        closeWelcomeModal();
      }
      if (e.target && e.target.id === "closeDecisionBtn") {
        dismissDecisionModal();
      }
      if (e.target && e.target.id === "closeModalBtn") {
        modalVisible = false;
        if (pendingAdvanceState) pendingAdvanceState = null;
        render();
      }
      if (e.target && e.target.id === "closeFinalBtn") {
        finalModalVisible = false;
        render();
      }
      if (e.target && e.target.id === "closePieceModalBtn") {
        pieceModalVisible = false;
        render();
      }
      if (summaryOverlay && e.target === summaryOverlay) {
        modalVisible = false;
        if (pendingAdvanceState) pendingAdvanceState = null;
        render();
      }
      if (finalOverlay && e.target === finalOverlay) {
        finalModalVisible = false;
        render();
      }
      if (pieceOverlay && e.target === pieceOverlay) {
        pieceModalVisible = false;
        render();
      }
      if (welcomeOverlay && e.target === welcomeOverlay) {
        closeWelcomeModal();
      }
      if (decisionOverlay && e.target === decisionOverlay) {
        dismissDecisionModal();
      }
    });

    function initDarkMode() {
      const saved = localStorage.getItem("theme") || "light";
      document.documentElement.setAttribute("data-theme", saved);
      updateThemeButton(saved);
    }

    function updateThemeButton(theme) {
      const btn = $("themeToggle");
      if (btn) btn.textContent = theme === "dark" ? "☀️" : "🌙";
    }

    function toggleDarkMode() {
      const current = document.documentElement.getAttribute("data-theme") || "light";
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
      updateThemeButton(next);
    }

    $("themeToggle").addEventListener("click", toggleDarkMode);

    initDarkMode();
    welcomeModalVisible = localStorage.getItem(welcomeStorageKey) !== "true";
    renderWelcomeModal();
    loadState();
  </script>

  <!-- End-of-day modal (centered) -->
  <div id="summaryModalOverlay" class="modal-overlay" role="dialog" aria-modal="true">
    <div class="modal">
      <h1>Daily Summary</h1Drop >
      <div class="modal-body" id="summaryModalBody"></div>
      <div>
        <h3>Notable Consequences</h3>
        <ul class="notes" id="summaryModalNotes"></ul>
      </div>
      <div class="modal-footer">
        <button id="modalAdvanceBtn" class="primary" onclick="commitAdvanceDay()">Advance Day</button>
      </div>
    </div>
  </div>
  <!-- Final-run modal (centered) -->
  <div id="finalModalOverlay" class="modal-overlay" role="dialog" aria-modal="true">
    <div class="modal">
      <div class="modal-body" id="finalModalBody"></div>
      <div>
        <h3>Outcome Drivers</h3>
        <ul class="notes" id="finalModalNotes"></ul>
      </div>
      <div class="modal-footer">
        <button id="closeFinalBtn" class="primary" onclick="closeFinalModal()">Close</button>
      </div>
    </div>
  </div>
  <div id="pieceModalOverlay" class="modal-overlay" role="dialog" aria-modal="true">
    <div class="modal">
      <div class="modal-body" id="pieceModalBody"></div>
      <div class="modal-footer">
        <button id="closePieceModalBtn" class="primary" onclick="closePieceModal()">Close</button>
      </div>
    </div>
  </div>
</body>
</html>
"""


if __name__ == "__main__":
    main()
