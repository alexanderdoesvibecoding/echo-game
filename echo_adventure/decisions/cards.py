"""Construct state-specific cards from the restored 75-decision catalog."""

from __future__ import annotations

import hashlib
import random

from ..config import GameConfig
from ..enums import DecisionType
from ..models import (
    DecisionCard,
    DecisionChoice,
    DecisionFollowUp,
    DecisionProgress,
    Job,
    PendingFollowUp,
    SimulationState,
)
from .definitions import (
    BASE_DEFINITIONS,
    DEFINITIONS_BY_ID,
    CatalogChoice,
    DecisionDefinition,
    choice_schedule_score,
    definition_schedule_score,
)


_NEUTRAL_THRESHOLD = 0.15


def generate_daily_decision_cards(state: SimulationState, config: GameConfig) -> list[DecisionCard]:
    """Create two-to-four varied questions, including eligible follow-ups."""
    incomplete = sorted(state.incomplete_jobs(), key=lambda job: (-job.remaining_days, job.id))
    if not incomplete:
        return []

    rng = random.Random(_stable_seed(state.seed, state.current_day, "daily-questions"))
    count = rng.randint(config.min_decisions_per_day, config.max_decisions_per_day)
    selected: list[tuple[DecisionDefinition, Job, PendingFollowUp | None]] = []

    due = _eligible_follow_ups(state)
    rng.shuffle(due)
    for pending in due[:count]:
        definition = DEFINITIONS_BY_ID.get(pending.definition_id)
        job = state.jobs.get(pending.job_id)
        if not definition or not definition.is_follow_up or not job or job.is_complete:
            continue
        selected.append((definition, job, pending))

    selected_pending = {pending for _, _, pending in selected if pending is not None}
    state.pending_follow_ups = [item for item in state.pending_follow_ups if item not in selected_pending]

    used_today = {definition.id for definition, _, _ in selected}
    assigned_jobs = {job.id for _, job, _ in selected}
    while len(selected) < count:
        pool = _available_base_definitions(state, used_today)
        if not pool:
            break
        definition = rng.choice(pool)
        job_pool = [job for job in incomplete if job.id not in assigned_jobs] or incomplete
        primary = rng.choice(job_pool)
        selected.append((definition, primary, None))
        used_today.add(definition.id)
        assigned_jobs.add(primary.id)

    cards: list[DecisionCard] = []
    for ordinal, (definition, primary, pending) in enumerate(selected, start=1):
        card = _build_card(state, incomplete, rng, ordinal, definition, primary, pending)
        cards.append(card)
        state.decision_cards[card.id] = card
        if definition.is_follow_up:
            state.shown_follow_up_decision_ids.add(definition.id)
    return cards


def _eligible_follow_ups(state: SimulationState) -> list[PendingFollowUp]:
    """Drop stale follow-ups and return those ready for today's still-active jobs."""
    retained: list[PendingFollowUp] = []
    eligible: list[PendingFollowUp] = []
    for pending in state.pending_follow_ups:
        job = state.jobs.get(pending.job_id)
        definition = DEFINITIONS_BY_ID.get(pending.definition_id)
        if (
            not job
            or job.is_complete
            or not definition
            or not definition.is_follow_up
            or pending.definition_id in state.shown_follow_up_decision_ids
        ):
            continue
        retained.append(pending)
        if pending.available_day <= state.current_day:
            eligible.append(pending)
    state.pending_follow_ups = retained
    return eligible


def _available_base_definitions(
    state: SimulationState,
    used_today: set[str],
) -> list[DecisionDefinition]:
    """Return the least-used definitions from the complete base catalog."""
    pool = [
        definition
        for definition in BASE_DEFINITIONS
        if definition.id not in used_today
    ]
    if not pool:
        return []

    appearances = {definition.id: 0 for definition in BASE_DEFINITIONS}
    for card in state.decision_cards.values():
        if card.definition_id in appearances:
            appearances[card.definition_id] += 1

    least_uses = min(appearances[definition.id] for definition in pool)
    return [definition for definition in pool if appearances[definition.id] == least_uses]


