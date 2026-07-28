"""Advance ECHO through the omniscient route solved in the decision web."""

from __future__ import annotations

from .decision_web import DecisionWeb, DecisionWebTransition
from .decisions import apply_choice
from .models import SimulationState
from .simulation import advance_day


def apply_omniscient_choice(
    state: SimulationState,
    web: DecisionWeb,
    node_id: str,
) -> DecisionWebTransition:
    """Apply exactly one globally optimal choice without advancing the day."""
    if state.final_item_completed:
        raise RuntimeError("ECHO cannot choose after completing every job.")
    # Drift would invalidate the solved policy, so fail before applying an edge
    # computed for a different compact runtime state.
    web.assert_runtime_matches(state, node_id)
    node = web.node(node_id)
    state.decision_cards[node.card.id] = node.card
    # The builder has already compared every complete continuation; runtime
    # ECHO therefore follows the stored optimal ID instead of choosing locally.
    choice = next(
        choice for choice in node.card.choices if choice.id == node.optimal_choice_id
    )
    apply_choice(
        state,
        node.card,
        choice,
        actor="ECHO",
        schedule_follow_ups=False,
    )
    return node.transitions[choice.id]


def advance_omniscient_day(
    state: SimulationState,
    transition: DecisionWebTransition,
) -> str | None:
    """Apply ECHO's once-per-day work tick after all choices for the day."""
    if not transition.advances_day:
        raise RuntimeError("ECHO cannot advance before completing its daily choices.")
    # Overtime cards are generated at runtime for the player only. A solved,
    # globally optimal ECHO route must always finish inside the immutable web.
    if transition.enters_overtime:
        raise RuntimeError("ECHO's solved route crossed the runtime-generation boundary.")
    advance_day(state)
    if transition.next_node_id is None and not state.final_item_completed:
        raise RuntimeError("ECHO reached a terminal web edge before completing every job.")
    return transition.next_node_id
