"""Small deterministic fixtures shared by the unit tests."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from echo_adventure.config import GameConfig, NO_RANDOM_DISRUPTION_PROFILE
from echo_adventure.enums import DecisionType, EventType, TargetType
from echo_adventure.metrics import update_state_metrics
from echo_adventure.models import (
    CampaignDecisionGraph,
    DecisionCard,
    DecisionChoice,
    Event,
    Job,
    PuzzlePiece,
    Scenario,
    Shop,
    SimulationState,
    WorkCenter,
)


def unit_config(**overrides: Any) -> GameConfig:
    """Return a small config that still exercises generation and campaign code."""
    config = GameConfig(
        total_days=4,
        shifts_per_day=3,
        piece_count=3,
        shop_count=3,
        min_workcenters_per_shop=2,
        max_workcenters_per_shop=3,
        min_jobs_per_piece=2,
        max_jobs_per_piece=3,
        min_job_duration_shifts=1,
        max_job_duration_shifts=2,
        setup_time_choices=(0,),
        transport_delay_probability=0.0,
        min_capable_workcenters_per_capability=1,
        min_candidate_workcenters_per_job=1,
        max_candidate_workcenters_per_job=4,
        max_alternate_workcenters_per_job=2,
        **asdict(NO_RANDOM_DISRUPTION_PROFILE),
        min_decisions_per_day=1,
        max_decisions_per_day=2,
        max_active_decision_cards_per_day=2,
        max_campaign_decision_nodes=30,
        max_future_unlocks_per_choice=2,
        max_branch_variants_per_day=4,
        seed=101,
    )
    return replace(config, **overrides)


def make_state(update_metrics: bool = True) -> SimulationState:
    """Build a tiny two-piece factory state by hand."""
    shops = {
        "SHOP-A": Shop(
            id="SHOP-A",
            name="Alpha Shop",
            capabilities=["assembly", "cutting"],
            workcenter_ids=["WC-A1", "WC-A2"],
        ),
        "SHOP-B": Shop(
            id="SHOP-B",
            name="Beta Shop",
            capabilities=["cutting", "inspection"],
            workcenter_ids=["WC-B1", "WC-B2"],
        ),
    }
    workcenters = {
        "WC-A1": WorkCenter(
            id="WC-A1",
            shop_id="SHOP-A",
            name="Alpha Cutter",
            capabilities=["cutting"],
            efficiency=1.0,
        ),
        "WC-A2": WorkCenter(
            id="WC-A2",
            shop_id="SHOP-A",
            name="Alpha Assembly",
            capabilities=["assembly"],
            efficiency=1.2,
        ),
        "WC-B1": WorkCenter(
            id="WC-B1",
            shop_id="SHOP-B",
            name="Beta Cutter",
            capabilities=["cutting"],
            efficiency=0.9,
        ),
        "WC-B2": WorkCenter(
            id="WC-B2",
            shop_id="SHOP-B",
            name="Beta Inspection",
            capabilities=["inspection"],
            efficiency=1.1,
        ),
    }
    jobs = {
        "JOB-01-001": Job(
            id="JOB-01-001",
            piece_id="PIECE-01",
            shop_id="SHOP-A",
            required_capability="cutting",
            candidate_workcenter_ids=["WC-A1", "WC-B1"],
            assigned_workcenter_id=None,
            base_duration_shifts=2,
            remaining_duration_shifts=2,
            setup_time_shifts=1,
            transport_delay_shifts=0,
            dependency_ids=[],
            priority=70,
            due_shift=5,
            risk_score=20.0,
        ),
        "JOB-01-002": Job(
            id="JOB-01-002",
            piece_id="PIECE-01",
            shop_id="SHOP-A",
            required_capability="assembly",
            candidate_workcenter_ids=["WC-A2"],
            assigned_workcenter_id=None,
            base_duration_shifts=1,
            remaining_duration_shifts=1,
            setup_time_shifts=0,
            transport_delay_shifts=0,
            dependency_ids=["JOB-01-001"],
            priority=55,
            due_shift=7,
            risk_score=10.0,
        ),
        "JOB-02-001": Job(
            id="JOB-02-001",
            piece_id="PIECE-02",
            shop_id="SHOP-B",
            required_capability="cutting",
            candidate_workcenter_ids=["WC-B1", "WC-A1"],
            assigned_workcenter_id=None,
            base_duration_shifts=3,
            remaining_duration_shifts=3,
            setup_time_shifts=0,
            transport_delay_shifts=0,
            dependency_ids=[],
            priority=82,
            due_shift=6,
            risk_score=35.0,
        ),
        "JOB-02-002": Job(
            id="JOB-02-002",
            piece_id="PIECE-02",
            shop_id="SHOP-B",
            required_capability="inspection",
            candidate_workcenter_ids=["WC-B2"],
            assigned_workcenter_id=None,
            base_duration_shifts=1,
            remaining_duration_shifts=1,
            setup_time_shifts=0,
            transport_delay_shifts=0,
            dependency_ids=["JOB-02-001"],
            priority=40,
            due_shift=10,
            risk_score=8.0,
        ),
    }
    jobs["JOB-01-001"].dependent_job_ids.append("JOB-01-002")
    jobs["JOB-02-001"].dependent_job_ids.append("JOB-02-002")
    pieces = {
        "PIECE-01": PuzzlePiece(
            id="PIECE-01",
            name="Job 01 - Alpha",
            job_ids=["JOB-01-001", "JOB-01-002"],
            total_job_count=2,
        ),
        "PIECE-02": PuzzlePiece(
            id="PIECE-02",
            name="Job 02 - Beta",
            job_ids=["JOB-02-001", "JOB-02-002"],
            total_job_count=2,
        ),
    }
    state = SimulationState(
        scenario_id="SCN-UNIT",
        seed=42,
        deadline_shift=12,
        shifts_per_day=3,
        shops=shops,
        workcenters=workcenters,
        pieces=pieces,
        jobs=jobs,
        event_timeline=[],
        campaign_decision_graph=CampaignDecisionGraph(max_active_cards_per_day=3),
    )
    if update_metrics:
        update_state_metrics(state)
    return state


def make_scenario(state: SimulationState | None = None) -> Scenario:
    """Wrap a hand-built state in a Scenario for initialize_state tests."""
    state = state or make_state()
    return Scenario(
        scenario_id=state.scenario_id,
        seed=state.seed,
        shops=state.shops,
        workcenters=state.workcenters,
        pieces=state.pieces,
        jobs=state.jobs,
        event_timeline=state.event_timeline,
        deadline_shift=state.deadline_shift,
        decision_cards=state.decision_cards,
        campaign_decision_graph=state.campaign_decision_graph,
    )


def make_event(
    event_id: str = "EVT-0001",
    event_type: EventType = EventType.MISSING_MATERIAL,
    target_type: TargetType = TargetType.JOB,
    target_id: str = "JOB-01-001",
    **overrides: Any,
) -> Event:
    """Return a compact event object."""
    values = {
        "id": event_id,
        "type": event_type,
        "target_type": target_type,
        "target_id": target_id,
        "start_shift": 2,
        "duration_shifts": 3,
        "severity": 3,
        "has_advance_warning": False,
        "warning_shift": None,
        "description": f"{event_type.value} for {target_id}",
    }
    values.update(overrides)
    return Event(**values)


def make_unexpected_job_event(event_id: str = "EVT-NEW", **overrides: Any) -> Event:
    """Return the standard unexpected-job request event used by tests."""
    return make_event(
        event_id,
        event_type=EventType.UNEXPECTED_JOB,
        target_type=TargetType.CAPABILITY,
        target_id="NEW_JOB",
        **overrides,
    )


def make_choice(
    choice_id: str = "A",
    effect_type: str = "note",
    **overrides: Any,
) -> DecisionChoice:
    """Return a decision choice for effect/scoring tests."""
    immediate_effects = dict(overrides.pop("immediate_effects", {"type": effect_type}))
    return DecisionChoice(
        id=choice_id,
        label=overrides.pop("label", f"{effect_type} choice"),
        description=overrides.pop("description", "Choice description"),
        immediate_effects=immediate_effects,
        risk_effect=overrides.pop("risk_effect", 0),
        reschedule_effect=overrides.pop("reschedule_effect", 0),
        next_card_id=overrides.pop("next_card_id", None),
        future_unlock_card_ids=overrides.pop("future_unlock_card_ids", []),
        branch_tags_added=overrides.pop("branch_tags_added", []),
        score_delta=overrides.pop("score_delta", 0.0),
    )


def make_card(
    card_id: str = "CARD-1",
    target_ids: list[str] | None = None,
    choices: list[DecisionChoice] | None = None,
    **overrides: Any,
) -> DecisionCard:
    """Return a decision card for graph and choice-effect tests."""
    return DecisionCard(
        id=card_id,
        day=overrides.pop("day", 1),
        type=overrides.pop("card_type", DecisionType.CRITICAL_PATH),
        title=overrides.pop("title", "Unit Card"),
        description=overrides.pop("description", "Unit decision"),
        target_ids=list(target_ids or ["JOB-01-001"]),
        severity=overrides.pop("severity", 3),
        choices=choices or [make_choice()],
        echo_choice_id=overrides.pop("echo_choice_id", None),
        required_tags=overrides.pop("required_tags", []),
        excluded_tags=overrides.pop("excluded_tags", []),
        campaign_priority=overrides.pop("campaign_priority", 100),
    )
