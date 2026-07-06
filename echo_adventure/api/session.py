"""Thread-safe game session ownership for the browser UI."""

from __future__ import annotations

import threading
from typing import Any

from ..config import GameConfig, resolve_seed
from ..decisions import (
    active_decision_cards,
    apply_choice as apply_decision_choice,
    decision_progress,
)
from ..echo import apply_echo_decisions_for_day, select_echo_choice_for_state
from ..metrics import calculate_snapshot, update_state_metrics
from ..models import DecisionCard, MetricSnapshot
from ..scenario_generator import generate_scenario
from ..schedulers.automated import AutomatedScheduler
from ..schedulers.manual import ManualScheduler
from ..simulation import (
    DayResult,
    advance_day as simulate_day,
    advance_shift as simulate_shift,
    initialize_state,
    prepare_day,
)
from .payloads import PayloadMixin
from .review import ReviewMixin


# GameSession is the stateful bridge between stateless HTTP requests and the
# mutable simulation engine. One process hosts one active session at a time.
class GameSession(PayloadMixin, ReviewMixin):
    """Owns one playable browser run and its hidden automated benchmark run.

    The browser server is threaded, so every public mutation/read takes the
    session lock. The player and automated states are initialized from the same
    scenario so the final reveal compares scheduling policy, not scenario luck.
    """

    def __init__(
        self,
        seed: int | None = None,
    ) -> None:
        # RLock allows helper methods called inside locked public methods to
        # safely reuse the same lock if the implementation grows later.
        self.lock = threading.RLock()
        # Resolve random seeds immediately so the UI can always display and
        # replay the exact generated scenario.
        self.seed = resolve_seed(seed)
        self.config = GameConfig.for_preset("normal", seed=self.seed)
        # Both schedulers share a scenario but mutate independent state copies.
        self.scenario = generate_scenario(self.config)
        self.player_state = initialize_state(self.scenario, self.config.shifts_per_day)
        self.automated_state = initialize_state(self.scenario, self.config.shifts_per_day)
        # Manual scheduler reflects player-driven priorities; automated is the
        # hidden ECHO benchmark revealed at the end.
        self.manual_scheduler = ManualScheduler()
        self.automated_scheduler = AutomatedScheduler()
        # Cards/choices are tracked at the session layer because they are a UI
        # interaction contract layered over the underlying simulation state.
        self.current_cards: list[DecisionCard] = []
        self.applied_choices: dict[str, str] = {}
        self.echo_completed_days: set[int] = set()
        self.choice_notes: list[str] = []
        self.last_result: DayResult | None = None
        self.last_summary_past_due_jobs: list[dict[str, Any]] | None = None
        self.last_summary_puzzle: dict[str, Any] | None = None
        self.day_start_snapshot: MetricSnapshot | None = None
        self.day_completed_before: set[str] = set()
        self.day_notes_start: int = 0
        self.day_start_shift: int | None = None
        self._ensure_cards()

    def apply_choice(self, card_id: str, choice_id: str) -> dict[str, Any]:
        """Apply one response to one active decision card."""
        with self.lock:
            # Guard all invalid interaction states server-side. The browser also
            # disables buttons, but the server is the rule authority.
            if self._game_over():
                raise ValueError("The run has already ended.")
            self._ensure_cards()
            card = next((candidate for candidate in self.current_cards if candidate.id == card_id), None)
            if not card:
                raise ValueError("Decision card is no longer active.")
            if card.id in self.applied_choices:
                raise ValueError("That decision already has a selected response.")
            choice = next((candidate for candidate in card.choices if candidate.id == choice_id), None)
            if not choice:
                raise ValueError("Choice is not valid for that decision.")
            # Decision effects can mutate current queues and future event
            # chains. The returned note is the human-readable audit trail.
            echo_choice = select_echo_choice_for_state(
                self.player_state,
                card,
                self.config,
                self.player_state.decision_cards,
            )
            notes_before = len(self.player_state.daily_notes)
            note = apply_decision_choice(self.player_state, card, choice, actor="player", echo_choice=echo_choice)
            if self.day_start_snapshot is not None:
                del self.player_state.daily_notes[notes_before:]
            self.applied_choices[card.id] = choice.id
            comparison = "Matched ECHO." if choice.id == echo_choice.id else f"ECHO would choose {echo_choice.label}."
            self.choice_notes.append(f"{card.title}: {choice.label}. {comparison} {note}")
            self._ensure_cards()
            return {"note": note, "allDecisionsMade": self.ready_to_advance()}

    def advance_shift(self) -> dict[str, Any]:
        """Advance the player simulation by one in-game shift."""
        with self.lock:
            if self._game_over():
                self._finish_automated()
                return {"summary": self._summary_payload(), "gameOver": True}
            self._ensure_cards()
            self._advance_player_shift()
            day_complete = self._player_day_complete()
            if day_complete:
                self._complete_player_day()
            else:
                self._ensure_cards()
            return {
                "summary": self._summary_payload(),
                "gameOver": self._game_over(),
                "dayComplete": day_complete,
                "shift": self.player_state.current_shift,
            }

    def advance_day(self) -> dict[str, Any]:
        """Advance both player and benchmark simulations through the current day."""
        with self.lock:
            if self._game_over():
                self._finish_automated()
                return {"summary": self._summary_payload(), "gameOver": True}
            self._ensure_cards()
            if not self.ready_to_advance():
                raise ValueError("Select a response for all decisions before advancing the day.")
            while not self._game_over():
                self._advance_player_shift()
                if self._player_day_complete():
                    break
            self._complete_player_day()
            return {"summary": self._summary_payload(), "gameOver": self._game_over()}

    def _advance_player_shift(self) -> None:
        """Run one shift for the player, preparing the day on the first shift."""
        if self._game_over():
            return
        self._begin_player_day_if_needed()
        if self._player_day_complete():
            return
        simulate_shift(self.player_state, self.manual_scheduler)

    def _begin_player_day_if_needed(self) -> None:
        """Prepare day-level scheduling state before the first shift runs."""
        if self.day_start_snapshot is not None:
            return
        # Daily notes are scoped to simulated shift activity. Choice notes are
        # kept separately until the day is committed, then reset with cards.
        self.player_state.daily_notes.clear()
        self.day_completed_before = set(self.player_state.completed_jobs)
        self.day_notes_start = 0
        self.day_start_shift = self.player_state.current_shift
        self.day_start_snapshot = prepare_day(self.player_state, self.manual_scheduler)

    def _player_day_complete(self) -> bool:
        """Return whether the in-progress player day has finished."""
        if self.day_start_snapshot is None or self.day_start_shift is None:
            return False
        return (
            self.player_state.final_item_completed
            or self.player_state.current_shift >= self.player_state.deadline_shift
            or self.player_state.current_shift - self.day_start_shift >= self.player_state.shifts_per_day
        )

    def _complete_player_day(self) -> None:
        """Finalize the current player day and advance the hidden benchmark."""
        if self.day_start_snapshot is None:
            return
        update_state_metrics(self.player_state)
        end_snapshot = calculate_snapshot(self.player_state)
        self.player_state.metric_history.append(end_snapshot)
        completed_today = sorted(self.player_state.completed_jobs - self.day_completed_before)
        notes = self.player_state.daily_notes[self.day_notes_start:]
        self.last_result = DayResult(
            completed_job_ids=completed_today,
            notes=notes,
            start_snapshot=self.day_start_snapshot,
            end_snapshot=end_snapshot,
        )
        self.last_summary_past_due_jobs = self._past_due_jobs_payload()
        self.last_summary_puzzle = self._build_summary_puzzle_payload()
        self._clear_day_progress()
        # The automated scheduler advances silently alongside the player so
        # it faces the same random event timeline.
        apply_echo_decisions_for_day(self.automated_state, self.config, self.echo_completed_days)
        simulate_day(self.automated_state, self.automated_scheduler)
        # A new day means fresh decision cards and no selected choices.
        self.current_cards = []
        self.applied_choices = {}
        self.choice_notes = []
        if self._game_over():
            self._finish_automated()
        else:
            self._ensure_cards()

    def _clear_day_progress(self) -> None:
        """Reset in-progress day bookkeeping after a day summary is built."""
        self.day_start_snapshot = None
        self.day_completed_before = set()
        self.day_notes_start = 0
        self.day_start_shift = None

    def ready_to_advance(self) -> bool:
        """Return whether every current daily decision has a selected choice."""
        self._ensure_cards()
        progress = decision_progress(self.player_state, self.player_state.current_day, self.applied_choices)
        return progress.total_questions == 0 or progress.answered_questions == progress.total_questions

    def _ensure_cards(self) -> None:
        if self._game_over():
            self.current_cards = []
            return
        # Cards are resolved from the prepared daily choices so a selected
        # answer can determine the next question without generating new cards.
        self.current_cards = active_decision_cards(
            self.player_state,
            self.player_state.current_day,
            self.applied_choices,
        )

    def _game_over(self) -> bool:
        """The run ends at project completion or the configured deadline."""
        return self.player_state.final_item_completed or self.player_state.current_shift >= self.player_state.deadline_shift

    def _finish_automated(self) -> None:
        # The benchmark is hidden during play. At game over, fast-forward it
        # through the same deadline so the reveal has a complete comparison.
        while (
            self.automated_state.current_shift < self.automated_state.deadline_shift
            and not self.automated_state.final_item_completed
        ):
            self.automated_state.daily_notes.clear()
            apply_echo_decisions_for_day(self.automated_state, self.config, self.echo_completed_days)
            simulate_day(self.automated_state, self.automated_scheduler)


class SessionStore:
    """Thread-safe owner for the one active browser game session."""

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
            result = self.session.apply_choice(card_id, choice_id)
            state = self.session.state_payload()
            state["action"] = result
            return state

    def shift_payload(self) -> dict[str, Any]:
        with self.lock:
            result = self.session.advance_shift()
            state = self.session.state_payload()
            state["shiftAdvance"] = result
            return state

    def advance_payload(self) -> dict[str, Any]:
        with self.lock:
            result = self.session.advance_day()
            state = self.session.state_payload()
            state["advance"] = result
            return state
