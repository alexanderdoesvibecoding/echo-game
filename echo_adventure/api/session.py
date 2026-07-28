"""Thread-safe ownership of the player and ECHO runs."""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any

from ..config import GameConfig, resolve_seed
from ..decision_web import (
    DecisionWebGenerationTimeout,
    DecisionWebTransition,
    generate_decision_web,
)
from ..decisions import apply_choice as apply_decision_choice
from ..decisions import generate_daily_decision_cards, generate_final_assembly_cards
from ..decisions import select_echo_choice_for_state
from ..echo import advance_omniscient_day, apply_omniscient_choice
from ..models import DecisionCard, DecisionChoice
from ..scenario_generator import generate_scenario
from ..simulation import DayResult, advance_day as simulate_day, initialize_state
from .automation import (
    AUTOMATION_STRATEGY_ORDER,
    AutomationContext,
    reachable_preplanned_days,
    select_preplanned_choice,
    select_runtime_choice,
    validate_automation_strategy,
)
from .payloads import PayloadMixin
from .review import ReviewMixin


_RANDOM_SEED_WEB_TIMEOUT_SECONDS = 10.0
_MAX_AUTOMATED_ACTIONS = 10_000
_MAX_AUTOMATED_DAYS = 1_000
_MAX_WORST_STAGNANT_DAYS = 20


def _process_current_rss_bytes() -> int | None:
    """Return the process's current resident memory using only the standard library."""
    # Each platform branch is best-effort because diagnostics must never prevent
    # a game from starting on an unsupported or sandboxed host.
    if sys.platform == "darwin":
        try:
            import ctypes

            class TimeValue(ctypes.Structure):
                """Mirror the Mach time-value structure used by task_info."""
                _fields_ = [
                    ("seconds", ctypes.c_int32),
                    ("microseconds", ctypes.c_int32),
                ]

            class MachTaskBasicInfo(ctypes.Structure):
                """Mirror the Mach basic task information structure."""
                _fields_ = [
                    ("virtual_size", ctypes.c_uint64),
                    ("resident_size", ctypes.c_uint64),
                    ("resident_size_max", ctypes.c_uint64),
                    ("user_time", TimeValue),
                    ("system_time", TimeValue),
                    ("policy", ctypes.c_int32),
                    ("suspend_count", ctypes.c_int32),
                ]

            library = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
            library.mach_task_self.restype = ctypes.c_uint32
            library.task_info.argtypes = [
                ctypes.c_uint32,
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_uint32),
            ]
            library.task_info.restype = ctypes.c_int
            info = MachTaskBasicInfo()
            count = ctypes.c_uint32(
                ctypes.sizeof(info) // ctypes.sizeof(ctypes.c_uint32)
            )
            # MACH_TASK_BASIC_INFO is passed numerically to avoid a third-party
            # binding solely for developer-mode memory reporting.
            status = library.task_info(
                library.mach_task_self(),
                20,  # MACH_TASK_BASIC_INFO
                ctypes.byref(info),
                ctypes.byref(count),
            )
            return int(info.resident_size) if status == 0 else None
        except (AttributeError, OSError, TypeError, ValueError):
            return None

    if sys.platform.startswith("linux"):
        try:
            # statm reports pages; sysconf supplies the runtime page size needed
            # to normalize the value to bytes.
            with open("/proc/self/statm", encoding="ascii") as statm:
                resident_pages = int(statm.read().split()[1])
            return resident_pages * int(os.sysconf("SC_PAGE_SIZE"))
        except (IndexError, OSError, TypeError, ValueError):
            return None

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                """Mirror the Windows process-memory counter structure."""
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("page_fault_count", wintypes.DWORD),
                    ("peak_working_set_size", ctypes.c_size_t),
                    ("working_set_size", ctypes.c_size_t),
                    ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                    ("quota_paged_pool_usage", ctypes.c_size_t),
                    ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                    ("quota_non_paged_pool_usage", ctypes.c_size_t),
                    ("pagefile_usage", ctypes.c_size_t),
                    ("peak_pagefile_usage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            # The Windows API writes directly into the structure and reports
            # success as a nonzero integer.
            status = ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(counters),
                counters.cb,
            )
            return int(counters.working_set_size) if status else None
        except (AttributeError, OSError, TypeError, ValueError):
            return None

    return None


