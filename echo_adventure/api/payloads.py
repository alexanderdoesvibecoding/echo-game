"""Payload builders for the browser UI session state."""

from __future__ import annotations

from typing import Any

from ..decisions import decision_progress
from ..enums import JobStatus
from ..metrics import (
    calculate_completion_bonus,
    calculate_echo_mastery_bonus,
    calculate_final_score,
    calculate_snapshot,
    day_shift,
    update_state_metrics,
)
from ..models import (
    DecisionCard,
    DecisionChoice,
    DecisionProgress,
    DecisionRecord,
    MetricSnapshot,
    PuzzlePiece,
    SimulationState,
)


class PayloadMixin:
    """Build JSON-ready payloads from a GameSession."""

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
            snapshot_payload = _snapshot_payload(snapshot, self.config.shifts_per_day, config=self.config)
            snapshot_payload["jobsCompletedToday"] = self._live_jobs_completed_today()
            payload: dict[str, Any] = {
                "seed": self.seed,
                "gameOver": game_over,
                "day": self.player_state.current_day,
                "currentDate": self.config.date_label_for_day(self.player_state.current_day),
                "dateRange": self.config.date_range_label,
                "deadlineDate": self.config.deadline_date_label,
                "shiftsPerDay": self.config.shifts_per_day,
                "dayCycleDurationMs": self.config.day_cycle_duration_ms,
                "projectedCompletion": self.config.date_label_for_shift(snapshot.projected_completion_shift),
                "snapshot": snapshot_payload,
                "pieces": self._pieces_payload(),
                "pastDueJobs": self._past_due_jobs_payload(),
                "criticalPath": self._critical_path_payload(),
                "decisions": [_card_payload(card, self.applied_choices.get(card.id)) for card in self.current_cards],
                "decisionProgress": _decision_progress_payload(
                    decision_progress(self.player_state, self.player_state.current_day, self.applied_choices)
                ),
                "appliedChoices": self.choice_notes[-6:],
                "livePuzzle": self._live_puzzle_payload(),
                "lastSummary": self._summary_payload(),
            }
            if game_over:
                # The automated state is lazy-finished only when it is needed
                # for the final reveal, keeping normal requests cheap.
                self._finish_automated()
                payload["finalReveal"] = self._final_payload()
            return payload

    def _live_jobs_completed_today(self) -> int:
        """Return subjobs completed during the current in-progress day."""
        if getattr(self, "day_start_snapshot", None) is None:
            return 0
        completed_before = set(getattr(self, "day_completed_before", set()))
        return max(0, len(set(self.player_state.completed_jobs) - completed_before))

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
                    "dueDate": self.config.date_label_for_shift(due_shift),
                    "projectedCompletion": self.config.date_label_for_shift(finish_shift),
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
                    "due": self.config.date_label_for_shift(job.due_shift),
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
            "projectedCompletion": self.config.date_label_for_shift(snapshot.projected_completion_shift),
            "pastDueJobs": self._summary_past_due_jobs_payload(),
            "puzzle": self._summary_puzzle_payload(),
            "notes": self.last_result.notes[-10:],
        }

    def _summary_past_due_jobs_payload(self) -> list[dict[str, Any]]:
        """Return frozen past-due subjob rows for the latest daily summary."""
        if self.last_summary_past_due_jobs is not None:
            return self.last_summary_past_due_jobs
        return self._past_due_jobs_payload()

    def _summary_puzzle_payload(self) -> dict[str, Any]:
        """Return submarine puzzle tiles for the latest daily summary."""
        if self.last_summary_puzzle is not None:
            return self.last_summary_puzzle
        return self._build_summary_puzzle_payload()

    def _live_puzzle_payload(self) -> dict[str, Any]:
        """Return the current submarine assembly state for live page rendering."""
        start_shift = (
            getattr(self, "day_start_shift", None)
            if getattr(self, "day_start_snapshot", None) is not None
            else None
        )
        return self._build_puzzle_payload(
            day=self.player_state.current_day,
            start_shift=start_shift,
            end_shift=self.player_state.current_shift,
        )

    def _build_summary_puzzle_payload(self) -> dict[str, Any]:
        """Build submarine puzzle tiles at the moment a daily summary is created."""
        if not self.last_result:
            return {"day": self.player_state.current_day, "total": 0, "completed": 0, "completedToday": 0, "tiles": []}

        return self._build_puzzle_payload(
            day=self.last_result.end_snapshot.day,
            start_shift=self.last_result.start_snapshot.shift,
            end_shift=self.last_result.end_snapshot.shift,
        )

    def _build_puzzle_payload(
        self,
        day: int,
        start_shift: int | None,
        end_shift: int,
    ) -> dict[str, Any]:
        """Build submarine puzzle tiles for a shift window."""
        tiles = []

        for piece in sorted(self.player_state.pieces.values(), key=lambda item: item.id):
            completion_shift = _piece_completion_shift(self.player_state, piece)
            due_shift = _piece_due_shift(self.player_state, piece)
            completed = completion_shift is not None
            late = bool(completed and completion_shift > due_shift)
            newly_completed = bool(
                completed
                and start_shift is not None
                and start_shift < completion_shift <= end_shift
            )

            tiles.append(
                {
                    "id": piece.id,
                    "label": _piece_display_id(piece.id),
                    "name": piece.name,
                    "completed": completed,
                    "newlyCompleted": newly_completed,
                    "late": late,
                    "tone": "late" if late else "on-time" if completed else "pending",
                    "due": self.config.date_label_for_shift(due_shift),
                    "completedAt": self.config.date_label_for_shift(completion_shift) if completion_shift else None,
                }
            )

        return {
            "day": day,
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
            "player": _snapshot_payload(
                player_snapshot,
                self.config.shifts_per_day,
                self.player_state,
                config=self.config,
            ),
            "automated": _snapshot_payload(
                automated_snapshot,
                self.config.shifts_per_day,
                self.automated_state,
                config=self.config,
            ),
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
        echo_question_count = sum(
            1
            for record in self.automated_state.decision_history
            if record.actor == "ECHO"
        )
        total_questions = max(1, player_question_count, echo_question_count)
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
        """Return decision metadata aligned by the day it actually occurred.

        Player and ECHO records used to be zipped only by sequence.  When
        ECHO completed earlier, its last real answers were displayed beside
        later player dates, making it look as though it kept receiving
        questions after all of its subjobs were done.
        """
        points: list[dict[str, Any]] = []
        player_cumulative = 0.0
        echo_cumulative = 0.0
        player_records = [
            record
            for record in self.player_state.decision_history
            if record.actor == "player"
        ]
        echo_records = [
            record
            for record in self.automated_state.decision_history
            if record.actor == "ECHO"
            and self._record_precedes_echo_completion(record)
        ]
        player_completion = _completion_score_record(self.player_state, "player")
        echo_completion = _completion_score_record(self.automated_state, "ECHO")
        if player_completion:
            player_records.append(player_completion)
        if echo_completion:
            echo_records.append(echo_completion)
        player_by_day = _records_by_day(player_records)
        echo_by_day = _records_by_day(echo_records)
        sequence = 0

        for day in sorted(set(player_by_day) | set(echo_by_day)):
            day_player_records = player_by_day.get(day, [])
            day_echo_records = echo_by_day.get(day, [])
            slots = max(len(day_player_records), len(day_echo_records))
            for slot in range(slots):
                sequence += 1
                record = day_player_records[slot] if slot < len(day_player_records) else None
                echo_record = day_echo_records[slot] if slot < len(day_echo_records) else None
                card = self.player_state.decision_cards.get(record.card_id) if record else None
                echo_card = self.automated_state.decision_cards.get(echo_record.card_id) if echo_record else None
                player_choice = _choice_by_id(card, record.choice_id) if record else None
                echo_choice = _choice_by_id(echo_card, echo_record.choice_id) if echo_record else None
                player_delta = _record_score_delta(record, player_choice)
                echo_delta = _record_score_delta(echo_record, echo_choice)
                player_cumulative = round(player_cumulative + player_delta, 4)
                echo_cumulative = round(echo_cumulative + echo_delta, 4)
                affected = self._decision_affected_payload(card) if card else self._decision_affected_payload(
                    echo_card,
                    state=self.automated_state,
                )
                question_card = card or echo_card
                question_record = record or echo_record
                player_is_score_event = bool(record and record.record_kind != "decision")
                echo_is_score_event = bool(echo_record and echo_record.record_kind != "decision")

                points.append(
                    {
                        "sequence": sequence,
                        "label": f"Q{sequence}",
                        "day": day,
                        "dateLabel": self.config.date_label_for_day(day),
                        "questionId": question_record.card_id,
                        "questionTitle": question_record.card_title,
                        "questionText": question_card.description if question_card else question_record.card_title,
                        "playerQuestionId": record.card_id if record and not player_is_score_event else None,
                        "playerQuestionTitle": record.card_title if record else "-",
                        "echoQuestionId": echo_record.card_id if echo_record and not echo_is_score_event else None,
                        "echoQuestionTitle": echo_record.card_title if echo_record else "-",
                        "sameQuestion": bool(
                            record
                            and echo_record
                            and not player_is_score_event
                            and not echo_is_score_event
                            and record.card_id == echo_record.card_id
                        ),
                        "playerEventKind": record.record_kind if record else None,
                        "echoEventKind": echo_record.record_kind if echo_record else None,
                        "playerScoreEvent": player_is_score_event,
                        "echoScoreEvent": echo_is_score_event,
                        "playerChoiceId": record.choice_id if record else None,
                        "playerChoice": record.choice_label if record else "-",
                        "echoChoiceId": echo_record.choice_id if echo_record else None,
                        "echoChoice": echo_record.choice_label if echo_record else "-",
                        "playerDelta": round(player_delta, 2),
                        "echoDelta": round(echo_delta, 2),
                        "playerCumulativeScore": round(player_cumulative, 2),
                        "echoCumulativeScore": round(echo_cumulative, 2),
                        **affected,
                    }
                )

        return points

    def _record_precedes_echo_completion(self, record) -> bool:
        """Exclude impossible/stale ECHO answers recorded after completion."""
        completion_shift = self.automated_state.completion_shift
        if completion_shift is None:
            return True
        if record.shift is not None:
            return record.shift <= completion_shift
        completion_day = max(1, ((completion_shift - 1) // self.automated_state.shifts_per_day) + 1)
        return record.day <= completion_day

    def _decision_affected_payload(
        self,
        card: DecisionCard | None,
        state: SimulationState | None = None,
    ) -> dict[str, Any]:
        """Return the most specific visible job/subjob target for a card."""
        state = state or self.player_state
        empty = {
            "affectedJobId": None,
            "affectedSubjobId": None,
            "affectedLabel": "-",
        }
        if not card:
            return empty

        for target_id in card.target_ids:
            job = state.jobs.get(target_id)
            if job:
                return {
                    "affectedJobId": job.piece_id,
                    "affectedSubjobId": job.id,
                    "affectedLabel": f"{_piece_display_id(job.piece_id)} / {job.id}",
                }

        for target_id in card.target_ids:
            piece = state.pieces.get(target_id)
            if piece:
                return {
                    "affectedJobId": piece.id,
                    "affectedSubjobId": None,
                    "affectedLabel": _piece_display_id(piece.id),
                }

        for target_id in card.target_ids:
            shop = state.shops.get(target_id)
            if shop:
                return {
                    "affectedJobId": None,
                    "affectedSubjobId": None,
                    "affectedLabel": f"Shop: {shop.name}",
                }

        for target_id in card.target_ids:
            workcenter = state.workcenters.get(target_id)
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
            completion_day = max(
                1,
                min(self.config.total_days, ((state.completion_shift - 1) // state.shifts_per_day) + 1),
            )
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


def _completion_score_record(state: SimulationState, actor: str) -> DecisionRecord | None:
    """Represent the realized early-finish payoff on the same score timeline."""
    mastery_bonus = calculate_echo_mastery_bonus(state)
    bonus = calculate_completion_bonus(state) + mastery_bonus
    if bonus <= 0 or state.completion_shift is None:
        return None
    day = max(1, ((state.completion_shift - 1) // state.shifts_per_day) + 1)
    same_shift_days = [
        record.day
        for record in state.decision_history
        if record.shift == state.completion_shift
    ]
    if same_shift_days:
        day = max(day, *same_shift_days)
    return DecisionRecord(
        day=day,
        card_id=f"SCORE-COMPLETION-{actor.upper()}",
        card_title="Project completed",
        actor=actor,
        choice_id="early-finish-bonus",
        choice_label=(
            "Early completion + benchmark mastery payoff"
            if mastery_bonus
            else "Early completion payoff"
        ),
        echo_choice_id=None,
        echo_choice_label=None,
        aligned_with_echo=False,
        note="Finished with time remaining before the deadline.",
        score_delta=bonus,
        cumulative_score=calculate_final_score(state),
        shift=state.completion_shift,
        record_kind="completion",
    )


def _records_by_day(records) -> dict[int, list]:
    """Group decision records without moving answers onto another date."""
    grouped: dict[int, list] = {}
    for record in records:
        grouped.setdefault(record.day, []).append(record)
    return grouped


def _record_score_delta(record, choice: DecisionChoice | None) -> float:
    """Read the immutable ledger value, falling back for legacy save data."""
    if record is not None and record.score_delta is not None:
        return float(record.score_delta)
    return float(choice.score_delta if choice else 0.0)

def _snapshot_payload(
    snapshot: MetricSnapshot,
    shifts_per_day: int,
    state: SimulationState | None = None,
    config=None,
) -> dict[str, Any]:
    """Convert a MetricSnapshot into frontend-friendly camelCase fields."""
    completion_shift = state.completion_shift if state else None
    shift_label = config.date_label_for_shift if config else lambda shift: day_shift(shift, shifts_per_day)
    payload = {
        "shift": snapshot.shift,
        "day": snapshot.day,
        "date": config.date_label_for_day(snapshot.day) if config else day_shift(snapshot.shift, shifts_per_day),
        "piecesCompleted": snapshot.pieces_completed,
        "jobsCompleted": snapshot.jobs_completed,
        "jobsRemaining": snapshot.jobs_remaining,
        "jobsBehindSchedule": snapshot.jobs_behind_schedule,
        "jobsLate": snapshot.jobs_late,
        "idleTime": snapshot.idle_time,
        "reschedules": snapshot.reschedules,
        "scheduleRisk": round(snapshot.schedule_risk, 1),
        "projectedCompletionShift": snapshot.projected_completion_shift,
        "projectedCompletion": shift_label(snapshot.projected_completion_shift),
        "finalItemCompleted": snapshot.final_item_completed,
        "deadlineMet": snapshot.deadline_met,
        "completion": shift_label(completion_shift) if completion_shift else None,
    }
    if state:
        payload.update(
            {
                "finalScore": calculate_final_score(state),
                "maxScheduleRisk": _max_schedule_risk(state, snapshot),
            }
        )
    return payload


def _max_schedule_risk(state: SimulationState, current_snapshot: MetricSnapshot) -> float:
    """Return the highest run risk captured in stored snapshots or the current snapshot."""
    return round(
        max(
            [state.max_schedule_risk_seen, current_snapshot.schedule_risk]
            + [snapshot.schedule_risk for snapshot in state.metric_history],
            default=current_snapshot.schedule_risk,
        ),
        1,
    )


def _choice_by_id(card: DecisionCard | None, choice_id: str | None) -> DecisionChoice | None:
    """Return a decision choice by id from an optional card."""
    if not card or not choice_id:
        return None
    return next((choice for choice in card.choices if choice.id == choice_id), None)


def _card_payload(card: DecisionCard, selected_choice: str | None) -> dict[str, Any]:
    """Convert a decision card into the shape rendered by the modal UI."""
    return {
        "id": card.id,
        "type": card.type.value,
        "title": card.title,
        "description": card.description,
        "context": card.context_label,
        "isFollowUp": card.is_follow_up,
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
    """Convert a choice without exposing internal shift/risk arithmetic."""
    return {
        "id": choice.id,
        "label": choice.label,
        "description": choice.description,
    }


def _piece_display_id(piece_id: str) -> str:
    """Convert an internal piece id into the player-facing top-level job label."""
    suffix = piece_id.split("-")[-1] if piece_id else ""
    return f"Job {suffix}" if suffix else "Job"


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
