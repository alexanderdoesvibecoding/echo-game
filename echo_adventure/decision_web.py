"""Generate and solve the complete seed-specific decision web at startup."""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field

from .config import GameConfig
from .decisions.cards import build_preplanned_decision_card
from .decisions.definitions import BASE_DEFINITIONS, DEFINITIONS_BY_ID, DecisionDefinition
from .enums import JobStatus
from .models import DecisionCard, DecisionChoice, Job, Scenario, SimulationState


_JOB_TARGET_SCHEDULE_LENGTH = 200
_JOB_TARGET_WINDOW_PATTERN = (2, 1)
_DEADLINE_CHECK_INTERVAL = 256


class DecisionWebGenerationTimeout(TimeoutError):
    """Raised before a partially generated decision web can be used."""


@dataclass(frozen=True)
class DecisionWebState:
    """All future-relevant state at one question node."""

    day: int
    question_index: int
    remaining_days: tuple[int, ...]
    completed_mask: int
    pending_definition_id: str = ""
    pending_job_index: int = -1
    pending_available_day: int = 0
    pending_trigger_delta: int = 0
    pending_source_day: int = 0
    pending_source_definition_id: str = ""
    pending_source_choice_id: str = ""


@dataclass(frozen=True)
class DecisionWebTransition:
    next_node_id: str | None
    advances_day: bool
    completion_day: int | None = None
    enters_overtime: bool = False
    unfinished_job_days: int = 0


@dataclass
class DecisionWebNode:
    state: DecisionWebState
    card: DecisionCard
    transitions: dict[str, DecisionWebTransition] = field(default_factory=dict)
    optimal_choice_id: str = ""
    optimal_completion_day: int = 0
    optimal_future_score: float = 0.0
    optimal_future_unfinished_job_days: int = 0


@dataclass
class DecisionWeb:
    """One fully materialized DAG shared by the player and ECHO."""

    root_node_id: str
    nodes: dict[str, DecisionWebNode]
    question_counts: dict[int, int]
    optimal_completion_day: int
    optimal_unfinished_job_days: int
    generation_attempt: int

    def node(self, node_id: str) -> DecisionWebNode:
        return self.nodes[node_id]

    def transition(self, node_id: str, choice_id: str) -> DecisionWebTransition:
        return self.nodes[node_id].transitions[choice_id]

    def question_count(self, day: int) -> int:
        return self.question_counts[day]

    def assert_runtime_matches(self, state: SimulationState, node_id: str) -> None:
        """Catch any drift between runtime traversal and the precomputed web."""
        node_state = self.nodes[node_id].state
        remaining = tuple(state.jobs[job_id].remaining_days for job_id in sorted(state.jobs))
        completed_mask = _completed_mask(state)
        if (
            state.current_day != node_state.day
            or remaining != node_state.remaining_days
            or completed_mask != node_state.completed_mask
        ):
            raise RuntimeError(f"Runtime state diverged from decision web node {node_id}.")


