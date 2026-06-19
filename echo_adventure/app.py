"""Terminal entry point and high-level game loop orchestration."""

from __future__ import annotations

import argparse
import sys

from .cli.input import ask_number
from .cli.menus import end_day_menu, inspection_menu, main_menu, seed_prompt
from .cli.renderer import GameRenderer
from .config import GameConfig, resolve_seed
from .decisions import apply_choice, generate_decision_cards
from .scenario_generator import generate_scenario
from .schedulers.automated import AutomatedScheduler
from .schedulers.manual import ManualScheduler
from .simulation import advance_day, initialize_state


def main(argv: list[str] | None = None) -> None:
    """Parse CLI options and route to either the terminal game or browser UI."""
    parser = argparse.ArgumentParser(description="Terminal scheduling strategy game.")
    parser.add_argument("--seed", type=int, help="Run a reproducible scenario seed.")
    parser.add_argument("--no-color", action="store_true", help="Disable colored terminal output where practical.")
    parser.add_argument("--debug", action="store_true", help="Show extra internal scenario information.")
    parser.add_argument("--ui", action="store_true", help="Run the local browser-based operations UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for the local UI server.")
    parser.add_argument("--port", type=int, default=8765, help="Port for the local UI server.")
    args = parser.parse_args(argv)

    if args.ui:
        from .ui_server import run_ui_server

        run_ui_server(seed=args.seed, host=args.host, port=args.port)
        return

    renderer = GameRenderer(use_color=not args.no_color)
    if args.seed is not None:
        run_game(seed=args.seed, renderer=renderer, use_color=not args.no_color, debug=args.debug)
        return

    while True:
        choice = main_menu(renderer)
        if choice is None or choice == 3:
            renderer.print("Good run discipline: no schedule started.")
            return
        if choice == 1:
            run_game(seed=None, renderer=renderer, use_color=not args.no_color, debug=args.debug)
        elif choice == 2:
            run_game(seed=seed_prompt(), renderer=renderer, use_color=not args.no_color, debug=args.debug)


def run_game(seed: int | None, renderer: GameRenderer, use_color: bool = True, debug: bool = False) -> None:
    """Run one complete terminal game, including the hidden ECHO benchmark."""
    resolved_seed = resolve_seed(seed)
    config = GameConfig(seed=resolved_seed, use_color=use_color, debug=debug)
    try:
        scenario = generate_scenario(config)
    except Exception as exc:  # pragma: no cover - defensive CLI path
        renderer.print(f"Scenario generation failed: {exc}")
        if debug:
            raise
        return

    # Both states start from identical deep copies of the scenario. The player
    # mutates one through daily decisions; ECHO mutates the other silently.
    player_state = initialize_state(scenario, config.shifts_per_day)
    automated_state = initialize_state(scenario, config.shifts_per_day)
    manual_scheduler = ManualScheduler()
    automated_scheduler = AutomatedScheduler()

    renderer.render_start(player_state)
    if debug:
        renderer.render_debug(player_state)

    while player_state.current_shift < player_state.deadline_shift and not player_state.final_item_completed:
        player_state.daily_notes.clear()
        renderer.render_overview(player_state)
        keep_going = inspection_menu(renderer, player_state)
        if not keep_going:
            renderer.print("Run ended without saving.")
            return

        # Daily cards are the only intentional manual intervention point before
        # the manual scheduler advances the queued work for the day.
        cards = generate_decision_cards(player_state, player_state.current_day, config)
        for card in cards:
            renderer.render_decision_card(card)
            selected = ask_number("Select response", 1, len(card.choices), allow_quit=True)
            if selected is None:
                renderer.print("Run ended without saving.")
                return
            note = apply_choice(player_state, card, card.choices[selected - 1])
            renderer.render_choice_confirmation(note)

        player_result = advance_day(player_state, manual_scheduler)
        # ECHO receives no player choices, but it does see the same generated
        # warnings and disruptions while it plans each day.
        advance_day(automated_state, automated_scheduler)
        renderer.render_day_summary(player_result, player_state)

        if player_state.final_item_completed or player_state.current_shift >= player_state.deadline_shift:
            break
        if not end_day_menu(renderer):
            renderer.print("Run ended without saving.")
            return

    _finish_automated_run(automated_state, automated_scheduler)
    renderer.render_final_reveal(player_state, automated_state, resolved_seed)


def _finish_automated_run(state, scheduler: AutomatedScheduler) -> None:
    """Fast-forward the benchmark after the player run ends."""
    while state.current_shift < state.deadline_shift and not state.final_item_completed:
        state.daily_notes.clear()
        advance_day(state, scheduler)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nRun interrupted.")
        sys.exit(130)
