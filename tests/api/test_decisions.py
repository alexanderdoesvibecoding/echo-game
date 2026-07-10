from __future__ import annotations

import unittest

from echo_adventure.decisions.effects import apply_choice
from echo_adventure.decisions.graph import (
    _set_card_context,
    active_campaign_decision_cards,
    apply_campaign_choice,
    decision_path_signature,
    decision_progress,
    project_choice_branch_state,
    unlock_future_decision_nodes,
)
from echo_adventure.decisions.scoring import score_echo_choice, select_echo_choice
from echo_adventure.decisions.selectors import (
    _alternate_routing_jobs,
    _best_alternate_workcenter,
    _events_related,
    _handoff_risk_job,
    _has_idle_opportunity,
    _jobs_for_card,
    _jobs_for_event,
    _piece_id_for_event,
    _quality_triage_job,
    _visible_events,
)
from echo_adventure.enums import DecisionType, EventType, JobStatus, TargetType, WorkCenterStatus

from .helpers import (
    make_card,
    make_choice,
    make_event,
    make_state,
    make_unexpected_job_event,
)


class DecisionGraphTests(unittest.TestCase):
    def test_project_choice_branch_state_adds_stable_deduped_tags(self):
        choice = make_choice(
            effect_type="wait",
            risk_effect=5,
            reschedule_effect=2,
        )

        primary, tags = project_choice_branch_state(choice)

        self.assertEqual(primary, "wait_escalation")
        self.assertEqual(len(tags), len(set(tags)))
        self.assertIn("risk_debt_created", tags)
        self.assertIn("crew_overloaded", tags)
        self.assertIn("supplier_risk_ignored", tags)

    def test_apply_campaign_choice_updates_branch_tags_unlocks_path_and_signature(self):
        state = make_state()
        future = make_card("FUTURE", day=2)
        state.decision_cards = {"FUTURE": future}
        choice = make_choice(
            branch_tags_added=["critical_path_protected", "crew_overloaded"],
            future_unlock_card_ids=["FUTURE", "MISSING"],
            score_delta=1.25,
        )
        card = make_card("CARD-1", choices=[choice])

        apply_campaign_choice(state, card, choice)

        self.assertEqual(state.campaign_selected_choices, {"CARD-1": "A"})
        self.assertEqual(state.campaign_branch_tag_order["critical_path_protected"], 0)
        self.assertEqual(state.campaign_branch_tag_order["crew_overloaded"], 1)
        self.assertEqual(state.unlocked_decision_card_ids, {"FUTURE"})
        self.assertEqual(state.decision_path, ["CARD-1:A"])
        self.assertEqual(state.decision_path_signature, decision_path_signature(state))
        self.assertEqual(state.decision_path_score_delta, 1.25)

    def test_active_campaign_cards_filter_by_unlocks_tags_exclusions_and_event_priority(self):
        state = make_state()
        event_card = make_card("EVT-CARD", day=1, campaign_priority=50)
        root = make_card("ROOT", day=1, campaign_priority=20)
        route = make_card(
            "ROUTE",
            day=1,
            required_tags=["critical_path_protected"],
            campaign_priority=5,
        )
        excluded = make_card(
            "EXCLUDED",
            day=1,
            excluded_tags=["critical_path_protected"],
            campaign_priority=1,
        )
        locked = make_card("LOCKED", day=1)
        state.decision_cards = {
            card.id: card
            for card in [event_card, root, route, excluded, locked]
        }
        state.campaign_decision_graph.cards_by_day = {
            1: ["ROOT", "ROUTE", "EXCLUDED", "LOCKED", "EVT-CARD"]
        }
        state.campaign_decision_graph.event_card_ids_by_day = {1: ["EVT-CARD"]}
        state.campaign_decision_graph.root_card_ids = ["ROOT"]
        state.campaign_decision_graph.max_active_cards_per_day = 3
        state.unlocked_decision_card_ids = {"ROUTE", "EXCLUDED"}
        state.campaign_branch_tags = {"critical_path_protected"}
        state.campaign_branch_tag_order = {"critical_path_protected": 0}

        cards = active_campaign_decision_cards(state, 1, {})

        self.assertEqual([card.id for card in cards], ["EVT-CARD", "ROUTE", "ROOT"])

    def test_decision_progress_merges_session_and_campaign_selected_choices(self):
        state = make_state()
        first = make_card("FIRST", day=1)
        second = make_card("SECOND", day=1)
        state.decision_cards = {"FIRST": first, "SECOND": second}
        state.campaign_decision_graph.cards_by_day = {1: ["FIRST", "SECOND"]}
        state.campaign_decision_graph.root_card_ids = ["FIRST", "SECOND"]
        state.campaign_decision_graph.max_active_cards_per_day = 3
        state.campaign_selected_choices = {"FIRST": "A"}

        progress = decision_progress(state, 1, {"SECOND": "A"})

        self.assertEqual(progress.total_questions, 2)
        self.assertEqual(progress.answered_questions, 2)
        self.assertEqual(progress.open_card_ids, [])

    def test_unlock_future_decision_nodes_ignores_unknown_ids(self):
        state = make_state()
        state.decision_cards = {"KNOWN": make_card("KNOWN")}

        unlock_future_decision_nodes(state, ["KNOWN", "UNKNOWN"])

        self.assertEqual(state.unlocked_decision_card_ids, {"KNOWN"})

    def test_unlocked_branch_card_is_still_filtered_by_exclusion_tags(self):
        state = make_state()
        card = make_card(
            "ROUTE",
            day=2,
            required_tags=["critical_path_protected"],
            excluded_tags=["crew_overloaded"],
        )
        state.decision_cards = {card.id: card}
        state.campaign_decision_graph.cards_by_day = {2: [card.id]}
        state.campaign_decision_graph.max_active_cards_per_day = 2
        state.unlocked_decision_card_ids = {card.id}
        state.campaign_branch_tags = {"critical_path_protected", "crew_overloaded"}

        self.assertEqual(active_campaign_decision_cards(state, 2, {}), [])

    def test_context_labels_use_short_impact_copy(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]

        job_card = make_card("JOB-CONTEXT", target_ids=[job.id])
        job_card.target_selector = "fixture"
        _set_card_context(state, job_card, job)

        self.assertEqual(job_card.context_label, "Job 01")

        shop_card = make_card("SHOP-CONTEXT", target_ids=[job.id])
        shop_card.target_selector = "shop"
        _set_card_context(state, shop_card, job)

        self.assertEqual(shop_card.context_label, "Alpha Shop")

        global_card = make_card("GLOBAL-CONTEXT", target_ids=[job.id])
        global_card.target_selector = "global"
        _set_card_context(state, global_card, job)

        self.assertEqual(global_card.context_label, "Overall schedule")


