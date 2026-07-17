"""JSON payloads for the jobs-only browser UI."""

from __future__ import annotations

from typing import Any

from ..metrics import calculate_snapshot
from ..models import DecisionCard, DecisionChoice, MetricSnapshot, SimulationState


class PayloadMixin:
    def state_payload(self) -> dict[str, Any]:
        with self.lock:
            self._ensure_cards()
            snapshot = calculate_snapshot(self.player_state)
            automated_snapshot = calculate_snapshot(self.automated_state)
            payload: dict[str, Any] = {
                "seed": self.seed,
                "gameOver": self._game_over(),
                "day": self.player_state.current_day,
                "currentDate": self.config.date_label_for_day(self.player_state.current_day),
                "scheduleStartDate": self.config.date_label_for_day(1),
                "jobCount": len(self.player_state.jobs),
                "dayCycleDurationMs": self.config.day_cycle_duration_ms,
                "dailySummaryCounterDurationMs": self.config.daily_summary_counter_duration_ms,
                "timelines": {
                    "player": self._timeline_payload(snapshot, self.player_state),
                    "echo": self._timeline_payload(automated_snapshot, self.automated_state),
                },
                "decisions": [self._card_payload(card) for card in self.current_cards],
                "decisionProgress": {
                    "completed": self.questions_answered_today,
                    "total": self.decision_total_today,
                },
                "livePuzzle": self._build_puzzle_payload(
                    set(self.player_state.completed_jobs)
                ),
                "lastSummary": self._summary_payload(),
            }
            if self._game_over():
                self._finish_automated()
                payload["finalReveal"] = self._final_payload()
            return payload

    def _summary_payload(self) -> dict[str, Any] | None:
        if not self.last_result:
            return None
        snapshot = self.last_result.end_snapshot
        return {
            "date": self.config.date_label_for_day(self.last_result.day),
            "completedToday": len(self.last_result.completed_job_ids),
            "jobsRemaining": snapshot.jobs_remaining,
            "previousTotalRemainingDays": self.last_result.start_snapshot.total_remaining_days,
            "totalRemainingDays": snapshot.total_remaining_days,
            "projectedCompletion": self.config.date_label_for_day(snapshot.projected_completion_day),
            "puzzle": self.last_summary_puzzle,
            "notes": self.last_result.notes[-10:] if self.last_result.completed_job_ids else [],
        }

    def _build_puzzle_payload(self, completed_before: set[str]) -> dict[str, Any]:
        tiles = []
        for job in sorted(self.player_state.jobs.values(), key=lambda item: item.id):
            tiles.append(
                {
                    "label": _job_label(job.id),
                    "name": job.name,
                    "completed": job.is_complete,
                    "newlyCompleted": job.is_complete and job.id not in completed_before,
                    "completedAt": (
                        self.config.date_label_for_day(job.completed_day)
                        if job.completed_day is not None
                        else None
                    ),
                }
            )
        return {"tiles": tiles}

    def _final_payload(self) -> dict[str, Any]:
        return {
            "player": self._final_actor_payload(self.player_state),
            "automated": self._final_actor_payload(self.automated_state),
            "completionHistory": self._completion_history_payload(),
            "review": self._final_review_payload(),
        }

    def _completion_history_payload(self) -> dict[str, Any]:
        return {"decisionPoints": self._decision_chart_payload()}

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
        for day in sorted(set(player_by_day) | set(echo_by_day)):
            player_records = player_by_day.get(day, [])
            echo_records = echo_by_day.get(day, [])
            for slot in range(max(len(player_records), len(echo_records))):
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
                player_decision = (
                    _chart_decision_payload(
                        player_record,
                        player_card,
                        position=slot + 1,
                        include_echo_preference=True,
                    )
                    if player_record
                    else None
                )
                echo_decision = (
                    _chart_decision_payload(
                        echo_record,
                        echo_card,
                        position=slot + 1,
                        include_echo_preference=False,
                    )
                    if echo_record
                    else None
                )
                points.append(
                    {
                        "day": day,
                        "dateLabel": self.config.date_label_for_day(day),
                        "playerDecision": player_decision,
                        "echoDecision": echo_decision,
                    }
                )
        return points

    def _final_actor_payload(self, state: SimulationState) -> dict[str, Any]:
        return {
            "completionDay": state.completion_day,
            "completion": (
                self.config.date_label_for_day(state.completion_day)
                if state.completion_day is not None
                else None
            ),
            "finalScore": round(state.decision_score, 2),
        }

    def _timeline_payload(
        self,
        snapshot: MetricSnapshot,
        state: SimulationState,
    ) -> dict[str, Any]:
        """Return an actor projection positioned against the shared story date."""
        start_day = 1
        story_day = max(start_day, self.player_state.current_day)
        if snapshot.final_item_completed and state.completion_day is not None:
            # A finished actor's endpoint is its actual completion day. Using the
            # advancing story day here made ECHO's displayed ECD keep moving after
            # ECHO had finished and repeatedly rescaled the completed timeline.
            display_completion_day = state.completion_day
            progress_percent = 100.0
        else:
            display_completion_day = max(story_day, snapshot.projected_completion_day)
            represented_days = display_completion_day - start_day
            if represented_days <= 0:
                progress_percent = 100.0 if story_day >= display_completion_day else 0.0
            else:
                elapsed_days = max(0, story_day - start_day)
                progress_percent = max(
                    0.0,
                    min(100.0, elapsed_days / represented_days * 100.0),
                )
        return {
            "projectedCompletion": self.config.date_label_for_day(
                snapshot.projected_completion_day
            ),
            "displayCompletion": self.config.date_label_for_day(display_completion_day),
            "completion": (
                self.config.date_label_for_day(state.completion_day)
                if state.completion_day is not None
                else None
            ),
            "progressPercent": round(progress_percent, 4),
        }

    @staticmethod
    def _card_payload(card: DecisionCard) -> dict[str, Any]:
        return {
            "id": card.id,
            "title": card.title,
            "description": card.description,
            "choices": [_choice_payload(choice) for choice in card.choices],
        }


def _choice_payload(choice: DecisionChoice) -> dict[str, Any]:
    return {
        "id": choice.id,
        "label": choice.label,
        "icon": choice.icon_key,
    }


def _chart_decision_payload(
    record: Any,
    card: DecisionCard | None,
    *,
    position: int,
    include_echo_preference: bool,
) -> dict[str, Any]:
    """Keep one actor's question context attached to that actor's answer."""
    payload = {
        "position": position,
        "questionId": record.card_id,
        "questionTitle": record.card_title,
        "questionText": card.description if card else record.card_title,
        "choice": record.choice_label,
        "scoreDelta": round(record.score_delta, 2),
        "cumulativeScore": round(record.cumulative_score, 2),
        "affectedLabel": card.context_label if card else "-",
    }
    if include_echo_preference:
        payload.update(
            {
                "echoPreferredChoice": record.echo_choice_label,
                "alignedWithEcho": record.aligned_with_echo,
            }
        )
    return payload


def _job_label(job_id: str) -> str:
    suffix = job_id.rsplit("-", 1)[-1]
    return f"Job {int(suffix)}"
