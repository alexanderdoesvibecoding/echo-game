from __future__ import annotations

from typing import Iterable

from ..metrics import calculate_snapshot, day_shift, update_state_metrics
from ..models import DecisionCard, MetricSnapshot, SimulationState
from ..simulation import DayResult

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    RICH_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal environments
    RICH_AVAILABLE = False
    Console = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]
    box = None  # type: ignore[assignment]


class GameRenderer:
    def __init__(self, use_color: bool = True) -> None:
        self.rich = RICH_AVAILABLE
        self.console = Console(no_color=not use_color) if RICH_AVAILABLE else None

    def print(self, message: str = "") -> None:
        if self.rich:
            self.console.print(message)
        else:
            print(_strip_markup(message))

    def rule(self, title: str) -> None:
        if self.rich:
            self.console.rule(title)
        else:
            print(f"\n=== {title} ===")

    def render_main_menu(self) -> None:
        self.rule("Advanced Manufacturing Yard Scheduling")
        self._panel(
            "Complete a 30-piece project in 30 days by steering priorities, reroutes, disruption response, and final integration readiness.",
            "Scheduling Strategy Game",
        )
        self.print("1. Start new game")
        self.print("2. Start new game with seed")
        self.print("3. Quit")

    def render_start(self, state: SimulationState) -> None:
        update_state_metrics(state)
        snapshot = calculate_snapshot(state)
        text = (
            f"Scenario {state.scenario_id}\n"
            f"Seed: {state.seed}\n"
            f"Deadline: Day 30, Shift 3 ({state.deadline_shift} shifts)\n"
            f"Puzzle pieces: {len(state.pieces)} | Shops: {len(state.shops)} | Jobs: {len(state.jobs)}\n"
            f"Initial projected completion: {day_shift(snapshot.projected_completion_shift, state.shifts_per_day)}"
        )
        self._panel(text, "New Run")

    def render_overview(self, state: SimulationState) -> None:
        update_state_metrics(state)
        snapshot = calculate_snapshot(state)
        active = len(state.active_events)
        warnings = len(state.known_warnings)
        bottlenecks = ", ".join(shop.name for shop in state.get_bottleneck_shops(2))
        critical = state.get_critical_path_jobs()[:3]
        critical_text = ", ".join(job.id for job in critical) or "No active critical jobs"
        self.rule(f"Start of Day {state.current_day}")
        rows = [
            ("Pieces ready", f"{snapshot.pieces_completed}/30"),
            ("Jobs complete", f"{snapshot.jobs_completed}/{len(state.jobs)}"),
            ("Jobs late", str(snapshot.jobs_late)),
            ("Active disruptions", str(active)),
            ("Known warnings", str(warnings)),
            ("Utilization", f"{snapshot.utilization:.0%}"),
            ("Schedule risk", f"{snapshot.schedule_risk:.0f}/100"),
            ("Projected completion", day_shift(snapshot.projected_completion_shift, state.shifts_per_day)),
            ("Major bottlenecks", bottlenecks or "None"),
            ("Critical path focus", critical_text),
        ]
        self._two_col_table(rows, "Project Status")

    def render_schedule_board(self, state: SimulationState) -> None:
        update_state_metrics(state)
        headers = [
            "Shop",
            "Active",
            "Queued",
            "Blocked",
            "Complete",
            "Util.",
            "Idle WC",
            "Highest Risk Piece",
            "Bottleneck",
            "Event",
        ]
        rows = []
        for shop in state.shops.values():
            risk_piece = _highest_risk_piece(state, shop.id)
            current_event = _shop_event_label(state, shop.id)
            rows.append(
                [
                    shop.name,
                    str(len(shop.active_job_ids)),
                    str(len(shop.queued_job_ids)),
                    str(len(shop.blocked_job_ids)),
                    str(len(shop.completed_job_ids)),
                    f"{shop.utilization:.0%}",
                    str(shop.idle_time),
                    risk_piece,
                    "Yes" if len(shop.queued_job_ids) + len(shop.blocked_job_ids) >= 5 else "",
                    current_event,
                ]
            )
        self._table(headers, rows, "Schedule Board")

    def render_shop_status(self, state: SimulationState) -> None:
        update_state_metrics(state)
        rows = []
        for shop in state.shops.values():
            rows.append(
                [
                    shop.id,
                    shop.name,
                    ", ".join(cap.replace("_", " ") for cap in shop.capabilities),
                    str(len(shop.workcenter_ids)),
                    f"{shop.utilization:.0%}",
                    f"{shop.risk_score:.0f}",
                    str(len(shop.queued_job_ids)),
                    str(len(shop.blocked_job_ids)),
                ]
            )
        self._table(["ID", "Shop", "Capabilities", "WCs", "Util.", "Risk", "Queued", "Blocked"], rows, "Shop Status")

    def render_workcenter_queues(self, state: SimulationState, shop_id: str) -> None:
        update_state_metrics(state)
        shop = state.shops[shop_id]
        rows = []
        for wc_id in shop.workcenter_ids[:50]:
            wc = state.workcenters[wc_id]
            current = wc.current_job_id or "-"
            remaining = state.jobs[current].remaining_duration_shifts if current in state.jobs else "-"
            next_job = wc.queue[0] if wc.queue else "-"
            rows.append(
                [
                    wc.id,
                    wc.status.value,
                    current,
                    str(remaining),
                    str(len(wc.queue)),
                    next_job,
                    ", ".join(cap.replace("_", " ") for cap in wc.capabilities[:2]),
                    str(wc.downtime_remaining or "-"),
                ]
            )
        self._table(
            ["Workcenter", "Status", "Current", "Remain", "Queue", "Next", "Capability", "Down"],
            rows,
            f"Workcenter Queues: {shop.name}",
        )

    def render_piece_progress(self, state: SimulationState) -> None:
        update_state_metrics(state)
        rows = []
        for piece in sorted(state.pieces.values(), key=lambda item: (-item.risk_score, item.id)):
            critical = any(state.jobs[job_id].critical_path for job_id in piece.job_ids)
            blocked = sum(1 for job_id in piece.job_ids if state.jobs[job_id].is_blocked)
            rows.append(
                [
                    piece.id,
                    piece.name,
                    piece.status.value,
                    _bar(piece.percent_complete),
                    f"{piece.completed_job_count}/{piece.total_job_count}",
                    str(blocked),
                    "Yes" if critical else "",
                    day_shift(piece.estimated_completion_shift, state.shifts_per_day),
                    f"{piece.risk_score:.0f}",
                ]
            )
        self._table(
            ["Piece", "Name", "Status", "Progress", "Jobs", "Blocked", "Critical", "Est. Complete", "Risk"],
            rows,
            "Puzzle Piece Progress",
        )

    def render_critical_path(self, state: SimulationState) -> None:
        update_state_metrics(state)
        rows = []
        for job in state.get_critical_path_jobs()[:18]:
            wc = state.workcenters.get(job.assigned_workcenter_id) if job.assigned_workcenter_id else None
            shop = state.shops.get(job.shop_id)
            slack = job.due_shift - state.current_shift - max(0, job.remaining_duration_shifts)
            impact = "Final integration" if job.id == state.final_integration_job else job.piece_id
            rows.append(
                [
                    job.id,
                    shop.name if shop else job.shop_id,
                    wc.id if wc else "-",
                    str(job.remaining_duration_shifts),
                    str(slack),
                    job.block_reason or "-",
                    impact,
                ]
            )
        self._table(["Job", "Shop", "Workcenter", "Remain", "Slack", "Blocking Issue", "Impact"], rows, "Critical Path")

    def render_risk_register(self, state: SimulationState) -> None:
        rows = []
        for event in state.event_timeline:
            if event.id not in state.active_events and event.id not in state.known_warnings:
                continue
            status = "Active" if event.id in state.active_events else "Warning"
            until = max(0, event.start_shift - state.current_shift) if status == "Warning" else max(0, event.end_shift - state.current_shift)
            category = _response_category(event.type.value)
            rows.append([status, event.id, event.type.value, event.target_id, str(event.severity), str(until), category])
        for job in state.get_blocked_jobs()[:12]:
            rows.append(["Blocked", job.id, "Job block", job.piece_id, f"{job.risk_score:.0f}", "-", "mitigation recommended"])
        self._table(
            ["Status", "ID", "Risk", "Affected", "Severity", "Shifts", "Response Category"],
            rows or [["Clear", "-", "No active risks", "-", "-", "-", "-"]],
            "Risk Register",
        )

    def render_decision_card(self, card: DecisionCard) -> None:
        body = f"{card.description}\n\n"
        for choice in card.choices:
            body += (
                f"{choice.id}. {choice.label}\n"
                f"   {choice.description}\n"
                f"   Risk {choice.risk_effect:+}, Cost +{choice.cost_effect}, Reschedules +{choice.reschedule_effect}\n"
            )
        self._panel(body.rstrip(), f"{card.type.value}: {card.title}")

    def render_choice_confirmation(self, note: str) -> None:
        self._panel(note, "Action Applied")

    def render_day_summary(self, result: DayResult, state: SimulationState) -> None:
        snap = result.end_snapshot
        rows = [
            ("Jobs completed today", str(len(result.completed_job_ids))),
            ("Jobs remaining", str(snap.jobs_remaining)),
            ("Pieces ready", f"{snap.pieces_completed}/30"),
            ("Jobs late", str(snap.jobs_late)),
            ("Reschedules", str(snap.reschedules)),
            ("Cost impact", f"{snap.cost:.0f}"),
            ("Utilization", f"{snap.utilization:.0%}"),
            ("Idle time", str(snap.idle_time)),
            ("Schedule risk", f"{snap.schedule_risk:.0f}/100"),
            ("Projected completion", day_shift(snap.projected_completion_shift, state.shifts_per_day)),
        ]
        self.rule(f"End of Day {max(1, (state.current_shift - 1) // state.shifts_per_day + 1)}")
        self._two_col_table(rows, "End-of-Day Summary")
        if result.notes:
            self._panel("\n".join(f"- {note}" for note in result.notes[-10:]), "Notable Consequences")

    def render_final_reveal(self, player: SimulationState, automated: SimulationState, seed: int) -> None:
        player_snapshot = calculate_snapshot(player)
        automated_snapshot = calculate_snapshot(automated)
        self.rule("Final Operational Comparison")
        self._panel(
            "A silent automated scheduling engine, ECHO, ran the same scenario and disruption timeline in parallel. "
            "No ECHO recommendations were shown during play; this is the end-of-run benchmark.",
            "Reveal",
        )
        rows = [
            ["Deadline met", _yes_no(player_snapshot.deadline_met), _yes_no(automated_snapshot.deadline_met)],
            ["Final item completed", _yes_no(player.final_item_completed), _yes_no(automated.final_item_completed)],
            [
                "Completion",
                day_shift(player.completion_shift or player.current_shift, player.shifts_per_day)
                if player.final_item_completed
                else "Not complete",
                day_shift(automated.completion_shift or automated.current_shift, automated.shifts_per_day)
                if automated.final_item_completed
                else "Not complete",
            ],
            ["Pieces ready", str(player_snapshot.pieces_completed), str(automated_snapshot.pieces_completed)],
            ["Jobs completed", str(player_snapshot.jobs_completed), str(automated_snapshot.jobs_completed)],
            ["Jobs late", str(player_snapshot.jobs_late), str(automated_snapshot.jobs_late)],
            ["Utilization", f"{player_snapshot.utilization:.0%}", f"{automated_snapshot.utilization:.0%}"],
            ["Idle time", str(player_snapshot.idle_time), str(automated_snapshot.idle_time)],
            ["Reschedules", str(player_snapshot.reschedules), str(automated_snapshot.reschedules)],
            ["Cost", f"{player_snapshot.cost:.0f}", f"{automated_snapshot.cost:.0f}"],
            ["Schedule risk", f"{player_snapshot.schedule_risk:.0f}", f"{automated_snapshot.schedule_risk:.0f}"],
        ]
        self._table(["Metric", "Player", "ECHO"], rows, "Final Metrics")
        explanation = [
            "ECHO continuously reprioritized critical-path work instead of waiting for daily manual decisions.",
            "It used alternate capable workcenters when queue pressure or downtime threatened slack.",
            "It reacted to warnings by pulling forward unaffected work and reducing bottleneck idle time.",
            "It avoided unnecessary preemption while still resequencing around blocked jobs quickly.",
            "Those behaviors reduced cascading delay, cost pressure, and end-of-run schedule risk.",
            f"Run seed: {seed}",
        ]
        self._panel("\n".join(f"- {line}" for line in explanation), "What Changed the Outcome")

    def render_debug(self, state: SimulationState) -> None:
        rows = [
            [
                event.id,
                event.type.value,
                event.target_id,
                day_shift(event.start_shift, state.shifts_per_day),
                str(event.duration_shifts),
                "Yes" if event.has_advance_warning else "No",
            ]
            for event in state.event_timeline
        ]
        self._table(["ID", "Type", "Target", "Start", "Duration", "Warning"], rows, "Debug Event Timeline")

    def _panel(self, body: str, title: str) -> None:
        if self.rich:
            self.console.print(Panel(body, title=title, border_style="cyan"))
        else:
            print(f"\n[{title}]\n{_strip_markup(body)}")

    def _table(self, headers: list[str], rows: Iterable[Iterable[str]], title: str) -> None:
        if self.rich:
            table = Table(title=title, box=box.SIMPLE_HEAVY, show_lines=False)
            for header in headers:
                table.add_column(header, overflow="fold")
            for row in rows:
                table.add_row(*[str(value) for value in row])
            self.console.print(table)
        else:
            print(f"\n{title}")
            print(" | ".join(headers))
            print("-" * min(120, sum(len(h) + 3 for h in headers)))
            for row in rows:
                print(" | ".join(str(value) for value in row))

    def _two_col_table(self, rows: Iterable[tuple[str, str]], title: str) -> None:
        self._table(["Metric", "Value"], rows, title)


