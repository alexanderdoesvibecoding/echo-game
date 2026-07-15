"""Thread-safe ownership of the player and ECHO runs."""

from __future__ import annotations

import threading
from typing import Any

from ..config import GameConfig, resolve_seed
from ..decision_web import DecisionWebTransition, generate_decision_web
from ..decisions import apply_choice as apply_decision_choice
from ..decisions import generate_daily_decision_cards
from ..echo import run_omniscient_echo
from ..models import DecisionCard, DecisionProgress
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
        self.decision_web = generate_decision_web(self.scenario, self.config)
        self.player_state = initialize_state(self.scenario)
        self.automated_state = initialize_state(self.scenario)
        self.automated_state.is_echo_benchmark = True
        self.player_node_id = self.decision_web.root_node_id
        self.pending_player_transition: DecisionWebTransition | None = None
        self.player_in_overtime = False
        self.overtime_cards: list[DecisionCard] = []
        self.overtime_card_index = 0
        self.overtime_ready_to_advance = False
        self.questions_answered_today = 0
        self.decision_total_today = self.decision_web.question_count(1)
        self.current_cards: list[DecisionCard] = []
        self.applied_choices: dict[str, str] = {}
        self.choice_notes: list[str] = []
        self.last_result: DayResult | None = None
        self.last_summary_puzzle: dict[str, Any] | None = None
        self.day_completed_before: set[str] = set(self.player_state.completed_jobs)
        run_omniscient_echo(self.automated_state, self.decision_web)
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
            note = apply_decision_choice(
                self.player_state,
                card,
                choice,
                actor="player",
                schedule_follow_ups=self.player_in_overtime,
            )
            self.applied_choices[card.id] = choice.id
            self.choice_notes.append(f"{card.title}: {choice.label}. {note}")
            self.questions_answered_today += 1
            self.current_cards = []
            if self.player_in_overtime:
                self.overtime_card_index += 1
                if self.overtime_card_index < len(self.overtime_cards):
                    self.current_cards = [self.overtime_cards[self.overtime_card_index]]
                else:
                    self.overtime_ready_to_advance = True
                return {"note": note, "allDecisionsMade": self.ready_to_advance()}

            transition = self.decision_web.transition(self.player_node_id, choice.id)
            if transition.advances_day:
                self.pending_player_transition = transition
            else:
                if transition.next_node_id is None:
                    raise RuntimeError("A non-daily web edge cannot be terminal.")
                self.player_node_id = transition.next_node_id
                self._ensure_cards()
            return {"note": note, "allDecisionsMade": self.ready_to_advance()}

    def advance_day(self) -> dict[str, Any]:
        with self.lock:
            if self._game_over():
                self._finish_automated()
                return {"summary": self._summary_payload(), "gameOver": True}
            if not self.ready_to_advance():
                raise ValueError("Select a response for all decisions before advancing the day.")
            if self.player_in_overtime:
                self._record_player_day()
                self._reset_daily_choices()
                if self._game_over():
                    self._finish_automated()
                else:
                    self._start_overtime_day()
                return {"summary": self._summary_payload(), "gameOver": self._game_over()}

            transition = self.pending_player_transition
            if transition is None:
                raise RuntimeError("The completed question sequence has no daily web transition.")
            self._record_player_day()
            self._reset_daily_choices()
            self.pending_player_transition = None
            if transition.next_node_id is not None:
                self.player_node_id = transition.next_node_id
                self.decision_web.assert_runtime_matches(self.player_state, self.player_node_id)
            elif transition.enters_overtime and not self._game_over():
                self.player_in_overtime = True
            if self._game_over():
                self._finish_automated()
            elif self.player_in_overtime:
                self._start_overtime_day()
            else:
                self.questions_answered_today = 0
                self.decision_total_today = self.decision_web.question_count(
                    self.player_state.current_day
                )
                self._ensure_cards()
            return {"summary": self._summary_payload(), "gameOver": self._game_over()}

    def ready_to_advance(self) -> bool:
        if self.player_in_overtime:
            return (
                self.questions_answered_today == self.decision_total_today
                and self.overtime_ready_to_advance
            )
        return (
            self.questions_answered_today == self.decision_total_today
            and self.pending_player_transition is not None
        )

    def current_decision_progress(self) -> DecisionProgress:
        return DecisionProgress(
            day=self.player_state.current_day,
            total_questions=self.decision_total_today,
            answered_questions=self.questions_answered_today,
            open_card_ids=[card.id for card in self.current_cards],
        )

    def _ensure_cards(self) -> None:
        if self._game_over():
            self.current_cards = []
        elif self.player_in_overtime:
            if self.overtime_cards and not self.overtime_ready_to_advance:
                self.current_cards = [self.overtime_cards[self.overtime_card_index]]
        elif self.pending_player_transition is not None:
            self.current_cards = []
        elif not self.current_cards:
            self.decision_web.assert_runtime_matches(self.player_state, self.player_node_id)
            card = self.decision_web.node(self.player_node_id).card
            self.player_state.decision_cards[card.id] = card
            self.current_cards = [card]

    def _record_player_day(self) -> None:
        self.last_result = simulate_day(self.player_state)
        self.last_result.completed_job_ids = sorted(
            self.player_state.completed_jobs - self.day_completed_before
        )
        self.last_summary_puzzle = self._build_puzzle_payload(
            day=self.last_result.day,
            completed_before=self.day_completed_before,
        )
        self.day_completed_before = set(self.player_state.completed_jobs)

    def _reset_daily_choices(self) -> None:
        self.current_cards = []
        self.applied_choices = {}
        self.choice_notes = []

    def _start_overtime_day(self) -> None:
        self.overtime_cards = generate_daily_decision_cards(self.player_state, self.config)
        if not self.overtime_cards:
            raise RuntimeError("Decision generation produced no questions for unfinished work.")
        self.overtime_card_index = 0
        self.overtime_ready_to_advance = False
        self.questions_answered_today = 0
        self.decision_total_today = len(self.overtime_cards)
        self.current_cards = [self.overtime_cards[0]]

    def _game_over(self) -> bool:
        return self.player_state.final_item_completed

    def _finish_automated(self) -> None:
        if not self.automated_state.final_item_completed:
            raise RuntimeError("ECHO's startup-solved web traversal did not complete.")


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
