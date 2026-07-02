"""Decision graph generation, card effects, and ECHO scoring."""

from __future__ import annotations

from .effects import apply_choice

from .graph import (
    active_campaign_decision_cards,
    active_decision_cards,
    apply_campaign_choice,
    decision_path_signature,
    decision_progress,
    generate_campaign_decision_graph,
    project_choice_branch_state,
    unlock_future_decision_nodes,
)

from .scoring import score_echo_choice, select_echo_choice

__all__ = [
    "active_campaign_decision_cards",
    "active_decision_cards",
    "apply_campaign_choice",
    "apply_choice",
    "decision_path_signature",
    "decision_progress",
    "generate_campaign_decision_graph",
    "project_choice_branch_state",
    "score_echo_choice",
    "select_echo_choice",
    "unlock_future_decision_nodes",
]
