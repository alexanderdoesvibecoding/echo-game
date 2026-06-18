from __future__ import annotations

from .input import ask_number, ask_optional_seed, pause
from .renderer import GameRenderer
from ..models import SimulationState


def main_menu(renderer: GameRenderer) -> int | None:
    renderer.render_main_menu()
    return ask_number("Choose", 1, 3)


def seed_prompt() -> int | None:
    return ask_optional_seed()


def inspection_menu(renderer: GameRenderer, state: SimulationState) -> bool:
    while True:
        renderer.render_schedule_board(state)
        renderer.print("\nInspect before decisions:")
        renderer.print("1. Overview")
        renderer.print("2. Shop status")
        renderer.print("3. Workcenter queues")
        renderer.print("4. Puzzle piece progress")
        renderer.print("5. Critical path")
        renderer.print("6. Risk register")
        renderer.print("7. Continue to decisions")
        renderer.print("0. Quit current run")
        choice = ask_number("Choose", 0, 7)
        if choice is None or choice == 0:
            return False
        if choice == 1:
            renderer.render_overview(state)
            pause()
        elif choice == 2:
            renderer.render_shop_status(state)
            pause()
        elif choice == 3:
            shop_id = choose_shop(renderer, state)
            if shop_id:
                renderer.render_workcenter_queues(state, shop_id)
                pause()
        elif choice == 4:
            renderer.render_piece_progress(state)
            pause()
        elif choice == 5:
            renderer.render_critical_path(state)
            pause()
        elif choice == 6:
            renderer.render_risk_register(state)
            pause()
        elif choice == 7:
            return True


def choose_shop(renderer: GameRenderer, state: SimulationState) -> str | None:
    renderer.print("\nSelect a shop:")
    shops = list(state.shops.values())
    for index, shop in enumerate(shops, start=1):
        renderer.print(f"{index}. {shop.name}")
    choice = ask_number("Shop", 1, len(shops), allow_quit=True)
    if choice is None:
        return None
    return shops[choice - 1].id


def end_day_menu(renderer: GameRenderer) -> bool:
    renderer.print("\n1. Continue to next day")
    renderer.print("2. Quit current run")
    choice = ask_number("Choose", 1, 2)
    return choice == 1
