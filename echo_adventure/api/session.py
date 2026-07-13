"""Thread-safe ownership of the player and ECHO runs."""

from __future__ import annotations

import threading
from typing import Any

from ..config import GameConfig, resolve_seed
from ..decisions import apply_choice as apply_decision_choice
from ..decisions import decision_progress, generate_daily_decision_cards
from ..echo import advance_echo_day
from ..models import DecisionCard
from ..scenario_generator import generate_scenario
from ..simulation import DayResult, advance_day as simulate_day, initialize_state
from .payloads import PayloadMixin
from .review import ReviewMixin


class GameSession(PayloadMixin, ReviewMixin):
    def __init__(self, seed: int | None = None) -> None:
        self.lock = threading.RLock()
        self.seed = resolve_seed(seed)
        self.config = GameConfig.for_preset("normal", seed=self.seed)
        self.scenario = generate_scenario(self.config)
        self.player_state = initialize_state(self.scenario)
        self.automated_state = initialize_state(self.scenario)
        self.automated_state.is_echo_benchmark = True
        self.current_cards: list[DecisionCard] = []
        self.applied_choices: dict[str, str] = {}
        self.choice_notes: list[str] = []
        self.last_result: DayResult | None = None
        self.last_summary_puzzle: dict[str, Any] | None = None
        self.day_completed_before: set[str] = set(self.player_state.completed_jobs)
        self._ensure_cards()

    def apply_choice(self, card_id: str, choice_id: str) -> dict[str, Any]:
        with self.lock:
            if self._game_over():
                raise ValueError("The run has already ended.")
            self._ensure_cards()
            card = next((item for item in self.current_cards if item.id == card_id), None)
            if not card:
                raise ValueError("Decision card is no longer active.")
            if card.id in self.applied_choices:
                raise ValueError("That decision already has a selected response.")
            choice = next((item for item in card.choices if item.id == choice_id), None)
            if not choice:
                raise ValueError("Choice is not valid for that decision.")
            note = apply_decision_choice(self.player_state, card, choice, actor="player")
            self.applied_choices[card.id] = choice.id
            self.choice_notes.append(f"{card.title}: {choice.label}. {note}")
            if self._game_over():
                self._finish_automated()
            return {"note": note, "allDecisionsMade": self.ready_to_advance()}

    def advance_day(self) -> dict[str, Any]:
        with self.lock:
            if self._game_over():
                self._finish_automated()
                return {"summary": self._summary_payload(), "gameOver": True}
            if not self.ready_to_advance():
                raise ValueError("Select a response for all decisions before advancing the day.")
            self.last_result = simulate_day(self.player_state)
            self.last_result.completed_job_ids = sorted(
                self.player_state.completed_jobs - self.day_completed_before
            )
            self.last_result.notes = [*self.choice_notes, *self.last_result.notes]
            self.last_summary_puzzle = self._build_puzzle_payload(
                day=self.last_result.day,
                completed_before=self.day_completed_before,
            )
            advance_echo_day(self.automated_state, self.config)
            self.current_cards = []
            self.applied_choices = {}
            self.choice_notes = []
            self.day_completed_before = set(self.player_state.completed_jobs)
            if self._game_over():
                self._finish_automated()
            else:
                self._ensure_cards()
            return {"summary": self._summary_payload(), "gameOver": self._game_over()}

    def ready_to_advance(self) -> bool:
        progress = decision_progress(self.current_cards, self.applied_choices, self.player_state.current_day)
        return progress.answered_questions == progress.total_questions

    def _ensure_cards(self) -> None:
        if self._game_over():
            self.current_cards = []
        elif not self.current_cards:
            self.current_cards = generate_daily_decision_cards(self.player_state, self.config)

    def _game_over(self) -> bool:
        return self.player_state.final_item_completed

    def _finish_automated(self) -> None:
        # ECHO always chooses the lowest-impact answer, so this converges well
        # before the guard. The guard prevents a malformed future question bank
        # from hanging a local request forever.
        for _ in range(365):
            if self.automated_state.final_item_completed:
                return
            advance_echo_day(self.automated_state, self.config)
        raise RuntimeError("ECHO did not complete within 365 game days.")


class SessionStore:
    def __init__(self, seed: int | None = None) -> None:
        self.lock = threading.RLock()
        self.session = GameSession(seed=seed)

    def state_payload(self) -> dict[str, Any]:
        with self.lock:
            return self.session.state_payload()

    def new_session_payload(self, seed: int | None = None) -> dict[str, Any]:
        with self.lock:
            self.session = GameSession(seed=seed)
            return self.session.state_payload()

    def choice_payload(self, card_id: str, choice_id: str) -> dict[str, Any]:
        with self.lock:
            action = self.session.apply_choice(card_id, choice_id)
            payload = self.session.state_payload()
            payload["action"] = action
            return payload

    def advance_payload(self) -> dict[str, Any]:
        with self.lock:
            action = self.session.advance_day()
            payload = self.session.state_payload()
            payload["advance"] = action
            return payload