class _DecisionWebBuilder:
    def __init__(
        self,
        scenario: Scenario,
        config: GameConfig,
        generation_attempt: int,
        deadline: float | None = None,
    ) -> None:
        self.scenario = scenario
        self.config = config
        self.generation_attempt = generation_attempt
        self.deadline = deadline
        self.job_ids = tuple(sorted(scenario.jobs))
        self.job_index = {job_id: index for index, job_id in enumerate(self.job_ids)}
        self.job_target_schedule = self._build_job_target_schedule()
        self.nodes: dict[str, DecisionWebNode] = {}
        self.nodes_by_state: dict[DecisionWebState, str] = {}
        self.nodes_by_step: dict[int, list[str]] = {}
        self.question_counts = {
            day: random.Random(
                _stable_seed(
                    scenario.seed,
                    day,
                    f"web-question-count-attempt-{generation_attempt}",
                )
            ).randint(
                config.min_decisions_per_day,
                config.max_decisions_per_day,
            )
            for day in range(1, config.max_campaign_day)
        }
        self.step_offsets: dict[int, int] = {}
        offset = 0
        for day in range(1, config.max_campaign_day):
            self.step_offsets[day] = offset
            offset += self.question_counts[day]
        self.base_schedule = self._build_base_schedule()

    def build(self) -> DecisionWeb:
        self._check_deadline(force=True)
        root_state = DecisionWebState(
            day=1,
            question_index=0,
            remaining_days=tuple(self.scenario.jobs[job_id].remaining_days for job_id in self.job_ids),
            completed_mask=0,
        )
        root_node_id = self._ensure_node(root_state)
        self._solve()
        self._check_deadline(force=True)
        root = self.nodes[root_node_id]
        return DecisionWeb(
            root_node_id=root_node_id,
            nodes=self.nodes,
            question_counts=self.question_counts,
            optimal_completion_day=root.optimal_completion_day,
            optimal_unfinished_job_days=root.optimal_future_unfinished_job_days,
            generation_attempt=self.generation_attempt,
        )

    def _build_job_target_schedule(self) -> tuple[str, ...]:
        rng = random.Random(
            _stable_seed(self.scenario.seed, 0, "web-job-target-schedule")
        )
        schedule: list[str] = []
        while len(schedule) < _JOB_TARGET_SCHEDULE_LENGTH:
            block = list(self.job_ids)
            rng.shuffle(block)
            schedule.extend(block)
        return tuple(schedule[:_JOB_TARGET_SCHEDULE_LENGTH])

    def _select_scheduled_job(self, day: int, incomplete: list[Job]) -> Job:
        incomplete_by_id = {job.id: job for job in incomplete}
        schedule_index = _target_window_index(day)
        for offset in range(_JOB_TARGET_SCHEDULE_LENGTH):
            job_id = self.job_target_schedule[
                (schedule_index + offset) % _JOB_TARGET_SCHEDULE_LENGTH
            ]
            if job_id in incomplete_by_id:
                return incomplete_by_id[job_id]
        raise RuntimeError("The target schedule contains no unfinished job.")

    def _build_base_schedule(self) -> dict[tuple[int, int], DecisionDefinition]:
        safe_definitions = [definition for definition in BASE_DEFINITIONS if not _has_follow_up(definition)]
        schedule: dict[tuple[int, int], DecisionDefinition] = {}
        scheduled_counts = {definition.id: 0 for definition in BASE_DEFINITIONS}
        for day, count in self.question_counts.items():
            used: set[str] = set()
            for question_index in range(count):
                # Keep the final question branch-free to bound pending-state
                # fanout while delayed follow-ups cross daily boundaries.
                pool = safe_definitions if question_index == count - 1 else list(BASE_DEFINITIONS)
                available = [definition for definition in pool if definition.id not in used] or pool
                least_uses = min(scheduled_counts[definition.id] for definition in available)
                candidates = [
                    definition
                    for definition in available
                    if scheduled_counts[definition.id] == least_uses
                ]
                rng = random.Random(
                    _stable_seed(
                        self.scenario.seed,
                        day,
                        f"web-definition-{question_index}-attempt-{self.generation_attempt}",
                    )
                )
                definition = rng.choice(candidates)
                schedule[(day, question_index)] = definition
                used.add(definition.id)
                scheduled_counts[definition.id] += 1
        return schedule

    def _ensure_node(self, state: DecisionWebState) -> str:
        existing = self.nodes_by_state.get(state)
        if existing:
            return existing

        self._check_deadline()

        node_id = f"NODE-{len(self.nodes) + 1:07d}"
        step = self.step_offsets[state.day] + state.question_index
        card = self._build_card(state, node_id)
        node = DecisionWebNode(state=state, card=card)
        self.nodes_by_state[state] = node_id
        self.nodes[node_id] = node
        self.nodes_by_step.setdefault(step, []).append(node_id)

        for choice in card.choices:
            transition = self._build_transition(state, node_id, card, choice)
            node.transitions[choice.id] = transition
        return node_id

    def _build_card(self, state: DecisionWebState, node_id: str) -> DecisionCard:
        runtime_state = self._runtime_state(state)
        incomplete = sorted(
            runtime_state.incomplete_jobs(),
            key=lambda job: (-job.remaining_days, job.id),
        )
        if not incomplete:
            raise RuntimeError("A completed planning state cannot contain another question node.")

        definition = self.base_schedule[(state.day, state.question_index)]
        primary = self._select_scheduled_job(state.day, incomplete)
        showing_pending = bool(
            state.pending_definition_id
            and state.pending_available_day <= state.day
            and not definition.shared_across_routes
        )
        if showing_pending:
            definition = DEFINITIONS_BY_ID[state.pending_definition_id]
            pending_job_id = self.job_ids[state.pending_job_index]
            pending_job = runtime_state.jobs[pending_job_id]
            if not pending_job.is_complete:
                primary = pending_job

        return build_preplanned_decision_card(
            runtime_state,
            definition,
            primary,
            incomplete,
            question_number=state.question_index + 1,
            node_token=node_id.rsplit("-", 1)[-1],
            trigger_delta=state.pending_trigger_delta if showing_pending else 0,
            follow_up_source_day=(
                state.pending_source_day if showing_pending else None
            ),
            follow_up_source_definition_id=(
                state.pending_source_definition_id if showing_pending else ""
            ),
            follow_up_source_choice_id=(
                state.pending_source_choice_id if showing_pending else ""
            ),
        )

    def _runtime_state(self, state: DecisionWebState) -> SimulationState:
        jobs: dict[str, Job] = {}
        completed: set[str] = set()
        for index, job_id in enumerate(self.job_ids):
            template = self.scenario.jobs[job_id]
            is_complete = bool(state.completed_mask & (1 << index))
            jobs[job_id] = Job(
                id=template.id,
                name=template.name,
                initial_duration_days=template.initial_duration_days,
                remaining_days=state.remaining_days[index],
                status=JobStatus.COMPLETE if is_complete else JobStatus.IN_PROGRESS,
            )
            if is_complete:
                completed.add(job_id)
        return SimulationState(
            seed=self.scenario.seed,
            jobs=jobs,
            current_day=state.day,
            completed_jobs=completed,
        )

    def _build_transition(
        self,
        state: DecisionWebState,
        node_id: str,
        card: DecisionCard,
        choice: DecisionChoice,
    ) -> DecisionWebTransition:
        remaining = list(state.remaining_days)
        completed_mask = state.completed_mask
        for job_id, delta in choice.day_changes.items():
            index = self.job_index[job_id]
            if not completed_mask & (1 << index):
                remaining[index] += delta
                if remaining[index] <= 0:
                    remaining[index] = 0
                    completed_mask |= 1 << index

        all_completed_mask = (1 << len(remaining)) - 1
        if completed_mask == all_completed_mask:
            return DecisionWebTransition(
                next_node_id=None,
                advances_day=True,
                completion_day=state.day,
            )

        pending_definition_id = state.pending_definition_id
        pending_job_index = state.pending_job_index
        pending_available_day = state.pending_available_day
        pending_trigger_delta = state.pending_trigger_delta
        pending_source_day = state.pending_source_day
        pending_source_definition_id = state.pending_source_definition_id
        pending_source_choice_id = state.pending_source_choice_id

        showing_pending = bool(
            pending_definition_id
            and card.definition_id == pending_definition_id
            and card.event_scope == "follow-up"
        )
        pending_job_completed = bool(
            pending_definition_id
            and completed_mask & (1 << pending_job_index)
        )
        if showing_pending or pending_job_completed:
            pending_definition_id = ""
            pending_job_index = -1
            pending_available_day = 0
            pending_trigger_delta = 0
            pending_source_day = 0
            pending_source_definition_id = ""
            pending_source_choice_id = ""

        primary_index = self.job_index[card.primary_job_id]
        if not pending_definition_id and not completed_mask & (1 << primary_index):
            for follow_up in choice.follow_ups:
                if _preplanned_follow_up_occurs(
                    self.scenario.seed,
                    card,
                    choice,
                    follow_up.definition_id,
                    follow_up.probability,
                    self.generation_attempt,
                ):
                    pending_definition_id = follow_up.definition_id
                    pending_job_index = primary_index
                    pending_available_day = state.day + follow_up.delay_days
                    pending_trigger_delta = sum(choice.day_changes.values())
                    pending_source_day = state.day
                    pending_source_definition_id = card.definition_id
                    pending_source_choice_id = choice.id
                    break

        question_count = self.question_counts[state.day]
        is_last_question = state.question_index + 1 == question_count
        if not is_last_question:
            next_state = DecisionWebState(
                day=state.day,
                question_index=state.question_index + 1,
                remaining_days=tuple(remaining),
                completed_mask=completed_mask,
                pending_definition_id=pending_definition_id,
                pending_job_index=pending_job_index,
                pending_available_day=pending_available_day,
                pending_trigger_delta=pending_trigger_delta,
                pending_source_day=pending_source_day,
                pending_source_definition_id=pending_source_definition_id,
                pending_source_choice_id=pending_source_choice_id,
            )
            return DecisionWebTransition(
                next_node_id=self._ensure_node(next_state),
                advances_day=False,
            )

        incomplete_indexes = [
            index
            for index in range(len(remaining))
            if not completed_mask & (1 << index)
        ]
        unfinished_job_days = sum(remaining[index] for index in incomplete_indexes)
        for index in incomplete_indexes:
            remaining[index] = max(0, remaining[index] - 1)
            if remaining[index] == 0:
                completed_mask |= 1 << index

        if (
            pending_definition_id
            and completed_mask & (1 << pending_job_index)
        ):
            pending_definition_id = ""
            pending_job_index = -1
            pending_available_day = 0
            pending_trigger_delta = 0
            pending_source_day = 0
            pending_source_definition_id = ""
            pending_source_choice_id = ""

        if completed_mask == all_completed_mask:
            return DecisionWebTransition(
                next_node_id=None,
                advances_day=True,
                completion_day=state.day,
                unfinished_job_days=unfinished_job_days,
            )
        if state.day + 1 >= self.config.max_campaign_day:
            return DecisionWebTransition(
                next_node_id=None,
                advances_day=True,
                enters_overtime=True,
                unfinished_job_days=unfinished_job_days,
            )

        next_state = DecisionWebState(
            day=state.day + 1,
            question_index=0,
            remaining_days=tuple(remaining),
            completed_mask=completed_mask,
            pending_definition_id=pending_definition_id,
            pending_job_index=pending_job_index,
            pending_available_day=pending_available_day,
            pending_trigger_delta=pending_trigger_delta,
            pending_source_day=pending_source_day,
            pending_source_definition_id=pending_source_definition_id,
            pending_source_choice_id=pending_source_choice_id,
        )
        return DecisionWebTransition(
            next_node_id=self._ensure_node(next_state),
            advances_day=True,
            unfinished_job_days=unfinished_job_days,
        )

    def _solve(self) -> None:
        """Solve backward by finish, score, unfinished work, then stable choice ID."""
        solved_nodes = 0
        for step in sorted(self.nodes_by_step, reverse=True):
            for node_id in self.nodes_by_step[step]:
                if solved_nodes % _DEADLINE_CHECK_INTERVAL == 0:
                    self._check_deadline(force=True)
                solved_nodes += 1
                node = self.nodes[node_id]
                candidates: list[tuple[int, float, int, str]] = []
                choices = {choice.id: choice for choice in node.card.choices}
                for choice_id, transition in node.transitions.items():
                    choice = choices[choice_id]
                    if transition.completion_day is not None:
                        completion_day = transition.completion_day
                        future_score = 0.0
                        future_unfinished_job_days = 0
                    elif transition.enters_overtime:
                        completion_day = self.config.max_campaign_day
                        future_score = 0.0
                        future_unfinished_job_days = 0
                    else:
                        successor = self.nodes[transition.next_node_id or ""]
                        completion_day = successor.optimal_completion_day
                        future_score = successor.optimal_future_score
                        future_unfinished_job_days = (
                            successor.optimal_future_unfinished_job_days
                        )
                    total_score = round(choice.score_delta + future_score, 2)
                    total_unfinished_job_days = (
                        transition.unfinished_job_days + future_unfinished_job_days
                    )
                    candidates.append(
                        (
                            completion_day,
                            total_score,
                            total_unfinished_job_days,
                            choice_id,
                        )
                    )

                completion_day, total_score, unfinished_job_days, choice_id = min(
                    candidates,
                    key=lambda candidate: (
                        candidate[0],
                        -candidate[1],
                        candidate[2],
                        candidate[3],
                    ),
                )
                node.optimal_choice_id = choice_id
                node.optimal_completion_day = completion_day
                node.optimal_future_score = total_score
                node.optimal_future_unfinished_job_days = unfinished_job_days
                node.card.echo_choice_id = choice_id

    def _check_deadline(self, *, force: bool = False) -> None:
        if self.deadline is None:
            return
        if not force and len(self.nodes) % _DEADLINE_CHECK_INTERVAL:
            return
        if time.monotonic() >= self.deadline:
            raise DecisionWebGenerationTimeout(
                f"Decision web generation timed out for seed {self.scenario.seed}."
            )


