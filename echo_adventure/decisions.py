"""Daily decision-card generation and player choice effects."""

from __future__ import annotations

import hashlib
import random

from .config import GameConfig
from .enums import DecisionType, EventType, JobStatus, TargetType, WorkCenterStatus
from .events import insert_unexpected_job, schedule_follow_on_event
from .metrics import update_state_metrics
from .models import (
    CampaignDecisionGraph,
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


_CAMPAIGN_ROUTE_THEMES: dict[str, tuple[str, str]] = {
    "supplier_risk_ignored": (
        "Supplier exposure",
        "Earlier supplier risk is still open.",
    ),
    "supplier_risk_mitigated": (
        "Supplier buffer",
        "Earlier supplier work bought some room.",
    ),
    "critical_path_protected": (
        "Protected work",
        "Earlier choices protected key work.",
    ),
    "crew_overloaded": (
        "Crew load",
        "Earlier moves loaded the crew.",
    ),
    "echo_trusted": (
        "ECHO reliance",
        "Earlier choices leaned on ECHO.",
    ),
    "echo_overridden": (
        "Manual override",
        "Earlier choices overrode ECHO.",
    ),
    "quality_debt_created": (
        "Quality debt",
        "Earlier quality risk was left open.",
    ),
    "schedule_debt_created": (
        "Schedule debt",
        "Earlier stability spent schedule room.",
    ),
    "cost_debt_created": (
        "Cost pressure",
        "Earlier recovery cost extra effort.",
    ),
    "risk_debt_created": (
        "Risk debt",
        "Earlier choices accepted risk.",
    ),
    "work_rerouted": (
        "Rerouted work",
        "Earlier work moved to another route.",
    ),
    "flow_resequenced": (
        "Flow resequenced",
        "Earlier choices changed queue order.",
    ),
    "wait_escalation": (
        "Escalated wait",
        "Earlier waiting raised pressure.",
    ),
    "priority_churn": (
        "Priority churn",
        "Earlier choices changed priority rules.",
    ),
}

_CHOICE_BRANCH_PROFILES: dict[str, tuple[str, tuple[str, ...]]] = {
    "echo_recommendation": ("echo_trusted", ("echo_trusted", "cost_debt_created")),
    "expedite_event": ("supplier_risk_mitigated", ("supplier_risk_mitigated", "cost_debt_created")),
    "protect_critical": ("critical_path_protected", ("critical_path_protected", "crew_overloaded")),
    "reroute": ("work_rerouted", ("work_rerouted", "schedule_debt_created")),
    "split_capacity": ("crew_overloaded", ("crew_overloaded", "cost_debt_created")),
    "pull_forward": ("critical_path_protected", ("critical_path_protected", "crew_overloaded")),
    "prioritize_new_job": ("priority_churn", ("priority_churn", "cost_debt_created")),
    "backlog_new_job": ("schedule_debt_created", ("schedule_debt_created", "supplier_risk_ignored")),
    "resequence": ("flow_resequenced", ("flow_resequenced",)),
    "preempt": ("crew_overloaded", ("crew_overloaded", "schedule_debt_created")),
    "defer": ("schedule_debt_created", ("schedule_debt_created", "quality_debt_created")),
    "wait": ("wait_escalation", ("wait_escalation", "risk_debt_created")),
    "note": ("risk_debt_created", ("risk_debt_created",)),
}


def generate_campaign_decision_graph(
    state: SimulationState,
    config: GameConfig,
) -> tuple[dict[str, DecisionCard], CampaignDecisionGraph]:
    """Build one bounded campaign-wide decision graph at scenario creation.

    Every future route card is created here. During play, choices only unlock
    and filter these existing cards by branch tags, so Day 5 cards can depend
    on Day 1 decisions without being generated on Day 5.
    """
    cards: dict[str, DecisionCard] = {}
    graph = CampaignDecisionGraph(
        max_active_cards_per_day=min(config.max_active_decision_cards_per_day, config.max_decisions_per_day),
    )
    day_templates: dict[int, list[DecisionCard]] = {}

    for day in range(1, config.total_days + 1):
        _prime_graph_state_for_day(state, day, config)
        event_cards = _generate_scheduled_event_cards(state, day, config)
        for event_card in event_cards:
            if len(cards) >= config.max_campaign_decision_nodes:
                break
            cards[event_card.id] = event_card
            graph.cards_by_day.setdefault(day, []).append(event_card.id)
            graph.event_card_ids_by_day.setdefault(day, []).append(event_card.id)
        day_templates[day] = _generate_root_decision_cards(state, day, config, include_events=False)

    day_one_templates = day_templates.get(1) or [_strategic_card(state, 1, 1)]
    root_count = max(1, min(config.min_decisions_per_day, config.max_active_decision_cards_per_day, len(day_one_templates)))
    for ordinal, template in enumerate(day_one_templates[:root_count], start=1):
        card_id = "CMP-D01-ROOT" if ordinal == 1 else f"CMP-D01-ROOT-{ordinal:02d}"
        root = _campaign_clone_card(
            template,
            card_id=card_id,
            day=1,
            title_prefix="Campaign opening" if ordinal == 1 else "Opening branch",
            description_prefix="This opening choice affects later days.",
            campaign_priority=ordinal,
        )
        cards[root.id] = root
        graph.root_card_ids.append(root.id)
        graph.cards_by_day.setdefault(1, []).append(root.id)

    route_tags = list(_CAMPAIGN_ROUTE_THEMES)[: config.max_branch_variants_per_day]
    for day in range(2, config.total_days + 1):
        templates = day_templates.get(day) or day_one_templates
        for index, tag in enumerate(route_tags):
            if len(cards) >= config.max_campaign_decision_nodes:
                break
            theme_title, theme_description = _CAMPAIGN_ROUTE_THEMES[tag]
            template = templates[index % len(templates)]
            card = _campaign_clone_card(
                template,
                card_id=_campaign_card_id(day, tag),
                day=day,
                title_prefix=theme_title,
                description_prefix=theme_description,
                required_tags=[tag],
                campaign_priority=20 + index,
            )
            cards[card.id] = card
            graph.cards_by_day.setdefault(day, []).append(card.id)

    _decorate_campaign_choices(cards, config)
    echo_score_memo: dict[str, float] = {}
    for card in cards.values():
        card.echo_choice_id = select_echo_choice(card, cards, echo_score_memo).id

    graph.cards_by_day = {day: ids for day, ids in sorted(graph.cards_by_day.items())}
    graph.event_card_ids_by_day = {day: ids for day, ids in sorted(graph.event_card_ids_by_day.items())}
    return cards, graph


def active_decision_cards(
    state: SimulationState,
    day: int,
    selected_choices: dict[str, str],
) -> list[DecisionCard]:
    """Return the currently visible campaign decision cards."""
    return active_campaign_decision_cards(state, day, selected_choices)


def active_campaign_decision_cards(
    state: SimulationState,
    day: int,
    selected_choices: dict[str, str],
) -> list[DecisionCard]:
    """Select prebuilt campaign graph nodes for today's active branch."""
    graph = state.campaign_decision_graph
    scheduled_events = set(graph.event_card_ids_by_day.get(day, []))
    unlocked = set(state.unlocked_decision_card_ids) | set(graph.root_card_ids) | scheduled_events
    candidate_ids = graph.cards_by_day.get(day) or [
        card_id for card_id, card in state.decision_cards.items() if card.day == day
    ]
    limit = graph.max_active_cards_per_day or len(candidate_ids)
    cards = [
        card
        for card_id in candidate_ids
        if (card := state.decision_cards.get(card_id))
        and _campaign_card_available(card, state, unlocked)
    ]
    cards.sort(key=lambda card: _campaign_active_sort_key(state, card))
    return cards[:limit] if limit > 0 else cards


def _campaign_card_available(
    card: DecisionCard,
    state: SimulationState,
    unlocked: set[str],
) -> bool:
    """Return whether a prebuilt campaign node belongs to the active route."""
    if card.id not in unlocked:
        return False
    if any(tag not in state.campaign_branch_tags for tag in card.required_tags):
        return False
    if any(tag in state.campaign_branch_tags for tag in card.excluded_tags):
        return False
    return True


def _campaign_active_sort_key(state: SimulationState, card: DecisionCard) -> tuple[int, int, int, str]:
    """Prefer earlier branch tags when too many route cards are unlocked."""
    event_ids = set(state.campaign_decision_graph.event_card_ids_by_day.get(card.day, []))
    if card.id in event_ids:
        return (-1, card.campaign_priority, -card.severity, card.id)
    tag_order = min(
        (state.campaign_branch_tag_order.get(tag, 999) for tag in card.required_tags),
        default=999,
    )
    return (tag_order, card.campaign_priority, -card.severity, card.id)


def decision_progress(
    state: SimulationState,
    day: int,
    selected_choices: dict[str, str],
) -> DecisionProgress:
    """Return progress through the day's fixed number of questions."""
    cards = active_campaign_decision_cards(state, day, selected_choices)
    effective_choices = {**state.campaign_selected_choices, **selected_choices}
    open_card_ids = [card.id for card in cards if card.id not in effective_choices]
    answered = len(cards) - len(open_card_ids)
    return DecisionProgress(
        day=day,
        total_questions=len(cards),
        answered_questions=answered,
        visible_cards=len(cards),
        open_card_ids=open_card_ids,
    )


def select_echo_choice(
    card: DecisionCard,
    graph: dict[str, DecisionCard] | None = None,
    memo: dict[str, float] | None = None,
) -> DecisionChoice:
    """Return the benchmark choice ECHO treats as the correct response."""
    if graph is None and memo is None and card.echo_choice_id:
        selected = next((choice for choice in card.choices if choice.id == card.echo_choice_id), None)
        if selected:
            return selected
    memo = memo if memo is not None else {}
    return min(
        card.choices,
        key=lambda choice: (_choice_path_score(choice, graph, memo=memo), choice.id),
    )


def score_echo_choice(
    choice: DecisionChoice,
    graph: dict[str, DecisionCard] | None = None,
    memo: dict[str, float] | None = None,
) -> float:
    """Return ECHO's static campaign-graph score for a choice."""
    return _choice_path_score(choice, graph, memo=memo)


def _choice_path_score(
    choice: DecisionChoice,
    graph: dict[str, DecisionCard] | None,
    visiting: frozenset[str] | None = None,
    memo: dict[str, float] | None = None,
) -> float:
    """Score a choice plus its best reachable downstream decision path for ECHO."""
    effect_rank = {
        "echo_recommendation": 0,
        "expedite_event": 1,
        "reroute": 2,
        "split_capacity": 3,
        "pull_forward": 4,
        "protect_critical": 5,
        "prioritize_new_job": 6,
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
    )
    if choice.score_delta:
        immediate -= choice.score_delta * 1.5
    if not graph:
        return immediate
    visiting = visiting if visiting is not None else frozenset()
    memo = memo if memo is not None else {}
    child_ids = []
    if choice.next_card_id:
        child_ids.append(choice.next_card_id)
    child_ids.extend(choice.future_unlock_card_ids)
    child_scores = []
    for child_id in dict.fromkeys(child_ids):
        if child_id in visiting:
            continue
        child = graph.get(child_id)
        if child:
            child_scores.append(_card_path_score(child, graph, visiting, memo))
    if not child_scores:
        return immediate
    return immediate + min(child_scores) * 0.65


def _card_path_score(
    card: DecisionCard,
    graph: dict[str, DecisionCard],
    visiting: frozenset[str],
    memo: dict[str, float],
) -> float:
    """Return ECHO's best full-tree score from one downstream card."""
    if card.id in memo:
        return memo[card.id]
    if card.id in visiting:
        return 0.0
    next_visiting = visiting | {card.id}
    best = min(
        _choice_path_score(child_choice, graph, next_visiting, memo)
        for child_choice in card.choices
    )
    memo[card.id] = best
    return best


def _generate_scheduled_event_cards(
    state: SimulationState,
    day: int,
    config: GameConfig,
) -> list[DecisionCard]:
    """Build day-fixed decisions from the event timeline, independent of branch."""
    max_event_cards = max(1, min(2, config.max_active_decision_cards_per_day))
    cards: list[DecisionCard] = []
    for ordinal, event in enumerate(_visible_events(state)[:max_event_cards], start=1):
        card = _event_card(state, event, ordinal, day)
        card.id = f"CMP-D{day:02d}-EVENT-{event.id}"
        card.campaign_priority = ordinal
        cards.append(card)
    return cards


def _generate_root_decision_cards(
    state: SimulationState,
    day: int,
    config: GameConfig | None = None,
    include_events: bool = True,
) -> list[DecisionCard]:
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
    visible_events = _visible_events(state) if include_events else []
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
                required_tags=list(card.required_tags),
                excluded_tags=list(card.excluded_tags),
                campaign_priority=card.campaign_priority,
            )
        )
    return renumbered


