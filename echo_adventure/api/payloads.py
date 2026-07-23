"""JSON payloads for the jobs-only browser UI."""

from __future__ import annotations

from typing import Any

from ..decisions import (
    projected_completion_day_after_choice,
    select_echo_choice_for_state,
)
from ..metrics import calculate_snapshot
from ..models import DecisionCard, DecisionChoice, MetricSnapshot, SimulationState
from ..scoring import public_score, public_score_delta
from .developer import inspect_preplanned_follow_up, inspect_runtime_follow_up


_FINAL_ASSEMBLY_DAY_CYCLE_DURATION_MS = 2_000
_FINAL_ASSEMBLY_SUMMARY_COUNTER_DURATION_MS = 500


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
                "dayCycleDurationMs": (
                    _FINAL_ASSEMBLY_DAY_CYCLE_DURATION_MS
                    if self.player_final_assembly_locked
                    else self.config.day_cycle_duration_ms
                ),
                "dailySummaryCounterDurationMs": (
                    _FINAL_ASSEMBLY_SUMMARY_COUNTER_DURATION_MS
                    if self.player_final_assembly_locked
                    else self.config.daily_summary_counter_duration_ms
                ),
                "timelines": {
                    "player": self._timeline_payload(snapshot, self.player_state),
                    "echo": self._timeline_payload(automated_snapshot, self.automated_state),
                },
                "decisions": [self._card_payload(card) for card in self.current_cards],
                "decisionProgress": {
                    "completed": self.questions_answered_today,
                    "total": self.decision_total_today,
                },
                "finalAssembly": self._final_assembly_payload(),
                "livePuzzle": self._build_puzzle_payload(
                    set(self.player_state.completed_jobs)
                ),
                "lastSummary": self._summary_payload(),
            }
            if self._game_over():
                self._finish_automated()
                payload["finalReveal"] = self._final_payload()
            if self.dev_mode:
                in_decision_web = (
                    not self._game_over()
                    and not self.player_in_overtime
                    and not self.player_final_assembly_started
                )
                payload["developer"] = {
                    "generation": {},
                    "runState": {
                        "inDecisionWeb": in_decision_web,
                        "canSkipToEnd": not self._game_over(),
                        "canSkipToDay": in_decision_web,
                        "reachableDaysByStrategy": (
                            self.reachable_days_by_strategy()
                            if in_decision_web
                            else {}
                        ),
                    },
                }
            return payload

    def _final_assembly_payload(self) -> dict[str, Any] | None:
        if not self.player_final_assembly_started:
            return None
        job_name = (
            self.final_assembly_cards[0].context_label
            if self.final_assembly_cards
            else "the final job"
        )
        return {
            "active": True,
            "status": "locked" if self.player_final_assembly_locked else "planning",
            "jobName": job_name,
        }

    def _summary_payload(self) -> dict[str, Any] | None:
        if not self.last_result:
            return None
        snapshot = self.last_result.end_snapshot
        job_count = len(self.player_state.jobs)
        return {
            "date": self.config.date_label_for_day(self.last_result.day),
            "completedToday": len(self.last_result.completed_job_ids),
            "previousJobsComplete": job_count - self.last_result.start_snapshot.jobs_remaining,
            "jobsComplete": job_count - snapshot.jobs_remaining,
            "previousJobsRemaining": self.last_result.start_snapshot.jobs_remaining,
            "jobsRemaining": snapshot.jobs_remaining,
            "previousTotalRemainingDays": self.last_result.start_snapshot.total_remaining_days,
            "totalRemainingDays": snapshot.total_remaining_days,
            "remainingJobs": self.last_summary_remaining_jobs,
            "projectedCompletion": self.config.date_label_for_day(snapshot.projected_completion_day),
            "puzzle": self.last_summary_puzzle,
            "notes": self.last_result.notes[-10:] if self.last_result.completed_job_ids else [],
        }

    def _build_remaining_jobs_payload(self) -> list[dict[str, Any]]:
        remaining_jobs = sorted(
            self.player_state.incomplete_jobs(),
            key=lambda job: job.id,
        )
        return [
            {
                "name": job.name,
                "remainingDays": max(0, job.remaining_days),
            }
            for job in remaining_jobs
        ]

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
                        include_echo_preference=(
                            player_record.aligned_with_echo is not None
                        ),
                        echo_comparison_state=_echo_comparison_state(
                            player_card,
                            echo_card,
                        ),
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
                        echo_comparison_state="different-events",
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
            "finalScore": public_score(state.decision_score),
            "unfinishedJobDays": state.cumulative_unfinished_job_days,
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
            # The completion date is a workday, not a point reached at its start.
            # Count it in the represented duration so an unfinished actor stays
            # short of 100% while that day's decisions are still being answered.
            represented_days = display_completion_day - start_day + 1
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

    def _card_payload(self, card: DecisionCard) -> dict[str, Any]:
        preference = self._choice_preference_payload(card) if self.dev_mode else None
        payload = {
            "id": card.id,
            "title": card.title,
            "description": card.description,
            "choices": [
                _choice_payload(
                    choice,
                    developer=(
                        self._choice_diagnostics_payload(
                            card,
                            choice,
                            preference or {},
                        )
                        if self.dev_mode
                        else None
                    ),
                )
                for choice in card.choices
            ],
            "eventId": card.event_id or card.id,
            "eventScope": card.event_scope,
        }
        if preference is not None:
            payload["developer"] = {"preference": preference}
            generated_by = self._generated_by_payload(card)
            if generated_by is not None:
                payload["developer"]["generatedBy"] = generated_by
        if card.follow_up_source_day is not None:
            payload["followUpSource"] = {
                "day": card.follow_up_source_day,
                "definitionId": card.follow_up_source_definition_id,
                "title": card.follow_up_source_title,
                "choiceId": card.follow_up_source_choice_id,
                "choice": card.follow_up_source_choice_label,
                "jobId": card.primary_job_id,
            }
        return payload

    def _choice_preference_payload(self, card: DecisionCard) -> dict[str, Any]:
        if card.player_only:
            choice_id = card.echo_choice_id
            kind = "player-only-recommendation"
            label = "Best player-only choice"
            basis = (
                "Highest raw schedule score among this player-only card's choices; "
                "ECHO does not take or prefer a final-assembly choice."
            )
        elif self.player_in_overtime:
            choice_id = select_echo_choice_for_state(
                self.player_state,
                card.choices,
            ).id
            kind = "echo-local"
            label = "ECHO locally preferred"
            basis = (
                "Best locally evaluated choice for the current runtime state: "
                "earliest immediate projected completion, then highest resulting raw score."
            )
        else:
            choice_id = self.decision_web.node(
                self.player_node_id
            ).optimal_choice_id
            kind = "echo-solved"
            label = "ECHO preferred"
            basis = (
                "Exact backward-solved choice for this preplanned node: completion day, "
                "then route score, then cumulative unfinished work."
            )
        choice_label = next(
            (
                choice.label
                for choice in card.choices
                if choice.id == choice_id
            ),
            "",
        )
        return {
            "choiceId": choice_id,
            "choiceLabel": choice_label,
            "kind": kind,
            "label": label,
            "basis": basis,
        }

    def _choice_diagnostics_payload(
        self,
        card: DecisionCard,
        choice: DecisionChoice,
        preference: dict[str, Any],
    ) -> dict[str, Any]:
        raw_before = self.player_state.decision_score
        raw_after = round(raw_before + choice.score_delta, 2)
        return {
            "rawScoreDelta": choice.score_delta,
            "publicScore": {
                "before": public_score(raw_before),
                "delta": public_score_delta(raw_before, raw_after),
                "after": public_score(raw_after),
            },
            "jobDayChanges": [
                self._job_day_change_payload(job_id, delta)
                for job_id, delta in sorted(choice.day_changes.items())
            ],
            "isPreferred": choice.id == preference.get("choiceId"),
            "completionProjection": self._choice_completion_projection(
                card,
                choice,
            ),
            "followUp": self._choice_follow_up_payload(card, choice),
        }

    def _generated_by_payload(
        self,
        card: DecisionCard,
    ) -> dict[str, Any] | None:
        if card.follow_up_source_day is None:
            return None
        job = self.player_state.jobs.get(card.primary_job_id)
        return {
            "sourceDay": card.follow_up_source_day,
            "sourceDefinitionId": card.follow_up_source_definition_id,
            "sourceTitle": card.follow_up_source_title,
            "sourceChoiceId": card.follow_up_source_choice_id,
            "sourceChoiceLabel": card.follow_up_source_choice_label,
            "affectedJob": {
                "jobId": card.primary_job_id,
                "jobLabel": _job_label(card.primary_job_id),
                "jobName": job.name if job else card.context_label,
            },
        }

    def _choice_follow_up_payload(
        self,
        card: DecisionCard,
        choice: DecisionChoice,
    ) -> dict[str, Any]:
        if self.player_in_overtime or card.player_only:
            return inspect_runtime_follow_up(
                self.player_state,
                card,
                choice,
            )

        cache_key = (self.player_node_id, choice.id)
        cached = self._developer_follow_up_cache.get(cache_key)
        if cached is None:
            cached = inspect_preplanned_follow_up(
                self.decision_web,
                self.player_node_id,
                choice,
                self.scenario.jobs,
                self.config.date_label_for_day,
            )
            self._developer_follow_up_cache[cache_key] = cached
        return cached

    def _job_day_change_payload(
        self,
        job_id: str,
        delta: int,
    ) -> dict[str, Any]:
        job = self.player_state.jobs.get(job_id)
        applies = bool(job and not job.is_complete)
        remaining_before = max(0, job.remaining_days) if job else None
        remaining_after = (
            max(0, (job.remaining_days if job else 0) + delta)
            if applies
            else remaining_before
        )
        return {
            "jobId": job_id,
            "jobLabel": _job_label(job_id),
            "jobName": job.name if job else job_id,
            "days": delta,
            "applies": applies,
            "remainingBefore": remaining_before,
            "remainingAfter": remaining_after,
        }

    def _choice_completion_projection(
        self,
        card: DecisionCard,
        choice: DecisionChoice,
    ) -> dict[str, Any]:
        if not self.player_in_overtime and not card.player_only:
            transition = self.decision_web.transition(
                self.player_node_id,
                choice.id,
            )
            exact = not transition.enters_overtime
            if transition.completion_day is not None:
                day = transition.completion_day
            elif transition.enters_overtime:
                day = self.config.max_campaign_day
            else:
                successor = self.decision_web.node(
                    transition.next_node_id or ""
                )
                day = successor.optimal_completion_day
            return {
                "day": day,
                "date": self.config.date_label_for_day(day),
                "exact": exact,
                "label": (
                    self.config.date_label_for_day(day)
                    if exact
                    else f"Day {day}+ (enters overtime)"
                ),
                "basis": "solved-optimal-continuation",
            }

        day = projected_completion_day_after_choice(
            self.player_state,
            choice,
        )
        return {
            "day": day,
            "date": self.config.date_label_for_day(day),
            "exact": False,
            "label": self.config.date_label_for_day(day),
            "basis": (
                "player-only-immediate-projection"
                if card.player_only
                else "runtime-local-immediate-projection"
            ),
        }


