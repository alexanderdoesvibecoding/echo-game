"""Apply the only decision mechanic: changing remaining job days."""

from __future__ import annotations

from ..models import DecisionCard, DecisionChoice, DecisionRecord, SimulationState


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
