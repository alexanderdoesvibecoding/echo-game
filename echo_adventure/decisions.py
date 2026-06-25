"""Daily decision-card generation and player choice effects."""

from __future__ import annotations

import hashlib
import random

from .config import GameConfig
from .enums import DecisionType, EventType, JobStatus, TargetType, WorkCenterStatus
from .events import insert_unexpected_job, schedule_follow_on_event
from .metrics import update_state_metrics
from .models import (
    DecisionCard,
    DecisionChoice,
    DecisionRecord,
    DecisionProgress,
    Event,
    Job,
    Shop,
    SimulationState,
    WorkCenter,
)


def generate_decision_graph(
    state: SimulationState,
    config: GameConfig,
) -> tuple[dict[str, DecisionCard], dict[int, list[str]], dict[int, int]]:
    """Prepare all daily decision paths once at scenario creation."""
    cards: dict[str, DecisionCard] = {}
    roots_by_day: dict[int, list[str]] = {}
    counts_by_day: dict[int, int] = {}
    for day in range(1, config.total_days + 1):
        _prime_graph_state_for_day(state, day, config)
        day_cards = _generate_root_decision_cards(state, day, config)
        counts_by_day[day] = len(day_cards)
        if not day_cards:
            roots_by_day[day] = []
            continue
        root = day_cards[0]
        root.id = f"DAY-{day:02d}-Q01"
        root.parent_card_id = None
        root.parent_choice_id = None
        cards[root.id] = root
        roots_by_day[day] = [root.id]
        _attach_next_question_cards(
            root,
            cards,
            day=day,
            question_number=2,
            total_questions=len(day_cards),
            question_templates=day_cards[1:],
        )
    for card in cards.values():
        card.echo_choice_id = select_echo_choice(card, cards).id
    return cards, roots_by_day, counts_by_day


def generate_decision_cards(
    state: SimulationState,
    day: int,
    config: GameConfig | None = None,
) -> list[DecisionCard]:
    """Return the deterministic daily card templates for one day.

    This helper is intentionally smaller than the branching graph builder: it
    exposes the player-facing card pool used for that day without attaching the
    answer-specific next-card tree.
    """
    if config is None:
        config = GameConfig()
    _prime_graph_state_for_day(state, day, config)
    return _generate_root_decision_cards(state, day, config)


def active_decision_cards(
    state: SimulationState,
    day: int,
    selected_choices: dict[str, str],
) -> list[DecisionCard]:
    """Return the currently visible daily questions."""
    cards: list[DecisionCard] = []
    question_limit = state.daily_decision_counts.get(day, 0)
    for root_id in state.daily_decision_roots.get(day, []):
        card_id: str | None = root_id
        visited: set[str] = set()
        while card_id and card_id not in visited and len(cards) < question_limit:
            visited.add(card_id)
            card = state.decision_cards.get(card_id)
            if not card:
                break
            cards.append(card)
            choice_id = selected_choices.get(card.id)
            if not choice_id:
                break
            choice = next((candidate for candidate in card.choices if candidate.id == choice_id), None)
            card_id = choice.next_card_id if choice else None
    return cards


def decision_progress(
    state: SimulationState,
    day: int,
    selected_choices: dict[str, str],
) -> DecisionProgress:
    """Return progress through the day's fixed number of questions."""
    total_questions = state.daily_decision_counts.get(day, len(state.daily_decision_roots.get(day, [])))
    visible = 0
    answered = 0
    open_card_ids: list[str] = []

    for root_id in state.daily_decision_roots.get(day, []):
        card_id: str | None = root_id
        visited: set[str] = set()
        while card_id and card_id not in visited and visible < total_questions:
            visited.add(card_id)
            card = state.decision_cards.get(card_id)
            if not card:
                break
            visible += 1
            choice_id = selected_choices.get(card.id)
            if not choice_id:
                open_card_ids.append(card.id)
                break
            answered += 1
            if answered >= total_questions:
                break
            choice = next((candidate for candidate in card.choices if candidate.id == choice_id), None)
            if not choice or not choice.next_card_id or choice.next_card_id not in state.decision_cards:
                break
            card_id = choice.next_card_id

    return DecisionProgress(
        day=day,
        total_questions=total_questions,
        answered_questions=min(answered, total_questions),
        visible_cards=visible,
        open_card_ids=open_card_ids,
    )


def select_echo_choice(card: DecisionCard, graph: dict[str, DecisionCard] | None = None) -> DecisionChoice:
    """Return the benchmark choice ECHO treats as the correct response."""
    if graph is None and card.echo_choice_id:
        selected = next((choice for choice in card.choices if choice.id == card.echo_choice_id), None)
        if selected:
            return selected
    return min(
        card.choices,
        key=lambda choice: (_choice_path_score(choice, graph), choice.id),
    )


def _choice_path_score(choice: DecisionChoice, graph: dict[str, DecisionCard] | None) -> float:
    """Score a choice plus its best downstream decision path for ECHO."""
    effect_rank = {
        "echo_recommendation": 0,
        "expedite_event": 1,
        "protect_critical": 2,
        "reroute": 3,
        "split_capacity": 4,
        "pull_forward": 5,
        "prioritize_new_job": 5,
        "resequence": 6,
        "backlog_new_job": 8,
        "preempt": 7,
        "defer": 8,
        "wait": 9,
    }
    immediate = (
        choice.risk_effect * 12
        + effect_rank.get(choice.immediate_effects.get("type", "note"), 20) * 3
        + choice.reschedule_effect * 4
        + choice.cost_effect * 0.08
    )
    if not graph or not choice.next_card_id or choice.next_card_id not in graph:
        return immediate
    child = graph[choice.next_card_id]
    return immediate + min(_choice_path_score(child_choice, graph) for child_choice in child.choices) * 0.9


def _generate_root_decision_cards(state: SimulationState, day: int, config: GameConfig | None = None) -> list[DecisionCard]:
    """Generate root cards used as fixed daily decision threads."""
    if config is None:
        config = GameConfig()
        update_state_metrics(state)
    rng = _decision_rng(state, day, config)
    target_count = rng.randint(config.min_decisions_per_day, config.max_decisions_per_day)
    selected: list[DecisionCard] = []
    candidate_pool: list[DecisionCard] = []

    # Keep the most urgent visible disruption in front of the player, then let
    # the rest compete with operational tradeoffs so later questions vary.
    visible_events = _visible_events(state)
    if visible_events:
        selected.append(_event_card(state, visible_events[0], 1, day))
        for event in visible_events[1:]:
            candidate_pool.append(_event_card(state, event, len(candidate_pool) + 1, day))

    candidate_pool.extend(_operational_decision_candidates(state, day, len(candidate_pool) + 1))
    candidate_pool = [card for card in candidate_pool if not _duplicates_any_card(selected, card)]
    candidate_pool.sort(key=lambda card: (rng.random() - card.severity * 0.14, card.type.value, card.title))

    for card in candidate_pool:
        if len(selected) >= target_count:
            break
        if _duplicates_any_card(selected, card):
            continue
        selected.append(card)

    if not selected:
        selected.append(_strategic_card(state, 1, day))
    while len(selected) < target_count:
        selected.append(_fallback_strategic_card(state, len(selected) + 1, day))
    return _renumber_decision_cards(selected, day)


def _operational_decision_candidates(state: SimulationState, day: int, start_ordinal: int = 1) -> list[DecisionCard]:
    """Build the broader daily candidate pool before seeded selection."""
    cards: list[DecisionCard] = []

    def add(card: DecisionCard | None) -> None:
        if card:
            cards.append(card)

    for shop in state.get_bottleneck_shops(3):
        pressure = len(shop.queued_job_ids) + len(shop.blocked_job_ids) * 2
        if pressure >= 2:
            add(_bottleneck_card(state, shop, start_ordinal + len(cards), day))
        if len(shop.queued_job_ids) >= 3:
            add(_queue_congestion_card(state, shop, start_ordinal + len(cards), day))

    for job in state.get_critical_path_jobs()[:3]:
        add(_critical_path_card(state, job, start_ordinal + len(cards), day))

    for job in _alternate_routing_jobs(state)[:3]:
        add(_alternate_card(state, job, start_ordinal + len(cards), day))

    handoff = _handoff_risk_job(state)
    if handoff:
        add(_handoff_card(state, handoff, start_ordinal + len(cards), day))

    quality = _quality_triage_job(state)
    if quality:
        add(_quality_triage_card(state, quality, start_ordinal + len(cards), day))

    if _has_idle_opportunity(state):
        add(_idle_card(state, start_ordinal + len(cards), day))
    if not state.all_pieces_ready():
        add(_completion_readiness_card(state, start_ordinal + len(cards), day))

    add(_strategic_card(state, start_ordinal + len(cards), day))
    return cards


