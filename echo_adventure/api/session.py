"""Thread-safe ownership of the player and ECHO runs."""

from __future__ import annotations

import threading
from typing import Any

from ..config import GameConfig, resolve_seed
from ..decision_web import DecisionWebTransition, generate_decision_web
from ..decisions import apply_choice as apply_decision_choice
from ..decisions import generate_daily_decision_cards
from ..echo import advance_omniscient_day, apply_omniscient_choice
from ..models import DecisionCard
from ..scenario_generator import generate_scenario
from ..simulation import DayResult, advance_day as simulate_day, initialize_state
from .payloads import PayloadMixin
from .review import ReviewMixin


class GameSession(PayloadMixin, ReviewMixin):
    def __init__(self, seed: int | None = None) -> None:
        self.lock = threading.RLock()
        self.seed = resolve_seed(seed)
        self.config = GameConfig(seed=self.seed)
        self.scenario = generate_scenario(self.config)
        self.decision_web = generate_decision_web(self.scenario, self.config)
        self.player_state = initialize_state(self.scenario)
        self.automated_state = initialize_state(self.scenario)
        self.player_node_id = self.decision_web.root_node_id
        self.pending_player_transition: DecisionWebTransition | None = None
        self.echo_node_id: str | None = self.decision_web.root_node_id
        self.pending_echo_transition: DecisionWebTransition | None = None
        self.echo_choices_applied_today = 0
        self.player_in_overtime = False
        self.overtime_cards: list[DecisionCard] = []
        self.overtime_card_index = 0
        self.overtime_ready_to_advance = False
        self.questions_answered_today = 0
        self.decision_total_today = self.decision_web.question_count(1)
        self.current_cards: list[DecisionCard] = []
        self.last_result: DayResult | None = None
        self.last_summary_puzzle: dict[str, Any] | None = None
        self.last_summary_remaining_jobs: list[dict[str, Any]] = []
        self.day_completed_before: set[str] = set(self.player_state.completed_jobs)
        self._ensure_cards()

    def apply_choice(self, card_id: str, choice_id: str) -> None:
        with self.lock:
            if self._game_over():
                raise ValueError("The run has already ended.")
            self._ensure_cards()
            card = next((item for item in self.current_cards if item.id == card_id), None)
            if not card:
                raise ValueError("Decision card is no longer active.")
            choice = next((item for item in card.choices if item.id == choice_id), None)
            if not choice:
                raise ValueError("Choice is not valid for that decision.")
            apply_decision_choice(
                self.player_state,
                card,
                choice,
                actor="player",
                schedule_follow_ups=self.player_in_overtime,
            )
            self.questions_answered_today += 1
            self._apply_echo_choice(self.questions_answered_today)
            self.current_cards = []
            if self._game_over():
                self._finish_automated()
                return
            if self.player_in_overtime:
                self.overtime_card_index += 1
                if self.overtime_card_index < len(self.overtime_cards):
                    self.current_cards = [self.overtime_cards[self.overtime_card_index]]
                else:
                    self.overtime_ready_to_advance = True
                return

            transition = self.decision_web.transition(self.player_node_id, choice.id)
            if transition.advances_day:
                self.pending_player_transition = transition
            else:
                if transition.next_node_id is None:
                    raise RuntimeError("A non-daily web edge cannot be terminal.")
                self.player_node_id = transition.next_node_id
                self._ensure_cards()

    def advance_day(self) -> None:
        with self.lock:
            if self._game_over():
                self._finish_automated()
                return
            if not self.ready_to_advance():
                raise ValueError("Select a response for all decisions before advancing the day.")
            if self.player_in_overtime:
                self._record_player_day()
                self._advance_echo_day()
                self._reset_daily_choices()
                if self._game_over():
                    self._finish_automated()
                else:
                    self._start_overtime_day()
                return

            transition = self.pending_player_transition
            if transition is None:
                raise RuntimeError("The completed question sequence has no daily web transition.")
            self._record_player_day()
            self._advance_echo_day()
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
            completed_before=self.day_completed_before,
        )
        self.last_summary_remaining_jobs = self._build_remaining_jobs_payload()
        self.day_completed_before = set(self.player_state.completed_jobs)

    def _apply_echo_choice(self, player_slot: int) -> None:
        """Apply ECHO's independent optimal answer for the matching daily slot."""
        if self.automated_state.final_item_completed:
            return
        expected_slot = self.echo_choices_applied_today + 1
        if player_slot != expected_slot:
            raise RuntimeError(
                f"ECHO decision slot mismatch: expected {expected_slot}, received {player_slot}."
            )
        if self.pending_echo_transition is not None or self.echo_node_id is None:
            raise RuntimeError("ECHO has no unapplied decision for this daily slot.")

        transition = apply_omniscient_choice(
            self.automated_state,
            self.decision_web,
            self.echo_node_id,
        )
        self.echo_choices_applied_today += 1
        if transition.advances_day:
            self.pending_echo_transition = transition
            self.echo_node_id = None
        else:
            if transition.next_node_id is None:
                raise RuntimeError("ECHO's non-daily transition has no successor.")
            self.echo_node_id = transition.next_node_id

    def _advance_echo_day(self) -> None:
        """Perform ECHO's remaining once-per-day work without replaying choices."""
        if self.automated_state.final_item_completed:
            return
        if self.echo_choices_applied_today != self.decision_total_today:
            raise RuntimeError("ECHO has not applied every expected decision for the day.")
        transition = self.pending_echo_transition
        if transition is None:
            raise RuntimeError("ECHO's completed question sequence has no daily transition.")

        self.echo_node_id = advance_omniscient_day(self.automated_state, transition)
        self.pending_echo_transition = None
        self.echo_choices_applied_today = 0

    def _reset_daily_choices(self) -> None:
        self.current_cards = []

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
        """Finish ECHO's solved route when the player completes during a question."""
        while not self.automated_state.final_item_completed:
            if self.pending_echo_transition is not None:
                transition = self.pending_echo_transition
                self.echo_node_id = advance_omniscient_day(
                    self.automated_state,
                    transition,
                )
                self.pending_echo_transition = None
                self.echo_choices_applied_today = 0
                continue
            if self.echo_node_id is None:
                raise RuntimeError("ECHO's solved route ended before completing every job.")
            transition = apply_omniscient_choice(
                self.automated_state,
                self.decision_web,
                self.echo_node_id,
            )
            self.echo_choices_applied_today += 1
            if transition.advances_day:
                self.pending_echo_transition = transition
                self.echo_node_id = None
            else:
                if transition.next_node_id is None:
                    raise RuntimeError("ECHO's non-daily transition has no successor.")
                self.echo_node_id = transition.next_node_id


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
            self.session.apply_choice(card_id, choice_id)
            return self.session.state_payload()

    def advance_payload(self) -> dict[str, Any]:
        with self.lock:
            self.session.advance_day()
            return self.session.state_payload()
