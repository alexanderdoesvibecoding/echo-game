import random
import unittest

from echo_adventure.config import GameConfig
from echo_adventure.decisions import active_decision_cards
from echo_adventure.scenario_generator import generate_scenario
from echo_adventure.simulation import initialize_state


def make_state(seed=12345):
    config = GameConfig.demo(seed=seed)
    scenario = generate_scenario(config)
    state = initialize_state(scenario, config.shifts_per_day)
    return state, config


def active_card_signature(seed=12345):
    state, _config = make_state(seed=seed)
    return card_signature(active_decision_cards(state, state.current_day, {}))


def card_signature(cards):
    """Compare stable player-facing card content, not object identity."""
    return [
        (
            card.id,
            card.day,
            card.type.value,
            card.title,
            tuple(card.target_ids),
            card.severity,
            tuple((choice.id, choice.label) for choice in card.choices),
        )
        for card in cards
    ]


class DeterministicDecisionGenerationTests(unittest.TestCase):
    def test_same_state_and_seed_ignore_global_random_seed(self):
        random.seed(1)
        first = active_card_signature(seed=12345)

        random.seed(5)
        second = active_card_signature(seed=12345)

        self.assertEqual(first, second)

    def test_generation_does_not_advance_module_level_random(self):
        expected_random = random.Random(314159)
        expected_random.random()
        expected_next = expected_random.random()

        random.seed(314159)
        random.random()
        active_card_signature(seed=54321)
        actual_next = random.random()

        self.assertEqual(actual_next, expected_next)

    def test_independent_replays_with_same_seed_have_same_cards(self):
        cards_a = active_card_signature(seed=777)
        cards_b = active_card_signature(seed=777)

        self.assertEqual(cards_a, cards_b)


if __name__ == "__main__":
    unittest.main()
