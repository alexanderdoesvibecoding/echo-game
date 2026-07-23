"""Read-only developer inspection for decision follow-ups."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..decision_web import DecisionWeb, DecisionWebNode, DecisionWebState
from ..decisions.definitions import DEFINITIONS_BY_ID, DecisionDefinition
from ..decisions.effects import follow_up_occurs
from ..models import DecisionCard, DecisionChoice, Job, SimulationState


_RUNTIME_EFFECT_NOTE = "Effect determined when follow-up appears"


def inspect_preplanned_follow_up(
    web: DecisionWeb,
    node_id: str,
    choice: DecisionChoice,
    jobs: Mapping[str, Job],
    date_label_for_day: Callable[[int], str],
) -> dict[str, Any]:
    """Inspect the realized follow-up subgraph for one immutable-web edge."""
    node = web.node(node_id)
    transition = node.transitions[choice.id]
    if transition.next_node_id is None:
        return _unscheduled_follow_up("preplanned")

    successor = web.node(transition.next_node_id)
    source = (
        node.state.day,
        node.card.definition_id,
        choice.id,
    )
    if not _state_has_source(successor.state, source):
        return _unscheduled_follow_up("preplanned")

    target_definition_id = successor.state.pending_definition_id
    target_definition = DEFINITIONS_BY_ID.get(target_definition_id)
    target_job_id = _pending_job_id(successor.state, jobs)
    target_job = jobs.get(target_job_id)
    visited: set[str] = set()
    stack = [transition.next_node_id]
    canceled_on_some_continuations = False
    variants: dict[tuple[Any, ...], dict[str, Any]] = {}

    while stack:
        current_node_id = stack.pop()
        if current_node_id in visited:
            continue
        visited.add(current_node_id)
        current = web.node(current_node_id)
        if not _state_has_source(
            current.state,
            source,
            target_definition_id=target_definition_id,
        ):
            canceled_on_some_continuations = True
            continue

        if _card_has_source(current.card, source):
            signature = _variant_signature(current.card)
            stored = variants.setdefault(
                signature,
                _preplanned_variant_payload(current, jobs),
            )
            stored["_possible_days"].add(current.state.day)
            continue

        for next_transition in current.transitions.values():
            if next_transition.next_node_id is None:
                canceled_on_some_continuations = True
                continue
            next_node = web.node(next_transition.next_node_id)
            if _state_has_source(
                next_node.state,
                source,
                target_definition_id=target_definition_id,
            ):
                stack.append(next_transition.next_node_id)
            else:
                canceled_on_some_continuations = True

    variant_payloads = []
    possible_days: set[int] = set()
    for variant in variants.values():
        days = sorted(variant.pop("_possible_days"))
        possible_days.update(days)
        variant["possibleDays"] = days
        variant_payloads.append(variant)
    variant_payloads.sort(
        key=lambda item: (
            item["possibleDays"],
            item["title"],
            item["signature"],
        )
    )
    ordered_days = sorted(possible_days)
    return {
        "mode": "preplanned",
        "scheduled": True,
        "target": {
            "definitionId": target_definition_id,
            "title": (
                target_definition.title
                if target_definition
                else target_definition_id
            ),
            "jobId": target_job_id,
            "jobLabel": _job_label(target_job_id),
            "jobName": target_job.name if target_job else target_job_id,
            "delayDays": (
                successor.state.pending_available_day
                - successor.state.pending_source_day
            ),
        },
        "earliestDay": ordered_days[0] if ordered_days else None,
        "earliestDate": (
            date_label_for_day(ordered_days[0])
            if ordered_days
            else None
        ),
        "possibleDays": ordered_days,
        "possibleDates": [
            date_label_for_day(day)
            for day in ordered_days
        ],
        "canceledOnSomeContinuations": canceled_on_some_continuations,
        "variants": variant_payloads,
    }


def inspect_runtime_follow_up(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
) -> dict[str, Any]:
    """Describe the exact runtime scheduling result without mutating state."""
    if card.player_only:
        return {
            **_unscheduled_follow_up("player-only"),
            "note": "Final-assembly choices do not schedule follow-ups.",
        }

    job = state.jobs.get(card.primary_job_id)
    pending_ids = {item.definition_id for item in state.pending_follow_ups}
    targets = []
    for follow_up in choice.follow_ups:
        definition = DEFINITIONS_BY_ID.get(follow_up.definition_id)
        eligible = bool(
            job
            and not job.is_complete
            and definition
            and definition.is_follow_up
            and follow_up.definition_id not in state.shown_follow_up_decision_ids
            and follow_up.definition_id not in pending_ids
        )
        occurs = bool(
            eligible
            and follow_up_occurs(
                state,
                card,
                choice,
                follow_up.definition_id,
                follow_up.probability,
            )
        )
        target = {
            "definitionId": follow_up.definition_id,
            "title": definition.title if definition else follow_up.definition_id,
            "jobId": card.primary_job_id,
            "jobLabel": _job_label(card.primary_job_id),
            "jobName": job.name if job else card.primary_job_id,
            "delayDays": follow_up.delay_days,
            "availableDay": state.current_day + follow_up.delay_days,
            "probability": follow_up.probability,
            "scheduled": occurs,
            "effectNote": _RUNTIME_EFFECT_NOTE,
            "possibilities": (
                _catalog_possibilities(definition)
                if definition
                else []
            ),
        }
        targets.append(target)
        if occurs:
            pending_ids.add(follow_up.definition_id)

    return {
        "mode": "runtime",
        "scheduled": any(target["scheduled"] for target in targets),
        "targets": targets,
    }


def _unscheduled_follow_up(mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "scheduled": False,
        "targets": [],
    }


def _state_has_source(
    state: DecisionWebState,
    source: tuple[int, str, str],
    *,
    target_definition_id: str | None = None,
) -> bool:
    source_day, source_definition_id, source_choice_id = source
    return bool(
        state.pending_definition_id
        and (
            target_definition_id is None
            or state.pending_definition_id == target_definition_id
        )
        and state.pending_source_day == source_day
        and state.pending_source_definition_id == source_definition_id
        and state.pending_source_choice_id == source_choice_id
    )


def _card_has_source(
    card: DecisionCard,
    source: tuple[int, str, str],
) -> bool:
    source_day, source_definition_id, source_choice_id = source
    return bool(
        card.event_scope == "follow-up"
        and card.follow_up_source_day == source_day
        and card.follow_up_source_definition_id == source_definition_id
        and card.follow_up_source_choice_id == source_choice_id
    )


def _pending_job_id(
    state: DecisionWebState,
    jobs: Mapping[str, Job],
) -> str:
    job_ids = tuple(sorted(jobs))
    if 0 <= state.pending_job_index < len(job_ids):
        return job_ids[state.pending_job_index]
    return ""


def _variant_signature(card: DecisionCard) -> tuple[Any, ...]:
    return (
        card.definition_id,
        card.title,
        card.description,
        card.primary_job_id,
        tuple(
            (
                choice.label,
                choice.score_delta,
                tuple(sorted(choice.day_changes.items())),
            )
            for choice in card.choices
        ),
    )


def _preplanned_variant_payload(
    node: DecisionWebNode,
    jobs: Mapping[str, Job],
) -> dict[str, Any]:
    card = node.card
    signature = "|".join(
        (
            card.definition_id,
            card.title,
            card.primary_job_id,
            *(
                f"{choice.label}:{choice.score_delta}:"
                f"{','.join(f'{job_id}={delta}' for job_id, delta in sorted(choice.day_changes.items()))}"
                for choice in card.choices
            ),
        )
    )
    return {
        "signature": signature,
        "definitionId": card.definition_id,
        "title": card.title,
        "description": card.description,
        "jobId": card.primary_job_id,
        "jobLabel": _job_label(card.primary_job_id),
        "jobName": jobs[card.primary_job_id].name,
        "choices": [
            {
                "id": choice.id,
                "label": choice.label,
                "rawScoreDelta": choice.score_delta,
                "jobDayChanges": [
                    _future_job_day_change_payload(
                        node.state,
                        jobs,
                        job_id,
                        delta,
                    )
                    for job_id, delta in sorted(choice.day_changes.items())
                ],
            }
            for choice in card.choices
        ],
        "_possible_days": set(),
    }


def _future_job_day_change_payload(
    state: DecisionWebState,
    jobs: Mapping[str, Job],
    job_id: str,
    delta: int,
) -> dict[str, Any]:
    job_ids = tuple(sorted(jobs))
    job_index = job_ids.index(job_id)
    applies = not bool(state.completed_mask & (1 << job_index))
    remaining_before = max(0, state.remaining_days[job_index])
    remaining_after = (
        max(0, remaining_before + delta)
        if applies
        else remaining_before
    )
    return {
        "jobId": job_id,
        "jobLabel": _job_label(job_id),
        "jobName": jobs[job_id].name,
        "days": delta,
        "applies": applies,
        "remainingBefore": remaining_before,
        "remainingAfter": remaining_after,
    }


def _catalog_possibilities(
    definition: DecisionDefinition,
) -> list[dict[str, Any]]:
    results = [
        ("catalog", definition.title, definition.description, definition.choices),
        *(
            ("alternate", result.title, result.description, result.choices)
            for result in definition.alternate_results
        ),
    ]
    return [
        {
            "kind": kind,
            "title": title,
            "description": description,
            "choices": [
                {
                    "label": choice.label,
                    "rawScoreDelta": choice.score_delta,
                    "effectNote": _RUNTIME_EFFECT_NOTE,
                }
                for choice in choices
            ],
        }
        for kind, title, description, choices in results
    ]


def _job_label(job_id: str) -> str:
    if not job_id:
        return ""
    suffix = job_id.rsplit("-", 1)[-1]
    return f"Job {int(suffix)}"
