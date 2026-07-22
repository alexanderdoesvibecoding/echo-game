"""Construct state-specific cards from the 75-decision catalog."""

from __future__ import annotations

import hashlib
import random
from dataclasses import replace

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
_FINAL_ASSEMBLY_BASE_DEFINITION_IDS = (
    "weather",
    "worker-off-day",
    "calibration-drift",
    "traveler-mismatch",
    "old-setup-sheet",
    "cleanliness-breach",
    "network-folder-offline",
    "gauge-dispute",
    "burr-cleanup",
    "vacuum-leak-chase",
    "label-printer-outage",
    "expired-stickers",
    "vendor-rep-on-site",
    "access-badge-failure",
    "reference-sample-missing",
)
_FINAL_ASSEMBLY_FOLLOW_UP_IDS = frozenset(
    {
        "narrow-drift-found",
        "finish-window-restored",
        "clean-room-cleared",
        "wrong-revision-loaded",
        "fit-check-failed",
        "cure-failure-found",
        "vacuum-trace-failed",
        "sticker-audit-hit",
        "weather-cleared-early",
        "setup-mismatch-found",
        "replacement-handoff-check",
        "returning-worker-shortcut",
    }
)


def generate_daily_decision_cards(
    state: SimulationState,
    config: GameConfig,
) -> list[DecisionCard]:
    """Create two-to-three varied questions, including eligible follow-ups."""
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
    prevent_delays = len(incomplete) == 1
    for ordinal, (definition, primary, pending) in enumerate(selected, start=1):
        card = _build_card(
            state,
            incomplete,
            rng,
            ordinal,
            definition,
            primary,
            pending,
            prevent_delays=prevent_delays,
        )
        cards.append(card)
        state.decision_cards[card.id] = card
        if definition.is_follow_up:
            state.shown_follow_up_decision_ids.add(definition.id)
    return cards


