"""Probability-aware point maximization for ECHO's decision graph."""

from __future__ import annotations

import hashlib

from ..models import DecisionCard, DecisionChoice, DecisionEffect, SimulationState


def select_echo_choice(
    card: DecisionCard,
    graph: dict[str, DecisionCard] | None = None,
    memo: dict[str, float] | None = None,
) -> DecisionChoice:
    """Return the response with the highest reachable expected point value."""
    if graph is None and memo is None and card.echo_choice_id:
        selected = next((choice for choice in card.choices if choice.id == card.echo_choice_id), None)
        if selected:
            return selected
    memo = memo if memo is not None else {}
    return min(
        card.choices,
        key=lambda choice: (
            -_choice_path_score(choice, graph, frozenset(), memo),
            _immediate_operational_cost(choice),
            choice.id,
        ),
    )


def score_echo_choice(
    choice: DecisionChoice,
    graph: dict[str, DecisionCard] | None = None,
    memo: dict[str, float] | None = None,
) -> float:
    return _choice_path_score(choice, graph, frozenset(), memo if memo is not None else {})


def select_realized_echo_choice(
    state: SimulationState,
    card: DecisionCard,
    graph: dict[str, DecisionCard] | None = None,
) -> DecisionChoice:
    """Choose the highest-scoring branch using this run's seeded outcomes.

    Static graph scores are probability-aware for generation and fallbacks.
    During a real or projected run ECHO knows the fixed scenario seed, so it
    can distinguish a temporary loss whose payoff will actually unlock from
    the same tempting choice whose payoff will not fire.
    """
    graph = graph or state.decision_cards
    return min(
        card.choices,
        key=lambda choice: (
            -score_realized_echo_choice(state, card, choice, graph),
            _immediate_operational_cost(choice),
            choice.id,
        ),
    )


def score_realized_echo_choice(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    graph: dict[str, DecisionCard] | None = None,
) -> float:
    """Return immediate points plus only the seeded follow-ups that will fire."""
    return _realized_choice_path_score(
        state,
        card,
        choice,
        graph or state.decision_cards,
        frozenset(),
    )


def _choice_path_score(
    choice: DecisionChoice,
    graph: dict[str, DecisionCard] | None,
    visiting: frozenset[str],
    memo: dict[str, float],
) -> float:
    immediate = _choice_points(choice)
    if not graph:
        return immediate

    expected_future = 0.0
    for edge in choice.follow_up_edges:
        child_id = f"DEF-{edge.target_definition_id}"
        if child_id in visiting or child_id not in graph:
            continue
        child_value = _card_path_score(graph[child_id], graph, visiting, memo)
        expected_future += max(0.0, min(1.0, edge.probability)) * child_value

    # Compatibility cards created by the legacy factories use direct card ids
    # instead of named probability edges. They remain useful in tests and for
    # custom scenarios, so include their deterministic successors too.
    legacy_child_ids = []
    if choice.next_card_id:
        legacy_child_ids.append(choice.next_card_id)
    legacy_child_ids.extend(choice.future_unlock_card_ids)
    for child_id in dict.fromkeys(legacy_child_ids):
        if child_id in visiting or child_id not in graph:
            continue
        expected_future += _card_path_score(graph[child_id], graph, visiting, memo)
    return immediate + expected_future


def _card_path_score(
    card: DecisionCard,
    graph: dict[str, DecisionCard],
    visiting: frozenset[str],
    memo: dict[str, float],
) -> float:
    if card.id in memo:
        return memo[card.id]
    if card.id in visiting:
        return 0.0
    next_visiting = visiting | {card.id}
    best = max(_choice_path_score(choice, graph, next_visiting, memo) for choice in card.choices)
    memo[card.id] = best
    return best


def _realized_choice_path_score(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    graph: dict[str, DecisionCard],
    visiting: frozenset[str],
) -> float:
    value = _choice_points(choice)
    next_visiting = visiting | {card.id}
    for edge in choice.follow_up_edges:
        child_id = state.campaign_decision_graph.follow_up_card_ids.get(
            edge.target_definition_id,
            f"DEF-{edge.target_definition_id}",
        )
        if child_id in next_visiting or child_id not in graph:
            continue
        outcome_key = f"{card.id}:{choice.id}:{edge.target_definition_id}"
        if not _seeded_edge_fires(state, outcome_key, edge.probability):
            continue
        child = graph[child_id]
        value += max(
            _realized_choice_path_score(state, child, child_choice, graph, next_visiting)
            for child_choice in child.choices
        )
    return value


def _seeded_edge_fires(state: SimulationState, outcome_key: str, probability: float) -> bool:
    if outcome_key in state.follow_up_outcomes:
        return state.follow_up_outcomes[outcome_key]
    material = f"{state.seed}|{state.scenario_id}|{outcome_key}"
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    roll = int.from_bytes(digest, "big") / float(2**256 - 1)
    return roll < max(0.0, min(1.0, probability))


def _choice_points(choice: DecisionChoice) -> float:
    """Return immediate visible points, with a legacy-card fallback."""
    if choice.effects or choice.score_delta:
        return float(choice.score_delta)
    # Older/custom cards may only carry risk/reschedule metadata. Preserve a
    # small, bounded penalty so ECHO can still detect a bad hidden tail.
    return max(-5.0, min(5.0, -choice.risk_effect * 0.25 - choice.reschedule_effect * 0.10))


def _immediate_operational_cost(choice: DecisionChoice) -> float:
    """Break equal-point ties in favor of the less disruptive response."""
    return sum(_effect_cost(effect) for effect in choice.effects)


def _effect_cost(effect: DecisionEffect) -> float:
    params = effect.params
    amount = _average(params.get("shifts", 0))
    count = max(1.0, min(8.0, _average(params.get("count", 1))))
    if params.get("mode") == "total":
        count = 1.0
    kind = effect.kind
    if kind in {"delay", "block", "downtime"}:
        return amount * count * 4.0
    if kind == "hold":
        return amount * count * 3.0
    if kind == "rework":
        return amount * count * 5.5
    if kind in {"recover", "open_capacity"}:
        return -amount * count * 4.5
    if kind == "release":
        return -count * 3.0
    if kind == "risk":
        return float(params.get("delta", 0)) * count * 1.2
    if kind == "reschedule":
        return float(params.get("count", 1)) * 2.0
    if kind == "reroute":
        return -1.5 * count
    if kind in {"queue_front", "batch", "nest", "approve", "verify", "qualify"}:
        return -1.0 * count
    if kind in {"material_transfer", "replace_worker"}:
        return -2.0
    if kind == "resource":
        action = str(params.get("action", ""))
        if action in {"open", "service", "calibrate", "certify", "temporary_fixture", "temporary_rack"}:
            return -3.0
        if action in {"unavailable", "hold", "needs_review"}:
            return 4.0 + amount
    return 0.0


def _average(value: object) -> float:
    if isinstance(value, (tuple, list)) and value:
        return (float(value[0]) + float(value[-1])) / 2.0
    return float(value or 0)
