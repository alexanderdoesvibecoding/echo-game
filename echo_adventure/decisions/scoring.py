"""ECHO static decision-tree scoring."""

from __future__ import annotations

from ..models import DecisionCard, DecisionChoice

def select_echo_choice(
    card: DecisionCard,
    graph: dict[str, DecisionCard] | None = None,
    memo: dict[str, float] | None = None,
) -> DecisionChoice:
    """Return the benchmark choice ECHO treats as the correct response."""
    if graph is None and memo is None and card.echo_choice_id:
        selected = next((choice for choice in card.choices if choice.id == card.echo_choice_id), None)
        if selected:
            return selected
    memo = memo if memo is not None else {}
    return min(
        card.choices,
        key=lambda choice: (_choice_path_score(choice, graph, memo=memo), choice.id),
    )

def score_echo_choice(
    choice: DecisionChoice,
    graph: dict[str, DecisionCard] | None = None,
    memo: dict[str, float] | None = None,
) -> float:
    """Return ECHO's static campaign-graph score for a choice."""
    return _choice_path_score(choice, graph, memo=memo)

def _choice_path_score(
    choice: DecisionChoice,
    graph: dict[str, DecisionCard] | None,
    visiting: frozenset[str] | None = None,
    memo: dict[str, float] | None = None,
) -> float:
    """Score a choice plus its best reachable downstream decision path for ECHO."""
    effect_rank = {
        "echo_recommendation": 0,
        "expedite_event": 1,
        "reroute": 2,
        "split_capacity": 3,
        "pull_forward": 4,
        "protect_critical": 5,
        "prioritize_new_job": 6,
        "resequence": 6,
        "backlog_new_job": 8,
        "preempt": 7,
        "defer": 8,
        "wait": 9,
    }
    immediate = (
        choice.risk_effect * 12
        + effect_rank.get(choice.immediate_effects.get("type", "note"), 20) * 3
        + choice.reschedule_effect * 4
    )
    if choice.score_delta:
        immediate -= choice.score_delta * 1.5
    if not graph:
        return immediate
    visiting = visiting if visiting is not None else frozenset()
    memo = memo if memo is not None else {}
    child_ids = []
    if choice.next_card_id:
        child_ids.append(choice.next_card_id)
    child_ids.extend(choice.future_unlock_card_ids)
    child_scores = []
    for child_id in dict.fromkeys(child_ids):
        if child_id in visiting:
            continue
        child = graph.get(child_id)
        if child:
            child_scores.append(_card_path_score(child, graph, visiting, memo))
    if not child_scores:
        return immediate
    return immediate + min(child_scores) * 0.65

def _card_path_score(
    card: DecisionCard,
    graph: dict[str, DecisionCard],
    visiting: frozenset[str],
    memo: dict[str, float],
) -> float:
    """Return ECHO's best full-tree score from one downstream card."""
    if card.id in memo:
        return memo[card.id]
    if card.id in visiting:
        return 0.0
    next_visiting = visiting | {card.id}
    best = min(
        _choice_path_score(child_choice, graph, next_visiting, memo)
        for child_choice in card.choices
    )
    memo[card.id] = best
    return best
