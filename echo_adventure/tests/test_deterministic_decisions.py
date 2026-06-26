import hashlib
import copy
import random
import unittest

from echo_adventure.config import GameConfig
from echo_adventure.decisions import active_decision_cards, apply_choice, generate_campaign_decision_graph
from echo_adventure.enums import EventType, TargetType
from echo_adventure.metrics import calculate_final_score
from echo_adventure.models import Event, SimulationState
from echo_adventure.scenario_generator import generate_scenario
from echo_adventure.schedulers.manual import ManualScheduler
from echo_adventure.simulation import advance_day
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


def graph_signature(scenario):
    return [
        (
            card.id,
            card.day,
            card.title,
            tuple(card.required_tags),
            tuple(card.future_unlock_card_ids),
            tuple(
                (
                    choice.id,
                    choice.branch_key,
                    tuple(choice.branch_tags_added),
                    tuple(choice.future_unlock_card_ids),
                    choice.score_delta,
                )
                for choice in card.choices
            ),
        )
        for card in sorted(scenario.decision_cards.values(), key=lambda item: item.id)
    ]


def choose_all_active_cards(state, chooser):
    day = state.current_day
    while True:
        cards = active_decision_cards(state, day, {})
        open_cards = [card for card in cards if card.id not in state.campaign_selected_choices]
        if not open_cards:
            return
        for card in open_cards:
            choice = chooser(state, card)
            apply_choice(state, card, choice)


def advance_to_day(state, target_day, chooser):
    scheduler = ManualScheduler()
    while state.current_day < target_day and not state.final_item_completed:
        choose_all_active_cards(state, chooser)
        advance_day(state, scheduler)


def run_demo_path(seed, chooser):
    config = GameConfig.demo(seed=seed)
    scenario = generate_scenario(config)
    state = initialize_state(scenario, config.shifts_per_day)
    scheduler = ManualScheduler()
    active_by_day = []
    while state.current_shift < state.deadline_shift and not state.final_item_completed:
        active_by_day.append(tuple(card.id for card in active_decision_cards(state, state.current_day, {})))
        choose_all_active_cards(state, chooser)
        advance_day(state, scheduler)
    return scenario, state, active_by_day, calculate_final_score(state)


def scenario_with_day_five_event(seed=24680):
    config = GameConfig.demo(seed=seed)
    scenario = generate_scenario(config)
    day_five_shift = (5 - 1) * config.shifts_per_day
    scenario.event_timeline.append(
        Event(
            id="EVT-DAY5",
            type=EventType.UNEXPECTED_JOB,
            target_type=TargetType.CAPABILITY,
            target_id="NEW_JOB",
            start_shift=day_five_shift,
            duration_shifts=config.shifts_per_day,
            severity=4,
            has_advance_warning=False,
            warning_shift=None,
            description="A new customer job arrived outside the initial job list.",
        )
    )
    graph_state = SimulationState(
        scenario_id=scenario.scenario_id,
        seed=scenario.seed,
        deadline_shift=scenario.deadline_shift,
        shifts_per_day=config.shifts_per_day,
        shops=copy.deepcopy(scenario.shops),
        workcenters=copy.deepcopy(scenario.workcenters),
        pieces=copy.deepcopy(scenario.pieces),
        jobs=copy.deepcopy(scenario.jobs),
        event_timeline=copy.deepcopy(scenario.event_timeline),
    )
    (
        scenario.decision_cards,
        scenario.campaign_decision_graph,
        scenario.daily_decision_roots,
        scenario.daily_decision_counts,
    ) = generate_campaign_decision_graph(graph_state, config)
    return scenario, config


