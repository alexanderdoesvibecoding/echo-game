"""Deterministic question bank for adding or removing job days."""

from __future__ import annotations

import hashlib
import random

from ..config import GameConfig
from ..enums import DecisionType
from ..models import DecisionCard, DecisionChoice, DecisionProgress, Job, SimulationState


DELAY_QUESTIONS = (
    ("Machine interruption", "A machine issue has interrupted {context}.", "machine"),
    ("Material delivery problem", "A material delivery problem affects {context}.", "material"),
    ("Staffing gap", "A short staffing gap affects {context}.", "crew"),
    ("Weather disruption", "Severe weather slows {context}.", "weather"),
    ("Quality concern", "A quality concern must be addressed on {context}.", "quality"),
    ("Planning data correction", "Updated planning data changes the work expected for {context}.", "planning"),
)

OPPORTUNITY_QUESTIONS = (
    ("Focused acceleration", "A short-lived opportunity could accelerate {context}.", "priority"),
    ("Process improvement", "A proven process improvement is available for {context}.", "process"),
    ("Early material arrival", "An early delivery can shorten work on {context}.", "material"),
    ("Team breakthrough", "The team found a safe shortcut for {context}.", "crew"),
    ("Shared learning", "Lessons from completed work can shorten {context}.", "planning"),
)


def generate_daily_decision_cards(state: SimulationState, config: GameConfig) -> list[DecisionCard]:
    """Create the configured two-to-four questions for the current day."""
    incomplete = sorted(state.incomplete_jobs(), key=lambda job: (-job.remaining_days, job.id))
    if not incomplete:
        return []
    rng = random.Random(_stable_seed(state.seed, state.current_day, "daily-questions"))
    count = rng.randint(config.min_decisions_per_day, config.max_decisions_per_day)
    cards: list[DecisionCard] = []

    # At least one acceleration question appears each day. When only a few
    # jobs remain, every question accelerates work so an unbounded run still
    # converges instead of repeatedly adding time to the final job.
    opportunity_count = count if len(incomplete) <= 2 else max(1, count // 2)
    kinds = [DecisionType.OPPORTUNITY] * opportunity_count + [DecisionType.DELAY] * (count - opportunity_count)
    rng.shuffle(kinds)

    for ordinal, decision_type in enumerate(kinds, start=1):
        card = _build_card(state, incomplete, rng, ordinal, decision_type)
        cards.append(card)
        state.decision_cards[card.id] = card
    return cards


def _build_card(
    state: SimulationState,
    incomplete: list[Job],
    rng: random.Random,
    ordinal: int,
    decision_type: DecisionType,
) -> DecisionCard:
    bank = OPPORTUNITY_QUESTIONS if decision_type == DecisionType.OPPORTUNITY else DELAY_QUESTIONS
    title, description, _flavor = rng.choice(bank)
    shuffled = list(incomplete)
    rng.shuffle(shuffled)
    primary = shuffled[0]
    group = shuffled[: min(3, len(shuffled))]
    broad = shuffled[: min(5, len(shuffled))]
    sign = -1 if decision_type == DecisionType.OPPORTUNITY else 1

    if sign < 0:
        specs = (
            ("Focus on one job", f"Remove 2 days from {primary.name}.", {primary.id: -2}),
            ("Help a small set", f"Remove 1 day from each of {len(group)} jobs.", {job.id: -1 for job in group}),
            ("Use the full opening", f"Remove 1 day from each of {len(broad)} jobs.", {job.id: -1 for job in broad}),
        )
    else:
        specs = (
            ("Contain the impact", f"Add 1 day to {primary.name}.", {primary.id: 1}),
            ("Spread the disruption", f"Add 1 day to each of {len(group)} jobs.", {job.id: 1 for job in group}),
            ("Take the longer correction", f"Add 2 days to {primary.name}.", {primary.id: 2}),
        )

    choices: list[DecisionChoice] = []
    for choice_index, (label, choice_description, changes) in enumerate(specs, start=1):
        score = -sum(changes.values())
        choices.append(
            DecisionChoice(
                id=f"choice-{choice_index}",
                label=label,
                description=choice_description,
                day_changes=changes,
                score_delta=float(score),
            )
        )
    echo_choice = select_echo_choice_from_choices(choices)
    target_ids = list(dict.fromkeys(job_id for choice in choices for job_id in choice.day_changes))
    context = ", ".join(job.name.split(" - ", 1)[0] for job in broad)
    return DecisionCard(
        id=f"DEC-D{state.current_day:03d}-{ordinal:02d}",
        day=state.current_day,
        type=decision_type,
        title=title,
        description=description.format(context=context),
        target_ids=target_ids,
        choices=choices,
        echo_choice_id=echo_choice.id,
        context_label=context,
    )


def select_echo_choice(card: DecisionCard) -> DecisionChoice:
    return select_echo_choice_from_choices(card.choices)


def select_echo_choice_from_choices(choices: list[DecisionChoice]) -> DecisionChoice:
    return max(choices, key=lambda choice: (choice.score_delta, choice.id))


def decision_progress(
    cards: list[DecisionCard],
    selected_choices: dict[str, str],
    day: int,
) -> DecisionProgress:
    open_ids = [card.id for card in cards if card.id not in selected_choices]
    return DecisionProgress(
        day=day,
        total_questions=len(cards),
        answered_questions=len(cards) - len(open_ids),
        open_card_ids=open_ids,
    )


def _stable_seed(seed: int, day: int, suffix: str) -> int:
    material = f"{seed}|{day}|{suffix}".encode("utf-8")
    return int(hashlib.sha256(material).hexdigest(), 16)