class DecisionScoringTests(unittest.TestCase):
    def test_select_echo_choice_uses_card_echo_choice_id_when_no_graph_is_supplied(self):
        preferred = make_choice("B", effect_type="wait")
        card = make_card(
            "CARD",
            choices=[make_choice("A", effect_type="note"), preferred],
            echo_choice_id="B",
        )

        self.assertIs(select_echo_choice(card), preferred)

    def test_score_echo_choice_handles_future_unlock_cycles(self):
        root_choice = make_choice("A", effect_type="wait", future_unlock_card_ids=["CHILD"])
        child_choice = make_choice("B", effect_type="expedite_event", future_unlock_card_ids=["ROOT"])
        root = make_card("ROOT", choices=[root_choice])
        child = make_card("CHILD", choices=[child_choice])
        graph = {"ROOT": root, "CHILD": child}

        score = score_echo_choice(root_choice, graph)

        self.assertIsInstance(score, float)
        self.assertGreater(score, 0)

    def test_select_echo_choice_tiebreaks_by_choice_id(self):
        card = make_card(
            "CARD",
            choices=[make_choice("B"), make_choice("A")],
        )

        self.assertEqual(select_echo_choice(card).id, "A")


class DecisionSelectorTests(unittest.TestCase):
    def test_visible_events_prioritizes_unexpected_active_events(self):
        state = make_state()
        unexpected = make_event(
            "EVT-NEW",
            event_type=EventType.UNEXPECTED_JOB,
            target_type=TargetType.CAPABILITY,
            target_id="NEW_JOB",
            severity=1,
        )
        active = make_event("EVT-ACTIVE", severity=5)
        warned = make_event("EVT-WARNED", severity=5)
        resolved = make_event("EVT-DONE", severity=5, resolved=True)
        state.event_timeline = [warned, resolved, active, unexpected]
        state.active_events = [active.id, unexpected.id, resolved.id]
        state.known_warnings = [warned.id]

        events = _visible_events(state)

        self.assertEqual([event.id for event in events], ["EVT-NEW", "EVT-ACTIVE", "EVT-WARNED"])

    def test_jobs_for_card_expands_targets_and_falls_back_to_critical_jobs(self):
        state = make_state()
        state.workcenters["WC-A1"].queue = ["JOB-01-001"]
        state.workcenters["WC-A1"].current_job_id = "JOB-02-001"
        event = make_event(
            "EVT-WC",
            event_type=EventType.MACHINE_DOWN,
            target_type=TargetType.WORKCENTER,
            target_id="WC-A1",
        )
        state.event_timeline = [event]

        event_jobs = _jobs_for_event(state, event)
        self.assertEqual({job.id for job in event_jobs}, {"JOB-01-001", "JOB-02-001"})

        card = make_card(target_ids=["SHOP-A", "PIECE-02", "EVT-WC"])
        expanded = _jobs_for_card(state, card)
        self.assertIn("JOB-01-001", {job.id for job in expanded})
        self.assertIn("JOB-02-001", {job.id for job in expanded})

        fallback = _jobs_for_card(state, make_card(target_ids=["UNKNOWN"]), fallback_limit=2)
        self.assertGreaterEqual(len(fallback), 1)

    def test_workcenter_and_job_selectors_find_operational_targets(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]
        job.assigned_workcenter_id = "WC-A1"
        job.critical_path = True
        job.risk_score = 70
        state.workcenters["WC-A1"].queue = ["OTHER"]

        alternate = _best_alternate_workcenter(state, job)

        self.assertEqual(alternate.id, "WC-B1")
        self.assertIn(job.id, {candidate.id for candidate in _alternate_routing_jobs(state)})
        self.assertTrue(_has_idle_opportunity(state))

        state.jobs["JOB-01-001"].shop_id = "SHOP-A"
        handoff = state.jobs["JOB-01-002"]
        handoff.shop_id = "SHOP-B"
        handoff.dependency_ids = ["JOB-01-001"]
        handoff.risk_score = 40
        self.assertEqual(_handoff_risk_job(state).id, handoff.id)

        quality = state.jobs["JOB-02-002"]
        quality.status = JobStatus.REWORK_REQUIRED
        self.assertEqual(_quality_triage_job(state).id, quality.id)

    def test_events_related_and_piece_id_resolution_use_job_context(self):
        state = make_state()
        source = make_event("EVT-1", target_id="JOB-01-001")
        same_piece = make_event("EVT-2", target_id="JOB-01-002")
        other_piece = make_event("EVT-3", target_id="JOB-02-001")

        self.assertTrue(_events_related(state, source, same_piece))
        self.assertFalse(_events_related(state, source, other_piece))
        self.assertEqual(_piece_id_for_event(state, source), "PIECE-01")