class DeterministicDecisionGenerationTests(unittest.TestCase):
    def test_campaign_graph_exists_at_scenario_creation(self):
        config = GameConfig.demo(seed=12345)
        scenario = generate_scenario(config)

        graph = scenario.campaign_decision_graph

        self.assertTrue(graph.card_ids)
        self.assertTrue(graph.campaign_root_card_id)
        self.assertIn(graph.campaign_root_card_id, scenario.decision_cards)
        self.assertTrue(any(card.day == 5 for card in scenario.decision_cards.values()))
        self.assertTrue(
            any(
                choice.future_unlock_card_ids
                for card in scenario.decision_cards.values()
                for choice in card.choices
            )
        )

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

    def test_day_one_choice_changes_day_five_cards(self):
        seed = 24680

        def run_with_first_choice(choice_index):
            state, _config = make_state(seed=seed)
            first_card_id = active_decision_cards(state, 1, {})[0].id

            def chooser(_state, card):
                if _state.current_day == 1 and card.id == first_card_id:
                    return card.choices[choice_index]
                return card.choices[0]

            advance_to_day(state, 5, chooser)
            return {card.id for card in active_decision_cards(state, 5, {})}

        day5_a = run_with_first_choice(0)
        day5_b = run_with_first_choice(1)

        self.assertNotEqual(day5_a, day5_b)

    def test_scheduled_event_cards_are_not_branch_cards(self):
        scenario, config = scenario_with_day_five_event(seed=24680)

        def run_with_first_choice(choice_index):
            state = initialize_state(scenario, config.shifts_per_day)
            first_card_id = active_decision_cards(state, 1, {})[0].id

            def chooser(_state, card):
                if _state.current_day == 1 and card.id == first_card_id:
                    return card.choices[choice_index]
                return card.choices[0]

            advance_to_day(state, 5, chooser)
            day5_cards = active_decision_cards(state, 5, {})
            event_cards = {card.id for card in day5_cards if card.id.startswith("CMP-D05-EVENT-")}
            branch_cards = {card.id for card in day5_cards if not card.id.startswith("CMP-D05-EVENT-")}
            event_timeline = [
                (event.id, event.start_shift, event.type)
                for event in state.event_timeline
                if event.id == "EVT-DAY5"
            ]
            return event_cards, branch_cards, event_timeline

        events_a, branch_a, timeline_a = run_with_first_choice(0)
        events_b, branch_b, timeline_b = run_with_first_choice(1)

        self.assertEqual(events_a, {"CMP-D05-EVENT-EVT-DAY5"})
        self.assertEqual(events_a, events_b)
        self.assertEqual(timeline_a, timeline_b)
        self.assertNotEqual(branch_a, branch_b)

    def test_same_seed_and_choices_are_deterministic(self):
        def chooser(_state, card):
            return card.choices[(card.day + len(card.id)) % len(card.choices)]

        scenario_a, state_a, active_a, score_a = run_demo_path(seed=13579, chooser=chooser)
        scenario_b, state_b, active_b, score_b = run_demo_path(seed=13579, chooser=chooser)

        self.assertEqual(graph_signature(scenario_a), graph_signature(scenario_b))
        self.assertEqual(active_a, active_b)
        self.assertEqual(state_a.decision_path, state_b.decision_path)
        self.assertEqual(state_a.decision_path_signature, state_b.decision_path_signature)
        self.assertEqual(score_a, score_b)
        self.assertEqual(sorted(state_a.completed_jobs), sorted(state_b.completed_jobs))

    def test_score_diversity_for_many_deterministic_paths(self):
        scores = set()

        for path_index in range(100):
            config = GameConfig.demo(seed=424242)
            scenario = generate_scenario(config)
            state = initialize_state(scenario, config.shifts_per_day)

            def chooser(_state, card, path_index=path_index):
                material = f"{path_index}:{_state.current_day}:{len(_state.decision_path)}:{card.id}"
                index = int(hashlib.sha256(material.encode("utf-8")).hexdigest()[:8], 16) % len(card.choices)
                return card.choices[index]

            for day in range(1, config.total_days + 1):
                state.current_shift = (day - 1) * config.shifts_per_day
                choose_all_active_cards(state, chooser)
            state.current_shift = state.deadline_shift
            scores.add(calculate_final_score(state))

        self.assertGreaterEqual(len(scores), 95)

    def test_unchosen_branch_cards_do_not_leak(self):
        state, _config = make_state(seed=97531)
        first_card = active_decision_cards(state, 1, {})[0]
        chosen = first_card.choices[0]
        unchosen = first_card.choices[1]
        unchosen_day5_unlocks = {
            card_id
            for card_id in unchosen.future_unlock_card_ids
            if state.decision_cards[card_id].day == 5
        }
        forbidden_tags = set(unchosen.branch_tags_added) - set(chosen.branch_tags_added)

        def chooser(_state, card):
            if _state.current_day == 1 and card.id == first_card.id:
                return chosen
            for candidate in card.choices:
                if forbidden_tags.isdisjoint(candidate.branch_tags_added):
                    return candidate
            return card.choices[0]

        advance_to_day(state, 5, chooser)
        day5_ids = {card.id for card in active_decision_cards(state, 5, {})}

        self.assertTrue(unchosen_day5_unlocks)
        self.assertTrue(day5_ids.isdisjoint(unchosen_day5_unlocks))


if __name__ == "__main__":
    unittest.main()
