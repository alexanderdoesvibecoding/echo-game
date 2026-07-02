"""Campaign decision graph generation and active-card filtering."""

from __future__ import annotations

import hashlib

from ..config import GameConfig
from ..metrics import update_state_metrics
from ..models import (
    CampaignDecisionGraph,
    DecisionCard,
    DecisionChoice,
    DecisionProgress,
    SimulationState,
)
from .cards import (
    _clone_choices,
    _generate_root_decision_cards,
    _generate_scheduled_event_cards,
    _strategic_card,
)
from .scoring import select_echo_choice

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