def _process_peak_rss_bytes() -> int | None:
    """Return this process's high-water RSS using platform-normalized bytes."""
    try:
        import resource
    except ImportError:
        return None

    # macOS already reports bytes; other supported Unix implementations report
    # kibibytes, so normalize before exposing a cross-platform payload field.
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform != "darwin":
        peak *= 1024
    return peak


class GameSession(PayloadMixin, ReviewMixin):
    """Own one real player run and its immutable ECHO comparison route."""

    def __init__(self, seed: int | None = None, dev_mode: bool = False) -> None:
        """Generate and initialize a complete deterministic game session."""
        self.lock = threading.RLock()
        self.dev_mode = dev_mode
        requested_seed_mode = "explicit" if seed is not None else "random"
        generation_started = time.perf_counter()
        timed_out_random_seeds = 0
        accepted_web_seconds = 0.0
        # Explicit seeds are reproducibility contracts and may build without a
        # deadline. Random seeds may be discarded until a fast valid web is found.
        while True:
            self.seed = resolve_seed(seed)
            self.config = GameConfig(seed=self.seed)
            self.scenario = generate_scenario(self.config)
            web_started = time.perf_counter()
            try:
                self.decision_web = generate_decision_web(
                    self.scenario,
                    self.config,
                    max_generation_seconds=(
                        _RANDOM_SEED_WEB_TIMEOUT_SECONDS
                        if seed is None
                        else None
                    ),
                )
            except DecisionWebGenerationTimeout:
                if seed is not None:
                    raise
                timed_out_random_seeds += 1
                continue
            accepted_web_seconds = time.perf_counter() - web_started
            break
        total_generation_seconds = time.perf_counter() - generation_started
        node_count = len(self.decision_web.nodes)
        # Generation metadata is retained for dev payloads and printed only when
        # developer mode explicitly requests it.
        self.generation_stats: dict[str, Any] = {
            "acceptedSeed": self.seed,
            "requestedSeedMode": requested_seed_mode,
            "totalGenerationSeconds": total_generation_seconds,
            "acceptedWebGenerationSeconds": accepted_web_seconds,
            "timedOutRandomSeedsDiscarded": timed_out_random_seeds,
            "nodeCount": node_count,
            "edgeCount": sum(
                len(node.transitions)
                for node in self.decision_web.nodes.values()
            ),
            "optimalCompletionDay": self.decision_web.optimal_completion_day,
            "nodesPerSecond": (
                node_count / accepted_web_seconds
                if accepted_web_seconds > 0
                else None
            ),
            "processCurrentRssBytes": _process_current_rss_bytes(),
            "processPeakRssBytes": _process_peak_rss_bytes(),
            "processPeakRssScope": "process-high-water-mark",
        }
        self._generation_stats_logged = False
        # Both actors begin from deep-copied identical jobs. The player may
        # diverge, while ECHO independently traverses the solved optimal policy.
        self.player_state = initialize_state(self.scenario)
        self.automated_state = initialize_state(self.scenario)
        self.player_node_id = self.decision_web.root_node_id
        self.pending_player_transition: DecisionWebTransition | None = None
        self.echo_node_id: str | None = self.decision_web.root_node_id
        self.pending_echo_transition: DecisionWebTransition | None = None
        self.echo_choices_applied_today = 0
        # Runtime phase fields are mutually coordinated by advance_day:
        # preplanned web -> optional overtime -> optional final assembly -> done.
        self.player_in_overtime = False
        self.overtime_cards: list[DecisionCard] = []
        self.overtime_card_index = 0
        self.overtime_ready_to_advance = False
        self.player_final_assembly_started = False
        self.player_final_assembly_locked = False
        self.final_assembly_cards: list[DecisionCard] = []
        self.final_assembly_card_index = 0
        self.questions_answered_today = 0
        self.decision_total_today = self.decision_web.question_count(1)
        self.current_cards: list[DecisionCard] = []
        self.last_result: DayResult | None = None
        self.last_summary_puzzle: dict[str, Any] | None = None
        self.last_summary_remaining_jobs: list[dict[str, Any]] = []
        self.day_completed_before: set[str] = set(self.player_state.completed_jobs)
        self._developer_follow_up_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._ensure_cards()

    def refresh_current_rss_stat(self) -> None:
        """Record retained memory after this session becomes the active run."""
        with self.lock:
            self.generation_stats["processCurrentRssBytes"] = (
                _process_current_rss_bytes()
            )

    def log_generation_stats_once(self) -> None:
        """Write this dev generation's retained statistics to stdout once."""
        with self.lock:
            if not self.dev_mode or self._generation_stats_logged:
                return
            self._generation_stats_logged = True
            stats = self.generation_stats
            current_rss = stats["processCurrentRssBytes"]
            peak_rss = stats["processPeakRssBytes"]
            current_label = (
                "unavailable"
                if current_rss is None
                else (
                    f"{current_rss} bytes "
                    f"({current_rss / (1024 * 1024):.2f} MiB)"
                )
            )
            peak_label = (
                "unavailable"
                if peak_rss is None
                else (
                    f"{peak_rss} bytes "
                    f"({peak_rss / (1024 * 1024):.2f} MiB)"
                )
            )
            # Assemble one write so concurrent server output cannot interleave
            # individual report lines.
            report = "\n".join(
                (
                    "[ECHO dev] Decision web generation",
                    f"  Accepted seed: {stats['acceptedSeed']}",
                    f"  Requested seed mode: {stats['requestedSeedMode']}",
                    (
                        "  Total generation time: "
                        f"{stats['totalGenerationSeconds']:.6f} seconds"
                    ),
                    (
                        "  Accepted web generation time: "
                        f"{stats['acceptedWebGenerationSeconds']:.6f} seconds"
                    ),
                    (
                        "  Timed-out random seeds discarded: "
                        f"{stats['timedOutRandomSeedsDiscarded']}"
                    ),
                    f"  Node count: {stats['nodeCount']}",
                    f"  Edge count: {stats['edgeCount']}",
                    (
                        "  Optimal completion day: "
                        f"{stats['optimalCompletionDay']}"
                    ),
                    (
                        "  Nodes per second: "
                        + (
                            "unavailable"
                            if stats["nodesPerSecond"] is None
                            else f"{stats['nodesPerSecond']:.2f}"
                        )
                    ),
                    f"  Process current RSS: {current_label}",
                    (
                        "  Process peak RSS: "
                        f"{peak_label} (lifetime high-water mark; does not decrease)"
                    ),
                )
            )
            print(report, flush=True)

    def apply_choice(self, card_id: str, choice_id: str) -> None:
        """Apply one valid player choice to the active daily decision."""
        with self.lock:
            if self._game_over():
                raise ValueError("The run has already ended.")
            self._ensure_cards()
            card = next((item for item in self.current_cards if item.id == card_id), None)
            if not card:
                raise ValueError("Decision card is no longer active.")
            choice = next((item for item in card.choices if item.id == choice_id), None)
            if not choice:
                raise ValueError("Choice is not valid for that decision.")
            # Overtime cards are not solved in the immutable web, so their ECHO
            # comparison is selected against the live schedule just before use.
            in_final_assembly = self.player_final_assembly_started
            if self.player_in_overtime and not in_final_assembly:
                card.echo_choice_id = select_echo_choice_for_state(
                    self.player_state,
                    card.choices,
                ).id
            apply_decision_choice(
                self.player_state,
                card,
                choice,
                actor="player",
                schedule_follow_ups=self.player_in_overtime and not in_final_assembly,
            )
            self.questions_answered_today += 1
            # Final assembly is player-only; otherwise ECHO consumes exactly the
            # matching decision slot even after its calendar has finished.
            if not in_final_assembly:
                self._apply_echo_choice(self.questions_answered_today)
            self.current_cards = []
            if self._game_over():
                self._finish_automated()
                return
            # Runtime card batches advance by local indexes; preplanned cards
            # instead advance through graph transitions below.
            if in_final_assembly:
                self.final_assembly_card_index += 1
                if self.final_assembly_card_index < len(self.final_assembly_cards):
                    self.current_cards = [
                        self.final_assembly_cards[self.final_assembly_card_index]
                    ]
                else:
                    self.player_final_assembly_locked = True
                return
            if self.player_in_overtime:
                self.overtime_card_index += 1
                if self.overtime_card_index < len(self.overtime_cards):
                    self.current_cards = [self.overtime_cards[self.overtime_card_index]]
                else:
                    self.overtime_ready_to_advance = True
                return

            transition = self.decision_web.transition(self.player_node_id, choice.id)
            if transition.advances_day:
                # Store the edge until the UI explicitly advances after showing
                # the completed set of daily questions.
                self.pending_player_transition = transition
            else:
                if transition.next_node_id is None:
                    raise RuntimeError("A non-daily web edge cannot be terminal.")
                self.player_node_id = transition.next_node_id
                self._ensure_cards()

    def advance_day(self) -> None:
        """Advance both actors through one legal simulation day."""
        with self.lock:
            if self._game_over():
                self._finish_automated()
                return
            if not self.ready_to_advance():
                raise ValueError("Select a response for all decisions before advancing the day.")
            # Final assembly does not advance ECHO: its solved run is already
            # complete and these cards belong only to the player endgame.
            if self.player_final_assembly_started:
                self._record_player_day()
                self._reset_daily_choices()
                if self._game_over():
                    self._finish_automated()
                else:
                    self.questions_answered_today = 0
                    self.decision_total_today = 0
                return
            # Overtime work uses live-generated cards, but the normal once-daily
            # simulation tick and independent ECHO progression still apply.
            if self.player_in_overtime:
                self._record_player_day()
                self._advance_echo_day()
                self._reset_daily_choices()
                if self._game_over():
                    self._finish_automated()
                elif self._should_start_final_assembly():
                    self._start_final_assembly()
                else:
                    self._start_overtime_day()
                return

            # In the preplanned phase the final answered question supplies the
            # already-built daily transition to the next graph node.
            transition = self.pending_player_transition
            if transition is None:
                raise RuntimeError("The completed question sequence has no daily web transition.")
            self._record_player_day()
            self._advance_echo_day()
            self._reset_daily_choices()
            self.pending_player_transition = None
            if self._game_over():
                self._finish_automated()
            elif self._should_start_final_assembly():
                self._start_final_assembly()
            elif transition.next_node_id is not None:
                self.player_node_id = transition.next_node_id
                self.decision_web.assert_runtime_matches(self.player_state, self.player_node_id)
            elif transition.enters_overtime and not self._game_over():
                self.player_in_overtime = True
            if self._game_over() or self.player_final_assembly_started:
                return
            if self.player_in_overtime:
                self._start_overtime_day()
            else:
                self.questions_answered_today = 0
                self.decision_total_today = self.decision_web.question_count(
                    self.player_state.current_day
                )
                self._ensure_cards()

    def ready_to_advance(self) -> bool:
        """Report whether all decisions for the current day are complete."""
        if self.player_final_assembly_started:
            return (
                self.player_final_assembly_locked
                and self.questions_answered_today == self.decision_total_today
            )
        if self.player_in_overtime:
            return (
                self.questions_answered_today == self.decision_total_today
                and self.overtime_ready_to_advance
            )
        return (
            self.questions_answered_today == self.decision_total_today
            and self.pending_player_transition is not None
        )

    def skip(
        self,
        strategy: object,
        target_day: object = None,
    ) -> None:
        """Automate normal choices/day advances for a developer request."""
        with self.lock:
            if not self.dev_mode:
                raise ValueError("Developer mode is not enabled.")
            strategy_name = validate_automation_strategy(strategy)
            target = self._validate_skip_target(target_day)
            if self._game_over():
                raise ValueError("The run has already ended.")

            # Capture the starting state once so random automation is repeatable
            # for dry reachability and the subsequent real traversal.
            context = AutomationContext(
                seed=self.seed,
                start_token=self._automation_start_token(),
            )
            if target is not None:
                if self.player_in_overtime or self.player_final_assembly_started:
                    raise ValueError(
                        "Specific-day skipping is only available in the "
                        "preplanned decision web."
                    )
                reachable_days = self._reachable_days(strategy_name, context)
                if target not in reachable_days:
                    raise ValueError(
                        f"Day {target} is not reachable with the "
                        f"{strategy_name!r} strategy from the current state."
                    )

            start_day = self.player_state.current_day
            actions = 0
            stagnant_days = 0
            previous_runtime_max: int | None = (
                self._maximum_remaining_duration()
                if self.player_in_overtime or self.player_final_assembly_started
                else None
            )

            # Automation intentionally calls the same public mutation methods as
            # manual play; the safety caps defend against malformed runtime state.
            while not self._game_over():
                if target is not None and self.player_state.current_day == target:
                    return
                if actions >= _MAX_AUTOMATED_ACTIONS:
                    raise RuntimeError(
                        "Automated skip exceeded its maximum action count."
                    )
                if self.player_state.current_day - start_day >= _MAX_AUTOMATED_DAYS:
                    raise RuntimeError(
                        "Automated skip exceeded its maximum day count."
                    )

                self._ensure_cards()
                if self.current_cards:
                    card = self.current_cards[0]
                    choice = self._automated_choice(
                        card,
                        strategy_name,
                        context,
                    )
                    self.apply_choice(card.id, choice.id)
                    actions += 1
                    continue

                if not self.ready_to_advance():
                    raise RuntimeError(
                        "Automated skip reached an unfinished state with no "
                        "decision and no available day advance."
                    )

                # The adversarial "worst" strategy receives an extra progress
                # watchdog once it leaves the finite preplanned DAG.
                was_runtime = (
                    self.player_in_overtime
                    or self.player_final_assembly_started
                )
                self.advance_day()
                actions += 1
                is_runtime = (
                    self.player_in_overtime
                    or self.player_final_assembly_started
                )
                if strategy_name != "worst" or self._game_over() or not is_runtime:
                    if not is_runtime:
                        previous_runtime_max = None
                    continue

                current_runtime_max = self._maximum_remaining_duration()
                if (
                    was_runtime
                    and previous_runtime_max is not None
                    and current_runtime_max >= previous_runtime_max
                ):
                    stagnant_days += 1
                else:
                    stagnant_days = 0
                previous_runtime_max = current_runtime_max
                if stagnant_days >= _MAX_WORST_STAGNANT_DAYS:
                    raise RuntimeError(
                        "Worst-strategy skip stopped after repeated overtime "
                        "days without schedule progress."
                    )

    def _automated_choice(
        self,
        card: DecisionCard,
        strategy: str,
        context: AutomationContext,
    ) -> DecisionChoice:
        """Select the next choice for a developer automation strategy."""
        if not self.player_in_overtime and not self.player_final_assembly_started:
            return select_preplanned_choice(
                self.decision_web,
                self.player_node_id,
                strategy,
                context,
                max_campaign_day=self.config.max_campaign_day,
            )
        return select_runtime_choice(
            self.player_state,
            card,
            strategy,
            context,
        )

    def _validate_skip_target(self, target_day: object) -> int | None:
        """Validate a requested developer skip target against reachable days."""
        if target_day is None:
            return None
        if isinstance(target_day, bool) or not isinstance(target_day, int):
            raise ValueError("Target day must be an integer or null.")
        if target_day <= self.player_state.current_day:
            raise ValueError("Target day must be later than the current day.")
        return target_day

    def reachable_days_by_strategy(self) -> dict[str, list[int]]:
        """Return dry preplanned routes for every developer automation strategy."""
        with self.lock:
            if (
                not self.dev_mode
                or self._game_over()
                or self.player_in_overtime
                or self.player_final_assembly_started
            ):
                return {}
            context = AutomationContext(
                seed=self.seed,
                start_token=self._automation_start_token(),
            )
            # Compute routes without mutating session state so rendering the
            # developer panel cannot change the game.
            return {
                strategy: self._reachable_days(strategy, context)
                for strategy in AUTOMATION_STRATEGY_ORDER
            }

    def _reachable_days(
        self,
        strategy: str,
        context: AutomationContext,
    ) -> list[int]:
        """Return the days reachable from the current real run state."""
        return reachable_preplanned_days(
            self.decision_web,
            self.player_node_id,
            strategy,
            context,
            current_day=self.player_state.current_day,
            max_campaign_day=self.config.max_campaign_day,
            pending_transition=self.pending_player_transition,
        )

    def _automation_start_token(self) -> str:
        """Build stable entropy for deterministic automated choices."""
        remaining = ",".join(
            f"{job.id}:{job.remaining_days}"
            for job in sorted(self.player_state.jobs.values(), key=lambda item: item.id)
        )
        pending_transition = self.pending_player_transition
        transition_token = (
            f"{pending_transition.next_node_id}:"
            f"{pending_transition.advances_day}:"
            f"{pending_transition.enters_overtime}"
            if pending_transition
            else ""
        )
        # Include every phase cursor that can make the same visible day/job
        # schedule represent a different automation position.
        return "|".join(
            (
                str(self.player_state.current_day),
                self.player_node_id,
                transition_token,
                str(len(self.player_state.decision_history)),
                str(self.overtime_card_index),
                str(self.final_assembly_card_index),
                str(self.player_state.decision_score),
                remaining,
            )
        )

    def _maximum_remaining_duration(self) -> int:
        """Return the longest unfinished player job duration."""
        return max(
            (
                max(0, job.remaining_days)
                for job in self.player_state.incomplete_jobs()
            ),
            default=0,
        )

    def _ensure_cards(self) -> None:
        """Materialize cards appropriate to the current run phase."""
        # Phase order matters: final assembly and overtime own runtime batches,
        # while a pending web transition means the day is waiting to advance.
        if self._game_over():
            self.current_cards = []
        elif self.player_final_assembly_started:
            if (
                not self.player_final_assembly_locked
                and self.final_assembly_cards
                and not self.current_cards
            ):
                self.current_cards = [
                    self.final_assembly_cards[self.final_assembly_card_index]
                ]
        elif self.player_in_overtime:
            if self.overtime_cards and not self.overtime_ready_to_advance:
                self.current_cards = [self.overtime_cards[self.overtime_card_index]]
        elif self.pending_player_transition is not None:
            self.current_cards = []
        elif not self.current_cards:
            # Validate compact-state agreement before exposing the immutable
            # graph card to the player.
            self.decision_web.assert_runtime_matches(self.player_state, self.player_node_id)
            card = self.decision_web.node(self.player_node_id).card
            self.player_state.decision_cards[card.id] = card
            self.current_cards = [card]

    def _record_player_day(self) -> None:
        """Append the player's end-of-day state to comparison history."""
        self.last_result = simulate_day(self.player_state)
        # Choice effects may complete jobs before the work tick, so recompute the
        # full day delta rather than relying only on simulate_day's tick delta.
        self.last_result.completed_job_ids = sorted(
            self.player_state.completed_jobs - self.day_completed_before
        )
        self.last_summary_puzzle = self._build_puzzle_payload(
            completed_before=self.day_completed_before,
        )
        self.last_summary_remaining_jobs = self._build_remaining_jobs_payload()
        self.day_completed_before = set(self.player_state.completed_jobs)

    def _apply_echo_choice(self, player_slot: int) -> None:
        """Apply ECHO's independent optimal answer for the matching daily slot."""
        if self.automated_state.final_item_completed:
            return
        # Slot synchronization prevents player request retries or phase bugs from
        # applying ECHO's optimal decision twice.
        expected_slot = self.echo_choices_applied_today + 1
        if player_slot != expected_slot:
            raise RuntimeError(
                f"ECHO decision slot mismatch: expected {expected_slot}, received {player_slot}."
            )
        if self.pending_echo_transition is not None or self.echo_node_id is None:
            raise RuntimeError("ECHO has no unapplied decision for this daily slot.")

        transition = apply_omniscient_choice(
            self.automated_state,
            self.decision_web,
            self.echo_node_id,
        )
        self.echo_choices_applied_today += 1
        if transition.advances_day:
            self.pending_echo_transition = transition
            self.echo_node_id = None
        else:
            if transition.next_node_id is None:
                raise RuntimeError("ECHO's non-daily transition has no successor.")
            self.echo_node_id = transition.next_node_id

    def _advance_echo_day(self) -> None:
        """Perform ECHO's remaining once-per-day work without replaying choices."""
        if self.automated_state.final_item_completed:
            return
        if self.echo_choices_applied_today != self.decision_total_today:
            raise RuntimeError("ECHO has not applied every expected decision for the day.")
        transition = self.pending_echo_transition
        if transition is None:
            raise RuntimeError("ECHO's completed question sequence has no daily transition.")

        # ECHO advances only after consuming the same number of daily question
        # slots the player was offered.
        self.echo_node_id = advance_omniscient_day(self.automated_state, transition)
        self.pending_echo_transition = None
        self.echo_choices_applied_today = 0

    def _reset_daily_choices(self) -> None:
        """Clear per-day decision state before entering a new day."""
        self.current_cards = []

    def _start_overtime_day(self) -> None:
        """Initialize one overtime workday after the solved web ends."""
        # Overtime cannot use the exhausted immutable web, so it generates cards
        # directly from the player's real remaining jobs.
        self.overtime_cards = generate_daily_decision_cards(self.player_state, self.config)
        if not self.overtime_cards:
            raise RuntimeError("Decision generation produced no questions for unfinished work.")
        self.overtime_card_index = 0
        self.overtime_ready_to_advance = False
        self.questions_answered_today = 0
        self.decision_total_today = len(self.overtime_cards)
        self.current_cards = [self.overtime_cards[0]]

    def _should_start_final_assembly(self) -> bool:
        """Report whether only the player-only assembly batch remains."""
        if (
            self.player_final_assembly_started
            or self.player_state.final_item_completed
            or not self.automated_state.final_item_completed
        ):
            return False
        incomplete = self.player_state.incomplete_jobs()
        if len(incomplete) != 1 or self.automated_state.completion_day is None:
            return False
        # Assembly is offered only when ordinary ticking would still leave the
        # player strictly behind ECHO; it can never create a winning route.
        projected_completion_day = (
            self.player_state.current_day + max(0, incomplete[0].remaining_days - 1)
        )
        return projected_completion_day > self.automated_state.completion_day

    def _start_final_assembly(self) -> None:
        """Leave the solved web for one player-only batch after ECHO has finished."""
        incomplete = self.player_state.incomplete_jobs()
        echo_completion_day = self.automated_state.completion_day
        if len(incomplete) != 1 or echo_completion_day is None:
            raise RuntimeError("Final assembly started outside its player endgame state.")
        projected_completion_day = (
            self.player_state.current_day + max(0, incomplete[0].remaining_days - 1)
        )
        # Cap total acceleration one day short of ECHO's completion date. This
        # preserves the invariant that a divergent player route cannot tie.
        self.final_assembly_cards = generate_final_assembly_cards(
            self.player_state,
            self.config,
            maximum_total_days_removed=max(
                0,
                projected_completion_day - echo_completion_day - 1,
            ),
        )
        if not self.final_assembly_cards:
            raise RuntimeError("Final assembly produced no player decisions.")
        self.player_final_assembly_started = True
        self.player_final_assembly_locked = False
        self.final_assembly_card_index = 0
        self.player_in_overtime = False
        self.overtime_cards = []
        self.overtime_card_index = 0
        self.overtime_ready_to_advance = False
        self.pending_player_transition = None
        self.questions_answered_today = 0
        self.decision_total_today = len(self.final_assembly_cards)
        self.current_cards = [self.final_assembly_cards[0]]

    def _game_over(self) -> bool:
        """Report whether both the player and ECHO have completed the run."""
        return self.player_state.final_item_completed

    def _finish_automated(self) -> None:
        """Finish ECHO's solved route when the player completes during a question."""
        # A player choice may finish the run before the UI performs the day's
        # normal advance, so drain ECHO's already-solved route for final review.
        while not self.automated_state.final_item_completed:
            if self.pending_echo_transition is not None:
                transition = self.pending_echo_transition
                self.echo_node_id = advance_omniscient_day(
                    self.automated_state,
                    transition,
                )
                self.pending_echo_transition = None
                self.echo_choices_applied_today = 0
                continue
            if self.echo_node_id is None:
                raise RuntimeError("ECHO's solved route ended before completing every job.")
            transition = apply_omniscient_choice(
                self.automated_state,
                self.decision_web,
                self.echo_node_id,
            )
            self.echo_choices_applied_today += 1
            if transition.advances_day:
                self.pending_echo_transition = transition
                self.echo_node_id = None
            else:
                if transition.next_node_id is None:
                    raise RuntimeError("ECHO's non-daily transition has no successor.")
                self.echo_node_id = transition.next_node_id


