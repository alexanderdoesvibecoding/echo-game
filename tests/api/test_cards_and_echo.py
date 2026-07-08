from __future__ import annotations

import math
import unittest
from unittest.mock import patch

from echo_adventure.decisions.cards import (
    _assigned_location_phrase,
    _bottleneck_card,
    _completion_readiness_card,
    _completion_readiness_description,
    _critical_path_card,
    _decision_type_for_event,
    _duplicates_any_card,
    _event_card,
    _event_context,
    _fallback_strategic_card,
    _generate_root_decision_cards,
    _generate_scheduled_event_cards,
    _handoff_card,
    _idle_capacity_description,
    _idle_card,
    _job_context,
    _job_state_phrase,
    _quality_triage_card,
    _queue_congestion_card,
    _renumber_decision_cards,
    _shop_pressure_description,
    _slack_phrase,
    _strategic_card,
    _target_name,
    _alternate_card,
)
from echo_adventure.echo import (
    _apply_static_echo_choices,
    _best_open_alternate,
    _event_expedite_value,
    _event_for_card,
    _event_for_choice,
    _failed_forecast_objective,
    _forecast_choice_objective,
    _late_stage,
    _live_operational_score,
    _queue_pressure_value,
    apply_echo_decisions_for_day,
    select_echo_choice_for_state,
)
from echo_adventure.enums import DecisionType, EventType, JobStatus, TargetType, WorkCenterStatus
from echo_adventure.metrics import update_state_metrics

from .helpers import make_card, make_choice, make_event, make_state, unit_config