def _choice_payload(
    choice: DecisionChoice,
    *,
    developer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": choice.id,
        "label": choice.label,
        "icon": choice.icon_key,
    }
    if developer is not None:
        payload["developer"] = developer
    return payload


def _chart_decision_payload(
    record: Any,
    card: DecisionCard | None,
    *,
    position: int,
    include_echo_preference: bool,
    echo_comparison_state: str,
) -> dict[str, Any]:
    """Keep one actor's question context attached to that actor's answer."""
    payload = {
        "position": position,
        "questionId": record.card_id,
        "questionTitle": record.card_title,
        "questionText": card.description if card else record.card_title,
        "choice": record.choice_label,
        "scoreDelta": public_score_delta(
            record.cumulative_score - record.score_delta,
            record.cumulative_score,
        ),
        "cumulativeScore": public_score(record.cumulative_score),
        "affectedLabel": card.context_label if card else "-",
        "eventId": (card.event_id or card.id) if card else record.card_id,
        "eventScope": card.event_scope if card else "route-specific",
    }
    if card and card.follow_up_source_day is not None:
        payload["followUpSource"] = {
            "day": card.follow_up_source_day,
            "definitionId": card.follow_up_source_definition_id,
            "title": card.follow_up_source_title,
            "choiceId": card.follow_up_source_choice_id,
            "choice": card.follow_up_source_choice_label,
            "jobId": card.primary_job_id,
        }
    if include_echo_preference:
        preferred_choice = (
            next(
                (
                    choice.label
                    for choice in card.choices
                    if choice.id == card.echo_choice_id
                ),
                record.echo_choice_label,
            )
            if card
            else record.echo_choice_label
        )
        aligned_with_preference = record.choice_label == preferred_choice
        choice_state = "same-choice" if aligned_with_preference else "different-choice"
        payload.update(
            {
                "echoPreferredChoice": preferred_choice,
                "alignedWithEcho": aligned_with_preference,
                "echoSituationMatches": echo_comparison_state == "same-context",
                "echoEventMatches": echo_comparison_state != "different-events",
                "echoComparisonState": echo_comparison_state,
                "echoPreferenceState": f"{echo_comparison_state}-{choice_state}",
                "echoPreferenceBasis": "completion-day-then-score-then-unfinished-work",
            }
        )
    return payload


def _echo_comparison_state(
    player_card: DecisionCard | None,
    echo_card: DecisionCard | None,
) -> str:
    if not player_card or not echo_card:
        return "different-events"
    player_event_id = player_card.event_id or player_card.id
    echo_event_id = echo_card.event_id or echo_card.id
    if player_event_id != echo_event_id:
        return "different-events"
    if player_card.primary_job_id == echo_card.primary_job_id:
        return "same-context"
    return "same-event-different-context"


def _job_label(job_id: str) -> str:
    suffix = job_id.rsplit("-", 1)[-1]
    return f"Job {int(suffix)}"