def _build_card(
    state: SimulationState,
    incomplete: list[Job],
    rng: random.Random,
    ordinal: int,
    definition: DecisionDefinition,
    primary: Job,
    pending: PendingFollowUp | None,
) -> DecisionCard:
    others = [job for job in incomplete if job.id != primary.id]
    rng.shuffle(others)
    targets = [primary, *others[:4]]
    choices = [
        _build_choice(
            definition,
            catalog_choice,
            targets,
            index,
            trigger_delta=pending.trigger_delta if pending else 0,
        )
        for index, catalog_choice in enumerate(definition.choices, start=1)
    ]
    echo_choice = select_echo_choice_from_choices(choices)
    target_ids = list(dict.fromkeys([primary.id, *(job_id for choice in choices for job_id in choice.day_changes)]))
    context = _format_job_list([job.name for job in targets])
    tie_text = "This follow-up remains tied to" if pending else "Today's affected job is"
    description = f"{_simplify_language(definition.description)} {tie_text} {primary.name}."
    return DecisionCard(
        id=f"DEC-D{state.current_day:03d}-{ordinal:02d}-{definition.id}",
        day=state.current_day,
        type=_decision_type(definition),
        title=_simplify_language(definition.title),
        description=description,
        target_ids=target_ids,
        choices=choices,
        echo_choice_id=echo_choice.id,
        context_label=context,
        definition_id=definition.id,
        primary_job_id=primary.id,
    )


def build_preplanned_decision_card(
    state: SimulationState,
    definition: DecisionDefinition,
    primary: Job,
    ordered_targets: list[Job],
    question_number: int,
    node_token: str,
    trigger_delta: int = 0,
) -> DecisionCard:
    """Build one immutable-web question for an exact precomputed state."""
    targets = [primary, *(job for job in ordered_targets if job.id != primary.id)][:5]
    deltas = _preplanned_deltas(definition, targets, trigger_delta)
    choices = [
        _build_preplanned_choice(
            definition,
            catalog_choice,
            targets,
            primary,
            index,
            deltas[index - 1],
        )
        for index, catalog_choice in enumerate(definition.choices, start=1)
    ]
    echo_choice = select_echo_choice_from_choices(choices)
    target_ids = list(
        dict.fromkeys([primary.id, *(job_id for choice in choices for job_id in choice.day_changes)])
    )
    context = _format_job_list([job.name for job in targets])
    is_follow_up = definition.is_follow_up
    tie_text = "This follow-up remains tied to" if is_follow_up else "Today's affected job is"
    description = f"{_simplify_language(definition.description)} {tie_text} {primary.name}."
    return DecisionCard(
        id=f"DEC-D{state.current_day:03d}-Q{question_number:02d}-{node_token}-{definition.id}",
        day=state.current_day,
        type=_decision_type(definition),
        title=_simplify_language(definition.title),
        description=description,
        target_ids=target_ids,
        choices=choices,
        echo_choice_id=echo_choice.id,
        context_label=context,
        definition_id=definition.id,
        primary_job_id=primary.id,
    )


def _build_preplanned_choice(
    definition: DecisionDefinition,
    catalog_choice: CatalogChoice,
    targets: list[Job],
    primary: Job,
    index: int,
    day_delta: int,
) -> DecisionChoice:
    """Keep web branching exact and tractable by changing one known job."""
    changes = {primary.id: day_delta} if day_delta else {}
    schedule_text = _format_change_summary(changes, targets)
    return DecisionChoice(
        id=f"choice-{index}",
        label=_simplify_language(catalog_choice.label),
        description=f"{_simplify_language(catalog_choice.description)} {schedule_text}",
        day_changes=changes,
        score_delta=float(-sum(changes.values())),
        icon_key=catalog_choice.icon_key,
        follow_ups=_choice_follow_ups(definition, catalog_choice),
    )


def _build_choice(
    definition: DecisionDefinition,
    catalog_choice: CatalogChoice,
    targets: list[Job],
    index: int,
    trigger_delta: int = 0,
) -> DecisionChoice:
    schedule_score = choice_schedule_score(definition, catalog_choice)
    changes = _day_changes(schedule_score, targets)
    changes = _avoid_exact_cancellation(changes, trigger_delta, targets[0].id if targets else "")
    schedule_text = _format_change_summary(changes, targets)
    follow_ups = _choice_follow_ups(definition, catalog_choice)
    return DecisionChoice(
        id=f"choice-{index}",
        label=_simplify_language(catalog_choice.label),
        description=f"{_simplify_language(catalog_choice.description)} {schedule_text}",
        day_changes=changes,
        score_delta=float(-sum(changes.values())),
        icon_key=catalog_choice.icon_key,
        follow_ups=follow_ups,
    )