def _duplicates_any_card(cards: list[DecisionCard], candidate: DecisionCard) -> bool:
    """Return whether a candidate repeats the same player-facing pressure."""
    candidate_targets = tuple(target for target in candidate.target_ids if not str(target).startswith("EVT-"))
    candidate_target_set = set(candidate_targets)
    candidate_key = (candidate.type, candidate_targets[:2], candidate.title)
    for card in cards:
        targets = tuple(target for target in card.target_ids if not str(target).startswith("EVT-"))
        if candidate_target_set and candidate_target_set & set(targets):
            return True
        if (card.type, targets[:2], card.title) == candidate_key:
            return True
    return False


def _renumber_decision_cards(cards: list[DecisionCard], day: int) -> list[DecisionCard]:
    """Normalize template IDs after the seeded variety pass chooses an order."""
    renumbered: list[DecisionCard] = []
    for ordinal, card in enumerate(cards, start=1):
        renumbered.append(
            DecisionCard(
                id=f"DAY-{day:02d}-DEC-{ordinal}",
                day=card.day,
                type=card.type,
                title=card.title,
                description=card.description,
                target_ids=list(card.target_ids),
                severity=card.severity,
                choices=_clone_choices(card.choices),
                echo_choice_id=card.echo_choice_id,
                parent_card_id=card.parent_card_id,
                parent_choice_id=card.parent_choice_id,
            )
        )
    return renumbered


def _decision_rng(state: SimulationState, day: int, config: GameConfig) -> random.Random:
    """Return a deterministic RNG for daily decision-card generation.

    The seed includes only replay-stable inputs, so the same scenario state and
    day always produce the same daily card count. It intentionally does not use
    the module-level random generator, which can be advanced by unrelated code.
    """
    seed_material = ":".join(
        str(part)
        for part in (
            state.seed,
            state.scenario_id,
            day,
            state.current_shift,
            config.min_decisions_per_day,
            config.max_decisions_per_day,
        )
    )
    seed_int = int.from_bytes(hashlib.sha256(seed_material.encode("utf-8")).digest()[:16], "big")
    return random.Random(seed_int)


def apply_choice(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    actor: str = "player",
    echo_choice: DecisionChoice | None = None,
) -> str:
    """Apply one selected choice and return a player-facing audit note."""
    if echo_choice is None:
        echo_choice = select_echo_choice(card)
    effects = choice.immediate_effects
    effect_type = effects.get("type", "note")
    state.cost += max(0, choice.cost_effect)
    state.reschedule_count += max(0, choice.reschedule_effect)
    _apply_risk_delta(state, card, choice.risk_effect)

    if effect_type == "wait":
        note = _wait_and_absorb(state, card)
    elif effect_type == "resequence":
        note = _resequence(state, card)
    elif effect_type == "protect_critical":
        note = _protect_critical(state)
    elif effect_type == "expedite_event":
        note = _expedite_event(state, effects.get("event_id"))
    elif effect_type == "reroute":
        note = _reroute_targets(state, card)
    elif effect_type == "preempt":
        note = _preempt_for_card(state, card)
    elif effect_type == "split_capacity":
        note = _split_capacity(state, card)
    elif effect_type == "defer":
        note = _defer_lower_risk(state, card)
    elif effect_type == "pull_forward":
        note = _pull_forward_unaffected(state, card)
    elif effect_type == "echo_recommendation":
        note = _use_echo_recommendation(state, card)
    elif effect_type == "prioritize_new_job":
        note = _add_unexpected_job(state, effects.get("event_id"), prioritize=True)
    elif effect_type == "backlog_new_job":
        note = _add_unexpected_job(state, effects.get("event_id"), prioritize=False)
    else:
        note = "Recorded the scheduling preference for today."
    # Choices affect both the current board and the future event chain. The
    # forward effect is recorded after the immediate action mutates priorities.
    forward_note = _apply_forward_decision_effect(state, card, choice)
    if forward_note:
        note = f"{note} {forward_note}"
    state.daily_notes.append(note)
    state.decision_history.append(
        DecisionRecord(
            day=card.day,
            card_id=card.id,
            card_title=card.title,
            actor=actor,
            choice_id=choice.id,
            choice_label=choice.label,
            echo_choice_id=echo_choice.id if echo_choice else None,
            echo_choice_label=echo_choice.label if echo_choice else None,
            aligned_with_echo=bool(echo_choice and choice.id == echo_choice.id),
            note=note,
        )
    )
    update_state_metrics(state)
    return note


def _prime_graph_state_for_day(state: SimulationState, day: int, config: GameConfig) -> None:
    """Set deterministic event visibility for graph generation."""
    state.current_shift = max(0, (day - 1) * config.shifts_per_day)
    state.active_events = []
    state.known_warnings = []
    for event in state.event_timeline:
        event.started = event.start_shift <= state.current_shift < event.end_shift
        event.resolved = state.current_shift >= event.end_shift
        if event.started and not event.resolved:
            state.active_events.append(event.id)
        elif (
            event.has_advance_warning
            and event.warning_shift is not None
            and event.warning_shift <= state.current_shift < event.start_shift
        ):
            state.known_warnings.append(event.id)
    update_state_metrics(state)


def _attach_next_question_cards(
    parent: DecisionCard,
    cards: dict[str, DecisionCard],
    day: int,
    question_number: int,
    total_questions: int,
    question_templates: list[DecisionCard],
) -> None:
    """Create answer-specific next questions under a parent card."""
    if question_number > total_questions:
        return
    template_index = question_number - 2
    template = question_templates[template_index] if template_index < len(question_templates) else None
    for choice in parent.choices:
        child_id = f"DAY-{day:02d}-Q{question_number:02d}-{parent.id.split('-', 2)[-1]}-C{choice.id}"
        child = _next_question_card(parent, choice, child_id, question_number, template)
        choice.next_card_id = child.id
        cards[child.id] = child
        _attach_next_question_cards(child, cards, day, question_number + 1, total_questions, question_templates)


def _next_question_card(
    parent: DecisionCard,
    parent_choice: DecisionChoice,
    card_id: str,
    question_number: int,
    template: DecisionCard | None = None,
) -> DecisionCard:
    """Build the next daily decision selected by a previous answer."""
    if template:
        return DecisionCard(
            id=card_id,
            day=parent.day,
            type=template.type,
            title=f"Decision {question_number}: {template.title}",
            description=(
                f"After choosing {parent_choice.label.lower()} on the prior tradeoff, "
                f"the next scheduling issue is: {template.description}"
            ),
            target_ids=list(template.target_ids),
            severity=template.severity,
            choices=_clone_choices(template.choices),
            parent_card_id=parent.id,
            parent_choice_id=parent_choice.id,
        )

    recommended = _recommended_effect_for_card(parent)
    event_id = parent_choice.immediate_effects.get("event_id") or next(
        (target_id for target_id in parent.target_ids if isinstance(target_id, str) and target_id.startswith("EVT-")),
        None,
    )
    title = f"Decision {question_number}: {parent_choice.label}"
    description = (
        f"{parent_choice.label} changes how the team handles {parent.title.lower()}. "
        "Choose the next scheduling response for today."
    )
    choices = _next_question_choices(recommended, event_id, question_number)
    return DecisionCard(
        id=card_id,
        day=parent.day,
        type=parent.type,
        title=title,
        description=description,
        target_ids=list(parent.target_ids),
        severity=max(1, parent.severity - (1 if question_number > 2 else 0)),
        choices=choices,
        parent_card_id=parent.id,
        parent_choice_id=parent_choice.id,
    )


def _clone_choices(choices: list[DecisionChoice]) -> list[DecisionChoice]:
    """Copy choice templates without carrying branch links between cards."""
    return [
        DecisionChoice(
            id=choice.id,
            label=choice.label,
            description=choice.description,
            immediate_effects=dict(choice.immediate_effects),
            risk_effect=choice.risk_effect,
            cost_effect=choice.cost_effect,
            reschedule_effect=choice.reschedule_effect,
        )
        for choice in choices
    ]