class DecisionEffectTests(unittest.TestCase):
    def test_apply_choice_wait_records_history_and_adds_pressure(self):
        state = make_state()
        event = make_event("EVT-WAIT", start_shift=1, duration_shifts=2)
        event.started = True
        state.event_timeline = [event]
        state.active_events = [event.id]
        card = make_card("CARD-WAIT", target_ids=[event.id], card_type=DecisionType.CRITICAL_PATH)
        choice = make_choice(
            "WAIT",
            effect_type="wait",
            immediate_effects={"type": "wait", "event_id": event.id},
            risk_effect=4,
            reschedule_effect=1,
            branch_tags_added=["wait_escalation"],
            score_delta=-0.5,
        )
        card.choices = [choice]
        state.decision_cards[card.id] = card

        note = apply_choice(state, card, choice, echo_choice=choice)

        self.assertIn("Held", note)
        self.assertGreater(event.duration_shifts, 2)
        self.assertEqual(state.reschedule_count, 1)
        self.assertEqual(state.decision_history[-1].choice_id, "WAIT")
        self.assertIn("CARD-WAIT:WAIT", state.decision_path)

    def test_apply_choice_expedite_reduces_current_and_related_future_event(self):
        state = make_state()
        source = make_event(
            "EVT-SOURCE",
            event_type=EventType.DELAYED_MATERIAL,
            target_id="JOB-01-001",
            severity=4,
            duration_shifts=5,
        )
        future = make_event(
            "EVT-FUTURE",
            event_type=EventType.SUPPLIER_ESCALATION,
            target_id="JOB-01-002",
            start_shift=8,
            severity=4,
            duration_shifts=4,
        )
        state.event_timeline = [source, future]
        state.active_events = [source.id]
        card = make_card("CARD-EXP", target_ids=[source.id])
        choice = make_choice(
            "EXP",
            effect_type="expedite_event",
            immediate_effects={"type": "expedite_event", "event_id": source.id},
        )
        card.choices = [choice]

        note = apply_choice(state, card, choice, echo_choice=choice)

        self.assertIn("Expedited", note)
        self.assertEqual(source.duration_shifts, 3)
        self.assertEqual(source.severity, 3)
        self.assertLess(future.severity, 4)
        self.assertIn(source.id, future.effects["upstream_mitigations"])

    def test_apply_choice_reroute_moves_disrupted_job_to_alternate(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]
        job.status = JobStatus.QUEUED
        job.assigned_workcenter_id = "WC-A1"
        state.workcenters["WC-A1"].queue = [job.id]
        state.workcenters["WC-A1"].status = WorkCenterStatus.DOWN
        card = make_card("CARD-REROUTE", target_ids=[job.id])
        choice = make_choice("REROUTE", effect_type="reroute")
        card.choices = [choice]

        note = apply_choice(state, card, choice, echo_choice=choice)

        self.assertIn("Rerouted", note)
        self.assertEqual(job.assigned_workcenter_id, "WC-B1")
        self.assertIn(job.id, state.workcenters["WC-B1"].queue)

    def test_apply_choice_prioritizes_unexpected_job_request(self):
        state = make_state()
        event = make_unexpected_job_event(severity=3)
        state.event_timeline = [event]
        card = make_card("CARD-NEW", target_ids=[event.id])
        choice = make_choice(
            "PRIORITIZE",
            effect_type="prioritize_new_job",
            immediate_effects={"type": "prioritize_new_job", "event_id": event.id},
        )
        card.choices = [choice]

        note = apply_choice(state, card, choice, echo_choice=choice)

        self.assertIn("prioritized", note)
        self.assertEqual(len(state.pieces), 3)
        piece_id = event.effects["unexpected_piece_id"]
        first_job = state.jobs[state.pieces[piece_id].job_ids[0]]
        self.assertGreaterEqual(first_job.priority, 90)

    def test_apply_choice_unknown_effect_records_safe_fallback(self):
        state = make_state()
        card = make_card("CARD-UNKNOWN")
        choice = make_choice(
            "UNKNOWN",
            effect_type="mystery_effect",
            immediate_effects={"type": "mystery_effect"},
        )
        card.choices = [choice]

        note = apply_choice(state, card, choice, echo_choice=choice)

        self.assertEqual(note, "Recorded the scheduling preference for today.")
        self.assertEqual(state.decision_history[-1].choice_id, "UNKNOWN")
        self.assertIn("CARD-UNKNOWN:UNKNOWN", state.decision_path)


if __name__ == "__main__":
    unittest.main()
