"""Choice selection for developer-mode automated play."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from ..decision_web import DecisionWeb
from ..decisions import (
    projected_completion_day_after_choice,
    select_echo_choice_for_state,
)
from ..models import DecisionCard, DecisionChoice, SimulationState


AUTOMATION_STRATEGIES = frozenset({"echo", "random", "first", "last", "worst"})


@dataclass(frozen=True)
class AutomationContext:
    """Stable material shared by one real or dry automated traversal."""

    seed: int
    start_token: str


def validate_automation_strategy(strategy: object) -> str:
    if not isinstance(strategy, str) or strategy not in AUTOMATION_STRATEGIES:
        supported = ", ".join(sorted(AUTOMATION_STRATEGIES))
        raise ValueError(f"Unknown automated strategy. Choose one of: {supported}.")
    return strategy


def select_preplanned_choice(
    web: DecisionWeb,
    node_id: str,
    strategy: str,
    context: AutomationContext,
    *,
    max_campaign_day: int,
) -> DecisionChoice:
    """Select one immutable-web choice without changing session state."""
    node = web.node(node_id)
    choices = node.card.choices
    if strategy == "echo":
        return _choice_by_id(choices, node.optimal_choice_id)
    if strategy == "first":
        return choices[0]
    if strategy == "last":
        return choices[-1]
    if strategy == "random":
        return _deterministic_choice(
            choices,
            context,
            "preplanned",
            node_id,
        )
    if strategy == "worst":
        return min(
            choices,
            key=lambda choice: _preplanned_worst_key(
                web,
                node_id,
                choice,
                max_campaign_day=max_campaign_day,
            ),
        )
    raise ValueError(f"Unsupported automated strategy: {strategy}.")


def select_runtime_choice(
    state: SimulationState,
    card: DecisionCard,
    strategy: str,
    context: AutomationContext,
) -> DecisionChoice:
    """Select an overtime/final-assembly choice from the current real state."""
    choices = card.choices
    if strategy == "echo":
        if card.player_only:
            return _choice_by_id(choices, card.echo_choice_id)
        return select_echo_choice_for_state(state, choices)
    if strategy == "first":
        return choices[0]
    if strategy == "last":
        return choices[-1]
    if strategy == "random":
        return _deterministic_choice(
            choices,
            context,
            "runtime",
            card.id,
            str(len(state.decision_history)),
        )
    if strategy == "worst":
        candidates = choices
        incomplete = state.incomplete_jobs()
        if len(incomplete) == 1:
            last_job = incomplete[0]
            progress_safe = [
                choice
                for choice in choices
                if choice.day_changes.get(last_job.id, 0) <= 0
            ]
            if not progress_safe:
                return select_echo_choice_for_state(state, choices)
            candidates = progress_safe
        return min(
            candidates,
            key=lambda choice: (
                -projected_completion_day_after_choice(state, choice),
                round(state.decision_score + choice.score_delta, 2),
                choice.id,
            ),
        )
    raise ValueError(f"Unsupported automated strategy: {strategy}.")


def _preplanned_worst_key(
    web: DecisionWeb,
    node_id: str,
    choice: DecisionChoice,
    *,
    max_campaign_day: int,
) -> tuple[int, float, str]:
    transition = web.transition(node_id, choice.id)
    if transition.completion_day is not None:
        completion_day = transition.completion_day
        future_score = 0.0
    elif transition.enters_overtime:
        completion_day = max_campaign_day
        future_score = 0.0
    else:
        successor = web.node(transition.next_node_id or "")
        completion_day = successor.optimal_completion_day
        future_score = successor.optimal_future_score
    resulting_score = round(choice.score_delta + future_score, 2)
    return (-completion_day, resulting_score, choice.id)


def _deterministic_choice(
    choices: list[DecisionChoice],
    context: AutomationContext,
    *location: str,
) -> DecisionChoice:
    material = "|".join(
        (
            str(context.seed),
            context.start_token,
            *location,
        )
    ).encode("utf-8")
    rng = random.Random(int(hashlib.sha256(material).hexdigest(), 16))
    return choices[rng.randrange(len(choices))]


def _choice_by_id(
    choices: list[DecisionChoice],
    choice_id: str,
) -> DecisionChoice:
    choice = next((item for item in choices if item.id == choice_id), None)
    if choice is None:
        raise RuntimeError(f"Automated choice {choice_id!r} is not present on its card.")
    return choice