class DecisionCardFactoryTests(unittest.TestCase):
    def test_event_card_variants_cover_echo_unexpected_and_rerouteable_events(self):
        state = make_state()
        echo_event = make_event(
            "EVT-ECHO",
            event_type=EventType.ECHO_RECOMMENDATION,
            target_type=TargetType.CAPABILITY,
            target_id="ECHO",
        )
        unexpected = make_event(
            "EVT-NEW",
            event_type=EventType.UNEXPECTED_JOB,
            target_type=TargetType.CAPABILITY,
            target_id="NEW_JOB",
        )
        material = make_event(
            "EVT-MAT",
            event_type=EventType.MISSING_MATERIAL,
            target_type=TargetType.JOB,
            target_id="JOB-01-001",
        )
        state.active_events = [echo_event.id, material.id]
        state.known_warnings = [unexpected.id]

        echo_card = _event_card(state, echo_event, 1, 1)
        new_card = _event_card(state, unexpected, 2, 1)
        material_card = _event_card(state, material, 3, 1)

        self.assertEqual(echo_card.type, DecisionType.ECHO_RECOMMENDATION)
        self.assertEqual([choice.immediate_effects["type"] for choice in echo_card.choices], ["echo_recommendation", "wait"])
        self.assertEqual(new_card.type, DecisionType.UNEXPECTED_JOB)
        self.assertEqual([choice.immediate_effects["type"] for choice in new_card.choices], ["prioritize_new_job", "backlog_new_job"])
        self.assertIn("reroute", {choice.immediate_effects["type"] for choice in material_card.choices})

    def test_generated_cards_use_visible_events_then_fallback_strategic_cards(self):
        state = make_state()
        active = make_event("EVT-A", severity=4)
        warned = make_event("EVT-W", severity=3)
        state.event_timeline = [active, warned]
        state.active_events = [active.id]
        state.known_warnings = [warned.id]
        config = unit_config(max_active_decision_cards_per_day=2)

        scheduled = _generate_scheduled_event_cards(state, day=1, config=config)

        self.assertEqual([card.id for card in scheduled], ["CMP-D01-EVENT-EVT-A", "CMP-D01-EVENT-EVT-W"])

        quiet = make_state()
        for job in quiet.jobs.values():
            job.status = JobStatus.COMPLETE
            job.completed_shift = 1
            quiet.completed_jobs.add(job.id)
        update_state_metrics(quiet)
        fallback_config = unit_config(min_decisions_per_day=3, max_decisions_per_day=3)

        root_cards = _generate_root_decision_cards(quiet, day=1, config=fallback_config, include_events=False)

        self.assertEqual(len(root_cards), 3)
        self.assertTrue(any(card.title.startswith("Small tradeoff") for card in root_cards))

    def test_card_text_helpers_describe_status_targets_and_pressure(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]
        job.assigned_workcenter_id = "WC-A1"
        job.status = JobStatus.QUEUED
        job.critical_path = False
        job.dependent_job_ids = ["JOB-01-002"]
        state.workcenters["WC-A1"].queue = [job.id]
        shop = state.shops["SHOP-A"]
        shop.queued_job_ids = [job.id]
        shop.blocked_job_ids = ["JOB-01-002"]

        self.assertEqual(_job_state_phrase(state, job), "queued")
        self.assertIn("slack", _slack_phrase(state, job))
        self.assertEqual(_assigned_location_phrase(state, job), "at Alpha Cutter")
        self.assertIn("unlocks later work", _job_context(state, job))
        self.assertIn("Queued and blocked", _shop_pressure_description(state, shop))
        self.assertIn("Stations are open", _idle_capacity_description(state))
        self.assertIn("unfinished jobs", _completion_readiness_description(state))
        self.assertEqual(_target_name(state, TargetType.SHOP, "SHOP-A"), "Alpha Shop")
        self.assertEqual(_target_name(state, TargetType.WORKCENTER, "WC-A1"), "Alpha Cutter")
        self.assertEqual(_target_name(state, TargetType.PIECE, "PIECE-01"), "Job 01")

        event = make_event("EVT-UNK", event_type=EventType.UNEXPECTED_JOB, target_type=TargetType.CAPABILITY, target_id="NEW_JOB")
        self.assertIn("New job", _event_context(state, event, "warning"))

    def test_card_factories_return_expected_decision_types_and_choices(self):
        state = make_state()
        shop = state.shops["SHOP-A"]
        shop.queued_job_ids = ["JOB-01-001", "JOB-01-002", "JOB-02-001"]
        shop.blocked_job_ids = ["JOB-01-002"]
        state.jobs["JOB-01-001"].critical_path = True
        state.jobs["JOB-01-001"].risk_score = 80
        handoff = state.jobs["JOB-01-002"]
        handoff.shop_id = "SHOP-B"
        quality = state.jobs["JOB-02-002"]
        quality.risk_score = 60
        quality.status = JobStatus.REWORK_REQUIRED

        cards = [
            _bottleneck_card(state, shop, 1, 1),
            _queue_congestion_card(state, shop, 2, 1),
            _critical_path_card(state, state.jobs["JOB-01-001"], 3, 1),
            _handoff_card(state, handoff, 4, 1),
            _alternate_card(state, state.jobs["JOB-01-001"], 5, 1),
            _quality_triage_card(state, quality, 6, 1),
            _idle_card(state, 7, 1),
            _completion_readiness_card(state, 8, 1),
            _strategic_card(state, 9, 1),
            _fallback_strategic_card(state, 10, 1),
        ]

        self.assertEqual(cards[0].type, DecisionType.BOTTLENECK)
        self.assertEqual(cards[1].type, DecisionType.QUEUE_CONGESTION)
        self.assertEqual(cards[2].type, DecisionType.CRITICAL_PATH)
        self.assertEqual(cards[3].type, DecisionType.PRIORITY_CHANGE)
        self.assertEqual(cards[4].type, DecisionType.ALTERNATE_ROUTING)
        self.assertEqual(cards[5].type, DecisionType.QUALITY_REWORK)
        self.assertTrue(all(card.choices for card in cards))

    def test_renumber_and_duplicate_detection_preserve_choice_copies(self):
        first = make_card("FIRST", target_ids=["JOB-01-001"])
        duplicate_target = make_card("SECOND", target_ids=["JOB-01-001", "EVT-1"])
        different = make_card("THIRD", target_ids=["JOB-02-001"])

        self.assertTrue(_duplicates_any_card([first], duplicate_target))
        self.assertFalse(_duplicates_any_card([first], different))

        renumbered = _renumber_decision_cards([first, different], day=3)
        self.assertEqual([card.id for card in renumbered], ["DAY-03-DEC-1", "DAY-03-DEC-2"])
        self.assertIsNot(renumbered[0].choices[0], first.choices[0])

    def test_event_type_mapping_covers_all_event_types(self):
        for event_type in EventType:
            with self.subTest(event_type=event_type):
                self.assertIsInstance(_decision_type_for_event(event_type), DecisionType)