def _campaign_clone_card(
    template: DecisionCard,
    card_id: str,
    day: int,
    title_prefix: str,
    description_prefix: str,
    required_tags: list[str] | None = None,
    excluded_tags: list[str] | None = None,
    campaign_priority: int = 100,
) -> DecisionCard:
    """Clone a generated operational template into a campaign graph node."""
    return DecisionCard(
        id=card_id,
        day=day,
        type=template.type,
        title=f"{title_prefix}: {template.title}",
        description=f"{description_prefix} Now: {template.description}",
        target_ids=list(template.target_ids),
        severity=template.severity,
        choices=_clone_choices(template.choices),
        echo_choice_id=template.echo_choice_id,
        required_tags=list(required_tags or []),
        excluded_tags=list(excluded_tags or []),
        campaign_priority=campaign_priority,
    )


def _campaign_card_id(day: int, tag: str) -> str:
    """Return the stable id for a prebuilt route card."""
    return f"CMP-D{day:02d}-{tag.upper().replace('_', '-')}"


def _decorate_campaign_choices(cards: dict[str, DecisionCard], config: GameConfig) -> None:
    """Attach branch projections, future unlocks, and score deltas to choices."""
    available_card_ids = set(cards)
    for card in cards.values():
        for choice in card.choices:
            _, tags = project_choice_branch_state(choice)
            choice.branch_tags_added = tags
            choice.future_unlock_card_ids = _future_unlock_card_ids_for_choice(
                choice_day=card.day,
                branch_tags=tags,
                available_card_ids=available_card_ids,
                config=config,
            )
            choice.score_delta = _decision_choice_score_delta(card, choice, tags)


