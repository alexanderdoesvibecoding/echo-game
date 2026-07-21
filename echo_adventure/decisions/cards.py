"""Construct state-specific cards from the 75-decision catalog."""

from __future__ import annotations

import hashlib
import random

from ..config import GameConfig
from ..models import (
    DecisionCard,
    DecisionChoice,
    DecisionFollowUp,
    Job,
    PendingFollowUp,
    SimulationState,
)
from .definitions import (
    BASE_DEFINITIONS,
    DEFINITIONS_BY_ID,
    CatalogChoice,
    DecisionDefinition,
)


_NEUTRAL_THRESHOLD = 0.15


def generate_daily_decision_cards(
    state: SimulationState,
    config: GameConfig,
) -> list[DecisionCard]:
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
        card = _build_card(
            state,
            incomplete,
            rng,
            ordinal,
            definition,
            primary,
            pending,
            prevent_delays=_should_prevent_delays(primary, incomplete),
        )
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
    prevent_delays: bool = False,
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
            prevent_delays=prevent_delays,
        )
        for index, catalog_choice in enumerate(definition.choices, start=1)
    ]
    echo_choice = select_echo_choice_from_choices(choices)
    context = _format_job_list([job.name for job in targets])
    tie_text = "This follow-up remains tied to" if pending else "Today's affected job is"
    description = f"{_simplify_language(definition.description)} {tie_text} {primary.name}."
    return DecisionCard(
        id=f"DEC-D{state.current_day:03d}-{ordinal:02d}-{definition.id}",
        title=_simplify_language(definition.title),
        description=description,
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
    if _should_prevent_delays(primary, ordered_targets):
        deltas = [min(0, delta) for delta in deltas]
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
    context = _format_job_list([job.name for job in targets])
    is_follow_up = definition.is_follow_up
    tie_text = "This follow-up remains tied to" if is_follow_up else "Today's affected job is"
    description = f"{_simplify_language(definition.description)} {tie_text} {primary.name}."
    return DecisionCard(
        id=f"DEC-D{state.current_day:03d}-Q{question_number:02d}-{node_token}-{definition.id}",
        title=_simplify_language(definition.title),
        description=description,
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
    return DecisionChoice(
        id=f"choice-{index}",
        label=_simplify_language(catalog_choice.label),
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
    prevent_delays: bool = False,
) -> DecisionChoice:
    changes = _day_changes(catalog_choice.score_delta, targets)
    changes = _avoid_exact_cancellation(changes, trigger_delta, targets[0].id if targets else "")
    if prevent_delays:
        changes = _remove_delays(changes)
    follow_ups = _choice_follow_ups(definition, catalog_choice)
    return DecisionChoice(
        id=f"choice-{index}",
        label=_simplify_language(catalog_choice.label),
        day_changes=changes,
        score_delta=float(-sum(changes.values())),
        icon_key=catalog_choice.icon_key,
        follow_ups=follow_ups,
    )


def _remove_delays(changes: dict[str, int]) -> dict[str, int]:
    """Keep a final job or schedule outlier from being extended further."""
    return {job_id: delta for job_id, delta in changes.items() if delta < 0}


def _should_prevent_delays(primary: Job, incomplete: list[Job]) -> bool:
    """Stop choices from worsening a final job or a unique schedule outlier."""
    if len(incomplete) == 1:
        return True
    ordered = sorted((job.remaining_days for job in incomplete), reverse=True)
    return primary.remaining_days == ordered[0] and ordered[0] > ordered[1] + 2


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
    scores = [choice.score_delta for choice in definition.choices]
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


def _simplify_language(value: str) -> str:
    """Remove obsolete subjob terminology while retaining manufacturing flavor."""
    return value.replace("subjobs", "jobs").replace("Subjobs", "Jobs").replace("subjob", "job").replace("Subjob", "Job")


def select_echo_choice_from_choices(choices: list[DecisionChoice]) -> DecisionChoice:
    return max(choices, key=lambda choice: (choice.score_delta, choice.id))


def select_echo_choice_for_state(
    state: SimulationState,
    choices: list[DecisionChoice],
) -> DecisionChoice:
    """Prefer the earliest resulting finish, then the highest overall score.

    The preplanned campaign replaces this provisional choice with the exact
    backward-solved route optimum. Runtime overtime cards have no successor
    web, so their end-date comparison uses the remaining schedule after each
    response and compares the resulting cumulative score second.
    """

    def outcome(choice: DecisionChoice) -> tuple[int, float, str]:
        remaining = {
            job.id: max(0, job.remaining_days)
            for job in state.incomplete_jobs()
        }
        for job_id, delta in choice.day_changes.items():
            if job_id in remaining:
                remaining[job_id] = max(0, remaining[job_id] + delta)
        longest = max(remaining.values(), default=0)
        completion_day = state.current_day + max(0, longest - 1)
        overall_score = round(state.decision_score + choice.score_delta, 2)
        return (-completion_day, overall_score, choice.id)

    return max(choices, key=outcome)


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