def _next_question_choices(
    recommended_effect: str,
    event_id: str | None,
    question_number: int,
) -> list[DecisionChoice]:
    """Return a compact set of choices for a next-question card."""
    event_payload = {"event_id": event_id} if event_id else {}
    risk_bonus = 1 if question_number > 2 else 0
    recommended_label = _effect_label(recommended_effect)
    return [
        DecisionChoice(
            id="1",
            label=f"Commit to {recommended_label}",
            description="Keep the response focused on the highest-leverage work and give it priority through the remaining shifts.",
            immediate_effects={"type": recommended_effect, **event_payload},
            risk_effect=-6 + risk_bonus,
            cost_effect=10 + question_number * 4,
            reschedule_effect=1,
        ),
        DecisionChoice(
            id="2",
            label="Broaden the recovery move",
            description="Use the same response pattern on adjacent work so the related queue does not become tomorrow's constraint.",
            immediate_effects={"type": "pull_forward", **event_payload},
            risk_effect=-4 + risk_bonus,
            cost_effect=14 + question_number * 5,
            reschedule_effect=2,
        ),
        DecisionChoice(
            id="3",
            label="Limit churn",
            description="Take the smallest possible action and preserve the current sequence unless the board gets worse.",
            immediate_effects={"type": "resequence", **event_payload},
            risk_effect=-1 + risk_bonus,
            cost_effect=4,
            reschedule_effect=1,
        ),
        DecisionChoice(
            id="4",
            label="Stand down",
            description="Stop adding interventions today and accept that unresolved pressure may affect later work.",
            immediate_effects={"type": "wait", **event_payload},
            risk_effect=3 + question_number,
            cost_effect=0,
            reschedule_effect=0,
        ),
    ]


def _recommended_effect_for_card(card: DecisionCard) -> str:
    """Choose the response ECHO should prefer for a card category."""
    if card.type in {DecisionType.MACHINE_DOWN, DecisionType.ALTERNATE_ROUTING}:
        return "reroute"
    if card.type in {
        DecisionType.MISSING_MATERIAL,
        DecisionType.INSPECTION_DELAY,
        DecisionType.ENGINEERING_HOLD,
    }:
        return "expedite_event"
    if card.type in {DecisionType.BOTTLENECK, DecisionType.QUEUE_CONGESTION}:
        return "split_capacity"
    if card.type == DecisionType.IDLE_WORKCENTER:
        return "pull_forward"
    if card.type == DecisionType.ECHO_RECOMMENDATION:
        return "echo_recommendation"
    if card.type == DecisionType.UNEXPECTED_JOB:
        return "prioritize_new_job"
    return "protect_critical"


def _effect_label(effect_type: str) -> str:
    """Return short player-facing text for a decision effect."""
    return {
        "echo_recommendation": "ECHO's recommendation",
        "expedite_event": "expedite recovery",
        "protect_critical": "critical-path protection",
        "reroute": "alternate routing",
        "split_capacity": "split capacity",
        "pull_forward": "pull-forward work",
        "prioritize_new_job": "prioritize the new job",
        "backlog_new_job": "backlog the new job",
        "resequence": "resequence queues",
        "preempt": "preemption",
        "defer": "deferred work",
        "wait": "waiting",
    }.get(effect_type, "the response")


def _visible_events(state: SimulationState) -> list[Event]:
    """Return active/warned events ordered by urgency for card generation."""
    ids = list(dict.fromkeys(state.active_events + state.known_warnings))
    events = [event for event in state.event_timeline if event.id in ids and not event.resolved]
    return sorted(
        events,
        key=lambda event: (
            0 if event.type == EventType.UNEXPECTED_JOB else 1,
            0 if event.id in state.active_events else 1,
            -event.severity,
            event.start_shift,
        ),
    )


def _capability_label(capability: str) -> str:
    """Return a readable capability name for decision text."""
    return capability.replace("_", " ")


def _job_state_phrase(state: SimulationState, job: Job) -> str:
    """Summarize a job state without exposing hidden scoring values."""
    if job.is_blocked:
        return "blocked by an active constraint"
    if job.status == JobStatus.RUNNING:
        return "already running"
    if job.status == JobStatus.QUEUED:
        return "queued and waiting for a workcenter opening"
    if job.status == JobStatus.SCHEDULED:
        return "scheduled but not yet started"
    if job.status == JobStatus.READY:
        return "ready to release"
    if not state.is_dependency_complete(job.id):
        return "waiting on predecessor work"
    return "not yet committed to the active queue"


def _slack_phrase(state: SimulationState, job: Job) -> str:
    """Describe schedule slack qualitatively."""
    slack = job.due_shift - state.current_shift - job.remaining_duration_shifts
    if slack < 0:
        return "its planning buffer is already gone"
    if slack <= 2:
        return "it has very little slack left"
    if slack <= 6:
        return "its slack is tightening"
    return "it still has some schedule room"


def _assigned_location_phrase(state: SimulationState, job: Job) -> str:
    """Describe the current assignment or best-known routing context."""
    if job.assigned_workcenter_id and job.assigned_workcenter_id in state.workcenters:
        wc = state.workcenters[job.assigned_workcenter_id]
        return f"currently tied to {wc.name}"
    shop = state.shops.get(job.shop_id)
    if shop:
        return f"planned through {shop.name}"
    return "not tied to a specific workcenter"


def _job_context(state: SimulationState, job: Job) -> str:
    """Build a compact operational context sentence for a job."""
    detail = [
        (
            f"The subjob is {_job_state_phrase(state, job)}; "
            f"{_slack_phrase(state, job)}, and it is {_assigned_location_phrase(state, job)}."
        )
    ]
    if job.critical_path:
        detail.append("It is on the critical path, so delays here can hold dependent work in place.")
    elif job.dependent_job_ids:
        detail.append("It unlocks downstream work once completed.")
    return " ".join(detail)


def _event_context(state: SimulationState, event: Event, status: str) -> str:
    """Describe why an event matters for the current operating board."""
    if event.type == EventType.UNEXPECTED_JOB:
        timing = "active now" if status == "active" else "visible as an advance warning"
        return (
            f"This request is {timing}; accepting it adds another top-level job "
            f"beyond the initial {len(state.pieces)} jobs."
        )
    jobs = _jobs_for_event(state, event)
    timing = "active now" if status == "active" else "visible as an advance warning"
    if not jobs:
        return f"This issue is {timing}; the response you choose can change how much pressure reaches later days."

    has_critical = any(job.critical_path for job in jobs)
    has_blocked = any(job.is_blocked for job in jobs)
    has_ready = any(job.status in {JobStatus.READY, JobStatus.QUEUED, JobStatus.SCHEDULED} for job in jobs)
    context: list[str] = [f"This issue is {timing}"]
    if has_critical:
        context.append("touching critical-path work")
    elif has_ready:
        context.append("touching work that could otherwise move today")
    else:
        context.append("touching work that feeds later dependencies")
    if has_blocked:
        context.append("with affected subjobs already blocked")
    return "; ".join(context) + "."


def _shop_pressure_description(state: SimulationState, shop: Shop) -> str:
    """Describe shop pressure without showing raw queue counts."""
    has_queued = bool(shop.queued_job_ids)
    has_blocked = bool(shop.blocked_job_ids)
    if has_queued and has_blocked:
        opening = "Queued and blocked work are both building in this shop."
    elif has_blocked:
        opening = "Blocked work is making this shop a pacing constraint."
    elif has_queued:
        opening = "Queue pressure is concentrating in this shop."
    else:
        opening = "This shop is close to becoming the next pacing constraint."

    critical_ids = {job.id for job in state.get_critical_path_jobs()}
    touches_critical = bool(critical_ids & (set(shop.queued_job_ids) | set(shop.blocked_job_ids)))
    if touches_critical:
        return f"{opening} Critical-path work is mixed into the pressure, so the next priority rule matters."
    return f"{opening} A targeted response can improve flow before downstream jobs lose more slack."


def _idle_capacity_description(state: SimulationState) -> str:
    """Describe the unused-capacity decision in operational terms."""
    ready_jobs = state.get_ready_jobs()
    critical_ready = any(job.critical_path for job in ready_jobs)
    if critical_ready:
        return "Open capacity exists while critical ready work is waiting. Pulling the right subjobs forward can convert idle time into schedule protection, but it may disturb stable queues."
    return "Open capacity exists while ready or nearly ready work is waiting. Today is a choice between filling idle stations now or keeping buffers available for disruption recovery."