def project_choice_branch_state(choice: DecisionChoice) -> tuple[str, list[str]]:
    """Project a choice into persistent campaign branch tags."""
    effect_type = choice.immediate_effects.get("type", "note")
    primary, tags = _CHOICE_BRANCH_PROFILES.get(effect_type, _CHOICE_BRANCH_PROFILES["note"])
    projected = list(tags)
    if choice.risk_effect > 0:
        projected.append("risk_debt_created")
    if choice.reschedule_effect >= 2:
        projected.append("crew_overloaded")
    if effect_type == "wait" and choice.risk_effect >= 4:
        projected.append("supplier_risk_ignored")
    return primary, _stable_unique_tags(projected)


def _stable_unique_tags(tags: list[str] | tuple[str, ...]) -> list[str]:
    """Deduplicate tags without changing route priority."""
    return [tag for tag in dict.fromkeys(tags) if tag in _CAMPAIGN_ROUTE_THEMES]


def _future_unlock_card_ids_for_choice(
    choice_day: int,
    branch_tags: list[str],
    available_card_ids: set[str],
    config: GameConfig,
) -> list[str]:
    """Return bounded future route nodes unlocked by one choice."""
    future_days = _future_unlock_days(choice_day, config.total_days)
    unlocks: list[str] = []
    primary_tags = branch_tags[: max(1, min(2, len(branch_tags)))]
    for future_day in future_days:
        for tag in primary_tags:
            card_id = _campaign_card_id(future_day, tag)
            if card_id in available_card_ids and card_id not in unlocks:
                unlocks.append(card_id)
                break
        if len(unlocks) >= config.max_future_unlocks_per_choice:
            break
    if len(unlocks) < config.max_future_unlocks_per_choice and len(branch_tags) > 1 and future_days:
        latest_day = future_days[-1]
        for tag in branch_tags[1:]:
            card_id = _campaign_card_id(latest_day, tag)
            if card_id in available_card_ids and card_id not in unlocks:
                unlocks.append(card_id)
            if len(unlocks) >= config.max_future_unlocks_per_choice:
                break
    return unlocks


