# echo_adventure/tests/test_echo_wins.py

from echo_adventure.config import GameConfig
from echo_adventure.echo import apply_echo_decisions_for_day
from echo_adventure.metrics import calculate_snapshot
from echo_adventure.scenario_generator import generate_scenario
from echo_adventure.schedulers.automated import AutomatedScheduler
from echo_adventure.simulation import advance_day, initialize_state


def _run_echo(config):
    scenario = generate_scenario(config)
    state = initialize_state(scenario, config.shifts_per_day)
    scheduler = AutomatedScheduler()
    completed_days = set()

    while state.current_shift < state.deadline_shift and not state.final_item_completed:
        apply_echo_decisions_for_day(state, config, completed_days)
        advance_day(state, scheduler)

    return calculate_snapshot(state)


def test_echo_wins_normal_sampled_seeds():
    balance_regression_seeds = [76, 99, 101, 139, 140]
    for seed in [*range(1, 31), *balance_regression_seeds]:
        config = GameConfig.for_preset("normal", seed=seed)
        snapshot = _run_echo(config)
        assert snapshot.deadline_met, f"ECHO missed normal seed {seed}"
        