def _completion_readiness_description(state: SimulationState) -> str:
    """Describe completion risk without exposing progress fractions."""
    incomplete = [piece for piece in state.pieces.values() if not piece.completed]
    if any(piece.risk_score >= 70 for piece in incomplete):
        return "Several remaining top-level jobs are close to becoming pacing items. Late dependencies can still push final delivery past the deadline unless the riskiest work gets protected."
    return "The project still has unfinished top-level jobs. Late dependencies can still push final delivery past the deadline, so today is about protecting the work most likely to unlock completions."


def _event_card(state: SimulationState, event: Event, ordinal: int, day: int) -> DecisionCard:
    """Build a decision card around a specific visible event."""
    dtype = _decision_type_for_event(event.type)
    status = "active" if event.id in state.active_events else "warning"
    target = _target_name(state, event.target_type, event.target_id)
    if event.type == EventType.ECHO_RECOMMENDATION:
        return DecisionCard(
            id=f"DAY-{day:02d}-DEC-{ordinal}",
            day=day,
            type=dtype,
            title="ECHO recommendation available",
            description=(
                "An experimental ECHO recommendation is available for today's board. "
                "It will look for critical-path moves and unused capacity, but the team may lose time if the recommendation is not usable."
            ),
            target_ids=[event.target_id, event.id],
            severity=event.severity,
            choices=[
                DecisionChoice(
                    id="1",
                    label="Use ECHO recommendation",
                    description="Let ECHO propose a move that protects urgent work and pulls useful capacity forward; there is a chance the analysis produces no usable schedule change.",
                    immediate_effects={"type": "echo_recommendation", "event_id": event.id},
                    risk_effect=-8,
                    cost_effect=10,
                    reschedule_effect=1,
                ),
                DecisionChoice(
                    id="2",
                    label="Do nothing",
                    description="Keep today's manual plan intact and avoid analysis churn, accepting that the recommendation will not reduce future pressure.",
                    immediate_effects={"type": "wait", "event_id": event.id},
                    risk_effect=2,
                    cost_effect=0,
                    reschedule_effect=0,
                ),
            ],
        )
    if event.type == EventType.UNEXPECTED_JOB:
        return DecisionCard(
            id=f"DAY-{day:02d}-DEC-{ordinal}",
            day=day,
            type=dtype,
            title="Unexpected job request",
            description=(
                f"A new customer job arrived outside the initial {len(state.pieces)} jobs. "
                "Do you want to prioritize it now or add it to the back of the queue?"
            ),
            target_ids=[event.target_id, event.id],
            severity=event.severity,
            choices=[
                DecisionChoice(
                    id="1",
                    label="Prioritize the new job",
                    description="Add the new job to the submarine build and push its first subjob toward the front of a capable queue.",
                    immediate_effects={"type": "prioritize_new_job", "event_id": event.id},
                    risk_effect=-4,
                    cost_effect=28,
                    reschedule_effect=1,
                ),
                DecisionChoice(
                    id="2",
                    label="Add it to the back",
                    description="Accept the new job but give it low priority so the original schedule stays protected for now.",
                    immediate_effects={"type": "backlog_new_job", "event_id": event.id},
                    risk_effect=4,
                    cost_effect=8,
                    reschedule_effect=0,
                ),
            ],
        )
    choices = [
        DecisionChoice(
            id="1",
            label="Resequence ready work",
            description="Change the order of ready and queued work around this issue while leaving active work in place; useful when a small queue change can keep dependent work moving.",
            immediate_effects={"type": "resequence", "event_id": event.id},
            risk_effect=-5,
            cost_effect=4,
            reschedule_effect=1,
        ),
        DecisionChoice(
            id="2",
            label="Expedite resolution",
            description="Commit extra recovery effort to shorten or soften the disruption; best when the target is already blocking important work.",
            immediate_effects={"type": "expedite_event", "event_id": event.id},
            risk_effect=-9,
            cost_effect=35 + event.severity * 8,
            reschedule_effect=1,
        ),
        DecisionChoice(
            id="3",
            label="Protect critical path",
            description="Put critical dependencies ahead of routine queue work so downstream jobs are less likely to stall behind this disruption.",
            immediate_effects={"type": "protect_critical", "event_id": event.id},
            risk_effect=-7,
            cost_effect=12,
            reschedule_effect=1,
        ),
    ]
    if event.type in {
        EventType.MACHINE_DOWN,
        EventType.MISSING_MATERIAL,
        EventType.DELAYED_MATERIAL,
        EventType.INSPECTION_DELAY,
        EventType.SUPPLIER_ESCALATION,
        EventType.LOGISTICS_BACKLOG,
        EventType.TOOLING_DAMAGE,
        EventType.CERTIFICATION_AUDIT,
    }:
        choices.append(
            DecisionChoice(
                id="4",
                label="Reroute affected work",
                description="Move affected work to another capable workcenter if capacity exists; this can reduce exposure but adds setup and coordination churn.",
                immediate_effects={"type": "reroute", "event_id": event.id},
                risk_effect=-6,
                cost_effect=18,
                reschedule_effect=1,
            )
        )
    else:
        choices.append(
            DecisionChoice(
                id="4",
                label="Wait and contain",
                description="Keep the current plan stable and monitor the issue, accepting that downstream slack may tighten if the disruption lingers.",
                immediate_effects={"type": "wait", "event_id": event.id},
                risk_effect=5,
                cost_effect=0,
                reschedule_effect=0,
            )
        )
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=dtype,
        title=f"{event.type.value} {status}",
        description=f"{target}: {event.description} {_event_context(state, event, status)}",
        target_ids=[event.target_id, event.id],
        severity=event.severity,
        choices=choices,
    )


def _bottleneck_card(state: SimulationState, shop: Shop, ordinal: int, day: int) -> DecisionCard:
    """Build a card for queue pressure concentrated in one shop."""
    queued = len(shop.queued_job_ids)
    blocked = len(shop.blocked_job_ids)
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.BOTTLENECK,
        title=f"Bottleneck pressure in {shop.name}",
        description=_shop_pressure_description(state, shop),
        target_ids=[shop.id],
        severity=min(5, 1 + queued // 4 + blocked // 2),
        choices=[
            DecisionChoice(
                id="1",
                label="Split capacity",
                description="Move eligible queued work into alternate capable capacity so this shop stops carrying the whole load; expect extra coordination.",
                immediate_effects={"type": "split_capacity"},
                risk_effect=-7,
                cost_effect=16,
                reschedule_effect=2,
            ),
            DecisionChoice(
                id="2",
                label="Protect critical subjobs",
                description="Advance the work most likely to control final delivery and let lower-risk jobs wait behind it.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-8,
                cost_effect=10,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Defer low-risk work",
                description="Make room by lowering priority on work with healthier slack, keeping the shop focused on urgent dependencies.",
                immediate_effects={"type": "defer"},
                risk_effect=-3,
                cost_effect=4,
                reschedule_effect=1,
            ),
        ],
    )


def _queue_congestion_card(state: SimulationState, shop: Shop, ordinal: int, day: int) -> DecisionCard:
    """Build a card for a shop queue that needs a dispatching rule."""
    queued_jobs = [state.jobs[job_id] for job_id in shop.queued_job_ids if job_id in state.jobs]
    critical_count = sum(1 for job in queued_jobs if job.critical_path)
    description = (
        f"{shop.name} has several subjobs waiting for the same capability family. "
        "The next dispatching rule can either thin the queue, protect the riskiest work, or preserve shop stability."
    )
    if critical_count:
        description += f" {critical_count} queued subjob(s) are on or near the critical path."
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.QUEUE_CONGESTION,
        title=f"Queue congestion in {shop.name}",
        description=description,
        target_ids=[shop.id],
        severity=min(5, 2 + len(queued_jobs) // 3 + critical_count),
        choices=[
            DecisionChoice(
                id="1",
                label="Dispatch by due date",
                description="Resequence the shop queue around the nearest due dates so late starts do not pile up.",
                immediate_effects={"type": "resequence"},
                risk_effect=-4,
                cost_effect=5,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Split overloaded queue",
                description="Move eligible work to alternate capacity and accept the added coordination cost.",
                immediate_effects={"type": "split_capacity"},
                risk_effect=-6,
                cost_effect=18,
                reschedule_effect=2,
            ),
            DecisionChoice(
                id="3",
                label="Defer slack-rich jobs",
                description="Lower priority on jobs with schedule room so constrained capacity stays focused on urgent dependencies.",
                immediate_effects={"type": "defer"},
                risk_effect=-2,
                cost_effect=4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Keep shop sequence",
                description="Avoid another queue change and let the current dispatch order run, accepting continued congestion risk.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
                cost_effect=0,
                reschedule_effect=0,
            ),
        ],
    )


