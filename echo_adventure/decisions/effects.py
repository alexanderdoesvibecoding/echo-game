"""Apply the only decision mechanic: changing remaining job days."""

from __future__ import annotations

import hashlib

from ..models import DecisionCard, DecisionChoice, DecisionRecord, PendingFollowUp, SimulationState


def apply_choice(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    actor: str,
) -> str:
    changes: list[str] = []
    for job_id, delta in choice.day_changes.items():
        job = state.jobs.get(job_id)
        if not job or job.is_complete:
            continue
        before = job.remaining_days
        # Completion is committed by the once-per-day simulation tick. Keeping
        # acceleration as a signed intra-day balance means every displayed
        # question still applies its full stated change, even when several
        # questions touch a nearly finished job on the same day.
        job.remaining_days = before + delta
        actual = job.remaining_days - before
        if actual:
            verb = "added to" if actual > 0 else "removed from"
            changes.append(f"{abs(actual)} day(s) {verb} {job.name}")
    _schedule_follow_ups(state, card, choice)
    echo_choice = next(item for item in card.choices if item.id == card.echo_choice_id)
    state.decision_score = round(state.decision_score + choice.score_delta, 2)
    note = "; ".join(changes) if changes else "No unfinished job was changed."
    state.decision_history.append(
        DecisionRecord(
            day=state.current_day,
            card_id=card.id,
            card_title=card.title,
            actor=actor,
            choice_id=choice.id,
            choice_label=choice.label,
            echo_choice_id=echo_choice.id,
            echo_choice_label=echo_choice.label,
            aligned_with_echo=choice.id == echo_choice.id,
            note=note,
            score_delta=choice.score_delta,
            cumulative_score=state.decision_score,
        )
    )
    return note


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
