"""Small terminal input helpers for menu-style prompts."""

from __future__ import annotations


def ask_number(prompt: str, minimum: int, maximum: int, allow_quit: bool = False) -> int | None:
    """Prompt until the user enters a number in range or quits/EOFs."""
    while True:
        suffix = f" [{minimum}-{maximum}]"
        if allow_quit:
            suffix += " or q"
        try:
            raw = input(f"{prompt}{suffix}: ").strip().lower()
        except EOFError:
            return None
        if allow_quit and raw in {"q", "quit", "exit"}:
            return None
        try:
            value = int(raw)
        except ValueError:
            print("Enter a number from the menu.")
            continue
        if minimum <= value <= maximum:
            return value
        print(f"Enter a number between {minimum} and {maximum}.")


def ask_optional_seed(prompt: str = "Seed") -> int | None:
    """Prompt for an integer seed, returning None for a random seed."""
    while True:
        try:
            raw = input(f"{prompt} (blank for random): ").strip()
        except EOFError:
            return None
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            print("Seed must be an integer.")


def pause(prompt: str = "Press Enter to continue") -> bool:
    """Wait for Enter and return False when the user quits or input ends."""
    try:
        raw = input(f"{prompt} ").strip().lower()
    except EOFError:
        return False
    return raw not in {"q", "quit", "exit"}
