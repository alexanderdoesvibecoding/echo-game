from __future__ import annotations

import unittest
from unittest.mock import patch

from echo_adventure.api.session import GameSession
from echo_adventure.config import GameConfig
from echo_adventure.decisions.definitions import DEFINITIONS_BY_ID
from echo_adventure.echo import apply_echo_decisions_for_day
from echo_adventure.metrics import (
    ECHO_MASTERY_BONUS,
    calculate_completion_bonus,
    calculate_echo_mastery_bonus,
    calculate_final_score,
)
from echo_adventure.models import DecisionRecord
from echo_adventure.scenario_generator import generate_scenario

from .helpers import make_card, make_state, unit_config


class ScoreScaleTests(unittest.TestCase):
    def test_all_named_choices_use_human_scale_points(self):
        scores = [
            choice.score_delta
            for definition in DEFINITIONS_BY_ID.values()
            for choice in definition.choices
        ]

        self.assertGreaterEqual(min(scores), -2.0)
        self.assertLessEqual(max(scores), 3.0)
        self.assertNotIn(-193.8, scores)

        reset = next(
            choice
            for choice in DEFINITIONS_BY_ID["cleanliness-breach"].choices
            if choice.label == "Full reset"
        )
        self.assertGreater(reset.score_delta, -2.0)

    def test_echo_temporary_loss_has_a_larger_realized_payoff(self):
        take_advice = next(
            choice
            for choice in DEFINITIONS_BY_ID["echo-recommendation"].choices
            if choice.label == "Take advice"
        )
        payoff = next(
            choice
            for choice in DEFINITIONS_BY_ID["echo-slack-pocket-found"].choices
            if choice.label == "Trust the full reshuffle"
        )

        self.assertLess(take_advice.score_delta, 0)
        self.assertGreater(payoff.score_delta, abs(take_advice.score_delta))
        self.assertGreater(take_advice.score_delta + payoff.score_delta, 0)

    def test_score_starts_at_zero_and_rewards_early_completion(self):
        state = make_state()

        self.assertEqual(calculate_final_score(state), 0.0)

        state.decision_path_score_delta = 2.0
        state.final_item_completed = True
        state.completion_shift = 6

        self.assertGreater(calculate_completion_bonus(state), 0.0)
        self.assertEqual(
            calculate_final_score(state),
            round(2.0 + calculate_completion_bonus(state), 2),
        )

        state.is_echo_benchmark = True
        self.assertEqual(calculate_echo_mastery_bonus(state), ECHO_MASTERY_BONUS)
        self.assertEqual(
            calculate_final_score(state),
            round(2.0 + calculate_completion_bonus(state) + ECHO_MASTERY_BONUS, 2),
        )


class EchoCompletionTests(unittest.TestCase):
    def test_echo_outscores_greedy_player_on_balance_regression_seeds(self):
        for seed in (1, 20, 47):
            with self.subTest(seed=seed):
                session = GameSession(seed=seed)
                while not session._game_over():
                    session._ensure_cards()
                    while not session.ready_to_advance():
                        card = next(
                            card
                            for card in session.current_cards
                            if card.id not in session.applied_choices
                        )
                        greedy_choice = max(
                            card.choices,
                            key=lambda choice: (choice.score_delta, choice.id),
                        )
                        session.apply_choice(card.id, greedy_choice.id)
                    session.advance_day()

                reveal = session.state_payload()["finalReveal"]

                self.assertGreater(
                    reveal["automated"]["finalScore"],
                    reveal["player"]["finalScore"],
                )
                self.assertTrue(session.automated_state.final_item_completed)
                self.assertFalse(
                    any(
                        record.shift is not None
                        and record.shift > session.automated_state.completion_shift
                        for record in session.automated_state.decision_history
                    )
                )

    def test_echo_stops_answering_remaining_cards_as_soon_as_it_finishes(self):
        state = make_state()
        config = unit_config(max_active_decision_cards_per_day=3)
        cards = [make_card(f"CARD-{index}") for index in range(3)]
        state.decision_cards = {card.id: card for card in cards}
        state.campaign_decision_graph.cards_by_day = {state.current_day: [card.id for card in cards]}
        state.campaign_decision_graph.max_active_cards_per_day = 3
        calls = []

        def finish_on_first_choice(target_state, card, choice, **_kwargs):
            calls.append(card.id)
            target_state.final_item_completed = True
            target_state.completion_shift = target_state.current_shift

        with patch("echo_adventure.echo.apply_choice", side_effect=finish_on_first_choice), patch(
            "echo_adventure.echo.select_echo_choice_for_state",
            side_effect=lambda _state, card, *_args: card.choices[0],
        ):
            applied = apply_echo_decisions_for_day(state, config, set())

        self.assertEqual(applied, 1)
        self.assertEqual(calls, [cards[0].id])

    def test_final_timeline_does_not_move_echo_answers_past_completion(self):
        session = GameSession(seed=123)
        player_card = session.current_cards[0]
        player_choice = player_card.choices[0]
        session.player_state.decision_history.append(
            DecisionRecord(
                day=2,
                card_id=player_card.id,
                card_title=player_card.title,
                actor="player",
                choice_id=player_choice.id,
                choice_label=player_choice.label,
                echo_choice_id=None,
                echo_choice_label=None,
                aligned_with_echo=False,
                note="player",
                score_delta=player_choice.score_delta,
                shift=4,
            )
        )
        session.automated_state.final_item_completed = True
        session.automated_state.completion_shift = 3
        session.automated_state.decision_history.append(
            DecisionRecord(
                day=2,
                card_id=player_card.id,
                card_title=player_card.title,
                actor="ECHO",
                choice_id=player_choice.id,
                choice_label=player_choice.label,
                echo_choice_id=player_choice.id,
                echo_choice_label=player_choice.label,
                aligned_with_echo=True,
                note="stale",
                score_delta=player_choice.score_delta,
                shift=4,
            )
        )

        day_two = [point for point in session._decision_chart_payload() if point["day"] == 2]

        self.assertTrue(day_two)
        self.assertTrue(all(point["echoQuestionId"] is None for point in day_two))


class ScenarioFeasibilityTests(unittest.TestCase):
    def test_generated_required_work_has_qualified_workers_and_enough_stock(self):
        scenario = generate_scenario(GameConfig.for_preset("normal", seed=123))
        demand: dict[str, int] = {}

        for job in scenario.jobs.values():
            self.assertIn(job.required_capability, scenario.workers[job.worker_id].skills)
            demand[job.material_id] = demand.get(job.material_id, 0) + 1

        for material_id, quantity in demand.items():
            self.assertGreaterEqual(scenario.material_stocks[material_id].quantity, quantity)


if __name__ == "__main__":
    unittest.main()