def _critical_path_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    """Build a card for a subjob that threatens final completion timing."""
    piece = state.pieces.get(job.piece_id)
    piece_name = piece.name if piece else "Project work"
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.CRITICAL_PATH,
        title=f"Critical path exposure on {job.id}",
        description=f"{piece_name} depends on {_capability_label(job.required_capability)} work. {_job_context(state, job)}",
        target_ids=[job.id],
        severity=5 if job.risk_score >= 70 else 4,
        choices=[
            DecisionChoice(
                id="1",
                label="Protect critical path",
                description="Lift this dependency and the downstream work it unlocks ahead of routine starts.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-8,
                cost_effect=12,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Reroute subjob",
                description="Use another capable workcenter to buy schedule room, accepting extra setup and coordination.",
                immediate_effects={"type": "reroute"},
                risk_effect=-6,
                cost_effect=20,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Preempt lower priority",
                description="Interrupt lower-priority work only if it is occupying the best capable workcenter for this dependency.",
                immediate_effects={"type": "preempt"},
                risk_effect=-7,
                cost_effect=24,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Hold sequence",
                description="Preserve the current queue order and avoid immediate churn, accepting that this critical-path item may keep losing slack.",
                immediate_effects={"type": "wait"},
                risk_effect=4,
                cost_effect=0,
                reschedule_effect=0,
            ),
        ],
    )


def _handoff_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    """Build a card around a cross-shop dependency handoff."""
    piece = state.pieces.get(job.piece_id)
    piece_name = piece.name.split(" - ", 1)[0] if piece else job.piece_id
    predecessor_names = [
        state.shops[state.jobs[dep_id].shop_id].name
        for dep_id in job.dependency_ids
        if dep_id in state.jobs and state.jobs[dep_id].shop_id in state.shops
    ]
    source = predecessor_names[0] if predecessor_names else "an upstream shop"
    destination = state.shops[job.shop_id].name if job.shop_id in state.shops else "the receiving shop"
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.PRIORITY_CHANGE,
        title=f"Handoff risk into {destination}",
        description=(
            f"{piece_name} needs a clean handoff from {source} into {destination}. "
            f"{_job_context(state, job)} A small sequencing miss here can leave the receiving shop waiting or force a late expedite."
        ),
        target_ids=[job.id],
        severity=4 if job.critical_path or job.risk_score >= 55 else 3,
        choices=[
            DecisionChoice(
                id="1",
                label="Pull predecessor work forward",
                description="Advance ready feeder work so the receiving shop has a cleaner start window.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                cost_effect=10,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Protect receiving shop",
                description="Raise priority on this handoff and the downstream dependency it unlocks.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-6,
                cost_effect=12,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Resequence handoff lane",
                description="Adjust queue order around the handoff while leaving active work in place.",
                immediate_effects={"type": "resequence"},
                risk_effect=-3,
                cost_effect=5,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Let shops coordinate",
                description="Keep the handoff informal and avoid schedule churn, accepting the risk of waiting time.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
                cost_effect=0,
                reschedule_effect=0,
            ),
        ],
    )


def _alternate_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    """Build a card when a risky subjob has viable alternate routing."""
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.ALTERNATE_ROUTING,
        title=f"Alternate routing available for {job.id}",
        description=f"{_capability_label(job.required_capability).title()} work can move off its current queue. {_job_context(state, job)} Rerouting can reduce exposure, while staying put preserves queue stability.",
        target_ids=[job.id],
        severity=3,
        choices=[
            DecisionChoice(
                id="1",
                label="Reroute subjob",
                description="Move the subjob to the best open alternate workcenter and give it a cleaner path through the shop floor.",
                immediate_effects={"type": "reroute"},
                risk_effect=-6,
                cost_effect=18,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Wait one day",
                description="Preserve the current workcenter queue and avoid setup churn, accepting that the routing option may not stay helpful.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
                cost_effect=0,
                reschedule_effect=0,
            ),
            DecisionChoice(
                id="3",
                label="Pull forward peers",
                description="Use the alternate capacity for related ready work so the capability family keeps flowing even if this subjob stays put.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                cost_effect=8,
                reschedule_effect=1,
            ),
        ],
    )


def _quality_triage_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    """Build a card for preventive quality or rework containment."""
    piece = state.pieces.get(job.piece_id)
    piece_name = piece.name if piece else job.piece_id
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.QUALITY_REWORK,
        title=f"Quality containment choice for {job.id}",
        description=(
            f"{piece_name} has {_capability_label(job.required_capability)} work with little room for a rework loop. "
            f"{_job_context(state, job)} Choose how much inspection and queue disruption to accept before defects can spill into later work."
        ),
        target_ids=[job.id],
        severity=4 if job.critical_path or job.risk_score >= 55 else 3,
        choices=[
            DecisionChoice(
                id="1",
                label="Add containment check",
                description="Protect the dependency by adding attention now, reducing the chance that rework spills into downstream starts.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-6,
                cost_effect=16,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Reroute for clean capacity",
                description="Move the work to a capable station with less pressure so quality checks do not fight the main queue.",
                immediate_effects={"type": "reroute"},
                risk_effect=-5,
                cost_effect=20,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Defer suspect starts",
                description="Lower priority on less urgent starts that could consume inspection attention before this job clears.",
                immediate_effects={"type": "defer"},
                risk_effect=-2,
                cost_effect=5,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Wait for formal rework",
                description="Avoid adding checks until a defect is confirmed, accepting that later rework could be more disruptive.",
                immediate_effects={"type": "wait"},
                risk_effect=4,
                cost_effect=0,
                reschedule_effect=0,
            ),
        ],
    )


def _idle_card(state: SimulationState, ordinal: int, day: int) -> DecisionCard:
    """Build a card for unused capacity while ready work exists."""
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.IDLE_WORKCENTER,
        title="Idle capacity while work is ready",
        description=_idle_capacity_description(state),
        target_ids=[],
        severity=3,
        choices=[
            DecisionChoice(
                id="1",
                label="Pull forward ready work",
                description="Release ready subjobs into open capacity now so useful shop time does not sit unused.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                cost_effect=6,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Protect critical subjobs",
                description="Use open capacity only where it helps critical dependencies or work that unlocks later starts.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-6,
                cost_effect=10,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Keep buffers open",
                description="Hold capacity back for recovery work if active disruptions or warnings are likely to need a fast response.",
                immediate_effects={"type": "wait"},
                risk_effect=2,
                cost_effect=0,
                reschedule_effect=0,
            ),
        ],
    )


def _completion_readiness_card(state: SimulationState, ordinal: int, day: int) -> DecisionCard:
    """Build a card for late-stage readiness of remaining top-level jobs."""
    late_stage_day = max(1, int((state.deadline_shift / state.shifts_per_day) * 0.67))
    incomplete_pieces = sorted(
        [piece for piece in state.pieces.values() if not piece.completed],
        key=lambda piece: (-piece.risk_score, piece.estimated_completion_shift, piece.id),
    )
    target_ids = [piece.id for piece in incomplete_pieces[:3]]
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.COMPLETION_READINESS,
        title="Project completion readiness",
        description=_completion_readiness_description(state),
        target_ids=target_ids,
        severity=4 if day >= late_stage_day else 3,
        choices=[
            DecisionChoice(
                id="1",
                label="Protect remaining dependencies",
                description="Raise priority on subjobs that unlock the most remaining completion work.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-7,
                cost_effect=12,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Expedite near-complete jobs",
                description="Spend recovery effort on jobs that are closest to completion so finished deliverables start stacking up.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-5,
                cost_effect=22,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Hold capacity buffer",
                description="Avoid queue churn and keep recovery capacity available for late disruptions.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
                cost_effect=0,
                reschedule_effect=0,
            ),
        ],
    )


