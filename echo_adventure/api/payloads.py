"""JSON payloads for the jobs-only browser UI."""

from __future__ import annotations

from typing import Any

from ..decisions import decision_progress
from ..metrics import calculate_final_score, calculate_snapshot
from ..models import DecisionCard, DecisionChoice, MetricSnapshot, SimulationState


class PayloadMixin:
    def state_payload(self) -> dict[str, Any]:
        with self.lock:
            self._ensure_cards()
            snapshot = calculate_snapshot(self.player_state)
            progress = decision_progress(self.current_cards, self.applied_choices, self.player_state.current_day)
            payload: dict[str, Any] = {
                "seed": self.seed,
                "gameOver": self._game_over(),
                "day": self.player_state.current_day,
                "currentDate": self.config.date_label_for_day(self.player_state.current_day),
                "jobCount": len(self.player_state.jobs),
                "dayCycleDurationMs": self.config.day_cycle_duration_ms,
                "dailySummaryCounterDurationMs": self.config.daily_summary_counter_duration_ms,
                "projectedCompletion": self.config.date_label_for_day(snapshot.projected_completion_day),
                "snapshot": self._snapshot_payload(snapshot, self.player_state),
                "jobs": self._jobs_payload(),
                "decisions": [self._card_payload(card, self.applied_choices.get(card.id)) for card in self.current_cards],
                "decisionProgress": {
                    "day": progress.day,
                    "completed": progress.answered_questions,
                    "total": progress.total_questions,
                    "visibleCards": progress.total_questions,
                    "openCardIds": progress.open_card_ids,
                },
                "appliedChoices": self.choice_notes[-6:],
                "livePuzzle": self._build_puzzle_payload(
                    self.player_state.current_day,
                    set(self.player_state.completed_jobs),
                ),
                "lastSummary": self._summary_payload(),
            }
            if self._game_over():
                self._finish_automated()
                payload["finalReveal"] = self._final_payload()
            return payload

    def _jobs_payload(self) -> list[dict[str, Any]]:
        rows = []
        for job in sorted(self.player_state.jobs.values(), key=lambda item: item.id):
            visible_remaining = max(0, job.remaining_days)
            worked = job.initial_duration_days - min(job.initial_duration_days, visible_remaining)
            rows.append(
                {
                    "id": job.id,
                    "label": _job_label(job.id),
                    "name": job.name,
                    "initialDays": job.initial_duration_days,
                    "remainingDays": visible_remaining,
                    "completed": job.is_complete,
                    "completedDay": job.completed_day,
                    "progress": 1.0 if job.is_complete else max(0.0, worked / job.initial_duration_days),
                }
            )
        return rows

    def _summary_payload(self) -> dict[str, Any] | None:
        if not self.last_result:
            return None
        snapshot = self.last_result.end_snapshot
        return {
            "day": self.last_result.day,
            "date": self.config.date_label_for_day(self.last_result.day),
            "completedToday": len(self.last_result.completed_job_ids),
            "jobsRemaining": snapshot.jobs_remaining,
            "jobsComplete": snapshot.jobs_completed,
            "previousTotalRemainingDays": self.last_result.start_snapshot.total_remaining_days,
            "totalRemainingDays": snapshot.total_remaining_days,
            "projectedCompletion": self.config.date_label_for_day(snapshot.projected_completion_day),
            "puzzle": self.last_summary_puzzle,
            "notes": self.last_result.notes[-10:] if self.last_result.completed_job_ids else [],
        }

    def _build_puzzle_payload(self, day: int, completed_before: set[str]) -> dict[str, Any]:
        tiles = []
        for job in sorted(self.player_state.jobs.values(), key=lambda item: item.id):
            tiles.append(
                {
                    "id": job.id,
                    "label": _job_label(job.id),
                    "name": job.name,
                    "completed": job.is_complete,
                    "newlyCompleted": job.is_complete and job.id not in completed_before,
                    "completedAt": (
                        self.config.date_label_for_day(job.completed_day)
                        if job.completed_day is not None
                        else None
                    ),
                    "remainingDays": job.remaining_days,
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
        player_snapshot = calculate_snapshot(self.player_state)
        automated_snapshot = calculate_snapshot(self.automated_state)
        return {
            "player": self._snapshot_payload(player_snapshot, self.player_state),
            "automated": self._snapshot_payload(automated_snapshot, self.automated_state),
            "completionHistory": self._completion_history_payload(),
            "decisionComparison": self._decision_comparison_payload(),
            "review": self._final_review_payload(),
        }

    def _completion_history_payload(self) -> dict[str, Any]:
        """Return completion totals plus decision-score points for the final chart."""
        player_by_day = {snapshot.day: snapshot.jobs_completed for snapshot in self.player_state.metric_history}
        echo_by_day = {snapshot.day: snapshot.jobs_completed for snapshot in self.automated_state.metric_history}
        if self.player_state.final_item_completed and self.player_state.completion_day is not None:
            player_by_day[self.player_state.completion_day] = len(self.player_state.jobs)
        if self.automated_state.final_item_completed and self.automated_state.completion_day is not None:
            echo_by_day[self.automated_state.completion_day] = len(self.automated_state.jobs)
        final_day = max(
            self.player_state.completion_day or 1,
            self.automated_state.completion_day or 1,
        )
        player_value = 0
        echo_value = 0
        history = []
        for day in range(0, final_day + 1):
            player_value = player_by_day.get(day, player_value)
            echo_value = echo_by_day.get(day, echo_value)
            history.append(
                {
                    "day": day,
                    "label": "Start" if day == 0 else self.config.date_label_for_day(day),
                    "player": player_value,
                    "automated": echo_value,
                }
            )
        return {
            "days": [point["day"] for point in history],
            "total": max(len(self.player_state.jobs), len(self.automated_state.jobs)),
            "player": [point["player"] for point in history],
            "automated": [point["automated"] for point in history],
            "decisionPoints": self._decision_chart_payload(),
        }

    def _decision_chart_payload(self) -> list[dict[str, Any]]:
        """Align player and ECHO decisions by game day for the score chart."""
        player_by_day: dict[int, list[Any]] = {}
        echo_by_day: dict[int, list[Any]] = {}
        for record in self.player_state.decision_history:
            if record.actor == "player":
                player_by_day.setdefault(record.day, []).append(record)
        for record in self.automated_state.decision_history:
            if record.actor == "ECHO":
                echo_by_day.setdefault(record.day, []).append(record)

        points = []
        sequence = 0
        for day in sorted(set(player_by_day) | set(echo_by_day)):
            player_records = player_by_day.get(day, [])
            echo_records = echo_by_day.get(day, [])
            for slot in range(max(len(player_records), len(echo_records))):
                sequence += 1
                player_record = player_records[slot] if slot < len(player_records) else None
                echo_record = echo_records[slot] if slot < len(echo_records) else None
                player_card = (
                    self.player_state.decision_cards.get(player_record.card_id)
                    if player_record
                    else None
                )
                echo_card = (
                    self.automated_state.decision_cards.get(echo_record.card_id)
                    if echo_record
                    else None
                )
                card = player_card or echo_card
                record = player_record or echo_record
                points.append(
                    {
                        "sequence": sequence,
                        "label": f"Q{sequence}",
                        "day": day,
                        "dateLabel": self.config.date_label_for_day(day),
                        "questionId": record.card_id,
                        "questionTitle": record.card_title,
                        "questionText": card.description if card else record.card_title,
                        "playerQuestionId": player_record.card_id if player_record else None,
                        "echoQuestionId": echo_record.card_id if echo_record else None,
                        "playerEventKind": "decision" if player_record else None,
                        "echoEventKind": "decision" if echo_record else None,
                        "playerChoice": player_record.choice_label if player_record else "-",
                        "echoChoice": echo_record.choice_label if echo_record else "-",
                        "playerDelta": round(player_record.score_delta, 2) if player_record else 0,
                        "echoDelta": round(echo_record.score_delta, 2) if echo_record else 0,
                        "playerCumulativeScore": (
                            round(player_record.cumulative_score, 2) if player_record else None
                        ),
                        "echoCumulativeScore": (
                            round(echo_record.cumulative_score, 2) if echo_record else None
                        ),
                        "affectedLabel": card.context_label if card else "-",
                    }
                )
        return points

    def _decision_comparison_payload(self) -> list[dict[str, Any]]:
        echo_records = {record.card_id: record for record in self.automated_state.decision_history}
        rows = []
        for record in self.player_state.decision_history:
            echo = echo_records.get(record.card_id)
            rows.append(
                {
                    "day": record.day,
                    "question": record.card_title,
                    "playerChoice": record.choice_label,
                    "echoChoice": echo.choice_label if echo else record.echo_choice_label,
                    "aligned": record.aligned_with_echo,
                    "scoreDelta": record.score_delta,
                }
            )
        return rows

    def _snapshot_payload(self, snapshot: MetricSnapshot, state: SimulationState) -> dict[str, Any]:
        return {
            "day": snapshot.day,
            "date": self.config.date_label_for_day(snapshot.day),
            "jobsCompleted": snapshot.jobs_completed,
            "jobsRemaining": snapshot.jobs_remaining,
            "totalRemainingDays": snapshot.total_remaining_days,
            "projectedCompletionDay": snapshot.projected_completion_day,
            "projectedCompletion": self.config.date_label_for_day(snapshot.projected_completion_day),
            "finalItemCompleted": snapshot.final_item_completed,
            "completionDay": state.completion_day,
            "completion": (
                self.config.date_label_for_day(state.completion_day)
                if state.completion_day is not None
                else None
            ),
            "finalScore": calculate_final_score(state),
        }

    @staticmethod
    def _card_payload(card: DecisionCard, selected_choice: str | None) -> dict[str, Any]:
        return {
            "id": card.id,
            "type": card.type.value,
            "title": card.title,
            "description": card.description,
            "context": card.context_label,
            "selectedChoice": selected_choice,
            "choices": [_choice_payload(choice) for choice in card.choices],
        }


def _choice_payload(choice: DecisionChoice) -> dict[str, Any]:
    return {
        "id": choice.id,
        "label": choice.label,
        "description": choice.description,
    }


def _job_label(job_id: str) -> str:
    suffix = job_id.rsplit("-", 1)[-1]
    return f"Job {int(suffix)}"
