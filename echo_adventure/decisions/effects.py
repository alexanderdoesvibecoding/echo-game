"""Apply the only decision mechanic: changing remaining job days."""

from __future__ import annotations

import hashlib

from ..models import DecisionCard, DecisionChoice, DecisionRecord, PendingFollowUp, SimulationState
from ..simulation import complete_job


def apply_choice(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    actor: str,
    schedule_follow_ups: bool = True,
) -> None:
    applied_day_changes: dict[str, int] = {}
    for job_id, delta in choice.day_changes.items():
        job = state.jobs.get(job_id)
        if not job or job.is_complete:
            continue
        applied_day_changes[job_id] = delta
        job.remaining_days += delta
        if job.remaining_days <= 0:
            complete_job(state, job.id)
    if schedule_follow_ups:
        _schedule_follow_ups(state, card, choice)
    echo_choice = (
        None
        if card.player_only
        else next(item for item in card.choices if item.id == card.echo_choice_id)
    )
    state.decision_score = round(state.decision_score + choice.score_delta, 2)
    state.decision_history.append(
        DecisionRecord(
            day=state.current_day,
            card_id=card.id,
            card_title=card.title,
            actor=actor,
            choice_label=choice.label,
            echo_choice_label=echo_choice.label if echo_choice else None,
            aligned_with_echo=(choice.id == echo_choice.id) if echo_choice else None,
            applied_day_changes=applied_day_changes,
            score_delta=choice.score_delta,
            cumulative_score=state.decision_score,
        )
    )


def _schedule_follow_ups(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
) -> None:
    """Queue selected-choice follow-ups against the originating active job."""
    job = state.jobs.get(card.primary_job_id)
    if not job or job.is_complete:
        return
    pending_ids = {item.definition_id for item in state.pending_follow_ups}
    for follow_up in choice.follow_ups:
        if (
            follow_up.definition_id in state.shown_follow_up_decision_ids
            or follow_up.definition_id in pending_ids
            or not _follow_up_occurs(state, card, choice, follow_up.definition_id, follow_up.probability)
        ):
            continue
        state.pending_follow_ups.append(
            PendingFollowUp(
                definition_id=follow_up.definition_id,
                job_id=job.id,
                available_day=state.current_day + follow_up.delay_days,
                trigger_delta=sum(choice.day_changes.values()),
                source_day=state.current_day,
                source_definition_id=card.definition_id,
                source_choice_id=choice.id,
            )
        )
        pending_ids.add(follow_up.definition_id)


def _follow_up_occurs(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    definition_id: str,
    probability: float,
) -> bool:
    material = "|".join(
        (
            str(state.seed),
            str(state.current_day),
            card.definition_id,
            card.primary_job_id,
            choice.id,
            definition_id,
        )
    ).encode("utf-8")
    roll = int(hashlib.sha256(material).hexdigest(), 16) / float(1 << 256)
    return roll < max(0.0, min(1.0, probability))
