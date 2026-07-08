"""Hidden ECHO decision policy used by the benchmark run."""

from __future__ import annotations

import copy
import logging
import math

from .config import GameConfig
from .decisions import active_decision_cards, apply_choice, score_echo_choice, select_echo_choice
from .decisions.selectors import (
    _event_by_id,
    _jobs_for_card,
)
from .enums import DecisionType, EventType
from .events import JOB_BLOCKING_EVENT_TYPES
from .metrics import calculate_final_score, calculate_snapshot, update_state_metrics
from .models import DecisionCard, DecisionChoice, Event, Job, SimulationState
from .schedulers.automated import AutomatedScheduler
from .schedulers.base import downstream_count
from .simulation import advance_day


logger = logging.getLogger(__name__)


def apply_echo_decisions_for_day(
    state: SimulationState,
    config: GameConfig,
    completed_days: set[int] | None = None,
) -> int:
    """Let ECHO answer all visible decisions for the state's current day."""
    day = state.current_day
    if completed_days is not None and day in completed_days:
        return 0
    if state.final_item_completed:
        return 0

    selected: dict[str, str] = {}
    applied = 0
    max_rounds = max(32, config.max_active_decision_cards_per_day * 6)
    for _ in range(max_rounds):
        cards = active_decision_cards(state, day, selected)
        open_cards = [
            card
            for card in cards
            if card.id not in selected and card.id not in state.campaign_selected_choices
        ]
        if not open_cards:
            if completed_days is not None:
                completed_days.add(day)
            return applied
        for card in open_cards:
            choice = select_echo_choice_for_state(state, card, config, state.decision_cards)
            apply_choice(state, card, choice, actor="ECHO", echo_choice=choice)
            selected[card.id] = choice.id
            applied += 1

    if completed_days is not None:
        completed_days.add(day)
    return applied


def select_echo_choice_for_state(
    state: SimulationState,
    card: DecisionCard,
    config: GameConfig,
    graph: dict[str, DecisionCard] | None = None,
) -> DecisionChoice:
    """Choose ECHO's response from the full campaign tree and live-board forecast."""
    graph = graph or state.decision_cards
    update_state_metrics(state)
    scored = []
    tree_score_memo: dict[str, float] = {}
    for choice in card.choices:
        objective = _forecast_choice_objective(state, card, choice, config, graph, tree_score_memo)
        scored.append((objective, choice.id, choice))
    return min(scored, key=lambda item: (item[0], item[1]))[2]


def _forecast_choice_objective(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    config: GameConfig,
    graph: dict[str, DecisionCard],
    tree_score_memo: dict[str, float],
) -> tuple[float, ...]:
    """Rank a choice by projected finish first, then projected final score."""
    heuristic_score = _heuristic_choice_score(state, card, choice, graph, tree_score_memo)
    projected = copy.deepcopy(state)
    projected_card = projected.decision_cards.get(card.id)
    if not projected_card:
        logger.warning(
            "ECHO forecast skipped because card %s was missing from projected state for day %s, seed %s.",
            card.id,
            state.current_day,
            state.seed,
        )
        return _failed_forecast_objective(heuristic_score)
    projected_choice = next((candidate for candidate in projected_card.choices if candidate.id == choice.id), None)
    if not projected_choice:
        logger.warning(
            "ECHO forecast skipped because choice %s on card %s was missing from projected state for day %s, seed %s.",
            choice.id,
            card.id,
            state.current_day,
            state.seed,
        )
        return _failed_forecast_objective(heuristic_score)

    try:
        baseline = select_echo_choice(projected_card)
        apply_choice(projected, projected_card, projected_choice, actor="ECHO-forecast", echo_choice=baseline)
        scheduler = AutomatedScheduler()
        day_limit = config.echo_choice_lookahead_days if config.echo_choice_lookahead_days > 0 else None
        days_advanced = 0
        while projected.current_shift < projected.deadline_shift and not projected.final_item_completed:
            if day_limit is not None and days_advanced >= day_limit:
                break
            if projected.final_item_completed or projected.current_shift >= projected.deadline_shift:
                break
            _apply_static_echo_choices(projected, config)
            advance_day(projected, scheduler)
            days_advanced += 1
    except Exception:
        logger.exception(
            "ECHO forecast failed for card %s choice %s on day %s, seed %s; falling back to heuristic score.",
            card.id,
            choice.id,
            state.current_day,
            state.seed,
        )
        return _failed_forecast_objective(heuristic_score)

    snapshot = calculate_snapshot(projected)
    completion_shift = projected.completion_shift or snapshot.projected_completion_shift
    final_score = calculate_final_score(projected)
    completion_rank = 0.0 if projected.final_item_completed else 1.0
    return (
        completion_rank,
        float(completion_shift),
        -final_score,
        float(snapshot.jobs_remaining),
        float(snapshot.jobs_late),
        float(snapshot.jobs_behind_schedule),
        float(snapshot.reschedules),
        float(snapshot.idle_time),
        float(snapshot.schedule_risk),
        heuristic_score,
    )


