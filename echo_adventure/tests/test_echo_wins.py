# echo_adventure/tests/test_echo_wins.py

from echo_adventure.config import GameConfig
from echo_adventure.decisions import active_decision_cards, apply_choice, select_echo_choice
from echo_adventure.metrics import calculate_snapshot
from echo_adventure.scenario_generator import generate_scenario
from echo_adventure.schedulers.automated import AutomatedScheduler
from echo_adventure.simulation import advance_day, initialize_state


def _apply_echo_decisions_for_day(state, completed_days):
    day = state.current_day
    if day in completed_days or state.final_item_completed:
        return

    selected = {}
    for _ in range(32):
        cards = active_decision_cards(state, day, selected)
        open_cards = [card for card in cards if card.id not in selected]
        if not open_cards:
            break

        for card in open_cards:
            choice = select_echo_choice(card, state.decision_cards)
            apply_choice(state, card, choice, actor="ECHO", echo_choice=choice)
            selected[card.id] = choice.id

    completed_days.add(day)


def _run_echo(config):
    scenario = generate_scenario(config)
    state = initialize_state(scenario, config.shifts_per_day)
    scheduler = AutomatedScheduler()
    completed_days = set()

    while state.current_shift < state.deadline_shift and not state.final_item_completed:
        _apply_echo_decisions_for_day(state, completed_days)
        advance_day(state, scheduler)

    return calculate_snapshot(state)


def test_echo_wins_normal_sampled_seeds():
    for seed in range(1, 31):
        config = GameConfig.for_preset("normal", seed=seed)
        snapshot = _run_echo(config)
        assert snapshot.deadline_met, f"ECHO missed normal seed {seed}"


def test_echo_wins_demo_sampled_seeds():
    balance_regression_seeds = [76, 99, 101, 139, 140]
    for seed in [*range(1, 31), *balance_regression_seeds]:
        config = GameConfig.for_preset("demo", seed=seed)
        snapshot = _run_echo(config)
        assert snapshot.deadline_met, f"ECHO missed demo seed {seed}"
        