def _future_unlock_days(choice_day: int, total_days: int) -> list[int]:
    """Choose future days that keep the graph branching without exploding."""
    days = []
    for offset in (1, 2, 4):
        day = choice_day + offset
        if day <= total_days:
            days.append(day)
    return days


def _decision_choice_score_delta(card: DecisionCard, choice: DecisionChoice, tags: list[str]) -> float:
    """Return a deterministic path-specific score modifier for one choice."""
    material = f"{card.id}:{choice.id}:{choice.label}:{','.join(tags)}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    path_fraction = (int(digest[:6], 16) % 1000) / 1000.0
    operational_value = (-choice.risk_effect * 0.28) - (choice.reschedule_effect * 0.18)
    if "cost_debt_created" in tags:
        operational_value -= 0.25
    if "supplier_risk_mitigated" in tags:
        operational_value += 0.35
    if "critical_path_protected" in tags:
        operational_value += 0.12
    if "risk_debt_created" in tags or "schedule_debt_created" in tags:
        operational_value -= 0.2
    return round(operational_value + path_fraction, 3)


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


def apply_campaign_choice(state: SimulationState, card: DecisionCard, choice: DecisionChoice) -> None:
    """Persist branch state changes from one campaign graph choice."""
    state.campaign_selected_choices[card.id] = choice.id
    next_order = len(state.campaign_branch_tag_order)
    for tag in choice.branch_tags_added:
        if tag not in state.campaign_branch_tag_order:
            state.campaign_branch_tag_order[tag] = next_order
            next_order += 1
    state.campaign_branch_tags.update(choice.branch_tags_added)
    unlock_future_decision_nodes(state, choice.future_unlock_card_ids)
    state.decision_path.append(f"{card.id}:{choice.id}")
    state.decision_path_signature = decision_path_signature(state)
    state.decision_path_score_delta = round(state.decision_path_score_delta + choice.score_delta, 4)


def unlock_future_decision_nodes(state: SimulationState, card_ids: list[str]) -> None:
    """Unlock prebuilt future campaign nodes, ignoring unknown save data ids."""
    for card_id in card_ids:
        if card_id in state.decision_cards:
            state.unlocked_decision_card_ids.add(card_id)


def decision_path_signature(state: SimulationState) -> str:
    """Return a deterministic signature of the ordered decision path."""
    if not state.decision_path:
        return ""
    material = "|".join(state.decision_path)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


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
    apply_campaign_choice(state, card, choice)
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


def _clone_choices(choices: list[DecisionChoice]) -> list[DecisionChoice]:
    """Copy choice templates without carrying branch links between cards."""
    return [
        DecisionChoice(
            id=choice.id,
            label=choice.label,
            description=choice.description,
            immediate_effects=dict(choice.immediate_effects),
            risk_effect=choice.risk_effect,
            reschedule_effect=choice.reschedule_effect,
            next_card_id=choice.next_card_id,
            future_unlock_card_ids=list(choice.future_unlock_card_ids),
            branch_tags_added=list(choice.branch_tags_added),
            score_delta=choice.score_delta,
        )
        for choice in choices
    ]


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


def _piece_label(piece_id: str) -> str:
    """Return the decision-card label for a top-level job."""
    suffix = piece_id.split("-")[-1] if piece_id else ""
    return f"Job {suffix}" if suffix else "Job"


def _job_state_phrase(state: SimulationState, job: Job) -> str:
    """Summarize a job state without exposing hidden scoring values."""
    if job.is_blocked:
        return "blocked"
    if job.status == JobStatus.RUNNING:
        return "running"
    if job.status == JobStatus.QUEUED:
        return "queued"
    if job.status == JobStatus.READY:
        return "ready"
    if not state.is_dependency_complete(job.id):
        return "waiting on earlier work"
    return "not queued"


def _slack_phrase(state: SimulationState, job: Job) -> str:
    """Describe schedule slack qualitatively."""
    slack = job.due_shift - state.current_shift - job.remaining_duration_shifts
    if slack < 0:
        return "no slack"
    if slack <= 2:
        return "thin slack"
    if slack <= 6:
        return "tightening slack"
    return "some slack"