def _apply_static_echo_choices(state: SimulationState, config: GameConfig) -> None:
    """Answer projection-only cards with the static campaign scorer."""
    selected: dict[str, str] = {}
    max_rounds = max(8, len(state.decision_cards), config.echo_choice_projection_limit)
    for _ in range(max_rounds):
        cards = active_decision_cards(state, state.current_day, selected)
        open_cards = [
            card
            for card in cards
            if card.id not in selected and card.id not in state.campaign_selected_choices
        ]
        if not open_cards:
            return
        if config.echo_choice_projection_limit > 0:
            cards_to_apply = open_cards[: config.echo_choice_projection_limit]
        else:
            cards_to_apply = open_cards
        for card in cards_to_apply:
            choice = select_echo_choice(card)
            apply_choice(state, card, choice, actor="ECHO-forecast", echo_choice=choice)
            selected[card.id] = choice.id


def _heuristic_choice_score(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    graph: dict[str, DecisionCard],
    tree_score_memo: dict[str, float],
) -> float:
    """Return the low-is-good fallback score used when projection cannot finish."""
    static_score = score_echo_choice(choice, graph, tree_score_memo) * 0.65
    live_score = _live_operational_score(state, card, choice)
    return live_score + static_score


def _failed_forecast_objective(heuristic_score: float) -> tuple[float, ...]:
    """Keep failed projections deterministic and worse than valid projections."""
    return (
        2.0,
        math.inf,
        math.inf,
        math.inf,
        math.inf,
        math.inf,
        math.inf,
        math.inf,
        math.inf,
        heuristic_score,
    )


def _live_operational_score(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
) -> float:
    """Return a low-is-good live-board score for one choice."""
    effect_type = str(choice.immediate_effects.get("type", "note"))
    jobs = _jobs_for_card(state, card, fallback_limit=6)
    event = _event_for_choice(state, choice) or _event_for_card(state, card)
    score = choice.risk_effect * 10.0 + choice.reschedule_effect * 3.0

    if effect_type == "wait":
        score += 18.0 + card.severity * 5.0 + _target_pressure(state, jobs) * 0.6
    elif effect_type == "defer":
        score += 8.0 if any(job.critical_path for job in jobs) else -2.0
    elif effect_type == "protect_critical":
        if card.type in {DecisionType.CRITICAL_PATH, DecisionType.COMPLETION_READINESS} and any(job.critical_path for job in jobs):
            score -= 30.0
            score -= min(18.0, sum(downstream_count(state, job) for job in jobs[:4]) * 1.8)
        else:
            score += 9.0
    elif effect_type == "reroute":
        score -= _reroute_value(state, jobs)
        if card.type == DecisionType.CRITICAL_PATH and not (
            event and event.id in state.active_events
        ):
            score += 10.0
    elif effect_type == "split_capacity":
        score -= _queue_pressure_value(state, card, jobs)
    elif effect_type == "pull_forward":
        score -= 16.0 if state.get_available_workcenters() and state.get_ready_jobs() else 0.0
    elif effect_type == "expedite_event":
        score -= _event_expedite_value(state, event)
    elif effect_type == "preempt":
        score -= 18.0 if any(job.critical_path or job.priority >= 88 for job in jobs) else 0.0
        if card.type == DecisionType.CRITICAL_PATH:
            score -= 8.0
    elif effect_type == "echo_recommendation":
        score -= 16.0
    elif effect_type == "prioritize_new_job":
        score += 10.0 if _late_stage(state) else -4.0
    elif effect_type == "backlog_new_job":
        score -= 5.0 if _late_stage(state) else 8.0

    if card.type == DecisionType.COMPLETION_READINESS and effect_type in {"protect_critical", "pull_forward", "resequence"}:
        score -= 14.0
    if card.type == DecisionType.IDLE_WORKCENTER and effect_type == "wait":
        score += 12.0
    if event and event.id in state.active_events and effect_type in {"expedite_event", "reroute", "split_capacity"}:
        score -= 8.0
    if event and event.id in state.known_warnings and effect_type in {"expedite_event", "reroute", "resequence"}:
        score -= 5.0

    return score