class SessionStore:
    """Serialize access to the single mutable game session shared by HTTP handlers."""

    def __init__(self, seed: int | None = None, dev_mode: bool = False) -> None:
        """Create the initial session and preserve the server-level developer flag."""
        self.lock = threading.RLock()
        self.dev_mode = dev_mode
        self.session = GameSession(seed=seed, dev_mode=self.dev_mode)

    def state_payload(self) -> dict[str, Any]:
        """Return the current browser payload under the session lock."""
        with self.lock:
            return self.session.state_payload()

    def new_session_payload(self, seed: int | None = None) -> dict[str, Any]:
        """Replace the run and return its initial payload atomically."""
        with self.lock:
            # Construct first, then swap, so generation failure leaves the
            # previous playable session intact.
            new_session = GameSession(seed=seed, dev_mode=self.dev_mode)
            self.session = new_session
            new_session.refresh_current_rss_stat()
            return self.session.state_payload()

    def log_generation_stats(self) -> None:
        """Emit each session's generation report at most once."""
        with self.lock:
            self.session.log_generation_stats_once()

    def choice_payload(self, card_id: str, choice_id: str) -> dict[str, Any]:
        """Apply one choice and return the updated state atomically."""
        with self.lock:
            self.session.apply_choice(card_id, choice_id)
            return self.session.state_payload()

    def advance_payload(self) -> dict[str, Any]:
        """Advance one day and return the updated state atomically."""
        with self.lock:
            self.session.advance_day()
            return self.session.state_payload()

    def skip_payload(
        self,
        strategy: object,
        target_day: object = None,
    ) -> dict[str, Any]:
        """Run a developer automation request under the session lock."""
        with self.lock:
            if not self.dev_mode:
                raise ValueError("Developer mode is not enabled.")
            self.session.skip(strategy, target_day)
            return self.session.state_payload()
