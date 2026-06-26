"""Hidden ECHO decision policy used by the benchmark run."""

from __future__ import annotations

import copy
import math

from .config import GameConfig
from .decisions import active_decision_cards, apply_choice, score_echo_choice, select_echo_choice
from .enums import DecisionType, EventType, JobStatus, TargetType, WorkCenterStatus
from .metrics import calculate_snapshot, update_state_metrics
from .models import DecisionCard, DecisionChoice, Event, Job, SimulationState
from .schedulers.automated import AutomatedScheduler
from .schedulers.base import downstream_count
from .simulation import advance_day


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
    """Choose ECHO's response from the campaign graph and a live-board forecast."""
    graph = graph or state.decision_cards
    update_state_metrics(state)
    scored = []
    for choice in card.choices:
        static_score = score_echo_choice(choice, graph) * 0.65
        live_score = _live_operational_score(state, card, choice)
        forecast_score = _forecast_choice_score(state, card, choice, config)
        scored.append((forecast_score + live_score + static_score, choice.id, choice))
    return min(scored, key=lambda item: (item[0], item[1]))[2]


def _forecast_choice_score(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    config: GameConfig,
) -> float:
    """Score a choice by applying it to a clone and advancing a short horizon."""
    if config.echo_choice_lookahead_days <= 0:
        return 0.0
    projected = copy.deepcopy(state)
    projected_card = projected.decision_cards.get(card.id)
    if not projected_card:
        return 0.0
    projected_choice = next((candidate for candidate in projected_card.choices if candidate.id == choice.id), None)
    if not projected_choice:
        return math.inf

    try:
        baseline = select_echo_choice(projected_card, projected.decision_cards)
        apply_choice(projected, projected_card, projected_choice, actor="ECHO-forecast", echo_choice=baseline)
        scheduler = AutomatedScheduler()
        for _ in range(config.echo_choice_lookahead_days):
            if projected.final_item_completed or projected.current_shift >= projected.deadline_shift:
                break
            _apply_static_echo_choices(projected, config)
            advance_day(projected, scheduler)
    except Exception:
        return math.inf

    snapshot = calculate_snapshot(projected)
    completion_shift = projected.completion_shift or snapshot.projected_completion_shift
    deadline_overrun = max(0, completion_shift - projected.deadline_shift)
    deadline_margin = projected.deadline_shift - completion_shift
    return (
        snapshot.jobs_remaining * 95.0
        + deadline_overrun * 22.0
        + snapshot.jobs_behind_schedule * 12.0
        + snapshot.jobs_late * 10.0
        + snapshot.schedule_risk * 3.4
        + snapshot.reschedules * 1.1
        + snapshot.idle_time * 0.02
        - snapshot.jobs_completed * 5.0
        - snapshot.pieces_completed * 18.0
        - max(0, deadline_margin) * 1.6
    )


def _apply_static_echo_choices(state: SimulationState, config: GameConfig) -> None:
    """Answer projection-only cards with the static campaign scorer."""
    selected: dict[str, str] = {}
    for _ in range(max(8, config.echo_choice_projection_limit)):
        cards = active_decision_cards(state, state.current_day, selected)
        open_cards = [
            card
            for card in cards
            if card.id not in selected and card.id not in state.campaign_selected_choices
        ]
        if not open_cards:
            return
        for card in open_cards[: config.echo_choice_projection_limit]:
            choice = select_echo_choice(card, state.decision_cards)
            apply_choice(state, card, choice, actor="ECHO-forecast", echo_choice=choice)
            selected[card.id] = choice.id


def _live_operational_score(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
) -> float:
    """Return a low-is-good live-board score for one choice."""
    effect_type = str(choice.immediate_effects.get("type", "note"))
    jobs = _jobs_for_card(state, card)
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


