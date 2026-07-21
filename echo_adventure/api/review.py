"""Final player-versus-ECHO explanation."""

from __future__ import annotations

from typing import Any

from ..models import DecisionRecord
from ..scoring import public_score


class ReviewMixin:
    def _final_review_payload(self) -> dict[str, Any]:
        player_day = self.player_state.completion_day or self.player_state.current_day
        echo_day = self.automated_state.completion_day or self.automated_state.current_day
        player_records = [
            record for record in self.player_state.decision_history if record.actor == "player"
        ]
        preplanned_records = [
            record for record in player_records if record.day < self.config.max_campaign_day
        ]
        overtime_records = [
            record for record in player_records if record.day >= self.config.max_campaign_day
        ]
        preplanned_aligned = sum(
            1 for record in preplanned_records if record.aligned_with_echo
        )
        aligned = sum(1 for record in player_records if record.aligned_with_echo)
        echo_records = [
            record for record in self.automated_state.decision_history if record.actor == "ECHO"
        ]
        identical_optimal_path = (
            not overtime_records
            and preplanned_aligned == len(preplanned_records) == len(echo_records)
        )
        player_score = round(self.player_state.decision_score, 2)
        echo_score = round(self.automated_state.decision_score, 2)
        player_unfinished_job_days = self.player_state.cumulative_unfinished_job_days
        echo_unfinished_job_days = self.automated_state.cumulative_unfinished_job_days

        if identical_optimal_path:
            headline = "You reproduced ECHO's exact optimal path, so the run is tied."
            outcome = "tied"
        elif player_day > echo_day:
            day_gap = player_day - echo_day
            day_unit = "day" if day_gap == 1 else "days"
            headline = (
                f"ECHO finished all {len(self.player_state.jobs)} jobs "
                f"{day_gap} {day_unit} earlier."
            )
            outcome = "behind"
        elif player_day == echo_day and player_score < echo_score:
            headline = "You matched ECHO's completion day, but ECHO achieved the higher score."
            outcome = "behind"
        elif (
            player_day == echo_day
            and player_score == echo_score
            and player_unfinished_job_days > echo_unfinished_job_days
        ):
            difference = player_unfinished_job_days - echo_unfinished_job_days
            unit = "job-day" if difference == 1 else "job-days"
            headline = (
                "You matched ECHO's completion day and score, but ECHO carried "
                f"{difference} fewer unfinished {unit}."
            )
            outcome = "behind"
        elif (
            player_day == echo_day
            and player_score == echo_score
            and player_unfinished_job_days == echo_unfinished_job_days
        ):
            headline = (
                "You matched ECHO's completion day, score, and unfinished-work total, "
                "but ECHO prevailed after your routes diverged."
            )
            outcome = "behind"
        else:
            raise RuntimeError("A player route surpassed the globally solved ECHO route.")

        reasons = self._outcome_driver_reasons(
            player_records,
            identical_optimal_path=identical_optimal_path,
            player_day=player_day,
            echo_day=echo_day,
            aligned=aligned,
        )
        return {
            "outcome": outcome,
            "headline": headline,
            "reasons": reasons,
        }

    def _outcome_driver_reasons(
        self,
        player_records: list[DecisionRecord],
        *,
        identical_optimal_path: bool,
        player_day: int,
        echo_day: int,
        aligned: int,
    ) -> list[str]:
        """Describe at most two evidence-backed drivers beneath the headline."""
        if identical_optimal_path:
            score = public_score(self.player_state.decision_score)
            return [
                f"You matched ECHO on all {len(player_records)} questions; both routes "
                f"finished on day {player_day} with a {score:.0f}/100 decision score and "
                f"{self.player_state.cumulative_unfinished_job_days} cumulative unfinished job-days."
            ]

        question_number_by_day: dict[int, int] = {}
        drivers: list[tuple[float, float, int, DecisionRecord, int]] = []
        for sequence, record in enumerate(player_records):
            question_number = question_number_by_day.get(record.day, 0) + 1
            question_number_by_day[record.day] = question_number
            if record.aligned_with_echo:
                continue
            card = self.player_state.decision_cards.get(record.card_id)
            if card is None:
                continue
            echo_choice = next(
                (choice for choice in card.choices if choice.id == card.echo_choice_id),
                None,
            )
            if echo_choice is None:
                continue
            job_day_cost = round(echo_choice.score_delta - record.score_delta, 2)
            drivers.append(
                (
                    max(0.0, job_day_cost),
                    abs(job_day_cost),
                    -sequence,
                    record,
                    question_number,
                )
            )

        drivers.sort(reverse=True, key=lambda item: item[:3])
        reasons = [
            self._decision_driver_sentence(record, question_number)
            for _, _, _, record, question_number in drivers[:2]
        ]
        if reasons:
            return reasons

        overtime_records = [
            record for record in player_records if record.day >= self.config.max_campaign_day
        ]
        if overtime_records:
            first_overtime_day = overtime_records[0].day
            return [
                f"Your route required {len(overtime_records)} overtime question(s), beginning on day {first_overtime_day}, after ECHO finished on day {echo_day}."
            ]
        return [
            f"You matched ECHO on {aligned} of {len(player_records)} questions but finished on day {player_day}, after ECHO's day {echo_day} finish."
        ]

    def _decision_driver_sentence(
        self,
        record: DecisionRecord,
        question_number: int,
    ) -> str:
        card = self.player_state.decision_cards[record.card_id]
        echo_choice = next(
            choice for choice in card.choices if choice.id == card.echo_choice_id
        )
        job_day_cost = round(echo_choice.score_delta - record.score_delta, 2)
        if job_day_cost > 0:
            comparison = (
                f"cost {_format_day_count(job_day_cost)} versus ECHO's response"
            )
        elif job_day_cost < 0:
            comparison = (
                f"saved {_format_day_count(abs(job_day_cost))} more immediately than ECHO's response but left its globally optimal route"
            )
        else:
            comparison = (
                "had the same immediate job-day total as ECHO's response but left its globally optimal route"
            )
        effects = _format_applied_changes(
            record.applied_day_changes,
            self.player_state.jobs,
        )
        return (
            f"On day {record.day}, question {question_number}, choosing “{record.choice_label}” "
            f"instead of “{record.echo_choice_label}” {comparison}; it {effects}."
        )


def _format_day_count(value: float) -> str:
    count = int(value) if float(value).is_integer() else value
    unit = "job-day" if count == 1 else "job-days"
    return f"{count:g} {unit}" if isinstance(count, float) else f"{count} {unit}"


def _format_applied_changes(changes: dict[str, int], jobs: dict[str, Any]) -> str:
    effects = []
    for job_id, delta in changes.items():
        job = jobs.get(job_id)
        job_name = job.name if job else job_id
        verb = "added" if delta > 0 else "removed"
        preposition = "to" if delta > 0 else "from"
        count = abs(delta)
        unit = "day" if count == 1 else "days"
        effects.append(f"{verb} {count} {unit} {preposition} {job_name}")
    if not effects:
        return "made no direct job-day change"
    if len(effects) == 1:
        return effects[0]
    if len(effects) == 2:
        return " and ".join(effects)
    return f"{', '.join(effects[:-1])}, and {effects[-1]}"