def _bar(percent: float) -> str:
    blocks = 12
    filled = int(round(percent * blocks))
    return "[" + "#" * filled + "." * (blocks - filled) + f"] {percent:.0%}"


def _highest_risk_piece(state: SimulationState, shop_id: str) -> str:
    piece_scores: dict[str, float] = {}
    for job in state.jobs.values():
        if job.shop_id == shop_id and job.piece_id in state.pieces and not job.is_complete:
            piece_scores[job.piece_id] = max(piece_scores.get(job.piece_id, 0.0), job.risk_score)
    if not piece_scores:
        return "-"
    piece_id = max(piece_scores, key=piece_scores.get)
    return f"{piece_id} ({piece_scores[piece_id]:.0f})"


def _shop_event_label(state: SimulationState, shop_id: str) -> str:
    labels = []
    for event in state.event_timeline:
        if event.id not in state.active_events:
            continue
        if event.target_id == shop_id:
            labels.append(event.type.value)
        elif event.target_id in state.workcenters and state.workcenters[event.target_id].shop_id == shop_id:
            labels.append(event.type.value)
    return ", ".join(labels[:2])


def _response_category(event_type: str) -> str:
    lower = event_type.lower()
    if "weather" in lower or "facility" in lower:
        return "pre-stage or shift unaffected work"
    if "material" in lower:
        return "resequence or expedite"
    if "machine" in lower or "workcenter" in lower:
        return "reroute or protect critical path"
    if "inspection" in lower or "engineering" in lower:
        return "mitigation recommended"
    return "priority review"


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _strip_markup(message: str) -> str:
    return (
        message.replace("[bold]", "")
        .replace("[/bold]", "")
        .replace("[red]", "")
        .replace("[/red]", "")
        .replace("[green]", "")
        .replace("[/green]", "")
    )