def _reroute_value(state: SimulationState, jobs: list[Job]) -> float:
    """Estimate how much rerouting can help affected jobs."""
    value = 0.0
    for job in jobs[:5]:
        current_wc = state.workcenters.get(job.assigned_workcenter_id) if job.assigned_workcenter_id else None
        best = _best_open_alternate(state, job)
        if not best:
            continue
        if current_wc and current_wc.is_disrupted:
            value += 20.0
        current_load = current_wc.load if current_wc else 4
        value += max(0.0, current_load - best.load) * 6.0
        if job.critical_path:
            value += 10.0
    return min(38.0, value)


def _queue_pressure_value(state: SimulationState, card: DecisionCard, jobs: list[Job]) -> float:
    """Estimate the value of splitting congested capacity."""
    shop_pressure = 0.0
    for target_id in card.target_ids:
        if target_id in state.shops:
            shop = state.shops[target_id]
            shop_pressure += len(shop.queued_job_ids) * 4.0 + len(shop.blocked_job_ids) * 7.0
    movable = sum(1 for job in jobs[:8] if _best_open_alternate(state, job) is not None)
    return min(42.0, shop_pressure + movable * 5.0)


def _event_expedite_value(state: SimulationState, event: Event | None) -> float:
    """Estimate whether expediting an event is worthwhile."""
    if not event:
        return 4.0
    value = event.severity * 6.0 + event.duration_shifts * 3.0
    if event.id in state.active_events:
        value += 12.0
    if event.type in JOB_BLOCKING_EVENT_TYPES | {EventType.ENGINEERING_HOLD}:
        value += 10.0
    return min(44.0, value)


def _target_pressure(state: SimulationState, jobs: list[Job]) -> float:
    """Return a compact pressure score for a set of affected jobs."""
    pressure = 0.0
    for job in jobs[:8]:
        slack = job.due_shift - state.current_shift - max(1, job.remaining_duration_shifts)
        pressure += max(0, 8 - slack)
        pressure += 9 if job.critical_path else 0
        pressure += 7 if job.is_blocked else 0
        pressure += min(8, job.queue_time)
    return pressure


def _best_open_alternate(state: SimulationState, job: Job):
    """Return a usable alternate workcenter for a job, if one exists."""
    candidates = []
    for wc_id in job.candidate_workcenter_ids:
        if wc_id not in state.workcenters:
            continue
        wc = state.workcenters[wc_id]
        if wc.id == job.assigned_workcenter_id:
            continue
        if job.required_capability not in wc.capabilities:
            continue
        if wc.is_disrupted:
            continue
        candidates.append(wc)
    if not candidates:
        return None
    return min(candidates, key=lambda wc: (wc.load, -wc.efficiency, wc.id))


def _event_for_choice(state: SimulationState, choice: DecisionChoice) -> Event | None:
    """Return the event explicitly referenced by a choice."""
    return _event_by_id(state, choice.immediate_effects.get("event_id"))


def _event_for_card(state: SimulationState, card: DecisionCard) -> Event | None:
    """Return the first event referenced by a decision card."""
    for target_id in card.target_ids:
        event = _event_by_id(state, target_id)
        if event:
            return event
    return None


def _late_stage(state: SimulationState) -> bool:
    """Return whether the run is in its final third."""
    return state.current_shift >= int(state.deadline_shift * 0.67)
