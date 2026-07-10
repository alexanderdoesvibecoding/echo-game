"""Named manufacturing decision graph generation and runtime filtering."""

from __future__ import annotations

import copy
import hashlib
import random

from ..config import GameConfig
from ..enums import DecisionType, ResourceKind
from ..models import (
    CampaignDecisionGraph,
    DecisionCard,
    DecisionChoice,
    DecisionDefinition,
    DecisionProgress,
    FollowUpEdge,
    Job,
    SimulationState,
)
from .definitions import BASE_DEFINITIONS, get_decision_definitions
from .scoring import select_echo_choice


def generate_campaign_decision_graph(
    state: SimulationState,
    config: GameConfig,
) -> tuple[dict[str, DecisionCard], CampaignDecisionGraph]:
    """Prebuild the complete named graph and sample repeatable run-time roots."""
    definitions = get_decision_definitions()
    cards: dict[str, DecisionCard] = {}
    graph = CampaignDecisionGraph(
        max_active_cards_per_day=min(config.max_active_decision_cards_per_day, config.max_decisions_per_day),
    )

    # Stable prototypes make every design definition inspectable by ECHO even
    # when a base card is not sampled into this particular run.
    for definition in definitions.values():
        prototype = _card_from_definition(definition, f"DEF-{definition.id}", day=0)
        cards[prototype.id] = prototype
        graph.definition_card_ids[definition.id] = prototype.id
        if definition.is_follow_up:
            graph.follow_up_card_ids[definition.id] = prototype.id

    rng = random.Random(_stable_int(f"{state.seed}|named-manufacturing-campaign"))
    choices_per_day = max(
        1,
        min(config.max_active_decision_cards_per_day, config.max_decisions_per_day),
    )
    base_population = list(BASE_DEFINITIONS)
    weights = [max(0.01, definition.weight) for definition in base_population]

    for day in range(1, config.total_days + 1):
        selected: list[DecisionDefinition] = []
        attempts = 0
        while len(selected) < choices_per_day and attempts < len(base_population) * 4:
            attempts += 1
            definition = rng.choices(base_population, weights=weights, k=1)[0]
            if any(item.id == definition.id for item in selected):
                continue
            selected.append(definition)
        for ordinal, definition in enumerate(selected, start=1):
            card_id = f"DEC-D{day:02d}-{ordinal:02d}-{definition.id.upper()}"
            card = _card_from_definition(definition, card_id, day)
            _retarget_card(state, card, day)
            cards[card.id] = card
            graph.cards_by_day.setdefault(day, []).append(card.id)
            graph.root_card_ids.append(card.id)

    memo: dict[str, float] = {}
    for card in cards.values():
        card.echo_choice_id = select_echo_choice(card, cards, memo).id

    return cards, graph


def _card_from_definition(definition: DecisionDefinition, card_id: str, day: int) -> DecisionCard:
    return DecisionCard(
        id=card_id,
        day=day,
        type=DecisionType.FOLLOW_UP if definition.is_follow_up else DecisionType.MANUFACTURING,
        title=definition.title,
        description=definition.description,
        target_ids=[],
        severity=definition.severity,
        choices=copy.deepcopy(list(definition.choices)),
        campaign_priority=10 if definition.is_follow_up else 100,
        definition_id=definition.id,
        target_selector=definition.target_selector,
        unavoidable_effects=copy.deepcopy(list(definition.unavoidable_effects)),
        unavoidable_follow_up_edges=copy.deepcopy(list(definition.unavoidable_follow_up_edges)),
        is_follow_up=definition.is_follow_up,
    )


def active_decision_cards(
    state: SimulationState,
    day: int,
    selected_choices: dict[str, str],
) -> list[DecisionCard]:
    """Return the current day's shared follow-ups and sampled base cards."""
    return active_campaign_decision_cards(state, day, selected_choices)


def active_campaign_decision_cards(
    state: SimulationState,
    day: int,
    selected_choices: dict[str, str],
) -> list[DecisionCard]:
    graph = state.campaign_decision_graph
    effective = {**state.campaign_selected_choices, **selected_choices}
    due_follow_ups = [
        card_id
        for card_id, due_shift in state.scheduled_decision_card_shifts.items()
        if due_shift <= state.current_shift
        and card_id in state.decision_cards
        and card_id not in effective
    ]
    # Keep cards already shown/answered today stable while new cards are being
    # selected.  Follow-ups take priority over routine sampled cards.
    already_today = [
        card_id
        for card_id in effective
        if (card := state.decision_cards.get(card_id)) and card.day == day
    ]
    root_ids = list(graph.cards_by_day.get(day, []))
    candidate_ids = list(dict.fromkeys([*already_today, *due_follow_ups, *root_ids]))

    visible: list[DecisionCard] = []
    for card_id in candidate_ids:
        card = state.decision_cards.get(card_id)
        if not card:
            continue
        if card.id not in effective and not _retarget_card(state, card, day):
            continue
        visible.append(card)

    visible.sort(
        key=lambda card: (
            0 if card.id in already_today else 1 if card.is_follow_up else 2,
            card.campaign_priority,
            -card.severity,
            card.id,
        )
    )
    limit = graph.max_active_cards_per_day or len(visible)
    return visible[:limit]