def _strategic_card(state: SimulationState, ordinal: int, day: int) -> DecisionCard:
    """Build a general strategy card when no sharper risk is available."""
    bottlenecks = state.get_bottleneck_shops(1)
    target_ids = [bottlenecks[0].id] if bottlenecks else []
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.STRATEGIC_PRIORITY,
        title="Strategic priority review",
        description="Several queues are close in priority; today's rule will shape which dependencies unlock first. Choose whether due dates, critical path, or queue stability should win when shops have competing starts.",
        target_ids=target_ids,
        severity=2,
        choices=[
            DecisionChoice(
                id="1",
                label="Earliest due first",
                description="Favor subjobs tied to the nearest target milestone so deadline pressure stays visible in every queue.",
                immediate_effects={"type": "resequence"},
                risk_effect=-3,
                cost_effect=4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Critical path first",
                description="Favor subjobs with tight slack and high downstream dependency value, even if less urgent work waits.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-5,
                cost_effect=8,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Stabilize queues",
                description="Let current workcenter queues run with minimal churn, preserving predictability at the cost of less intervention.",
                immediate_effects={"type": "wait"},
                risk_effect=2,
                cost_effect=0,
                reschedule_effect=0,
            ),
        ],
    )


def _fallback_strategic_card(state: SimulationState, ordinal: int, day: int) -> DecisionCard:
    """Build extra broad-planning cards to satisfy the daily card count."""
    bottlenecks = state.get_bottleneck_shops(1)
    target_ids = [bottlenecks[0].id] if bottlenecks else []
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.STRATEGIC_PRIORITY,
        title=f"Strategic planning review {ordinal}",
        description="Use a broad schedule review to keep work aligned when no single disruption demands attention. The choice sets the tone for how the manual scheduler handles today's smaller tradeoffs.",
        target_ids=target_ids,
        severity=2,
        choices=[
            DecisionChoice(
                id="1",
                label="Rebalance priorities",
                description="Shift attention toward urgent work and keep flow moving across shops before pressure concentrates.",
                immediate_effects={"type": "resequence"},
                risk_effect=-2,
                cost_effect=3,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Protect key milestones",
                description="Choose the sequence that safeguards the nearest delivery and the dependencies that unlock it.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-4,
                cost_effect=6,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Maintain stability",
                description="Keep current queues intact and let shop teams execute without another scheduling change.",
                immediate_effects={"type": "wait"},
                risk_effect=2,
                cost_effect=0,
                reschedule_effect=0,
            ),
        ],
    )


def _resequence(state: SimulationState, card: DecisionCard) -> str:
    """Sort queues by due date/priority and nudge ready work upward."""
    affected = 0
    for wc in state.workcenters.values():
        before = list(wc.queue)
        wc.queue.sort(key=lambda job_id: (state.jobs[job_id].due_shift, -state.jobs[job_id].priority))
        if wc.queue != before:
            affected += 1
    for job in state.get_ready_jobs()[:12]:
        job.priority += 3
    return f"Resequenced {affected} queues around the highlighted issue."


def _wait_and_absorb(state: SimulationState, card: DecisionCard) -> str:
    """Accept near-term delay and increase future pressure for affected work."""
    affected = 0
    limit = 8 if card.type in {DecisionType.CRITICAL_PATH, DecisionType.COMPLETION_READINESS} else 4
    delay = 3 if card.severity >= 4 else 2
    if card.type in {DecisionType.CRITICAL_PATH, DecisionType.COMPLETION_READINESS}:
        delay += 1
    for job in _jobs_for_card(state, card)[:limit]:
        if job.status not in {JobStatus.COMPLETE, JobStatus.RUNNING}:
            job.priority = max(5, job.priority - 6)
            job.remaining_duration_shifts += delay
            affected += 1
    for target_id in card.target_ids:
        event = _event_by_id(state, target_id)
        if event and event.id in state.active_events:
            event.duration_shifts += 1
            event.effects["mitigation_score"] = int(event.effects.get("mitigation_score", 0)) - 2
    if affected:
        return f"Held sequence; {affected} affected subjob(s) absorbed extra queue or coordination delay."
    return "Held current sequence and accepted near-term risk."


def _protect_critical(state: SimulationState) -> str:
    """Raise critical-path subjob priorities and pull queued ones forward."""
    critical = state.get_critical_path_jobs()[:10]
    for job in critical:
        job.priority += 10
        if job.assigned_workcenter_id and job.status == JobStatus.QUEUED:
            state.assign_job(job.id, job.assigned_workcenter_id, front=True)
    return f"Protected {len(critical)} critical-path subjobs by raising priority and queue position."


def _expedite_event(state: SimulationState, event_id: str | None) -> str:
    """Spend cost to shorten and soften an active or warned event."""
    event = _event_by_id(state, event_id)
    if not event:
        return "Expedite budget reserved for the highest active disruption."
    reduction = 2 if event.severity >= 4 else 1
    event.duration_shifts = max(1, event.duration_shifts - reduction)
    event.severity = max(1, event.severity - 1)
    event.effects["mitigation_score"] = int(event.effects.get("mitigation_score", 0)) + 3
    if event.type in {
        EventType.MISSING_MATERIAL,
        EventType.DELAYED_MATERIAL,
        EventType.INSPECTION_DELAY,
        EventType.SUPPLIER_ESCALATION,
        EventType.LOGISTICS_BACKLOG,
        EventType.CERTIFICATION_AUDIT,
    }:
        for job_id in event.effects.get("blocked_job_ids", [])[:2]:
            if job_id in state.jobs and state.jobs[job_id].block_reason:
                state.jobs[job_id].priority += 12
    return f"Expedited {event.id}; expected disruption duration reduced by {reduction} shift(s)."


def _reroute_targets(state: SimulationState, card: DecisionCard) -> str:
    """Move affected subjobs to less-loaded alternate workcenters."""
    jobs = _jobs_for_card(state, card)
    moved = 0
    for job in jobs[:3]:
        alt = _best_alternate_workcenter(state, job)
        if alt:
            state.assign_job(job.id, alt.id, front=job.critical_path)
            job.priority += 5
            moved += 1
    return f"Rerouted {moved} affected subjob(s) to alternate capable workcenters."


def _preempt_for_card(state: SimulationState, card: DecisionCard) -> str:
    """Interrupt lower-priority work when a card's target justifies it."""
    for job in _jobs_for_card(state, card):
        for wc_id in job.candidate_workcenter_ids:
            if wc_id not in state.workcenters:
                continue
            wc = state.workcenters[wc_id]
            if wc.current_job_id and state.jobs[wc.current_job_id].priority + 15 < job.priority:
                state.preempt_current_job(wc.id, job.id)
                return f"Preempted lower-priority work on {wc.name} for {job.id}."
    return "No safe preemption was available; priority was raised instead."


def _split_capacity(state: SimulationState, card: DecisionCard) -> str:
    """Move queued shop work across alternate capable capacity."""
    shop_ids = [target for target in card.target_ids if target in state.shops]
    moved = 0
    for shop_id in shop_ids:
        shop = state.shops[shop_id]
        queued = [state.jobs[job_id] for job_id in shop.queued_job_ids if job_id in state.jobs]
        for job in queued:
            alt = _best_alternate_workcenter(state, job)
            if alt and alt.shop_id != shop_id:
                state.assign_job(job.id, alt.id)
                moved += 1
                if moved >= 6:
                    return f"Split {moved} queued subjobs across alternate capacity."
    return f"Split {moved} queued subjobs across alternate capacity."


def _defer_lower_risk(state: SimulationState, card: DecisionCard) -> str:
    """Lower priority on slack-rich subjobs so urgent work can flow first."""
    shop_ids = [target for target in card.target_ids if target in state.shops]
    jobs = [
        job
        for job in state.jobs.values()
        if not job.is_complete and not job.critical_path and (not shop_ids or job.shop_id in shop_ids)
    ]
    for job in sorted(jobs, key=lambda item: (item.risk_score, -item.due_shift))[:12]:
        job.priority = max(10, job.priority - 8)
    return f"Deferred {min(12, len(jobs))} lower-risk subjobs to relieve queue pressure."