def _assigned_location_phrase(state: SimulationState, job: Job) -> str:
    """Describe the current assignment or best-known routing context."""
    if job.assigned_workcenter_id and job.assigned_workcenter_id in state.workcenters:
        wc = state.workcenters[job.assigned_workcenter_id]
        return f"at {wc.name}"
    shop = state.shops.get(job.shop_id)
    if shop:
        return f"in {shop.name}"
    return "not assigned"


def _job_context(state: SimulationState, job: Job) -> str:
    """Build a compact operational context sentence for a job."""
    detail = [f"{job.id} is {_job_state_phrase(state, job)}: {_slack_phrase(state, job)}, {_assigned_location_phrase(state, job)}."]
    if job.critical_path:
        detail.append("Delay here can hold later work.")
    elif job.dependent_job_ids:
        detail.append("It unlocks later work.")
    return " ".join(detail)


def _event_context(state: SimulationState, event: Event, status: str) -> str:
    """Describe why an event matters for the current operating board."""
    if event.type == EventType.UNEXPECTED_JOB:
        timing = "now" if status == "active" else "soon"
        return f"New job is due {timing}; it adds work to the build."
    jobs = _jobs_for_event(state, event)
    timing = "now" if status == "active" else "soon"
    if not jobs:
        return f"This hits {timing}. Your response changes later pressure."

    has_critical = any(job.critical_path for job in jobs)
    has_blocked = any(job.is_blocked for job in jobs)
    has_ready = any(job.status in {JobStatus.READY, JobStatus.QUEUED} for job in jobs)
    context: list[str] = [f"This hits {timing}"]
    if has_critical:
        context.append("near key work")
    elif has_ready:
        context.append("near work that can move")
    else:
        context.append("near later dependencies")
    if has_blocked:
        context.append("with blocked subjobs")
    return "; ".join(context) + "."


def _shop_pressure_description(state: SimulationState, shop: Shop) -> str:
    """Describe shop pressure without showing raw queue counts."""
    has_queued = bool(shop.queued_job_ids)
    has_blocked = bool(shop.blocked_job_ids)
    if has_queued and has_blocked:
        opening = "Queued and blocked work are building here."
    elif has_blocked:
        opening = "Blocked work is making this shop slow."
    elif has_queued:
        opening = "The queue is backing up here."
    else:
        opening = "This shop may become the next pinch point."

    critical_ids = {job.id for job in state.get_critical_path_jobs()}
    touches_critical = bool(critical_ids & (set(shop.queued_job_ids) | set(shop.blocked_job_ids)))
    if touches_critical:
        return f"{opening} Some key work is in the mix."
    return f"{opening} Pick a simple rule for today."


def _idle_capacity_description(state: SimulationState) -> str:
    """Describe the unused-capacity decision in operational terms."""
    ready_jobs = state.get_ready_jobs()
    critical_ready = any(job.critical_path for job in ready_jobs)
    if critical_ready:
        return "Stations are open while key work waits. Use them or keep a buffer?"
    return "Stations are open while work waits. Fill them or save room for trouble?"


