"""Hidden ECHO policy for the jobs-only benchmark."""

from __future__ import annotations

from .config import GameConfig
from .decisions import apply_choice, generate_daily_decision_cards, select_echo_choice
from .models import SimulationState
from .simulation import advance_day


def advance_echo_day(state: SimulationState, config: GameConfig) -> None:
    if state.final_item_completed:
        return
    for card in generate_daily_decision_cards(state, config):
        apply_choice(state, card, select_echo_choice(card), actor="ECHO")
        if state.final_item_completed:
            return
    advance_day(state)
