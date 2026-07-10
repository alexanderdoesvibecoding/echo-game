"""Probability-aware static scoring for the named manufacturing graph."""

from __future__ import annotations

from ..models import DecisionCard, DecisionChoice, DecisionEffect


def select_echo_choice(
    card: DecisionCard,
    graph: dict[str, DecisionCard] | None = None,
    memo: dict[str, float] | None = None,
) -> DecisionChoice:
    """Return ECHO's lowest expected-cost response."""
    if graph is None and memo is None and card.echo_choice_id:
        selected = next((choice for choice in card.choices if choice.id == card.echo_choice_id), None)
        if selected:
            return selected
    memo = memo if memo is not None else {}
    return min(card.choices, key=lambda choice: (_choice_path_score(choice, graph, frozenset(), memo), choice.id))


def score_echo_choice(
    choice: DecisionChoice,
    graph: dict[str, DecisionCard] | None = None,
    memo: dict[str, float] | None = None,
) -> float:
    return _choice_path_score(choice, graph, frozenset(), memo if memo is not None else {})


def _choice_path_score(
    choice: DecisionChoice,
    graph: dict[str, DecisionCard] | None,
    visiting: frozenset[str],
    memo: dict[str, float],
) -> float:
    immediate = sum(_effect_cost(effect) for effect in choice.effects)
    immediate -= choice.score_delta * 0.25
    if not graph:
        return immediate

    expected_future = 0.0
    for edge in choice.follow_up_edges:
        child_id = f"DEF-{edge.target_definition_id}"
        if child_id in visiting or child_id not in graph:
            continue
        child_cost = _card_path_score(graph[child_id], graph, visiting, memo)
        expected_future += max(0.0, min(1.0, edge.probability)) * child_cost * 0.65
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
    best = min(_choice_path_score(choice, graph, next_visiting, memo) for choice in card.choices)
    memo[card.id] = best
    return best


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