def generate_final_assembly_cards(
    state: SimulationState,
    config: GameConfig,
    *,
    maximum_total_days_removed: int = 0,
) -> list[DecisionCard]:
    """Create one bounded, player-only decision batch for the final normal job."""
    incomplete = state.incomplete_jobs()
    if len(incomplete) != 1:
        raise ValueError("Final assembly requires exactly one unfinished job.")

    final_job = incomplete[0]
    rng = random.Random(_stable_seed(state.seed, state.current_day, "final-assembly"))
    count = rng.randint(config.min_decisions_per_day, config.max_decisions_per_day)
    accelerating_card_count = min(count, max(0, maximum_total_days_removed))
    selected: list[tuple[DecisionDefinition, PendingFollowUp | None]] = []
    used: set[str] = set()

    pending = sorted(
        (
            item
            for item in state.pending_follow_ups
            if item.job_id == final_job.id
            and item.available_day <= state.current_day
            and item.definition_id in _FINAL_ASSEMBLY_FOLLOW_UP_IDS
        ),
        key=lambda item: (item.available_day, item.definition_id),
    )
    for item in pending:
        definition = DEFINITIONS_BY_ID.get(item.definition_id)
        if not definition or not definition.is_follow_up or definition.id in used:
            continue
        selected.append((definition, item))
        used.add(definition.id)
        if len(selected) == count:
            break

    state.pending_follow_ups.clear()
    base_pool = [
        DEFINITIONS_BY_ID[definition_id]
        for definition_id in _FINAL_ASSEMBLY_BASE_DEFINITION_IDS
        if definition_id not in used
    ]
    rng.shuffle(base_pool)
    selected.extend(
        (definition, None)
        for definition in base_pool[: max(0, count - len(selected))]
    )

    cards: list[DecisionCard] = []
    for ordinal, (original_definition, pending_item) in enumerate(selected, start=1):
        trigger_delta = pending_item.trigger_delta if pending_item else 0
        definition = _select_preplanned_follow_up_result(
            state,
            original_definition,
            final_job,
            ordinal,
            trigger_delta,
        )
        best_catalog_score = max(choice.score_delta for choice in definition.choices)
        worst_catalog_score = min(choice.score_delta for choice in definition.choices)
        choices = [
            _build_final_assembly_choice(
                catalog_choice,
                final_job,
                index,
                best_catalog_score,
                worst_catalog_score,
                allow_acceleration=ordinal <= accelerating_card_count,
            )
            for index, catalog_choice in enumerate(definition.choices, start=1)
        ]
        preferred_choice = max(choices, key=lambda choice: (choice.score_delta, choice.id))
        description = (
            f"{_simplify_language(definition.description)} Only {final_job.name} remains "
            "before final assembly, so this response applies to that job's locked production plan."
        )
        card_id = f"FINAL-D{state.current_day:03d}-Q{ordinal:02d}-{definition.id}"
        event_scope, event_id = _event_identity(
            state.current_day,
            ordinal,
            definition,
            final_job,
            source_day=pending_item.source_day if pending_item else None,
            source_definition_id=(
                pending_item.source_definition_id if pending_item else ""
            ),
        )
        card = DecisionCard(
            id=card_id,
            title=f"Final Assembly: {_simplify_language(definition.title)}",
            description=description,
            choices=choices,
            # Player-only cards are never presented to ECHO. Keeping a stable
            # preferred ID satisfies the shared card shape without recording an
            # ECHO comparison.
            echo_choice_id=preferred_choice.id,
            context_label=final_job.name,
            definition_id=definition.id,
            primary_job_id=final_job.id,
            player_only=True,
            event_id=event_id,
            event_scope=event_scope,
            follow_up_source_day=pending_item.source_day if pending_item else None,
            follow_up_source_definition_id=(
                pending_item.source_definition_id if pending_item else ""
            ),
            follow_up_source_title=_source_title(
                pending_item.source_definition_id if pending_item else ""
            ),
            follow_up_source_choice_id=(
                pending_item.source_choice_id if pending_item else ""
            ),
            follow_up_source_choice_label=_source_choice_label(
                pending_item.source_definition_id if pending_item else "",
                pending_item.source_choice_id if pending_item else "",
            ),
        )
        cards.append(card)
        state.decision_cards[card.id] = card
        if original_definition.is_follow_up:
            state.shown_follow_up_decision_ids.add(original_definition.id)
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
    description = _simplify_language(definition.description)
    card_id = f"DEC-D{state.current_day:03d}-{ordinal:02d}-{definition.id}"
    event_scope, event_id = _event_identity(
        state.current_day,
        ordinal,
        definition,
        primary,
        source_day=pending.source_day if pending else None,
        source_definition_id=pending.source_definition_id if pending else "",
    )
    source_title = _source_title(pending.source_definition_id if pending else "")
    return DecisionCard(
        id=card_id,
        title=_simplify_language(definition.title),
        description=description,
        choices=choices,
        echo_choice_id=echo_choice.id,
        context_label=context,
        definition_id=definition.id,
        primary_job_id=primary.id,
        event_id=event_id,
        event_scope=event_scope,
        follow_up_source_day=pending.source_day if pending else None,
        follow_up_source_definition_id=(
            pending.source_definition_id if pending else ""
        ),
        follow_up_source_title=source_title,
        follow_up_source_choice_id=pending.source_choice_id if pending else "",
        follow_up_source_choice_label=_source_choice_label(
            pending.source_definition_id if pending else "",
            pending.source_choice_id if pending else "",
        ),
    )


def build_preplanned_decision_card(
    state: SimulationState,
    definition: DecisionDefinition,
    primary: Job,
    ordered_targets: list[Job],
    question_number: int,
    node_token: str,
    trigger_delta: int = 0,
    follow_up_source_day: int | None = None,
    follow_up_source_definition_id: str = "",
    follow_up_source_choice_id: str = "",
) -> DecisionCard:
    """Build one immutable-web question for an exact precomputed state."""
    targets = [primary, *(job for job in ordered_targets if job.id != primary.id)][:5]
    definition = _select_preplanned_follow_up_result(
        state,
        definition,
        primary,
        question_number,
        trigger_delta,
    )
    deltas = _preplanned_deltas(definition, targets, trigger_delta)
    if len(targets) == 1:
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
    description = _simplify_language(definition.description)
    card_id = f"DEC-D{state.current_day:03d}-Q{question_number:02d}-{node_token}-{definition.id}"
    event_scope, event_id = _event_identity(
        state.current_day,
        question_number,
        definition,
        primary,
        source_day=follow_up_source_day,
        source_definition_id=follow_up_source_definition_id,
    )
    return DecisionCard(
        id=card_id,
        title=_simplify_language(definition.title),
        description=description,
        choices=choices,
        echo_choice_id=echo_choice.id,
        context_label=context,
        definition_id=definition.id,
        primary_job_id=primary.id,
        event_id=event_id,
        event_scope=event_scope,
        follow_up_source_day=follow_up_source_day,
        follow_up_source_definition_id=follow_up_source_definition_id,
        follow_up_source_title=_source_title(follow_up_source_definition_id),
        follow_up_source_choice_id=follow_up_source_choice_id,
        follow_up_source_choice_label=_source_choice_label(
            follow_up_source_definition_id,
            follow_up_source_choice_id,
        ),
    )