def _completion_readiness_description(state: SimulationState) -> str:
    """Describe completion risk without exposing progress fractions."""
    incomplete = [piece for piece in state.pieces.values() if not piece.completed]
    if any(piece.risk_score >= 70 for piece in incomplete):
        return "Some unfinished jobs are getting risky. Pick what gets help today."
    return "The project still has unfinished jobs. Pick what moves first today."


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
            title="ECHO can help today",
            description="ECHO has a schedule move. Use it or keep the manual plan?",
            target_ids=[event.target_id, event.id],
            severity=event.severity,
            choices=[
                DecisionChoice(
                    id="1",
                    label="Use ECHO",
                    description="Take ECHO's move for today's board.",
                    immediate_effects={"type": "echo_recommendation", "event_id": event.id},
                    risk_effect=-8,
                    reschedule_effect=1,
                ),
                DecisionChoice(
                    id="2",
                    label="Keep manual plan",
                    description="Skip the analysis and run the current plan.",
                    immediate_effects={"type": "wait", "event_id": event.id},
                    risk_effect=2,
                    reschedule_effect=0,
                ),
            ],
        )
    if event.type == EventType.UNEXPECTED_JOB:
        return DecisionCard(
            id=f"DAY-{day:02d}-DEC-{ordinal}",
            day=day,
            type=dtype,
            title="New job arrived",
            description=f"A customer added work. Put it up front or at the back?",
            target_ids=[event.target_id, event.id],
            severity=event.severity,
            choices=[
                DecisionChoice(
                    id="1",
                    label="Put it up front",
                    description="Add the job and start its first subjob soon.",
                    immediate_effects={"type": "prioritize_new_job", "event_id": event.id},
                    risk_effect=-2,
                    reschedule_effect=2,
                ),
                DecisionChoice(
                    id="2",
                    label="Put it at the back",
                    description="Accept it, but keep today's old work ahead.",
                    immediate_effects={"type": "backlog_new_job", "event_id": event.id},
                    risk_effect=4,
                    reschedule_effect=0,
                ),
            ],
        )
    choices = [
        DecisionChoice(
            id="1",
            label="Change the queue",
            description="Move ready work around the trouble spot.",
            immediate_effects={"type": "resequence", "event_id": event.id},
            risk_effect=-5,
            reschedule_effect=1,
        ),
        DecisionChoice(
            id="2",
            label="Fix it now",
            description="Spend effort to shorten the disruption.",
            immediate_effects={"type": "expedite_event", "event_id": event.id},
            risk_effect=-9,
            reschedule_effect=2,
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
                id="3",
                label="Go around it",
                description="Move affected work to another capable station.",
                immediate_effects={"type": "reroute", "event_id": event.id},
                risk_effect=-6,
                reschedule_effect=1,
            )
        )
    else:
        choices.append(
            DecisionChoice(
                id="3",
                label="Ride it out",
                description="Keep the plan steady and absorb the risk.",
                immediate_effects={"type": "wait", "event_id": event.id},
                risk_effect=5,
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
        title=f"{shop.name} is backing up",
        description=_shop_pressure_description(state, shop),
        target_ids=[shop.id],
        severity=min(5, 1 + queued // 4 + blocked // 2),
        choices=[
            DecisionChoice(
                id="1",
                label="Split the load",
                description="Move eligible work to other capable stations.",
                immediate_effects={"type": "split_capacity"},
                risk_effect=-7,
                reschedule_effect=2,
            ),
            DecisionChoice(
                id="2",
                label="Due dates first",
                description="Run the nearest due work first.",
                immediate_effects={"type": "resequence"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Push easy work back",
                description="Make room by delaying work with slack.",
                immediate_effects={"type": "defer"},
                risk_effect=-3,
                reschedule_effect=1,
            ),
        ],
    )


def _queue_congestion_card(state: SimulationState, shop: Shop, ordinal: int, day: int) -> DecisionCard:
    """Build a card for a shop queue that needs a dispatching rule."""
    queued_jobs = [state.jobs[job_id] for job_id in shop.queued_job_ids if job_id in state.jobs]
    critical_count = sum(1 for job in queued_jobs if job.critical_path)
    description = (
        f"{shop.name} has several subjobs waiting for the same kind of station. Pick the dispatch rule."
    )
    if critical_count:
        description += f" {critical_count} waiting subjob(s) matter a lot."
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.QUEUE_CONGESTION,
        title=f"{shop.name} queue is crowded",
        description=description,
        target_ids=[shop.id],
        severity=min(5, 2 + len(queued_jobs) // 3 + critical_count),
        choices=[
            DecisionChoice(
                id="1",
                label="Due dates first",
                description="Run the nearest due work first.",
                immediate_effects={"type": "resequence"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Split the queue",
                description="Move some work to other capable stations.",
                immediate_effects={"type": "split_capacity"},
                risk_effect=-6,
                reschedule_effect=2,
            ),
            DecisionChoice(
                id="3",
                label="Push slack back",
                description="Delay work that has room.",
                immediate_effects={"type": "defer"},
                risk_effect=-2,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Keep the line",
                description="Do not change the queue today.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
                reschedule_effect=0,
            ),
        ],
    )


def _critical_path_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    """Build a card for a subjob that threatens final completion timing."""
    piece_name = _piece_label(job.piece_id)
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.CRITICAL_PATH,
        title=f"{piece_name} is at risk",
        description=f"{piece_name} needs {_capability_label(job.required_capability)} work. {_job_context(state, job)}",
        target_ids=[job.id],
        severity=5 if job.risk_score >= 70 else 4,
        choices=[
            DecisionChoice(
                id="1",
                label="Protect this job",
                description="Put this dependency ahead of routine starts.",
                immediate_effects={"type": "protect_critical"},
                risk_effect=-6,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Reroute it",
                description="Move it to another capable station.",
                immediate_effects={"type": "reroute"},
                risk_effect=-6,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Bump lower work",
                description="Interrupt lower-priority work if it blocks this job.",
                immediate_effects={"type": "preempt"},
                risk_effect=-7,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Hold the line",
                description="Keep the queue steady and accept the risk.",
                immediate_effects={"type": "wait"},
                risk_effect=4,
                reschedule_effect=0,
            ),
        ],
    )


def _handoff_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    """Build a card around a cross-shop dependency handoff."""
    piece_name = _piece_label(job.piece_id)
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
        title=f"Handoff into {destination}",
        description=f"{piece_name} is moving from {source} to {destination}. {_job_context(state, job)}",
        target_ids=[job.id],
        severity=4 if job.critical_path or job.risk_score >= 55 else 3,
        choices=[
            DecisionChoice(
                id="1",
                label="Pull feeder work",
                description="Move earlier work up so the handoff is ready.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Hold a slot",
                description="Keep receiving capacity open for this handoff.",
                immediate_effects={"type": "resequence"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Reroute feeder",
                description="Use a different station if the current lane is tight.",
                immediate_effects={"type": "reroute"},
                risk_effect=-5,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Let shops sort it",
                description="Keep the handoff informal today.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
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
        title=f"{job.id} has another route",
        description=f"{_capability_label(job.required_capability).title()} work can move. {_job_context(state, job)}",
        target_ids=[job.id],
        severity=3,
        choices=[
            DecisionChoice(
                id="1",
                label="Reroute it",
                description="Move the subjob to another capable station.",
                immediate_effects={"type": "reroute"},
                risk_effect=-6,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Wait one day",
                description="Keep the current queue and avoid setup churn.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
                reschedule_effect=0,
            ),
            DecisionChoice(
                id="3",
                label="Move similar work",
                description="Use the open route for related ready work.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
        ],
    )


def _quality_triage_card(state: SimulationState, job: Job, ordinal: int, day: int) -> DecisionCard:
    """Build a card for preventive quality or rework containment."""
    piece_name = _piece_label(job.piece_id)
    return DecisionCard(
        id=f"DAY-{day:02d}-DEC-{ordinal}",
        day=day,
        type=DecisionType.QUALITY_REWORK,
        title=f"{job.id} may need rework",
        description=f"{piece_name} has little room for a quality loop. {_job_context(state, job)}",
        target_ids=[job.id],
        severity=4 if job.critical_path or job.risk_score >= 55 else 3,
        choices=[
            DecisionChoice(
                id="1",
                label="Check it now",
                description="Add a quick containment check before it moves on.",
                immediate_effects={"type": "resequence"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Use clean capacity",
                description="Move it to a less crowded station.",
                immediate_effects={"type": "reroute"},
                risk_effect=-5,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Slow suspect starts",
                description="Hold lower-urgency starts until this clears.",
                immediate_effects={"type": "defer"},
                risk_effect=-2,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="4",
                label="Wait for proof",
                description="Do nothing unless a defect is confirmed.",
                immediate_effects={"type": "wait"},
                risk_effect=4,
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
        title="A station is idle",
        description=_idle_capacity_description(state),
        target_ids=[],
        severity=3,
        choices=[
            DecisionChoice(
                id="1",
                label="Fill it now",
                description="Move ready work into the open station.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Save it",
                description="Keep the station open for trouble.",
                immediate_effects={"type": "wait"},
                risk_effect=2,
                reschedule_effect=0,
            ),
            DecisionChoice(
                id="3",
                label="Move short jobs",
                description="Use the open station for quick ready work.",
                immediate_effects={"type": "resequence"},
                risk_effect=-3,
                reschedule_effect=1,
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
        title="Unfinished jobs remain",
        description=_completion_readiness_description(state),
        target_ids=target_ids,
        severity=4 if day >= late_stage_day else 3,
        choices=[
            DecisionChoice(
                id="1",
                label="Finish near-done jobs",
                description="Push jobs that are closest to complete.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-5,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Clear blockers",
                description="Spend effort where work is stuck.",
                immediate_effects={"type": "resequence"},
                risk_effect=-4,
                reschedule_effect=2,
            ),
            DecisionChoice(
                id="3",
                label="Keep a buffer",
                description="Avoid queue churn and save recovery room.",
                immediate_effects={"type": "wait"},
                risk_effect=3,
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
        title="Pick today's rule",
        description="Several queues are close. What wins today?",
        target_ids=target_ids,
        severity=2,
        choices=[
            DecisionChoice(
                id="1",
                label="Due dates first",
                description="Run the work with the nearest due date.",
                immediate_effects={"type": "resequence"},
                risk_effect=-3,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Open stations first",
                description="Fill idle capacity before it is wasted.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-4,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Stable queues",
                description="Let the current shop order run.",
                immediate_effects={"type": "wait"},
                risk_effect=2,
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
        title=f"Small tradeoff {ordinal}",
        description="No single problem owns the day. Pick the shop rule.",
        target_ids=target_ids,
        severity=2,
        choices=[
            DecisionChoice(
                id="1",
                label="Rebalance work",
                description="Move attention toward urgent queues.",
                immediate_effects={"type": "resequence"},
                risk_effect=-2,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="2",
                label="Pull work forward",
                description="Use open capacity before the day gets crowded.",
                immediate_effects={"type": "pull_forward"},
                risk_effect=-3,
                reschedule_effect=1,
            ),
            DecisionChoice(
                id="3",
                label="Stay steady",
                description="Keep queues intact today.",
                immediate_effects={"type": "wait"},
                risk_effect=2,
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
    accelerated = 0
    assigned = 0
    for job in critical:
        job.priority += 12
        if job.assigned_workcenter_id and job.status == JobStatus.QUEUED:
            state.assign_job(job.id, job.assigned_workcenter_id, front=True)
            assigned += 1
        elif job.status == JobStatus.READY:
            target = _best_alternate_workcenter(state, job, allow_primary=True)
            if target and state.assign_job(job.id, target.id, front=True):
                assigned += 1
        if _prepare_urgent_job(job):
            accelerated += 1
    detail = f"Protected {len(critical)} critical-path subjobs by raising priority"
    if assigned:
        detail += f", front-loading {assigned}"
    if accelerated:
        detail += f", accelerating {accelerated}"
    return f"{detail}."


def _prepare_urgent_job(job: Job) -> bool:
    """Make urgent work genuinely shorter, including before duration locking."""
    if job.is_complete:
        return False
    changed = False
    if not job.started_once and job.base_duration_shifts > 1:
        job.base_duration_shifts -= 1
        changed = True
    if job.remaining_duration_shifts > 1:
        job.remaining_duration_shifts -= 1
        changed = True
    return changed


def _expedite_event(state: SimulationState, event_id: str | None) -> str:
    """Shorten and soften an active or warned event."""
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
        if not alt:
            continue
        current = state.workcenters.get(job.assigned_workcenter_id) if job.assigned_workcenter_id else None
        current_disrupted = bool(
            current
            and current.status in {WorkCenterStatus.DOWN, WorkCenterStatus.BLOCKED, WorkCenterStatus.WEATHER_IMPACTED}
        )
        if job.status == JobStatus.RUNNING and not current_disrupted:
            continue
        if current and not current_disrupted:
            current_load = len(current.queue) + (1 if current.current_job_id else 0)
            alt_load = len(alt.queue) + (1 if alt.current_job_id else 0)
            if alt_load >= current_load:
                continue
        if alt:
            state.assign_job(job.id, alt.id, front=job.critical_path)
            job.priority += 5
            moved += 1
    if moved:
        return f"Rerouted {moved} affected subjob(s) to alternate capable workcenters."
    boosted = 0
    prepared = 0
    for job in jobs[:3]:
        if job.is_complete:
            continue
        job.priority += 8
        if job.assigned_workcenter_id and job.status == JobStatus.QUEUED:
            state.assign_job(job.id, job.assigned_workcenter_id, front=True)
        elif job.status == JobStatus.READY:
            target = _best_alternate_workcenter(state, job, allow_primary=True)
            if target:
                state.assign_job(job.id, target.id, front=True)
        if _prepare_urgent_job(job):
            prepared += 1
        boosted += 1
    if boosted:
        note = f"No better route was open; raised priority on {boosted} urgent subjob(s)"
        if prepared:
            note += f" and prepared {prepared}"
        return f"{note}."
    return "No better route was open today."


def _preempt_for_card(state: SimulationState, card: DecisionCard) -> str:
    """Interrupt lower-priority work when a card's target justifies it."""
    jobs = _jobs_for_card(state, card)
    for job in jobs:
        for wc_id in job.candidate_workcenter_ids:
            if wc_id not in state.workcenters:
                continue
            wc = state.workcenters[wc_id]
            if wc.current_job_id and state.jobs[wc.current_job_id].priority + 15 < job.priority:
                state.preempt_current_job(wc.id, job.id)
                return f"Preempted lower-priority work on {wc.name} for {job.id}."
    boosted = 0
    prepared = 0
    for job in jobs[:3]:
        if job.is_complete:
            continue
        job.priority += 9
        if job.assigned_workcenter_id and job.status == JobStatus.QUEUED:
            state.assign_job(job.id, job.assigned_workcenter_id, front=True)
        if _prepare_urgent_job(job):
            prepared += 1
        boosted += 1
    if boosted:
        note = f"No safe preemption was available; raised priority on {boosted} urgent subjob(s)"
        if prepared:
            note += f" and prepared {prepared}"
        return f"{note}."
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
    if moved:
        return f"Pulled forward {moved} ready subjobs into available capacity."
    prepared = 0
    for job in _jobs_for_card(state, card)[:3]:
        job.priority += 6
        if _prepare_urgent_job(job):
            prepared += 1
    if prepared:
        return f"No ready work could move; prepared {prepared} urgent subjob(s)."
    return f"Pulled forward {moved} ready subjobs into available capacity."


def _use_echo_recommendation(state: SimulationState, card: DecisionCard) -> str:
    """Apply the experimental ECHO recommendation with a deterministic failure chance."""
    event_id = next((target_id for target_id in card.target_ids if _event_by_id(state, target_id)), card.id)
    roll = random.Random(f"{state.seed}:{event_id}:echo-recommendation")
    if roll.random() < 0.28:
        return "ECHO recommendation did not produce a usable move; the team lost some analysis time."

    protected_note = _protect_critical(state)
    pulled_note = _pull_forward_unaffected(state, card)
    accelerated = 0
    for job in state.get_critical_path_jobs()[:4]:
        if job.status in {JobStatus.QUEUED, JobStatus.READY} and job.remaining_duration_shifts > 1:
            job.remaining_duration_shifts -= 1
            accelerated += 1
    return f"ECHO recommendation worked: {protected_note} {pulled_note} Accelerated {accelerated} critical subjob(s)."


def _add_unexpected_job(state: SimulationState, event_id: str | None, prioritize: bool) -> str:
    """Add the event's new top-level job with the selected priority mode."""
    event = _event_by_id(state, event_id)
    if not event:
        return "No new job request was available to add."
    piece_id = insert_unexpected_job(state, event, prioritize=prioritize)
    mode = "prioritized" if prioritize else "added to the back of the queue"
    return f"{_piece_label(piece_id)} was {mode}; the submarine build now has {len(state.pieces)} top-level jobs."


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
    live_jobs = list({job.id: job for job in jobs if not job.is_complete}.values())
    if not live_jobs:
        live_jobs = state.get_critical_path_jobs()[:5] or state.get_ready_jobs()[:5]
    return sorted(
        live_jobs,
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
        return _piece_label(target_id)
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