def generate_decision_web(
    scenario: Scenario,
    config: GameConfig,
    *,
    max_generation_seconds: float | None = None,
) -> DecisionWeb:
    """Materialize a web whose globally optimal route finishes before overtime."""
    if max_generation_seconds is not None and max_generation_seconds <= 0:
        raise ValueError("max_generation_seconds must be greater than zero.")
    deadline = (
        None
        if max_generation_seconds is None
        else time.monotonic() + max_generation_seconds
    )
    for generation_attempt in range(32):
        web = _DecisionWebBuilder(
            scenario,
            config,
            generation_attempt,
            deadline=deadline,
        ).build()
        if web.optimal_completion_day < config.max_campaign_day:
            return web
    raise RuntimeError("Could not generate an ECHO-winning decision web in 32 attempts.")


def _has_follow_up(definition: DecisionDefinition) -> bool:
    return bool(
        definition.unavoidable_follow_up_edges
        or any(choice.follow_up_edges for choice in definition.choices)
    )


def _target_window_index(day: int) -> int:
    zero_based_day = day - 1
    cycle, position = divmod(zero_based_day, sum(_JOB_TARGET_WINDOW_PATTERN))
    window_in_cycle = next(
        index
        for index in range(len(_JOB_TARGET_WINDOW_PATTERN))
        if position < sum(_JOB_TARGET_WINDOW_PATTERN[: index + 1])
    )
    return cycle * len(_JOB_TARGET_WINDOW_PATTERN) + window_in_cycle


def _preplanned_follow_up_occurs(
    seed: int,
    card: DecisionCard,
    choice: DecisionChoice,
    definition_id: str,
    probability: float,
    generation_attempt: int,
) -> bool:
    material = "|".join(
        (
            str(seed),
            str(generation_attempt),
            card.event_id or card.id,
            choice.id,
            definition_id,
        )
    ).encode("utf-8")
    roll = int(hashlib.sha256(material).hexdigest(), 16) / float(1 << 256)
    return roll < max(0.0, min(1.0, probability))


def _stable_seed(seed: int, day: int, suffix: str) -> int:
    material = f"{seed}|{day}|{suffix}".encode("utf-8")
    return int(hashlib.sha256(material).hexdigest(), 16)


def _completed_mask(state: SimulationState) -> int:
    mask = 0
    for index, job_id in enumerate(sorted(state.jobs)):
        if state.jobs[job_id].is_complete:
            mask |= 1 << index
    return mask