def _select_preplanned_follow_up_result(
    state: SimulationState,
    definition: DecisionDefinition,
    primary: Job,
    question_number: int,
    trigger_delta: int,
) -> DecisionDefinition:
    """Resolve one result without adding a chance branch to the startup web."""
    if not definition.alternate_results:
        return definition

    remaining = ",".join(
        f"{job_id}:{state.jobs[job_id].remaining_days}"
        for job_id in sorted(state.jobs)
    )
    material = "|".join(
        (
            str(state.seed),
            str(state.current_day),
            str(question_number),
            definition.id,
            primary.id,
            str(trigger_delta),
            remaining,
        )
    ).encode("utf-8")
    result_index = int(hashlib.sha256(material).hexdigest(), 16) % (
        len(definition.alternate_results) + 1
    )
    if result_index == 0:
        return definition

    result = definition.alternate_results[result_index - 1]
    return replace(
        definition,
        title=result.title,
        description=result.description,
        choices=result.choices,
        alternate_results=(),
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


def _build_final_assembly_choice(
    catalog_choice: CatalogChoice,
    final_job: Job,
    index: int,
    best_catalog_score: float,
    worst_catalog_score: float,
    *,
    allow_acceleration: bool,
) -> DecisionChoice:
    """Apply a hidden, bounded final adjustment without allowing an ECHO tie."""
    scores_differ = best_catalog_score != worst_catalog_score
    if not scores_differ:
        delta = 0
    elif allow_acceleration and catalog_choice.score_delta == best_catalog_score:
        delta = -1
    elif catalog_choice.score_delta == worst_catalog_score:
        delta = 1
    else:
        delta = 0
    changes = {final_job.id: delta} if delta else {}
    return DecisionChoice(
        id=f"choice-{index}",
        label=_simplify_language(catalog_choice.label),
        day_changes=changes,
        score_delta=float(-delta),
        icon_key=catalog_choice.icon_key,
        follow_ups=(),
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
    """Keep the last unfinished job from being extended forever."""
    return {job_id: delta for job_id, delta in changes.items() if delta < 0}


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


def _event_identity(
    day: int,
    question_number: int,
    definition: DecisionDefinition,
    primary: Job,
    *,
    source_day: int | None = None,
    source_definition_id: str = "",
) -> tuple[str, str]:
    """Return a semantic event identity independent of a DAG node ID."""
    if definition.is_follow_up:
        source = source_definition_id or "unknown-source"
        source_day_key = source_day if source_day is not None else day
        return (
            "follow-up",
            f"FOLLOW-D{source_day_key:03d}-{source}-{primary.id}-{definition.id}",
        )
    if definition.shared_across_routes:
        return (
            "shared-day",
            f"SHARED-D{day:03d}-Q{question_number:02d}-{definition.id}",
        )
    return (
        "route-specific",
        f"ROUTE-D{day:03d}-Q{question_number:02d}-{definition.id}-{primary.id}",
    )


def _source_title(definition_id: str) -> str:
    definition = DEFINITIONS_BY_ID.get(definition_id)
    return _simplify_language(definition.title) if definition else ""


def _source_choice_label(definition_id: str, choice_id: str) -> str:
    definition = DEFINITIONS_BY_ID.get(definition_id)
    if not definition or not choice_id.startswith("choice-"):
        return ""
    try:
        index = int(choice_id.rsplit("-", 1)[-1]) - 1
        choice = definition.choices[index]
    except (ValueError, IndexError):
        return ""
    return _simplify_language(choice.label)


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
