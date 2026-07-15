"""Execute ECHO's omniscient route through the solved decision web."""

from __future__ import annotations

from .decision_web import DecisionWeb
from .decisions import apply_choice
from .models import SimulationState
from .simulation import advance_day


def run_omniscient_echo(state: SimulationState, web: DecisionWeb) -> None:
    """Traverse the globally optimal policy already solved at startup."""
    node_id = web.root_node_id
    while not state.final_item_completed:
        web.assert_runtime_matches(state, node_id)
        node = web.node(node_id)
        state.decision_cards[node.card.id] = node.card
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
        transition = node.transitions[choice.id]
        if transition.advances_day:
            advance_day(state)
        if transition.enters_overtime:
            raise RuntimeError("ECHO's solved route crossed the runtime-generation boundary.")
        if transition.next_node_id is None:
            if not state.final_item_completed:
                raise RuntimeError("ECHO reached a terminal web edge before completing every job.")
            return
        node_id = transition.next_node_id