def _jobs_for_card(state: SimulationState, card: DecisionCard) -> list[Job]:
    """Expand a decision card into affected jobs without mutating state."""
    jobs: list[Job] = []
    for target_id in card.target_ids:
        if target_id in state.jobs:
            jobs.append(state.jobs[target_id])
        elif target_id in state.shops:
            jobs.extend(
                job
                for job in state.jobs.values()
                if job.shop_id == target_id and not job.is_complete and job.status != JobStatus.RUNNING
            )
        elif target_id in state.pieces:
            jobs.extend(state.jobs[job_id] for job_id in state.pieces[target_id].job_ids if job_id in state.jobs)
        elif target_id.startswith("EVT-"):
            event = _event_by_id(state, target_id)
            if event:
                jobs.extend(_jobs_for_event(state, event))
    if not jobs:
        jobs = state.get_critical_path_jobs()[:6] or state.get_ready_jobs()[:6]
    live_jobs = list({job.id: job for job in jobs if not job.is_complete}.values())
    if not live_jobs:
        live_jobs = state.get_critical_path_jobs()[:6] or state.get_ready_jobs()[:6]
    return sorted(
        live_jobs,
        key=lambda job: (job.critical_path, job.risk_score, job.priority),
        reverse=True,
    )


def _jobs_for_event(state: SimulationState, event: Event) -> list[Job]:
    """Expand an event target into affected jobs."""
    piece_id = event.effects.get("unexpected_piece_id")
    if piece_id in state.pieces:
        return [state.jobs[job_id] for job_id in state.pieces[piece_id].job_ids if job_id in state.jobs]
    if event.target_type == TargetType.JOB and event.target_id in state.jobs:
        return [state.jobs[event.target_id]]
    if event.target_type == TargetType.PIECE and event.target_id in state.pieces:
        return [state.jobs[job_id] for job_id in state.pieces[event.target_id].job_ids if job_id in state.jobs]
    if event.target_type == TargetType.SHOP and event.target_id in state.shops:
        return [job for job in state.jobs.values() if job.shop_id == event.target_id and not job.is_complete]
    if event.target_type == TargetType.WORKCENTER and event.target_id in state.workcenters:
        wc = state.workcenters[event.target_id]
        ids = list(wc.queue)
        if wc.current_job_id:
            ids.append(wc.current_job_id)
        return [state.jobs[job_id] for job_id in ids if job_id in state.jobs]
    return []


def _reroute_value(state: SimulationState, jobs: list[Job]) -> float:
    """Estimate how much rerouting can help affected jobs."""
    value = 0.0
    for job in jobs[:5]:
        current_wc = state.workcenters.get(job.assigned_workcenter_id) if job.assigned_workcenter_id else None
        best = _best_open_alternate(state, job)
        if not best:
            continue
        if current_wc and current_wc.status in {WorkCenterStatus.DOWN, WorkCenterStatus.BLOCKED, WorkCenterStatus.WEATHER_IMPACTED}:
            value += 20.0
        current_load = _workcenter_load(current_wc) if current_wc else 4
        value += max(0.0, current_load - _workcenter_load(best)) * 6.0
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
    if event.type in {
        EventType.MISSING_MATERIAL,
        EventType.DELAYED_MATERIAL,
        EventType.INSPECTION_DELAY,
        EventType.SUPPLIER_ESCALATION,
        EventType.LOGISTICS_BACKLOG,
        EventType.CERTIFICATION_AUDIT,
        EventType.ENGINEERING_HOLD,
    }:
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
        if wc.status in {WorkCenterStatus.DOWN, WorkCenterStatus.BLOCKED, WorkCenterStatus.WEATHER_IMPACTED}:
            continue
        candidates.append(wc)
    if not candidates:
        return None
    return min(candidates, key=lambda wc: (_workcenter_load(wc), -wc.efficiency, wc.id))


def _workcenter_load(wc) -> int:
    """Return queued-plus-running load for a workcenter-like object."""
    if not wc:
        return 999
    return len(wc.queue) + (1 if wc.current_job_id else 0)


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


def _event_by_id(state: SimulationState, event_id: object) -> Event | None:
    """Find an event by id."""
    if not isinstance(event_id, str):
        return None
    return next((event for event in state.event_timeline if event.id == event_id), None)


def _late_stage(state: SimulationState) -> bool:
    """Return whether the run is in its final third."""
    return state.current_shift >= int(state.deadline_shift * 0.67)