def _pull_forward_unaffected(state: SimulationState, card: DecisionCard) -> str:
    """Queue ready subjobs into available capacity before it is wasted."""
    moved = 0
    ready = sorted(state.get_ready_jobs(), key=lambda job: (-job.priority, job.due_shift))
    for job in ready[:18]:
        alt = _best_alternate_workcenter(state, job, allow_primary=True)
        if alt:
            state.assign_job(job.id, alt.id, front=job.critical_path)
            moved += 1
    return f"Pulled forward {moved} ready subjobs into available capacity."


def _use_echo_recommendation(state: SimulationState, card: DecisionCard) -> str:
    """Apply the experimental ECHO recommendation with a deterministic failure chance."""
    event_id = next((target_id for target_id in card.target_ids if _event_by_id(state, target_id)), card.id)
    roll = random.Random(f"{state.seed}:{event_id}:echo-recommendation")
    if roll.random() < 0.28:
        state.cost += 12
        return "ECHO recommendation did not produce a usable move; the team lost some analysis time."

    protected_note = _protect_critical(state)
    pulled_note = _pull_forward_unaffected(state, card)
    accelerated = 0
    for job in state.get_critical_path_jobs()[:4]:
        if job.status in {JobStatus.QUEUED, JobStatus.READY, JobStatus.SCHEDULED} and job.remaining_duration_shifts > 1:
            job.remaining_duration_shifts -= 1
            accelerated += 1
    return f"ECHO recommendation worked: {protected_note} {pulled_note} Accelerated {accelerated} critical subjob(s)."


def _add_unexpected_job(state: SimulationState, event_id: str | None, prioritize: bool) -> str:
    """Add the event's new top-level job with the selected priority mode."""
    event = _event_by_id(state, event_id)
    if not event:
        return "No new job request was available to add."
    piece_id = insert_unexpected_job(state, event, prioritize=prioritize)
    piece = state.pieces[piece_id]
    mode = "prioritized" if prioritize else "added to the back of the queue"
    return f"{piece.name} was {mode}; the submarine build now has {len(state.pieces)} top-level jobs."


def _apply_forward_decision_effect(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
) -> str:
    """Translate a decision into future mitigation or follow-on risk."""
    event = _event_by_id(state, choice.immediate_effects.get("event_id"))
    if not event:
        return ""
    effect_type = choice.immediate_effects.get("type", "note")
    mitigation_delta = {
        "expedite_event": 3,
        "reroute": 2,
        "protect_critical": 2,
        "resequence": 1,
        "split_capacity": 1,
        "pull_forward": 1,
        "prioritize_new_job": 1,
        "backlog_new_job": -1,
        "preempt": 1,
        "echo_recommendation": 2,
        "wait": -2,
        "defer": -1,
    }.get(effect_type, 0)
    # mitigation_score is later consumed by the cascade evaluator. Positive
    # choices reduce pressure; passive/defer choices can create a new event.
    event.effects["mitigation_score"] = int(event.effects.get("mitigation_score", 0)) + mitigation_delta
    event.effects.setdefault("decision_history", []).append(
        {
            "day": state.current_day,
            "card": card.id,
            "choice": choice.label,
            "effect": effect_type,
            "mitigation": mitigation_delta,
        }
    )
    if mitigation_delta > 0:
        affected = _soften_related_future_events(state, event, mitigation_delta)
        if affected:
            return f"Future related risk was reduced on {affected} event(s)."
        return "Future cascade risk was reduced."
    if mitigation_delta < 0:
        follow_on = _schedule_decision_follow_on(state, event, abs(mitigation_delta), choice.label)
        if follow_on:
            return f"Follow-on risk {follow_on.id} was added to the timeline."
    return ""


def _soften_related_future_events(state: SimulationState, source_event: Event, strength: int) -> int:
    """Reduce severity/duration on future events related to the mitigated one."""
    affected = 0
    for event in state.event_timeline:
        if event.id == source_event.id or event.started or event.resolved:
            continue
        if event.start_shift <= state.current_shift:
            continue
        if not _events_related(state, source_event, event):
            continue
        event.severity = max(1, event.severity - min(2, strength))
        event.duration_shifts = max(1, event.duration_shifts - 1)
        event.effects.setdefault("upstream_mitigations", []).append(source_event.id)
        affected += 1
        if affected >= strength:
            break
    return affected


def _schedule_decision_follow_on(
    state: SimulationState,
    source_event: Event,
    pressure: int,
    choice_label: str,
) -> Event | None:
    """Schedule one downstream risk caused by a low-mitigation decision."""
    key = f"decision_follow_on:{choice_label}"
    if key in source_event.effects:
        return None
    event_type, target_type, target_id = _decision_follow_on_target(state, source_event)
    if not target_id:
        return None
    follow_on = schedule_follow_on_event(
        state=state,
        source_event=source_event,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        delay_shifts=2 + min(3, source_event.severity),
        severity=max(1, min(5, source_event.severity + pressure - 1)),
        description=f"Deferred response to {source_event.id} creates a downstream {event_type.value.lower()} risk.",
    )
    if follow_on:
        source_event.effects[key] = follow_on.id
    return follow_on


def _decision_follow_on_target(state: SimulationState, source_event: Event) -> tuple[EventType, TargetType, str]:
    """Choose the plausible event type/target for a decision-driven cascade."""
    if source_event.type == EventType.UNEXPECTED_JOB:
        piece_id = source_event.effects.get("unexpected_piece_id")
        if piece_id in state.pieces:
            return EventType.PRIORITY_CHANGE, TargetType.PIECE, piece_id
        shop = max(
            state.shops.values(),
            key=lambda item: (len(item.queued_job_ids) + len(item.blocked_job_ids), item.risk_score),
        )
        return EventType.LOGISTICS_BACKLOG, TargetType.SHOP, shop.id
    if source_event.type == EventType.ECHO_RECOMMENDATION:
        shop = max(
            state.shops.values(),
            key=lambda item: (len(item.queued_job_ids) + len(item.blocked_job_ids), item.risk_score),
        )
        return EventType.LOGISTICS_BACKLOG, TargetType.SHOP, shop.id
    if source_event.type in {EventType.MISSING_MATERIAL, EventType.DELAYED_MATERIAL, EventType.SUPPLIER_ESCALATION}:
        if source_event.target_type == TargetType.JOB and source_event.target_id in state.jobs:
            job = state.jobs[source_event.target_id]
            return EventType.LOGISTICS_BACKLOG, TargetType.SHOP, job.shop_id
        return EventType.SUPPLIER_ESCALATION, source_event.target_type, source_event.target_id
    if source_event.type in {EventType.MACHINE_DOWN, EventType.TOOLING_DAMAGE}:
        return EventType.TOOLING_DAMAGE, source_event.target_type, source_event.target_id
    if source_event.type in {EventType.QUALITY_REWORK, EventType.REWORK_SPILLOVER}:
        return EventType.REWORK_SPILLOVER, TargetType.PIECE, _piece_id_for_event(state, source_event)
    if source_event.type in {EventType.INSPECTION_DELAY, EventType.CERTIFICATION_AUDIT}:
        return EventType.CERTIFICATION_AUDIT, TargetType.PIECE, _piece_id_for_event(state, source_event)
    if source_event.type in {EventType.ENGINEERING_HOLD, EventType.ENGINEERING_DATA_REVISION, EventType.PRIORITY_CHANGE}:
        return EventType.ENGINEERING_DATA_REVISION, TargetType.PIECE, _piece_id_for_event(state, source_event)
    if source_event.type in {EventType.WEATHER, EventType.FACILITY_OUTAGE, EventType.CREW_SHORTAGE, EventType.LOGISTICS_BACKLOG}:
        return EventType.CREW_SHORTAGE, source_event.target_type, source_event.target_id
    return EventType.LOGISTICS_BACKLOG, source_event.target_type, source_event.target_id


def _events_related(state: SimulationState, source: Event, candidate: Event) -> bool:
    """Return whether two events touch the same job, piece, or shop context."""
    if source.target_id == candidate.target_id:
        return True
    source_jobs = _jobs_for_event(state, source)
    candidate_jobs = _jobs_for_event(state, candidate)
    if source_jobs and candidate_jobs:
        source_job_ids = {job.id for job in source_jobs}
        candidate_job_ids = {job.id for job in candidate_jobs}
        if source_job_ids & candidate_job_ids:
            return True
        source_piece_ids = {job.piece_id for job in source_jobs}
        candidate_piece_ids = {job.piece_id for job in candidate_jobs}
        if source_piece_ids & candidate_piece_ids:
            return True
        source_shop_ids = {job.shop_id for job in source_jobs}
        candidate_shop_ids = {job.shop_id for job in candidate_jobs}
        if source_shop_ids & candidate_shop_ids:
            return True
    if source.target_type == TargetType.SHOP and candidate.target_type == TargetType.SHOP:
        return source.target_id == candidate.target_id
    return False