class EchoPolicyHelperTests(unittest.TestCase):
    def test_apply_echo_decisions_handles_completed_days_and_simple_active_card(self):
        state = make_state()
        config = unit_config(max_active_decision_cards_per_day=1)
        completed_days = {state.current_day}

        self.assertEqual(apply_echo_decisions_for_day(state, config, completed_days), 0)

        completed_days.clear()
        card = make_card("ECHO-CARD", choices=[make_choice("A", effect_type="note")])
        state.decision_cards = {card.id: card}
        state.campaign_decision_graph.cards_by_day = {state.current_day: [card.id]}
        state.campaign_decision_graph.root_card_ids = [card.id]
        state.campaign_decision_graph.max_active_cards_per_day = 1

        applied = apply_echo_decisions_for_day(state, config, completed_days)

        self.assertEqual(applied, 1)
        self.assertIn(state.current_day, completed_days)
        self.assertEqual(state.decision_history[-1].actor, "ECHO")

        state.final_item_completed = True
        self.assertEqual(apply_echo_decisions_for_day(state, config, set()), 0)

    def test_forecast_choice_objective_falls_back_for_missing_card_or_choice(self):
        state = make_state()
        config = unit_config(echo_choice_lookahead_days=1)
        missing_card = make_card("MISSING", choices=[make_choice("A")])
        choice = missing_card.choices[0]

        with self.assertLogs("echo_adventure.echo", level="WARNING"):
            objective = _forecast_choice_objective(state, missing_card, choice, config, {}, {})

        self.assertEqual(objective[0], 2.0)
        self.assertTrue(math.isinf(objective[1]))

        projected_card = make_card("CARD", choices=[make_choice("A")])
        external_choice = make_choice("B")
        state.decision_cards = {projected_card.id: projected_card}

        with self.assertLogs("echo_adventure.echo", level="WARNING"):
            objective = _forecast_choice_objective(state, projected_card, external_choice, config, state.decision_cards, {})

        self.assertEqual(objective[0], 2.0)
        self.assertTrue(math.isinf(objective[1]))

    def test_static_projection_choice_limit_caps_total_applied_choices(self):
        state = make_state()
        cards = [
            make_card("CARD-A", choices=[make_choice("A")]),
            make_card("CARD-B", choices=[make_choice("A")]),
            make_card("CARD-C", choices=[make_choice("A")]),
        ]
        state.decision_cards = {card.id: card for card in cards}
        state.campaign_decision_graph.cards_by_day = {state.current_day: [card.id for card in cards]}
        state.campaign_decision_graph.root_card_ids = [card.id for card in cards]
        state.campaign_decision_graph.max_active_cards_per_day = 3
        config = unit_config(echo_choice_projection_limit=1, max_active_decision_cards_per_day=3)

        _apply_static_echo_choices(state, config)

        self.assertEqual(len(state.campaign_selected_choices), 1)
        self.assertEqual(len(state.decision_history), 1)

    def test_forecast_choice_objective_respects_positive_lookahead_days(self):
        state = make_state()
        card = make_card("CARD", choices=[make_choice("A")])
        choice = card.choices[0]
        state.decision_cards = {card.id: card}
        advance_calls = 0

        def fake_advance_day(projected_state, scheduler):
            nonlocal advance_calls
            advance_calls += 1
            projected_state.current_shift += projected_state.shifts_per_day

        with patch("echo_adventure.echo._apply_static_echo_choices"), patch(
            "echo_adventure.echo.advance_day",
            side_effect=fake_advance_day,
        ):
            objective = _forecast_choice_objective(
                state,
                card,
                choice,
                unit_config(echo_choice_lookahead_days=2),
                state.decision_cards,
                {},
            )

        self.assertEqual(advance_calls, 2)
        self.assertEqual(objective[0], 1.0)

    def test_live_echo_choice_tiebreaks_by_choice_id_after_equal_forecasts(self):
        state = make_state()
        card = make_card(
            "CARD",
            choices=[make_choice("B", effect_type="wait"), make_choice("A", effect_type="wait")],
        )
        state.decision_cards = {card.id: card}

        with patch("echo_adventure.echo._forecast_choice_objective", return_value=(0.0, 1.0, 0.0)):
            selected = select_echo_choice_for_state(state, card, unit_config(), state.decision_cards)

        self.assertEqual(selected.id, "A")

    def test_live_operational_score_branches_for_major_choice_types(self):
        state = make_state()
        source = make_event(
            "EVT-SOURCE",
            event_type=EventType.INSPECTION_DELAY,
            target_type=TargetType.JOB,
            target_id="JOB-01-001",
            severity=4,
            duration_shifts=3,
        )
        state.event_timeline = [source]
        state.active_events = [source.id]
        state.jobs["JOB-01-001"].critical_path = True
        card = make_card(
            "CARD",
            target_ids=[source.id],
            card_type=DecisionType.COMPLETION_READINESS,
            severity=4,
        )
        wait_score = _live_operational_score(state, card, make_choice("WAIT", effect_type="wait", risk_effect=3))
        protect_score = _live_operational_score(state, card, make_choice("PROTECT", effect_type="protect_critical"))
        expedite_score = _live_operational_score(
            state,
            card,
            make_choice("EXP", effect_type="expedite_event", immediate_effects={"type": "expedite_event", "event_id": source.id}),
        )
        echo_score = _live_operational_score(state, card, make_choice("ECHO", effect_type="echo_recommendation"))

        self.assertGreater(wait_score, protect_score)
        self.assertLess(expedite_score, wait_score)
        self.assertLess(echo_score, wait_score)

        state.current_shift = int(state.deadline_shift * 0.8)
        prioritize = _live_operational_score(state, card, make_choice("NEW", effect_type="prioritize_new_job"))
        backlog = _live_operational_score(state, card, make_choice("BACK", effect_type="backlog_new_job"))
        self.assertGreater(prioritize, backlog)

    def test_echo_helper_functions_cover_event_and_workcenter_edges(self):
        state = make_state()
        event = make_event("EVT-1", event_type=EventType.DELAYED_MATERIAL, severity=4, duration_shifts=4)
        state.event_timeline = [event]
        state.active_events = [event.id]
        job = state.jobs["JOB-01-001"]
        job.assigned_workcenter_id = "WC-A1"
        state.workcenters["WC-A1"].queue = [job.id]
        state.workcenters["WC-B1"].queue = []
        card = make_card("CARD", target_ids=[event.id, "SHOP-A"])
        choice = make_choice("EXP", immediate_effects={"type": "expedite_event", "event_id": event.id})

        self.assertEqual(_failed_forecast_objective(12.5)[-1], 12.5)
        self.assertEqual(_event_expedite_value(state, None), 4.0)
        self.assertGreater(_event_expedite_value(state, event), 20.0)
        self.assertGreater(_queue_pressure_value(state, card, [job]), 0.0)
        self.assertEqual(state.workcenters["WC-A1"].load, 1)
        self.assertEqual(_event_for_choice(state, choice), event)
        self.assertEqual(_event_for_card(state, card), event)
        self.assertEqual(_best_open_alternate(state, job).id, "WC-B1")
        self.assertFalse(_late_stage(state))
        state.current_shift = state.deadline_shift
        self.assertTrue(_late_stage(state))

        state.workcenters["WC-B1"].status = WorkCenterStatus.DOWN
        self.assertTrue(state.workcenters["WC-B1"].is_disrupted)
        self.assertIsNone(_best_open_alternate(state, job))


if __name__ == "__main__":
    unittest.main()