def _preplanned_deltas(
    definition: DecisionDefinition,
    targets: list[Job],
    trigger_delta: int,
) -> list[int]:
    """Return ranked one-job deltas without erasing follow-up differences.

    Base questions retain the catalog's weak/strong distinction but are capped
    at two days to keep the precomputed web compact. Follow-ups use up to four
    small tiers. When their direction opposes the triggering answer, its exact
    magnitude is reserved so no answer can merely refund the earlier change.
    """
    scores = [choice_schedule_score(definition, choice) for choice in definition.choices]
    if not definition.is_follow_up:
        deltas: list[int] = []
        for score in scores:
            net_change = sum(_day_changes(score, targets).values())
            if not net_change:
                deltas.append(0)
                continue
            magnitude = min(2, abs(net_change))
            deltas.append(magnitude if net_change > 0 else -magnitude)
        return deltas

    deltas = [0] * len(scores)
    for direction in (-1, 1):
        indexes = [
            index
            for index, score in enumerate(scores)
            if abs(score) >= _NEUTRAL_THRESHOLD
            and (-1 if score > 0 else 1) == direction
        ]
        strengths = sorted({abs(scores[index]) for index in indexes})
        magnitudes = [1, 2, 3, 4]
        if (
            trigger_delta
            and direction == (-1 if trigger_delta > 0 else 1)
            and abs(trigger_delta) in magnitudes
        ):
            magnitudes.remove(abs(trigger_delta))
        rank_to_magnitude = {
            strength: magnitudes[rank]
            for rank, strength in enumerate(strengths)
        }
        for index in indexes:
            deltas[index] = direction * rank_to_magnitude[abs(scores[index])]
    return deltas


def _avoid_exact_cancellation(
    changes: dict[str, int],
    trigger_delta: int,
    primary_job_id: str,
) -> dict[str, int]:
    """Strengthen an inverse follow-up by one day instead of netting to zero."""
    follow_up_delta = sum(changes.values())
    if not trigger_delta or not follow_up_delta or trigger_delta + follow_up_delta:
        return changes
    direction = 1 if follow_up_delta > 0 else -1
    adjusted = dict(changes)
    adjusted[primary_job_id] = adjusted.get(primary_job_id, 0) + direction
    return adjusted


def _day_changes(schedule_score: float, targets: list[Job]) -> dict[str, int]:
    """Convert a catalog score into a bounded one-to-three-job day effect."""
    if abs(schedule_score) < _NEUTRAL_THRESHOLD or not targets:
        return {}
    direction = -1 if schedule_score > 0 else 1
    strength = abs(schedule_score)
    breadth = 1 if strength < 0.75 else 2 if strength < 1.5 else 3
    breadth = min(breadth, len(targets))
    magnitude = 2 if breadth == 1 and strength >= 1.75 else 1
    return {job.id: direction * magnitude for job in targets[:breadth]}


def _choice_follow_ups(
    definition: DecisionDefinition,
    catalog_choice: CatalogChoice,
) -> tuple[DecisionFollowUp, ...]:
    edges = (*catalog_choice.follow_up_edges, *definition.unavoidable_follow_up_edges)
    unique: dict[str, DecisionFollowUp] = {}
    for edge in edges:
        unique[edge.target_definition_id] = DecisionFollowUp(
            definition_id=edge.target_definition_id,
            probability=edge.probability,
            delay_days=max(1, edge.delay_days),
        )
    return tuple(unique.values())


def _decision_type(definition: DecisionDefinition) -> DecisionType:
    score = definition_schedule_score(definition)
    if score > _NEUTRAL_THRESHOLD:
        return DecisionType.OPPORTUNITY
    if score < -_NEUTRAL_THRESHOLD:
        return DecisionType.DELAY
    return DecisionType.NEUTRAL


def _format_change_summary(changes: dict[str, int], targets: list[Job]) -> str:
    if not changes:
        return "Schedule effect: no days added or removed."
    names = {job.id: job.name for job in targets}
    delta = next(iter(changes.values()))
    verb = "Remove" if delta < 0 else "Add"
    amount = abs(delta)
    job_names = _format_job_list([names[job_id] for job_id in changes])
    each = " each" if len(changes) > 1 else ""
    return f"Schedule effect: {verb} {amount} day{'s' if amount != 1 else ''}{each} {'from' if delta < 0 else 'to'} {job_names}."


def _simplify_language(value: str) -> str:
    """Remove obsolete subjob terminology while retaining manufacturing flavor."""
    return value.replace("subjobs", "jobs").replace("Subjobs", "Jobs").replace("subjob", "job").replace("Subjob", "Job")


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


def _format_job_list(job_names: list[str]) -> str:
    if not job_names:
        return ""
    if len(job_names) == 1:
        return job_names[0]
    if len(job_names) == 2:
        return f"{job_names[0]} and {job_names[1]}"
    return f"{', '.join(job_names[:-1])}, and {job_names[-1]}"