def _piece_id_for_event(state: SimulationState, event: Event) -> str:
    """Resolve the piece id most closely associated with an event."""
    if event.target_type == TargetType.PIECE and event.target_id in state.pieces:
        return event.target_id
    if event.target_type == TargetType.JOB and event.target_id in state.jobs:
        return state.jobs[event.target_id].piece_id
    jobs = _jobs_for_event(state, event)
    if jobs:
        return jobs[0].piece_id
    return next(iter(state.pieces))


def _apply_risk_delta(state: SimulationState, card: DecisionCard, delta: int) -> None:
    """Apply a choice's risk delta to the most relevant jobs/entities."""
    for job in _jobs_for_card(state, card)[:8]:
        job.risk_score = max(0, min(100, job.risk_score + delta))
    for target_id in card.target_ids:
        if target_id in state.shops:
            state.shops[target_id].risk_score = max(0, min(100, state.shops[target_id].risk_score + delta))
        if target_id in state.pieces:
            state.pieces[target_id].risk_score = max(0, min(100, state.pieces[target_id].risk_score + delta))


def _jobs_for_card(state: SimulationState, card: DecisionCard) -> list[Job]:
    """Expand a card's targets into concrete affected jobs."""
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
        jobs = state.get_critical_path_jobs()[:5] or state.get_ready_jobs()[:5]
    return sorted(
        list({job.id: job for job in jobs if not job.is_complete}.values()),
        key=lambda job: (job.critical_path, job.risk_score, job.priority),
        reverse=True,
    )


def _jobs_for_event(state: SimulationState, event: Event) -> list[Job]:
    """Expand an event target into concrete affected jobs."""
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


def _best_alternate_workcenter(
    state: SimulationState,
    job: Job,
    allow_primary: bool = False,
) -> WorkCenter | None:
    """Return the least-loaded capable workcenter for a reroute."""
    candidates: list[WorkCenter] = []
    for wc_id in job.candidate_workcenter_ids:
        if wc_id not in state.workcenters:
            continue
        wc = state.workcenters[wc_id]
        if wc.status in {WorkCenterStatus.DOWN, WorkCenterStatus.BLOCKED, WorkCenterStatus.WEATHER_IMPACTED}:
            continue
        if not allow_primary and wc.id == job.assigned_workcenter_id:
            continue
        if job.required_capability in wc.capabilities:
            candidates.append(wc)
    if not candidates:
        return None
    return min(candidates, key=lambda wc: (len(wc.queue) + (1 if wc.current_job_id else 0), -wc.efficiency, wc.id))


def _event_by_id(state: SimulationState, event_id: str | None) -> Event | None:
    """Find an event by id, tolerating missing ids from generic cards."""
    if not event_id:
        return None
    return next((event for event in state.event_timeline if event.id == event_id), None)


def _target_name(state: SimulationState, target_type: TargetType, target_id: str) -> str:
    """Resolve an event target into display text for a card description."""
    if target_type == TargetType.SHOP and target_id in state.shops:
        return state.shops[target_id].name
    if target_type == TargetType.WORKCENTER and target_id in state.workcenters:
        return state.workcenters[target_id].name
    if target_type == TargetType.PIECE and target_id in state.pieces:
        return state.pieces[target_id].name
    return target_id


def _decision_type_for_event(event_type: EventType) -> DecisionType:
    """Map specific disruption types into broader decision-card categories."""
    return {
        EventType.MISSING_MATERIAL: DecisionType.MISSING_MATERIAL,
        EventType.DELAYED_MATERIAL: DecisionType.MISSING_MATERIAL,
        EventType.MACHINE_DOWN: DecisionType.MACHINE_DOWN,
        EventType.QUALITY_REWORK: DecisionType.QUALITY_REWORK,
        EventType.PRIORITY_CHANGE: DecisionType.PRIORITY_CHANGE,
        EventType.INSPECTION_DELAY: DecisionType.INSPECTION_DELAY,
        EventType.ENGINEERING_HOLD: DecisionType.ENGINEERING_HOLD,
        EventType.URGENT_JOB: DecisionType.URGENT_JOB,
        EventType.WEATHER: DecisionType.WEATHER,
        EventType.FACILITY_OUTAGE: DecisionType.WEATHER,
        EventType.SUPPLIER_ESCALATION: DecisionType.MISSING_MATERIAL,
        EventType.LOGISTICS_BACKLOG: DecisionType.MISSING_MATERIAL,
        EventType.TOOLING_DAMAGE: DecisionType.MACHINE_DOWN,
        EventType.CREW_SHORTAGE: DecisionType.BOTTLENECK,
        EventType.REWORK_SPILLOVER: DecisionType.QUALITY_REWORK,
        EventType.CERTIFICATION_AUDIT: DecisionType.INSPECTION_DELAY,
        EventType.ENGINEERING_DATA_REVISION: DecisionType.ENGINEERING_HOLD,
        EventType.UNEXPECTED_JOB: DecisionType.UNEXPECTED_JOB,
        EventType.ECHO_RECOMMENDATION: DecisionType.ECHO_RECOMMENDATION,
    }[event_type]


def _top_bottleneck(state: SimulationState) -> Shop | None:
    """Return the most pressured shop if it is worth showing as a card."""
    shops = state.get_bottleneck_shops(1)
    if not shops:
        return None
    shop = shops[0]
    if len(shop.queued_job_ids) + len(shop.blocked_job_ids) < 2:
        return None
    return shop


def _top_critical_job(state: SimulationState) -> Job | None:
    """Return the highest-priority critical-path job, if any."""
    critical = state.get_critical_path_jobs()
    return critical[0] if critical else None


def _alternate_routing_job(state: SimulationState) -> Job | None:
    """Find a risky job with a usable alternate workcenter."""
    jobs = _alternate_routing_jobs(state)
    return jobs[0] if jobs else None


def _alternate_routing_jobs(state: SimulationState) -> list[Job]:
    """Find risky jobs with usable alternate workcenters."""
    candidates = [
        job
        for job in state.jobs.values()
        if not job.is_complete
        and len(job.candidate_workcenter_ids) > 1
        and (job.critical_path or job.risk_score > 40)
        and _best_alternate_workcenter(state, job) is not None
    ]
    return sorted(candidates, key=lambda job: (job.critical_path, job.risk_score, job.priority), reverse=True)


def _handoff_risk_job(state: SimulationState) -> Job | None:
    """Find a dependency handoff where shops differ and timing is tight."""
    candidates: list[Job] = []
    for job in state.jobs.values():
        if job.is_complete or not job.dependency_ids:
            continue
        upstream_shops = {
            state.jobs[dep_id].shop_id
            for dep_id in job.dependency_ids
            if dep_id in state.jobs and state.jobs[dep_id].shop_id != job.shop_id
        }
        if not upstream_shops:
            continue
        slack = job.due_shift - state.current_shift - job.remaining_duration_shifts
        if job.critical_path or slack <= 8 or job.risk_score >= 35:
            candidates.append(job)
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda job: (job.critical_path, job.risk_score, -job.due_shift, job.priority),
        reverse=True,
    )[0]


def _quality_triage_job(state: SimulationState) -> Job | None:
    """Find work where preventive quality attention could change the day."""
    quality_capabilities = {
        "inspection",
        "metrology",
        "certification",
        "alignment",
        "calibration",
        "finishing",
    }
    candidates = [
        job
        for job in state.jobs.values()
        if not job.is_complete
        and (
            job.rework_count > 0
            or job.status == JobStatus.REWORK_REQUIRED
            or job.required_capability in quality_capabilities
            or job.risk_score >= 45
        )
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda job: (job.rework_count, job.status == JobStatus.REWORK_REQUIRED, job.critical_path, job.risk_score),
        reverse=True,
    )[0]


def _has_idle_opportunity(state: SimulationState) -> bool:
    """Return whether open workcenters and ready jobs coexist."""
    return bool(state.get_ready_jobs()) and bool(state.get_available_workcenters())
