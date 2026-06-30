"""Local browser UI server for ECHO Adventure."""

from __future__ import annotations

import argparse
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from ..config import GameConfig, resolve_seed
from ..decisions import (
    active_decision_cards,
    apply_choice,
    decision_progress,
)
from ..echo import apply_echo_decisions_for_day, select_echo_choice_for_state
from ..enums import JobStatus
from ..metrics import (
    calculate_final_score,
    calculate_snapshot,
    day_shift,
    score_decision_path_differentiator,
    update_state_metrics,
)
from ..models import DecisionCard, DecisionChoice, DecisionProgress, MetricSnapshot, PuzzlePiece, SimulationState
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
    ) -> None:
        # RLock allows helper methods called inside locked public methods to
        # safely reuse the same lock if the implementation grows later.
        self.lock = threading.RLock()
        # Resolve random seeds immediately so the UI can always display and
        # replay the exact generated scenario.
        self.seed = resolve_seed(seed)
        self.config = GameConfig.for_preset("normal", seed=self.seed)
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
        self.echo_completed_days: set[int] = set()
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
                "gameOver": game_over,
                "day": self.player_state.current_day,
                "projectedCompletion": day_shift(snapshot.projected_completion_shift, self.config.shifts_per_day),
                "snapshot": _snapshot_payload(snapshot, self.config.shifts_per_day),
                "pieces": self._pieces_payload(),
                "criticalPath": self._critical_path_payload(),
                "decisions": [_card_payload(card, self.applied_choices.get(card.id)) for card in self.current_cards],
                "decisionProgress": _decision_progress_payload(
                    decision_progress(self.player_state, self.player_state.current_day, self.applied_choices)
                ),
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
            echo_choice = select_echo_choice_for_state(self.player_state, card, self.config, self.player_state.decision_cards)
            note = apply_choice(self.player_state, card, choice, actor="player", echo_choice=echo_choice)
            self.applied_choices[card.id] = choice.id
            comparison = "Matched ECHO." if choice.id == echo_choice.id else f"ECHO would choose {echo_choice.label}."
            self.choice_notes.append(f"{card.title}: {choice.label}. {comparison} {note}")
            self._ensure_cards()
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
            apply_echo_decisions_for_day(self.automated_state, self.config, self.echo_completed_days)
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
        self._ensure_cards()
        progress = decision_progress(self.player_state, self.player_state.current_day, self.applied_choices)
        return progress.total_questions == 0 or progress.answered_questions == progress.total_questions

    def _ensure_cards(self) -> None:
        if self._game_over():
            self.current_cards = []
            return
        # Cards are resolved from the prepared daily choices so a selected
        # answer can determine the next question without generating new cards.
        self.current_cards = active_decision_cards(
            self.player_state,
            self.player_state.current_day,
            self.applied_choices,
        )

    def _game_over(self) -> bool:
        """The run ends at project completion or the configured deadline."""
        return self.player_state.final_item_completed or self.player_state.current_shift >= self.player_state.deadline_shift

    def _finish_automated(self) -> None:
        # The benchmark is hidden during play. At game over, fast-forward it
        # through the same deadline so the reveal has a complete comparison.
        while self.automated_state.current_shift < self.automated_state.deadline_shift and not self.automated_state.final_item_completed:
            self.automated_state.daily_notes.clear()
            apply_echo_decisions_for_day(self.automated_state, self.config, self.echo_completed_days)
            advance_day(self.automated_state, self.automated_scheduler)

    def _pieces_payload(self) -> list[dict[str, Any]]:
        """Return the compact top-level job rows rendered by the current UI."""
        pieces = []
        for piece in sorted(self.player_state.pieces.values(), key=lambda item: item.id):
            due_shift = _piece_due_shift(self.player_state, piece)
            projected_shift = _piece_projected_completion_shift(self.player_state, piece)
            completion_shift = _piece_completion_shift(self.player_state, piece)
            finish_shift = completion_shift or projected_shift
            pieces.append(
                {
                    "id": piece.id,
                    "displayId": _piece_display_id(piece.id),
                    "completed": piece.completed_job_count,
                    "total": piece.total_job_count,
                    "dueDate": day_shift(due_shift, self.config.shifts_per_day),
                    "projectedCompletion": day_shift(finish_shift, self.config.shifts_per_day),
                }
            )
        return pieces

    def _critical_path_payload(self) -> list[dict[str, Any]]:
        """Return critical-path rows used by the welcome preview."""
        rows = []
        for job in self.player_state.get_critical_path_jobs()[:18]:
            shop = self.player_state.shops.get(job.shop_id)
            slack = job.due_shift - self.player_state.current_shift - max(0, job.remaining_duration_shifts)
            rows.append(
                {
                    "id": job.id,
                    "shop": shop.name if shop else job.shop_id,
                    "remaining": job.remaining_duration_shifts,
                    "slack": slack,
                    "impact": _piece_display_id(job.piece_id),
                }
            )
        return rows
    
    def _past_due_jobs_payload(self, limit: int = 8) -> list[dict[str, Any]]:
        """Return incomplete subjobs that are already past due."""
        past_due = []

        for job in self.player_state.jobs.values():
            if job.is_complete:
                continue
            if job.due_shift >= self.player_state.current_shift:
                continue

            shop = self.player_state.shops.get(job.shop_id)
            past_due.append(
                {
                    "id": job.id,
                    "piece": _piece_display_id(job.piece_id),
                    "shop": shop.name if shop else job.shop_id,
                    "due": day_shift(job.due_shift, self.config.shifts_per_day),
                    "daysLate": max(
                        1,
                        (self.player_state.current_shift - job.due_shift + self.config.shifts_per_day - 1)
                        // self.config.shifts_per_day,
                    ),
                    "remaining": job.remaining_duration_shifts,
                }
            )

        return sorted(
            past_due,
            key=lambda row: (
                -row["daysLate"],
                row["piece"],
                row["id"],
            ),
        )[:limit]

    def _summary_payload(self) -> dict[str, Any] | None:
        """Return the latest end-of-day summary, if a day has advanced."""
        if not self.last_result:
            return None
        snapshot = self.last_result.end_snapshot
        return {
            "completedToday": len(self.last_result.completed_job_ids),
            "jobsRemaining": snapshot.jobs_remaining,
            "piecesCompleted": snapshot.pieces_completed,
            "jobsBehindSchedule": snapshot.jobs_behind_schedule,
            "jobsLate": snapshot.jobs_late,
            "reschedules": snapshot.reschedules,
            "idleTime": snapshot.idle_time,
            "risk": round(snapshot.schedule_risk, 1),
            "projectedCompletion": day_shift(snapshot.projected_completion_shift, self.config.shifts_per_day),
            "pastDueJobs": self._past_due_jobs_payload(),
            "puzzle": self._summary_puzzle_payload(),
            "notes": self.last_result.notes[-10:],
        }

    def _summary_puzzle_payload(self) -> dict[str, Any]:
        """Return submarine puzzle tiles for the latest daily summary."""
        if not self.last_result:
            return {"day": self.player_state.current_day, "total": 0, "completed": 0, "completedToday": 0, "tiles": []}

        start_shift = self.last_result.start_snapshot.shift
        end_shift = self.last_result.end_snapshot.shift
        tiles = []

        for piece in sorted(self.player_state.pieces.values(), key=lambda item: item.id):
            completion_shift = _piece_completion_shift(self.player_state, piece)
            due_shift = _piece_due_shift(self.player_state, piece)
            completed = completion_shift is not None
            late = bool(completed and completion_shift > due_shift)
            newly_completed = bool(completed and start_shift < completion_shift <= end_shift)

            tiles.append(
                {
                    "id": piece.id,
                    "label": _piece_display_id(piece.id),
                    "name": piece.name,
                    "completed": completed,
                    "newlyCompleted": newly_completed,
                    "late": late,
                    "tone": "late" if late else "on-time" if completed else "pending",
                    "due": day_shift(due_shift, self.config.shifts_per_day),
                    "completedAt": day_shift(completion_shift, self.config.shifts_per_day) if completion_shift else None,
                }
            )

        return {
            "day": self.last_result.end_snapshot.day,
            "total": len(tiles),
            "completed": sum(1 for tile in tiles if tile["completed"]),
            "completedToday": sum(1 for tile in tiles if tile["newlyCompleted"]),
            "tiles": tiles,
        }

    def _final_payload(self) -> dict[str, Any]:
        """Return the final player-vs-ECHO comparison payload."""
        player_snapshot = calculate_snapshot(self.player_state)
        automated_snapshot = calculate_snapshot(self.automated_state)
        review = self._final_review_payload(player_snapshot, automated_snapshot)

        return {
            "player": _snapshot_payload(player_snapshot, self.config.shifts_per_day, self.player_state),
            "automated": _snapshot_payload(automated_snapshot, self.config.shifts_per_day, self.automated_state),
            "decisionAudit": self._decision_audit_payload(),
            "completionHistory": self._completion_history_payload(player_snapshot, automated_snapshot),
            "review": review,
            "explanation": review["reasons"],
        }

    def _completion_history_payload(
        self,
        player_snapshot: MetricSnapshot,
        automated_snapshot: MetricSnapshot,
    ) -> dict[str, Any]:
        """Return question-indexed cumulative subjob completion counts for the final chart."""
        total_jobs = max(len(self.player_state.jobs), len(self.automated_state.jobs))
        player_question_count = sum(
            1
            for record in self.player_state.decision_history
            if record.actor == "player"
        )
        total_questions = max(1, player_question_count)
        questions = list(range(total_questions + 1))

        return {
            "days": questions,
            "questions": questions,
            "total": total_jobs,
            "player": self._completion_series(self.player_state, player_snapshot, total_questions, total_jobs),
            "automated": self._completion_series(self.automated_state, automated_snapshot, total_questions, total_jobs),
            "decisionPoints": self._decision_chart_payload(),
        }

    def _decision_chart_payload(self) -> list[dict[str, Any]]:
        """Return per-question metadata for the final interactive chart."""
        points: list[dict[str, Any]] = []
        player_cumulative = 0.0
        echo_cumulative = 0.0
        player_records = [
            record
            for record in self.player_state.decision_history
            if record.actor == "player"
        ]

        for sequence, record in enumerate(player_records, start=1):
            card = self.player_state.decision_cards.get(record.card_id)
            player_choice = _choice_by_id(card, record.choice_id)
            echo_choice = _choice_by_id(card, record.echo_choice_id)
            player_delta = float(player_choice.score_delta if player_choice else 0.0)
            echo_delta = float(echo_choice.score_delta if echo_choice else 0.0)
            player_cumulative = round(player_cumulative + player_delta, 4)
            echo_cumulative = round(echo_cumulative + echo_delta, 4)
            affected = self._decision_affected_payload(card)

            points.append(
                {
                    "sequence": sequence,
                    "label": f"Q{sequence}",
                    "day": record.day,
                    "questionId": record.card_id,
                    "questionTitle": record.card_title,
                    "questionText": card.description if card else record.card_title,
                    "playerChoiceId": record.choice_id,
                    "playerChoice": record.choice_label,
                    "echoChoiceId": record.echo_choice_id,
                    "echoChoice": record.echo_choice_label or "-",
                    "playerDelta": round(player_delta, 2),
                    "echoDelta": round(echo_delta, 2),
                    "playerCumulativeScore": round(player_cumulative, 2),
                    "echoCumulativeScore": round(echo_cumulative, 2),
                    **affected,
                }
            )

        return points

    def _decision_affected_payload(self, card: DecisionCard | None) -> dict[str, Any]:
        """Return the most specific visible job/subjob target for a card."""
        empty = {
            "affectedJobId": None,
            "affectedSubjobId": None,
            "affectedLabel": "-",
        }
        if not card:
            return empty

        for target_id in card.target_ids:
            job = self.player_state.jobs.get(target_id)
            if job:
                return {
                    "affectedJobId": job.piece_id,
                    "affectedSubjobId": job.id,
                    "affectedLabel": f"{_piece_display_id(job.piece_id)} / {job.id}",
                }

        for target_id in card.target_ids:
            piece = self.player_state.pieces.get(target_id)
            if piece:
                return {
                    "affectedJobId": piece.id,
                    "affectedSubjobId": None,
                    "affectedLabel": _piece_display_id(piece.id),
                }

        for target_id in card.target_ids:
            shop = self.player_state.shops.get(target_id)
            if shop:
                return {
                    "affectedJobId": None,
                    "affectedSubjobId": None,
                    "affectedLabel": f"Shop: {shop.name}",
                }

        for target_id in card.target_ids:
            workcenter = self.player_state.workcenters.get(target_id)
            if workcenter:
                return {
                    "affectedJobId": None,
                    "affectedSubjobId": None,
                    "affectedLabel": f"Workcenter: {workcenter.name}",
                }

        return empty

    def _completion_series(
        self,
        state: SimulationState,
        final_snapshot: MetricSnapshot,
        total_questions: int,
        total_jobs: int,
    ) -> list[int]:
        """Build a carry-forward series bucketed by answered question count."""
        question_count_by_day = self._question_count_by_day(state)
        completions_by_question: dict[int, int] = {0: 0}
        for snapshot in state.metric_history:
            question = max(0, min(total_questions, question_count_by_day.get(snapshot.day, 0)))
            completions_by_question[question] = max(
                completions_by_question.get(question, 0),
                snapshot.jobs_completed,
            )

        final_question = max(0, min(total_questions, question_count_by_day.get(final_snapshot.day, total_questions)))
        completions_by_question[final_question] = max(
            completions_by_question.get(final_question, 0),
            final_snapshot.jobs_completed,
        )

        if state.final_item_completed and state.completion_shift:
            completion_day = max(1, min(self.config.total_days, ((state.completion_shift - 1) // state.shifts_per_day) + 1))
            completion_question = max(0, min(total_questions, question_count_by_day.get(completion_day, total_questions)))
            completions_by_question[completion_question] = max(
                completions_by_question.get(completion_question, 0),
                total_jobs,
            )

        current = 0
        series: list[int] = []
        for question in range(total_questions + 1):
            current = max(current, completions_by_question.get(question, current))
            series.append(min(total_jobs, current))
        return series

    def _question_count_by_day(self, state: SimulationState) -> dict[int, int]:
        """Return cumulative answered decision-question counts by day."""
        questions_on_day: dict[int, int] = {}
        for record in state.decision_history:
            questions_on_day[record.day] = questions_on_day.get(record.day, 0) + 1

        cumulative = 0
        counts = {0: 0}
        for day in range(1, self.config.total_days + 1):
            cumulative += questions_on_day.get(day, 0)
            counts[day] = cumulative
        return counts
    
    def _final_review_payload(
        self,
        player_snapshot: MetricSnapshot,
        automated_snapshot: MetricSnapshot,
    ) -> dict[str, Any]:
        """Explain the main reasons the player won or lost."""
        player_won = player_snapshot.deadline_met
        echo_won = automated_snapshot.deadline_met

        player_complete_label = (
            day_shift(self.player_state.completion_shift, self.config.shifts_per_day)
            if self.player_state.completion_shift
            else "not completed"
        )

        if player_won:
            headline = f"You won: the project finished by the deadline at {player_complete_label}."
            outcome = "won"
        else:
            headline = f"You lost: the project did not finish by the deadline. Final status was {player_complete_label}."
            outcome = "lost"

        reasons: list[str] = []

        if player_won:
            reasons.extend(self._win_reasons(player_snapshot, automated_snapshot))
        else:
            reasons.extend(self._loss_reasons(player_snapshot, automated_snapshot))

        # Always include the benchmark comparison when it is meaningful.
        if echo_won and not player_won:
            reasons.append("ECHO met the deadline while your schedule did not, mainly by protecting critical-path work and reducing queue pressure earlier.")
        elif player_won and not echo_won:
            reasons.append("You beat the benchmark: your schedule met the deadline while ECHO's benchmark run did not.")
        elif player_won and echo_won:
            if self.player_state.completion_shift and self.automated_state.completion_shift:
                delta = self.player_state.completion_shift - self.automated_state.completion_shift
                if delta < 0:
                    reasons.append(f"You finished {abs(delta)} shift(s) earlier than ECHO.")
                elif delta > 0:
                    reasons.append(f"You met the deadline, but ECHO finished {delta} shift(s) earlier.")
                else:
                    reasons.append("You and ECHO finished at the same shift.")

        decision_records = [
            record
            for record in self.player_state.decision_history
            if record.actor == "player"
        ]
        if decision_records:
            matched = sum(1 for record in decision_records if record.aligned_with_echo)
            match_rate = round((matched / len(decision_records)) * 100)
            reasons.append(f"You matched ECHO on {matched}/{len(decision_records)} decisions ({match_rate}%).")

        return {
            "outcome": outcome,
            "headline": headline,
            "reasons": reasons[:8],
        }
    
    def _loss_reasons(
        self,
        player_snapshot: MetricSnapshot,
        automated_snapshot: MetricSnapshot,
    ) -> list[str]:
        """Build specific reasons for a missed-deadline run."""
        reasons: list[str] = []

        incomplete_jobs = [
            job
            for job in self.player_state.jobs.values()
            if not job.is_complete
        ]
        late_jobs = [
            job
            for job in self.player_state.jobs.values()
            if _job_was_late(self.player_state, job)
        ]
        critical_late = [
            job
            for job in late_jobs
            if job.critical_path
        ]
        blocked_jobs = self.player_state.get_blocked_jobs()
        rework_jobs = [
            job
            for job in self.player_state.jobs.values()
            if job.rework_count > 0 or job.status == JobStatus.REWORK_REQUIRED
        ]

        if incomplete_jobs:
            reasons.append(f"{len(incomplete_jobs)} subjob(s) were still incomplete when the deadline arrived.")

        if critical_late:
            reasons.append(f"{len(critical_late)} critical-path subjob(s) were late, which directly pushed the project finish out.")

        if late_jobs:
            reasons.append(f"{len(late_jobs)} total subjob(s) were late by the end of the run.")

        if blocked_jobs:
            reasons.append(f"{len(blocked_jobs)} subjob(s) were still blocked or waiting on dependencies.")

        bottlenecks = self.player_state.get_bottleneck_shops(2)
        if bottlenecks:
            bottleneck_text = ", ".join(shop.name for shop in bottlenecks)
            reasons.append(f"The largest remaining bottleneck pressure was in: {bottleneck_text}.")

        if rework_jobs:
            reasons.append(f"Quality/rework affected {len(rework_jobs)} subjob(s), adding extra schedule pressure.")

        if player_snapshot.schedule_risk >= 70:
            reasons.append(f"End-of-run schedule risk stayed high at {round(player_snapshot.schedule_risk)}/100.")

        if player_snapshot.jobs_late > automated_snapshot.jobs_late:
            delta = player_snapshot.jobs_late - automated_snapshot.jobs_late
            reasons.append(f"Your schedule had {delta} more late subjob(s) than ECHO's benchmark.")

        return reasons or ["The project missed the deadline because remaining work exceeded the available shifts."]


    def _win_reasons(
        self,
        player_snapshot: MetricSnapshot,
        automated_snapshot: MetricSnapshot,
    ) -> list[str]:
        """Build specific reasons for a successful run."""
        reasons: list[str] = []

        if self.player_state.completion_shift:
            margin = self.player_state.deadline_shift - self.player_state.completion_shift
            if margin > 0:
                reasons.append(f"You finished with {margin} shift(s) of deadline margin.")
            else:
                reasons.append("You finished exactly at the deadline.")

        critical_remaining = [
            job
            for job in self.player_state.jobs.values()
            if job.critical_path and not job.is_complete
        ]
        if not critical_remaining:
            reasons.append("All critical-path work was completed before the final review.")

        if player_snapshot.jobs_late == 0:
            reasons.append("No subjobs were late at the end of the run.")
        else:
            reasons.append(f"You still had {player_snapshot.jobs_late} late subjob(s), but recovered enough downstream work to finish.")

        bottlenecks = self.player_state.get_bottleneck_shops(2)
        if bottlenecks:
            bottleneck_text = ", ".join(shop.name for shop in bottlenecks)
            reasons.append(f"You finished despite bottleneck pressure in: {bottleneck_text}.")

        if player_snapshot.schedule_risk < automated_snapshot.schedule_risk:
            reasons.append("Your final schedule risk was lower than ECHO's benchmark.")
        elif player_snapshot.schedule_risk < 45:
            reasons.append(f"Final schedule risk was controlled at {round(player_snapshot.schedule_risk)}/100.")

        return reasons or ["You won because all required jobs were completed before the deadline."]

    def _decision_audit_payload(self) -> list[dict[str, Any]]:
        """Return the player decision trail with ECHO's preferred answers."""
        return [
            {
                "day": record.day,
                "card": record.card_title,
                "playerChoice": record.choice_label,
                "echoChoice": record.echo_choice_label or "-",
                "matched": record.aligned_with_echo,
                "note": record.note,
            }
            for record in self.player_state.decision_history
            if record.actor == "player"
        ]


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
                type(self).session = GameSession(
                    seed=_parse_optional_seed(data.get("seed")),
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


def run_ui_server(seed: int | None = None, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start the local browser UI server."""
    # A fresh handler subclass lets us attach a mutable class-level session
    # without modifying BaseHTTPRequestHandler itself.
    handler = type("SessionHandler", (GameRequestHandler,), {})
    handler.session = GameSession(seed=seed)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}"
    print(f"ECHO Adventure UI running at {url} (normal mode)")
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
    payload = {
        "shift": snapshot.shift,
        "day": snapshot.day,
        "piecesCompleted": snapshot.pieces_completed,
        "jobsCompleted": snapshot.jobs_completed,
        "jobsRemaining": snapshot.jobs_remaining,
        "jobsBehindSchedule": snapshot.jobs_behind_schedule,
        "jobsLate": snapshot.jobs_late,
        "idleTime": snapshot.idle_time,
        "reschedules": snapshot.reschedules,
        "scheduleRisk": round(snapshot.schedule_risk, 1),
        "projectedCompletionShift": snapshot.projected_completion_shift,
        "projectedCompletion": day_shift(snapshot.projected_completion_shift, shifts_per_day),
        "finalItemCompleted": snapshot.final_item_completed,
        "deadlineMet": snapshot.deadline_met,
        "completion": day_shift(completion_shift, shifts_per_day) if completion_shift else None,
    }
    if state:
        payload.update(
            {
                "finalScore": calculate_final_score(state),
                "decisionPathDifferentiator": score_decision_path_differentiator(state),
                "decisionPathSignature": state.decision_path_signature or "-",
            }
        )
    return payload


def _choice_by_id(card: DecisionCard | None, choice_id: str | None) -> DecisionChoice | None:
    """Return a decision choice by id from an optional card."""
    if not card or not choice_id:
        return None
    return next((choice for choice in card.choices if choice.id == choice_id), None)


def _parse_optional_seed(value: Any) -> int | None:
    """Return an integer seed from a JSON value, or None for a random run."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Seed must be an integer.") from exc


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


def _decision_progress_payload(progress: DecisionProgress) -> dict[str, Any]:
    """Convert decision progress into stable UI counters."""
    return {
        "day": progress.day,
        "completed": progress.answered_questions,
        "total": progress.total_questions,
        "visibleCards": progress.visible_cards,
        "openCardIds": progress.open_card_ids,
    }


def _choice_payload(choice: DecisionChoice) -> dict[str, Any]:
    """Convert a decision choice while preserving simulation effect hints."""
    return {
        "id": choice.id,
        "label": choice.label,
        "description": choice.description,
        "riskEffect": choice.risk_effect,
        "rescheduleEffect": choice.reschedule_effect,
    }


def _piece_display_id(piece_id: str) -> str:
    """Convert an internal piece id into the player-facing top-level job label."""
    suffix = piece_id.split("-")[-1] if piece_id else ""
    return f"Job {suffix}" if suffix else "Job"


def _job_was_late(state: SimulationState, job) -> bool:
    """Return whether a subjob finished late or is currently past due."""
    if job.is_complete:
        return job.completed_shift is not None and job.completed_shift > job.due_shift
    return job.due_shift < state.current_shift


def _piece_due_shift(state: SimulationState, piece: PuzzlePiece) -> int:
    """Return the top-level job due shift."""
    due_shifts = [
        state.jobs[job_id].due_shift
        for job_id in piece.job_ids
        if job_id in state.jobs
    ]
    return max(due_shifts, default=state.deadline_shift)


def _piece_projected_completion_shift(state: SimulationState, piece: PuzzlePiece) -> int:
    """Estimate when a top-level job will finish from its remaining dependency path."""
    completion_shift = _piece_completion_shift(state, piece)
    if completion_shift is not None:
        return completion_shift

    job_ids = [job_id for job_id in piece.job_ids if job_id in state.jobs]
    if not job_ids:
        return state.current_shift

    piece_job_ids = set(job_ids)
    memo: dict[str, int] = {}

    def remaining_path(job_id: str) -> int:
        if job_id in memo:
            return memo[job_id]

        job = state.jobs[job_id]
        if job.is_complete:
            own_remaining = 0
        else:
            own_remaining = max(1, job.remaining_duration_shifts)
            if job.status == JobStatus.QUEUED:
                own_remaining += min(4, _job_queue_wait(state, job_id))
            elif job.is_blocked:
                own_remaining += 3

        downstream = [
            remaining_path(dependent_id)
            for dependent_id in job.dependent_job_ids
            if dependent_id in piece_job_ids
        ]
        memo[job_id] = own_remaining + max(downstream, default=0)
        return memo[job_id]

    incomplete = [
        job_id
        for job_id in job_ids
        if not state.jobs[job_id].is_complete
    ]
    if not incomplete:
        return state.current_shift
    return state.current_shift + max(remaining_path(job_id) for job_id in incomplete)


def _job_queue_wait(state: SimulationState, job_id: str) -> int:
    """Return a small queue-position estimate for a queued subjob."""
    job = state.jobs[job_id]
    if not job.assigned_workcenter_id or job.assigned_workcenter_id not in state.workcenters:
        return 0
    wc = state.workcenters[job.assigned_workcenter_id]
    wait = 1 if wc.current_job_id and wc.current_job_id != job_id else 0
    if job_id in wc.queue:
        wait += wc.queue.index(job_id)
    return wait


def _piece_completion_shift(state: SimulationState, piece: PuzzlePiece) -> int | None:
    """Return the shift when all subjobs for a top-level job were complete."""
    completion_shifts = []
    for job_id in piece.job_ids:
        job = state.jobs.get(job_id)
        if not job or not job.is_complete or job.completed_shift is None:
            return None
        completion_shifts.append(job.completed_shift)
    return max(completion_shifts, default=None)