def decision_progress(
    state: SimulationState,
    day: int,
    selected_choices: dict[str, str],
) -> DecisionProgress:
    cards = active_campaign_decision_cards(state, day, selected_choices)
    effective = {**state.campaign_selected_choices, **selected_choices}
    open_card_ids = [card.id for card in cards if card.id not in effective]
    return DecisionProgress(
        day=day,
        total_questions=len(cards),
        answered_questions=len(cards) - len(open_card_ids),
        visible_cards=len(cards),
        open_card_ids=open_card_ids,
    )


def apply_campaign_choice(state: SimulationState, card: DecisionCard, choice: DecisionChoice) -> None:
    """Persist the decision path and resolve all named edges deterministically."""
    state.campaign_selected_choices[card.id] = choice.id
    state.decision_path.append(f"{card.id}:{choice.id}")
    state.decision_path_signature = decision_path_signature(state)
    state.decision_path_score_delta = round(state.decision_path_score_delta + choice.score_delta, 4)
    _resolve_follow_up_edges(state, card, choice.id, choice.follow_up_edges)
    _resolve_follow_up_edges(state, card, "unavoidable", card.unavoidable_follow_up_edges)


def _resolve_follow_up_edges(
    state: SimulationState,
    source_card: DecisionCard,
    source_choice_id: str,
    edges: list[FollowUpEdge],
) -> None:
    for edge in edges:
        outcome_key = f"{source_card.id}:{source_choice_id}:{edge.target_definition_id}"
        if outcome_key in state.follow_up_outcomes:
            fired = state.follow_up_outcomes[outcome_key]
        else:
            material = f"{state.seed}|{state.scenario_id}|{outcome_key}"
            roll = _stable_int(material) / float(2**256 - 1)
            fired = roll < max(0.0, min(1.0, edge.probability))
            state.follow_up_outcomes[outcome_key] = fired
        if not fired:
            continue
        card_id = state.campaign_decision_graph.follow_up_card_ids.get(edge.target_definition_id)
        if not card_id or card_id in state.campaign_selected_choices:
            continue
        if card_id not in state.scheduled_decision_card_shifts:
            due_shift = min(state.deadline_shift, state.current_shift + max(1, edge.delay_shifts))
            state.scheduled_decision_card_shifts[card_id] = due_shift
            state.follow_up_sources[card_id] = source_card.id
            state.unlocked_decision_card_ids.add(card_id)
            follow_up = state.decision_cards[card_id]
            follow_up.target_ids = list(source_card.target_ids)
            follow_up.context_label = source_card.context_label
            follow_up.day = min(
                state.deadline_shift // state.shifts_per_day,
                (due_shift // state.shifts_per_day) + 1,
            )


def unlock_future_decision_nodes(state: SimulationState, card_ids: list[str]) -> None:
    """Compatibility helper for callers holding stable prebuilt card ids."""
    for card_id in card_ids:
        if card_id not in state.decision_cards:
            continue
        state.unlocked_decision_card_ids.add(card_id)
        state.scheduled_decision_card_shifts.setdefault(card_id, state.current_shift + state.shifts_per_day)


def project_choice_branch_state(choice: DecisionChoice) -> tuple[str, list[str]]:
    """Return the first named successor and all reachable definition ids."""
    ids = [edge.target_definition_id for edge in choice.follow_up_edges]
    return (ids[0] if ids else "", ids)


def decision_path_signature(state: SimulationState) -> str:
    if not state.decision_path:
        return ""
    return hashlib.sha256("|".join(state.decision_path).encode("utf-8")).hexdigest()[:16]


def _retarget_card(state: SimulationState, card: DecisionCard, day: int) -> bool:
    """Keep every visible card attached to relevant incomplete work."""
    current_jobs = [state.jobs[target_id] for target_id in card.target_ids if target_id in state.jobs]
    current_jobs = [job for job in current_jobs if not job.is_complete]
    if current_jobs:
        _set_card_context(state, card, current_jobs[0])
        return True

    candidates = _target_candidates(state, card.target_selector)
    if not candidates:
        return False
    candidates.sort(key=lambda job: (job.due_shift, -job.priority, job.id))
    index = _stable_int(f"{state.seed}|{card.id}|{day}|{card.target_selector}") % len(candidates)
    job = candidates[index]
    card.target_ids = [job.id]
    _append_domain_targets(state, card, job)
    _set_card_context(state, card, job)
    return True


def _target_candidates(state: SimulationState, selector: str) -> list[Job]:
    incomplete = [job for job in state.jobs.values() if not job.is_complete]
    if selector in {"critical", "critical_family"}:
        return [job for job in incomplete if job.critical_path] or incomplete
    if selector in {"inspection", "gauge"}:
        selected = [job for job in incomplete if job.required_capability in {"inspection", "metrology", "calibration", "certification"}]
        return selected or incomplete
    if selector in {"fixture", "tool"}:
        selected = [job for job in incomplete if job.required_capability in {"tooling", "fixture", "fitting", "alignment", "forming"}]
        return selected or incomplete
    if selector == "batch":
        selected = [job for job in incomplete if job.required_capability in {"curing", "coating", "surface_prep", "bonding", "finishing"}]
        return selected or incomplete
    if selector in {"handoff", "crane"}:
        selected = [job for job in incomplete if job.dependency_ids or job.transport_delay_shifts]
        return selected or incomplete
    if selector in {"ready", "software"}:
        selected = [job for job in incomplete if state.is_dependency_complete(job.id)]
        return selected or incomplete
    if selector == "document":
        selected = [job for job in incomplete if job.document_id]
        return selected or incomplete
    return incomplete


def _append_domain_targets(state: SimulationState, card: DecisionCard, job: Job) -> None:
    selector = card.target_selector
    if selector in {"workcenter", "handoff"}:
        wc_id = job.assigned_workcenter_id or (job.candidate_workcenter_ids[0] if job.candidate_workcenter_ids else None)
        if wc_id:
            card.target_ids.append(wc_id)
    if selector == "worker" and job.worker_id:
        card.target_ids.append(job.worker_id)
    if selector == "material" and job.material_id:
        card.target_ids.append(job.material_id)
    if selector == "document" and job.document_id:
        card.target_ids.append(job.document_id)
    if selector in {"inspection", "gauge"} and job.inspection_method_id:
        card.target_ids.append(job.inspection_method_id)
    if selector == "fixture" and job.fixture_id:
        card.target_ids.append(job.fixture_id)
    if selector == "controlled" and job.area_id:
        card.target_ids.append(job.area_id)

    kind_by_selector = {
        "crane": ResourceKind.CRANE,
        "software": ResourceKind.SOFTWARE_SEAT,
        "batch": ResourceKind.BATCH_SLOT,
        "staging": ResourceKind.STAGING_LANE,
        "waste": ResourceKind.WASTE_CONTAINER,
        "tool": ResourceKind.TOOL,
    }
    kind = kind_by_selector.get(selector)
    if kind:
        matches = [
            resource.id
            for resource in state.shared_resources.values()
            if resource.kind == kind and resource.shop_id in {None, job.shop_id}
        ]
        if matches:
            card.target_ids.append(sorted(matches)[0])
    if selector in {"shop", "staging", "controlled", "waste", "global"}:
        card.target_ids.append(job.shop_id)


def _set_card_context(state: SimulationState, card: DecisionCard, job: Job) -> None:
    shop = state.shops.get(job.shop_id)
    if card.target_selector == "global":
        card.context_label = "Overall schedule"
        return
    if card.target_selector in {"shop", "staging", "controlled", "waste"} and shop:
        card.context_label = shop.name
        return
    if card.target_selector == "workcenter":
        wc_id = job.assigned_workcenter_id or (job.candidate_workcenter_ids[0] if job.candidate_workcenter_ids else "")
        if wc_id in state.workcenters:
            card.context_label = state.workcenters[wc_id].name
            return
    card.context_label = _job_impact_label(state, job)


def _job_impact_label(state: SimulationState, job: Job) -> str:
    piece = state.pieces.get(job.piece_id)
    if piece:
        return piece.name.split(" - ", 1)[0]
    suffix = job.piece_id.split("-")[-1] if job.piece_id else ""
    return f"Job {suffix}" if suffix else job.id


def _stable_int(material: str) -> int:
    return int(hashlib.sha256(material.encode("utf-8")).hexdigest(), 16)
