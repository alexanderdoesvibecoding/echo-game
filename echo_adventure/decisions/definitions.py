"""Restored decision catalog adapted to the flat job-day simulation.

The legacy effect vocabulary is inert metadata used only to derive whether a
choice adds, removes, or leaves job days unchanged. It does not restore shifts,
workcenters, workers, routing, inventory, or any removed simulation system.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class DecisionEffect:
    """Legacy decision intent retained only long enough to derive a day change."""

    kind: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FollowUpEdge:
    """A possible later question tied to the job that caused it."""

    target_definition_id: str
    probability: float
    delay_days: int = 3
    context: str = ""


@dataclass(frozen=True)
class CatalogChoice:
    id: str
    label: str
    description: str
    effects: tuple[DecisionEffect, ...]
    follow_up_edges: tuple[FollowUpEdge, ...]
    score_delta: float
    icon_key: str = ""


@dataclass(frozen=True)
class DecisionDefinition:
    id: str
    title: str
    description: str
    target_selector: str
    choices: tuple[CatalogChoice, ...]
    severity: int = 3
    is_follow_up: bool = False
    unavoidable_effects: tuple[DecisionEffect, ...] = ()
    unavoidable_follow_up_edges: tuple[FollowUpEdge, ...] = ()


def E(effect_kind: str, **params: object) -> DecisionEffect:
    return DecisionEffect(kind=effect_kind, params=dict(params))


def F(target: str, probability: float, delay_shifts: int = 3, context: str = "") -> FollowUpEdge:
    # The old simulation expressed this delay in shifts. The simplified game
    # has only days, so the numeric delay becomes a day delay without restoring
    # shifts, workcenters, workers, or any other removed resource model.
    return FollowUpEdge(target, probability, delay_shifts, context)


def _effect_score(effects: tuple[DecisionEffect, ...]) -> float:
    """Return a bounded, human-scale score for immediate choice effects.

    Effect ``count`` values describe selector breadth, and a few definitions
    intentionally use 99 to mean "all matching work."  Treating that sentinel
    as 99 independent score penalties produced choices worth almost -200
    points.  Scores are game feedback, not another duration total, so breadth
    has diminishing returns and one answer is always kept within +/-5 points.
    """
    value = 0.0
    for effect in effects:
        params = effect.params
        shifts = params.get("shifts", 0)
        if isinstance(shifts, (tuple, list)):
            amount = (float(shifts[0]) + float(shifts[-1])) / 2.0
        else:
            amount = float(shifts or 0)
        count_value = params.get("count", 1)
        if isinstance(count_value, (tuple, list)):
            count = max(1.0, (float(count_value[0]) + float(count_value[-1])) / 2.0)
        else:
            count = max(1.0, float(count_value or 1))
        breadth = 1.0 if params.get("mode") == "total" else min(3.0, math.sqrt(count))
        workload = amount * breadth

        if effect.kind in {"recover", "open_capacity"}:
            value += workload * 0.65
        elif effect.kind == "release":
            value += breadth * 0.45
        elif effect.kind in {"qualify", "approve", "verify"}:
            value += breadth * 0.35
        elif effect.kind == "delay":
            value -= workload * 0.45
        elif effect.kind in {"block", "downtime"}:
            value -= workload * 0.55
        elif effect.kind == "rework":
            value -= workload * 0.75
        elif effect.kind == "hold":
            value -= workload * 0.40
        elif effect.kind == "risk":
            value -= float(params.get("delta", 0)) * breadth * 0.09
        elif effect.kind == "reschedule":
            # Queue churn is often the mechanism of the correct recovery, not
            # a bad outcome by itself. Lateness/delay effects already price a
            # harmful reshuffle, so do not charge it twice in visible points.
            value += 0.0
        elif effect.kind == "reroute":
            value += breadth * 0.30
        elif effect.kind in {"queue_front", "batch", "nest"}:
            value += breadth * 0.25
        elif effect.kind in {"material_transfer", "replace_worker"}:
            value += 0.35
        elif effect.kind == "worker_load":
            value -= min(4.0, float(params.get("amount", 1) or 1)) * 0.10
        elif effect.kind == "resource":
            action = str(params.get("action", ""))
            if action in {"open", "service", "calibrate", "certify", "temporary_fixture", "temporary_rack"}:
                value += 0.45
            elif action in {"unavailable", "hold", "needs_review"}:
                value -= 0.45 + amount * 0.15
        elif effect.kind in {"inspection", "document", "material", "worker", "priority"}:
            # These effects are operationally meaningful, but their direction
            # depends on the action. Keep them as small tie-breaker gains.
            value += 0.15
    # Half-point-scale normalization keeps a strong whole campaign near the
    # historical 25-30 point ceiling once the early-finish payoff is included.
    return round(max(-5.0, min(5.0, value)) * 0.5, 2)


def C(
    label: str,
    description: str,
    *effects: DecisionEffect,
    follow: tuple[FollowUpEdge, ...] = (),
    score: float | None = None,
) -> CatalogChoice:
    operations = tuple(effects)
    return CatalogChoice(
        id=label.lower().replace("'", "").replace(" ", "-").replace("/", "-")[:64],
        label=label,
        description=description,
        effects=operations,
        follow_up_edges=follow,
        score_delta=round(max(-5.0, min(5.0, score if score is not None else _effect_score(operations))), 2),
    )


def D(
    definition_id: str,
    title: str,
    description: str,
    target: str,
    *choices: CatalogChoice,
    severity: int = 3,
    is_follow_up: bool = False,
    unavoidable: tuple[DecisionEffect, ...] = (),
    card_follow: tuple[FollowUpEdge, ...] = (),
) -> DecisionDefinition:
    icon_keys = DECISION_CHOICE_ICON_KEYS.get(definition_id)
    if icon_keys is None or len(icon_keys) != len(choices):
        raise ValueError(f"Decision {definition_id!r} must define one icon key per choice.")
    if len(set(icon_keys)) != len(icon_keys):
        raise ValueError(f"Decision {definition_id!r} cannot repeat an icon key.")
    unknown_icon_keys = set(icon_keys) - SUPPORTED_CHOICE_ICON_KEYS
    if unknown_icon_keys:
        raise ValueError(f"Decision {definition_id!r} uses unknown icon keys: {sorted(unknown_icon_keys)}")
    choices_with_icons = tuple(
        replace(choice, icon_key=icon_key)
        for choice, icon_key in zip(choices, icon_keys, strict=True)
    )
    return DecisionDefinition(
        id=definition_id,
        title=title,
        description=description,
        target_selector=target,
        choices=choices_with_icons,
        severity=severity,
        is_follow_up=is_follow_up,
        unavoidable_effects=unavoidable,
        unavoidable_follow_up_edges=card_follow,
    )


SUPPORTED_CHOICE_ICON_KEYS = frozenset(
    {
        "accelerate", "adjust", "branch", "calendar", "calibrate", "discard", "document",
        "echo", "exchange", "flag", "gauge", "idea", "inspect", "inventory", "material",
        "merge", "monitor", "people", "printer", "protect", "quality", "release", "repair",
        "route", "search", "stop", "study", "tool", "wait",
    }
)


DECISION_CHOICE_ICON_KEYS = {
    "weather": ("route", "wait"),
    "workstation-breakdown": ("route", "wait"),
    "materials-not-here": ("wait", "inventory", "calendar"),
    "echo-recommendation": ("echo", "adjust"),
    "worker-off-day": ("exchange", "wait"),
    "calibration-drift": ("calibrate", "inspect", "route"),
    "traveler-mismatch": ("inspect", "quality", "branch"),
    "shared-fixture-claim": ("flag", "tool", "wait"),
    "changeover-drag": ("merge", "tool", "route"),
    "batch-window-opens": ("merge", "protect", "calendar"),
    "consumables-short": ("protect", "exchange", "wait"),
    "label-printer-outage": ("document", "printer", "wait"),
    "shop-air-pressure-dip": ("protect", "tool", "monitor"),
    "coolant-change-due": ("repair", "quality", "route"),
    "fod-sweep": ("release",),
    "handoff-window-missed": ("wait", "release", "exchange"),
    "crane-reservation-conflict": ("wait", "route", "calendar"),
    "nesting-opportunity": ("merge", "branch", "tool"),
    "old-setup-sheet": ("tool", "inspect", "document"),
    "wip-crowding": ("route", "adjust", "inventory"),
    "cleanliness-breach": ("repair", "stop", "quality"),
    "software-seat-conflict": ("protect", "exchange", "people"),
    "network-folder-offline": ("document", "branch", "wait"),
    "gauge-dispute": ("inspect", "study", "gauge"),
    "count-variance": ("inspect", "inventory", "material"),
    "burr-cleanup": ("repair", "tool", "release"),
    "cure-clock": ("wait", "branch", "quality"),
    "vacuum-leak-chase": ("search", "tool", "monitor"),
    "tool-crib-hold": ("wait", "tool", "material"),
    "fixture-soak": ("wait", "tool", "material"),
    "shift-overlap-bonus": ("people", "adjust", "calendar"),
    "waste-container-full": ("inventory", "tool", "route"),
    "preapproved-package": ("merge", "quality", "document"),
    "expired-stickers": ("inspect", "printer", "quality"),
    "vendor-rep-on-site": ("tool", "monitor", "release"),
    "training-run": ("people", "protect", "wait"),
    "off-peak-utility-slot": ("merge", "accelerate", "calendar"),
    "floor-walk-insight": ("idea", "document", "adjust"),
    "wash-tank-chemistry": ("repair", "route", "monitor"),
    "rack-shortage": ("tool", "material", "adjust"),
    "safety-drill": ("release",),
    "access-badge-failure": ("wait", "adjust", "people"),
    "reference-sample-missing": ("quality", "gauge", "calibrate"),
    "staging-map-reset": ("adjust", "inventory", "quality"),
    "narrow-drift-found": ("gauge", "inspect", "stop"),
    "route-shortcut-approved": ("route", "accelerate", "exchange"),
    "spare-fixture-certified": ("inspect", "tool", "material"),
    "family-run-unlocked": ("merge", "branch", "tool"),
    "bulk-lot-released": ("inventory", "material", "inspect"),
    "clean-packet-release": ("stop", "release", "inspect"),
    "finish-window-restored": ("adjust", "protect", "repair"),
    "combined-lift": ("merge", "branch", "route"),
    "setup-library-update": ("tool", "material", "repair"),
    "aisles-cleared": ("repair", "release", "tool"),
    "clean-room-cleared": ("release", "quality", "inspect"),
    "program-template-saved": ("adjust", "document", "discard"),
    "gauge-method-locked": ("quality", "flag", "gauge"),
    "operator-qualified": ("accelerate", "exchange", "people"),
    "process-tweak-validated": ("adjust", "document", "protect"),
    "rack-recovery-sprint": ("route", "protect", "tool"),
    "batch-data-accepted": ("merge", "branch", "study"),
    "clamp-marks-found": ("inspect", "quality", "study"),
    "covered-work-reopened": ("inspect", "quality", "study"),
    "wrong-revision-loaded": ("repair", "merge", "tool"),
    "phantom-stock-confirmed": ("inventory", "stop", "search"),
    "fit-check-failed": ("repair", "tool", "quality"),
    "cure-failure-found": ("discard", "inspect", "repair"),
    "vacuum-trace-failed": ("tool", "quality", "inspect"),
    "waste-lane-blocked": ("route", "tool", "exchange"),
    "sticker-audit-hit": ("inspect", "quality", "study"),
    "weather-cleared-early": ("wait", "release", "monitor"),
    "setup-mismatch-found": ("tool", "material", "inspect"),
    "echo-slack-pocket-found": ("echo", "route", "monitor"),
    "replacement-handoff-check": ("release", "exchange", "people"),
    "returning-worker-shortcut": ("tool", "route", "material"),
}


BASE_DEFINITIONS = (
    D(
        "weather", "Exposed work areas are closed by weather", "Severe weather has closed exposed work areas, pausing affected jobs.", "workcenter",
        C("Reroute exposed work", "Move affected work to capable covered stations, with added setup pressure.", E("reroute", selector="target", count=3), E("delay", selector="receiving", shifts=1, count=2), E("reschedule", count=2)),
        C("Wait it out", "Keep the queues stable and resume when the area reopens.", follow=(F("weather-cleared-early", 0.62),)),
        severity=4, unavoidable=(E("downtime", selector="target_workcenters", shifts=(3, 9), count=(1, 3), status="weather"),),
    ),
    D(
        "workstation-breakdown", "A workstation has stopped working", "An unexpected workstation fault has stopped the job currently running there.", "workcenter",
        C("Move affected subjobs", "Transfer the work to another capable station and absorb a fresh setup.", E("reroute", selector="target", count=2), E("delay", selector="target", shifts=1, count=2), E("reschedule", count=1), follow=(F("setup-mismatch-found", 0.48),)),
        C("Wait for repair", "Keep the original route and resume after maintenance releases the station.", E("block", selector="target", shifts=(3, 9), count=1)),
        severity=4, unavoidable=(E("downtime", selector="target_workcenters", shifts=(3, 9), count=1, status="down"),),
    ),
    D(
        "materials-not-here", "Required material has not arrived", "Required material has not arrived at the planned workstation.", "material",
        C("Wait for materials", "Hold the affected work without disturbing another job's allocation.", E("block", selector="target", shifts=2, count=1), follow=(F("bulk-lot-released", 0.58),)),
        C("Use another subjob's material", "Keep urgent work moving by borrowing a verified allocation elsewhere.", E("material_transfer", selector="target", quantity=1), E("delay", selector="donor", shifts=2, count=1), follow=(F("phantom-stock-confirmed", 0.46),)),
        C("Switch to verified work", "Pull another ready job forward while this one waits for stock.", E("block", selector="target", shifts=2, count=1), E("queue_front", selector="ready", count=1), E("reschedule", count=1)),
        severity=4,
    ),
    D(
        "echo-recommendation", "A third-party process optimization tool sees a possible schedule move", "A third-party process optimization tool recommends a disruptive, board-wide reshuffle whose benefit may not be immediately visible.", "critical",
        C("Take advice", "Reshuffle active and queued work to expose hidden capacity.", E("delay", selector="all_active", shifts=(1, 2), count=99), E("reschedule", count=3), follow=(F("echo-slack-pocket-found", 0.68),), score=-1.5),
        C("Ignore the tool", "Leave today's board unchanged and pass on the possible opening."),
        severity=3,
    ),
    D(
        "worker-off-day", "The assigned operator is unavailable", "The operator assigned to this job is unavailable today.", "worker",
        C("Find a replacement", "Use a qualified replacement and accept a handoff review.", E("replace_worker", selector="target"), follow=(F("replacement-handoff-check", 0.52),)),
        C("Hold until the worker returns", "Pause the job and preserve the original handoff.", E("block", selector="target", shifts=1, count=1), follow=(F("returning-worker-shortcut", 0.58),)),
        unavoidable=(E("worker_unavailable", selector="target_worker", shifts=1),),
    ),
    D(
        "calibration-drift", "Measurements may be unreliable", "Recent measurement work is suspect until the measurement chain is trusted again.", "inspection",
        C("Recalibrate now", "Take the measurement resource offline and clear the broader risk.", E("inspection", action="recalibrate"), E("downtime", selector="inspection_workcenter", shifts=(1, 2), count=1), E("risk", selector="family", delta=-8), follow=(F("narrow-drift-found", 0.64),)),
        C("Add witness checks", "Keep work moving with additional verification on affected jobs.", E("delay", selector="family", shifts=1, count=3), E("risk", selector="family", delta=-4)),
        C("Send checks elsewhere", "Move verification to another capable station and crowd its queue.", E("reroute", selector="inspection", count=3), E("delay", selector="receiving", shifts=1, count=2), E("reschedule", count=1)),
        severity=4, unavoidable=(E("inspection", action="drift", amount=2),),
    ),
    D(
        "traveler-mismatch", "The job instructions do not match", "The paper traveler and digital route disagree about the next operation.", "document",
        C("Stop and reconcile it", "Hold the job briefly and establish the controlled instruction.", E("delay", selector="target", shifts=1, count=1), E("approve", selector="target_document"), follow=(F("route-shortcut-approved", 0.62),)),
        C("Use the floor copy", "Continue on the local instruction and carry revision risk.", E("document", action="use_stale"), E("risk", selector="target", delta=8), follow=(F("wrong-revision-loaded", 0.48),)),
        C("Start only the unaffected steps", "Pull safe parallel work forward while the disputed operation remains held.", E("block", selector="target", shifts=1, count=1), E("queue_front", selector="parallel", count=1), E("reschedule", count=1)),
        severity=4,
    ),
    D(
        "shared-fixture-claim", "Two jobs need the same key fixture", "Two ready jobs need the same qualified fixture at the same time.", "fixture",
        C("Give it to the tightest job", "Protect the nearest-due path and delay the competing claim.", E("queue_front", selector="critical", count=1), E("delay", selector="donor", shifts=(2, 3), count=1)),
        C("Build a temporary fixture", "Open a second route with added setup and verification exposure.", E("resource", action="temporary_fixture"), E("delay", selector="target", shifts=1, count=2), E("risk", selector="target", delta=4), follow=(F("spare-fixture-certified", 0.61),)),
        C("Keep the original sequence", "Preserve the sequence and wait for the qualified fixture to free.", E("block", selector="donor", shifts=(2, 3), count=1)),
    ),
    D(
        "changeover-drag", "A changeover is taking longer than planned", "A family changeover is taking longer than the dispatch plan allowed.", "family",
        C("Finish similar work first", "Keep the current family running and push the odd job behind it.", E("recover", selector="family", shifts=1, count=3, mode="each"), E("queue_back", selector="target", count=1), E("reschedule", count=1)),
        C("Pay the changeover now", "Keep the target job's place and absorb the setup interruption.", E("delay", selector="target_workcenter_job", shifts=(1, 2), count=1), follow=(F("family-run-unlocked", 0.65),)),
        C("Move the odd job", "Send the out-of-family job to an alternate route.", E("reroute", selector="target", count=1), E("delay", selector="target", shifts=1, count=1), E("reschedule", count=1)),
    ),
    D(
        "batch-window-opens", "An early batch window is available", "A shared process window is available earlier than expected.", "batch",
        C("Fill the batch", "Pull compatible work together and use the open window.", E("batch", selector="family", count=4), E("recover", selector="family", shifts=1, count=4, mode="each"), E("reschedule", count=1), follow=(F("batch-data-accepted", 0.63),)),
        C("Reserve it for critical work", "Protect the slot for the highest-risk compatible job.", E("queue_front", selector="critical", count=1), E("resource", action="reserve", kind="batch slot")),
        C("Ignore the window", "Keep the current dispatch plan and give up the extra capacity."),
    ),
    D(
        "consumables-short", "Shop supplies are running low", "A shop's working stock is too low to sustain every planned start.", "material",
        C("Ration to due work", "Keep urgent work supplied and slow routine starts.", E("queue_front", selector="near_due", count=2), E("delay", selector="low_priority", shifts=(1, 2), count=3)),
        C("Borrow from another shop", "Restore this lane by transferring stock and pressure from a donor shop.", E("material_transfer", selector="shop", quantity=2), E("delay", selector="donor_shop", shifts=1, count=2), E("reschedule", count=1)),
        C("Wait for restock", "Pause the affected capability until fresh stock is staged.", E("block", selector="family", shifts=(2, 3), count=3), follow=(F("bulk-lot-released", 0.6),)),
        severity=4,
    ),
    D(
        "label-printer-outage", "Finished work cannot be labeled", "Completed work cannot receive controlled labels at the release desk.", "document",
        C("Handwrite controlled labels", "Close a small number of jobs and carry added document review risk.", E("release", selector="near_complete", count=2), E("document", action="manual_label"), E("risk", selector="target", delta=5)),
        C("Borrow a printer", "Restore label flow after a short support handoff elsewhere.", E("release", selector="near_complete", count=2), E("hold", selector="near_complete", shifts=1, count=2), E("resource", action="borrow", kind="label printer"), E("delay", selector="donor_shop", shifts=1, count=1)),
        C("Hold completions", "Keep release control clean and let finished work wait for formal closeout.", E("hold", selector="near_complete", shifts=(1, 2), count=3), follow=(F("clean-packet-release", 0.64),)),
        severity=3, unavoidable=(E("resource", action="unavailable", kind="label printer", shifts=2), E("hold", selector="near_complete", shifts=2, count=3)),
    ),
    D(
        "shop-air-pressure-dip", "Shop air is weakening tools and clamps", "Pneumatic tools and clamps are running below normal reliability.", "shop",
        C("Throttle noncritical work", "Preserve critical production and delay routine work in the area.", E("queue_front", selector="critical", count=2), E("delay", selector="low_priority", shifts=(1, 3), count=3)),
        C("Move hand-tool work forward", "Pull work that does not depend on shop air into the open capacity.", E("queue_front", selector="ready", count=3), E("reschedule", count=2)),
        C("Run through it", "Keep the sequence and accept slower, less reliable clamping.", E("delay", selector="shop", shifts=(1, 3), count=4), E("risk", selector="shop", delta=7), follow=(F("clamp-marks-found", 0.49),)),
        severity=4,
    ),
    D(
        "coolant-change-due", "A machine needs coolant service", "A cutting or machining station is approaching its finish-quality limit.", "workcenter",
        C("Service it now", "Take the station down and restore its process condition.", E("downtime", selector="target_workcenters", shifts=1, count=1), E("resource", action="service", kind="tool"), E("risk", selector="family", delta=-7), follow=(F("finish-window-restored", 0.66),)),
        C("Run one more shift", "Keep the current job moving and accept cleanup exposure later.", E("risk", selector="target", delta=7), E("delay", selector="target", shifts=1, count=1)),
        C("Move precision work away", "Reroute sensitive jobs and leave rough work on the station.", E("reroute", selector="precision", count=2), E("reschedule", count=1)),
    ),
    D(
        "fod-sweep", "A controlled area needs a debris sweep", "Foreign object debris requires a controlled-area sweep before work resumes.", "controlled",
        C("Acknowledge", "Absorb the interruption and resume when the area is released."),
        severity=3,
        unavoidable=(E("block", selector="shop", shifts=1, count=99), E("resource", action="hold", kind="controlled area", shifts=1)),
        card_follow=(F("covered-work-reopened", 0.42),),
    ),
    D(
        "handoff-window-missed", "A handoff missed its receiving window", "A cross-shop move missed the receiving station's planned intake window.", "handoff",
        C("Hold the receiving slot", "Protect the next intake opportunity while the station waits.", E("resource", action="reserve", kind="staging lane"), E("downtime", selector="receiving_workcenter", shifts=1, count=1)),
        C("Release the slot", "Keep the receiving shop productive and defer the handoff.", E("block", selector="target", shifts=1, count=1), E("queue_front", selector="ready", count=1)),
        C("Pull a substitute subjob", "Use the open station on other ready work.", E("queue_front", selector="ready", count=1), E("reschedule", count=1)),
    ),
    D(
        "crane-reservation-conflict", "The crane is booked elsewhere", "A shared heavy-lift resource is committed to another shop.", "crane",
        C("Wait for the crane", "Keep the setup intact and wait for the reserved lift.", E("block", selector="target", shifts=(1, 2), count=1), follow=(F("combined-lift", 0.62),)),
        C("Swap in bench work", "Pull smaller work forward while the heavy move remains queued.", E("queue_front", selector="ready", count=2), E("queue_back", selector="target", count=1), E("reschedule", count=1)),
        C("Use the off-shift slot", "Protect the heavy move and transfer fatigue into the next start.", E("resource", action="reserve", kind="crane"), E("worker_load", amount=2), E("delay", selector="next_shift", shifts=1, count=2)),
    ),
    D(
        "nesting-opportunity", "Similar jobs can share setup", "Compatible work can share a setup, fixture, program, or batch.", "family",
        C("Nest the jobs", "Combine compatible work and lock it to one route.", E("nest", selector="family", count=3), E("recover", selector="family", shifts=(1, 2), count=3, mode="total"), E("resource", action="reserve", kind="fixture")),
        C("Nest only low-risk work", "Take a smaller setup saving without tying the critical path to the group.", E("nest", selector="low_risk", count=2), E("recover", selector="low_risk", shifts=1, count=2, mode="total")),
        C("Keep them separate", "Preserve routing flexibility and forgo the shared setup."),
    ),
    D(
        "old-setup-sheet", "An old setup sheet might help", "A proven setup sheet exists for similar work, but its applicability is not yet controlled.", "document",
        C("Use it as-is", "Take the setup shortcut and accept revision exposure.", E("recover", selector="target", shifts=1, count=1, component="setup"), E("risk", selector="target", delta=5), E("document", action="use_stale")),
        C("Validate first", "Review the sheet now so later matching starts can use it safely.", E("delay", selector="target", shifts=1, count=1), E("approve", selector="target_document"), follow=(F("setup-library-update", 0.67),)),
        C("Ignore it", "Use the current setup plan without adding new risk."),
    ),
    D(
        "wip-crowding", "Work in progress is crowding the floor", "Staging space, carts, and access lanes are constraining work in progress.", "staging",
        C("Freeze new starts", "Stop feeding the area and let running work clear cleanly.", E("block", selector="ready_shop", shifts=1, count=3), E("resource", action="hold", kind="staging lane", shifts=1), follow=(F("aisles-cleared", 0.65),)),
        C("Clear shortest work first", "Finish small jobs quickly to free floor space.", E("queue_front", selector="short", count=3), E("queue_back", selector="critical", count=1), E("reschedule", count=2)),
        C("Move WIP to overflow", "Restore floor access with added transport and tracking exposure.", E("delay", selector="shop", shifts=1, count=4), E("risk", selector="shop", delta=5), E("resource", action="open", kind="staging lane")),
        severity=4,
    ),
    D(
        "cleanliness-breach", "A clean area failed inspection", "A controlled area failed its cleanliness check while work was open.", "controlled",
        C("Full reset", "Stop the area, remove the exposure, and requalify it.", E("block", selector="controlled", shifts=2, count=99), E("resource", action="service", kind="controlled area"), E("risk", selector="controlled", delta=-12), follow=(F("clean-room-cleared", 0.69),)),
        C("Isolate the zone", "Pause only work inside the affected zone.", E("block", selector="target", shifts=2, count=2), E("resource", action="hold", kind="controlled area", shifts=2)),
        C("Continue under covers", "Keep protected work moving and carry an acceptance question.", E("hold", selector="target", shifts=1, count=2), E("risk", selector="target", delta=8), follow=(F("covered-work-reopened", 0.52),)),
        severity=5,
    ),
    D(
        "software-seat-conflict", "Programming seats are full", "Programming-dependent work cannot release while all software seats are occupied.", "software",
        C("Reserve the next seat", "Protect the most urgent program and defer other programming work.", E("queue_front", selector="critical", count=1), E("delay", selector="family", shifts=1, count=2), E("resource", action="reserve", kind="software seat"), follow=(F("program-template-saved", 0.66),)),
        C("Borrow after hours", "Clear the affected job with a delayed handoff into the next shift.", E("block", selector="target", shifts=1, count=1), E("delay", selector="next_shift", shifts=1, count=2)),
        C("Run a manual fallback", "Start sooner with additional operator verification.", E("delay", selector="target", shifts=1, count=1), E("worker_load", amount=1)),
    ),
    D(
        "network-folder-offline", "Shop files are temporarily offline", "Current programs and acceptance files are temporarily unreachable.", "document",
        C("Use cached copies", "Keep familiar work moving while carrying document-version exposure.", E("document", action="use_stale"), E("risk", selector="family", delta=7), follow=(F("wrong-revision-loaded", 0.51),)),
        C("Start independent work", "Pull work that does not need the missing files into the open capacity.", E("queue_front", selector="ready", count=3), E("queue_back", selector="target", count=1), E("reschedule", count=2)),
        C("Wait for IT", "Hold affected starts until the controlled files return.", E("block", selector="family", shifts=(1, 2), count=3)),
        severity=4, unavoidable=(E("document", action="offline"),),
    ),
    D(
        "gauge-dispute", "Two gauges disagree", "Two gauges disagree and the affected feature cannot be accepted yet.", "gauge",
        C("Cross-check quickly", "Delay acceptance briefly and compare against the trusted method.", E("hold", selector="target", shifts=1, count=1), E("inspection", action="cross_check")),
        C("Run a formal study", "Take a longer measurement hold and improve confidence for matching work.", E("hold", selector="family", shifts=(2, 3), count=2), E("inspection", action="formal_study"), follow=(F("gauge-method-locked", 0.7),)),
        C("Accept the trusted gauge", "Release the job now and carry a later quality question.", E("release", selector="target", count=1), E("risk", selector="target", delta=8)),
        severity=4,
    ),
    D(
        "count-variance", "Inventory counts do not match", "System inventory and the floor count disagree about available stock.", "material",
        C("Cycle count now", "Pause affected starts and establish verified inventory.", E("block", selector="family", shifts=1, count=3), E("verify", selector="target_material")),
        C("Consume visible stock", "Keep a small number of jobs moving and risk starving later starts.", E("material", action="consume", quantity=2), E("queue_front", selector="target", count=2), E("risk", selector="family", delta=5), follow=(F("phantom-stock-confirmed", 0.54),)),
        C("Reassign starts", "Move dispatch toward jobs with verified stock.", E("queue_front", selector="verified_material", count=3), E("reschedule", count=2)),
    ),
    D(
        "burr-cleanup", "Parts need extra cleanup", "Cut or machined parts need more cleanup than the downstream plan allowed.", "family",
        C("Clean before release", "Protect downstream fitting by absorbing cleanup upstream.", E("delay", selector="target", shifts=1, count=3), E("risk", selector="target", delta=-4)),
        C("Send to finishing early", "Use finishing capacity to absorb cleanup and crowd that queue.", E("reroute", selector="target", count=2), E("delay", selector="receiving", shifts=1, count=2), E("reschedule", count=1)),
        C("Release rough", "Keep the upstream station on plan and carry fit exposure downstream.", E("risk", selector="target", delta=9), follow=(F("fit-check-failed", 0.52),)),
    ),
    D(
        "cure-clock", "A process cure is not finished", "The next dependency cannot safely begin until a process dwell completes.", "family",
        C("Wait the clock out", "Hold the dependent work until the cure is complete.", E("block", selector="dependent", shifts=(1, 2), count=1)),
        C("Pull parallel work", "Use ready parallel work while the cure finishes.", E("queue_front", selector="parallel", count=2), E("reschedule", count=1)),
        C("Force the next step", "Protect today's timing and accept a later bond-quality question.", E("release", selector="dependent", count=1), E("risk", selector="dependent", delta=12), follow=(F("cure-failure-found", 0.55),)),
        severity=4,
    ),
    D(
        "vacuum-leak-chase", "A setup will not hold vacuum", "A bag, seal, or holding fixture will not maintain process pressure.", "fixture",
        C("Chase the leak", "Keep the original setup and repair the likely leak path.", E("delay", selector="target", shifts=1, count=1), E("risk", selector="target", delta=-4)),
        C("Rebuild the setup", "Take a longer setup interruption and reduce the failure tail.", E("delay", selector="target", shifts=2, count=1), E("resource", action="service", kind="fixture"), E("risk", selector="target", delta=-10)),
        C("Run with monitoring", "Start now under monitoring and accept the chance of lost work.", E("risk", selector="target", delta=12), follow=(F("vacuum-trace-failed", 0.54),)),
        severity=4,
    ),
    D(
        "tool-crib-hold", "Calibrated tools are held up", "Calibrated hand tools are waiting on controlled crib release.", "tool",
        C("Wait for release", "Hold tool-dependent starts until the normal release completes.", E("block", selector="tool_dependent", shifts=1, count=3)),
        C("Borrow substitutes", "Keep urgent starts moving and delay a donor station's setup.", E("resource", action="borrow", kind="tool"), E("delay", selector="donor", shifts=1, count=1), follow=(F("sticker-audit-hit", 0.46),)),
        C("Split the queue", "Start work that does not need the held tools.", E("queue_front", selector="ready", count=3), E("block", selector="tool_dependent", shifts=1, count=2), E("reschedule", count=1)),
    ),
    D(
        "fixture-soak", "A fixture is not ready yet", "A large fixture has not reached its required process condition.", "fixture",
        C("Wait for soak", "Preserve the process and start after the fixture is ready.", E("block", selector="target", shifts=1, count=1)),
        C("Preheat a second fixture", "Spend capacity now to prepare another future setup.", E("delay", selector="ready", shifts=1, count=1), E("resource", action="temporary_fixture"), E("recover", selector="family", shifts=1, count=1)),
        C("Switch to a ready fixture", "Use an alternate qualified route with additional setup churn.", E("reroute", selector="target", count=1), E("delay", selector="target", shifts=1, count=1), E("reschedule", count=1), follow=(F("spare-fixture-certified", 0.58),)),
    ),
    D(
        "shift-overlap-bonus", "Extra crew overlap is available", "An unexpected overlap creates a short window of extra coordination.", "shop",
        C("Use it for a handoff", "Remove delay from a cross-shop dependency.", E("recover", selector="handoff", shifts=1, count=1)),
        C("Use it for short jobs", "Accelerate a small group of ready jobs.", E("recover", selector="short", shifts=1, count=2, mode="each"), E("queue_front", selector="short", count=2)),
        C("Use it for setup prep", "Prepare a later start before the overlap ends.", E("recover", selector="ready", shifts=1, count=1, component="setup")),
        severity=2,
    ),
    D(
        "waste-container-full", "Waste containers are full", "Affected stations cannot continue producing until waste flow is restored.", "waste",
        C("Empty containers now", "Stop the area briefly and restore normal production.", E("block", selector="shop", shifts=1, count=3), E("resource", action="service", kind="waste container")),
        C("Use small interim carts", "Keep work moving at reduced flow and crowd the waste lane.", E("delay", selector="shop", shifts=2, count=3), E("resource", action="hold", kind="cart", shifts=2), follow=(F("waste-lane-blocked", 0.5),)),
        C("Divert to another area", "Clear this shop and transfer crowding pressure elsewhere.", E("resource", action="open", kind="waste container"), E("delay", selector="donor_shop", shifts=1, count=3), E("reschedule", count=1)),
        severity=4,
    ),
    D(
        "preapproved-package", "Approved paperwork can close similar work", "One work family already has an accepted closeout package.", "document",
        C("Pull matching work forward", "Use the approval on compatible work and delay unrelated dispatch.", E("recover", selector="family", shifts=1, count=3, mode="each"), E("queue_front", selector="family", count=3), E("queue_back", selector="other_family", count=2), E("reschedule", count=1)),
        C("Use it on near-complete jobs", "Convert near-complete compatible work into accepted completions faster.", E("release", selector="near_complete", count=3), E("approve", selector="family_documents"), E("recover", selector="near_complete", shifts=1, count=3, mode="each"), follow=(F("clean-packet-release", 0.62),)),
        C("Save the package", "Keep today's plan stable and reserve the approval for later."),
        severity=2,
    ),
    D(
        "expired-stickers", "Tool calibration stickers are expired", "Calibration stickers on several hand tools are out of date.", "tool",
        C("Audit and resticker", "Hold starts briefly and restore controlled tool status.", E("block", selector="tool_dependent", shifts=1, count=3), E("resource", action="calibrate", kind="tool")),
        C("Swap tools", "Protect the highest-priority job and delay a lower-priority station.", E("resource", action="borrow", kind="tool"), E("queue_front", selector="critical", count=1), E("delay", selector="donor", shifts=1, count=1)),
        C("Keep using them", "Avoid an immediate stop and carry documentation and quality exposure.", E("risk", selector="tool_dependent", delta=10), E("resource", action="needs_review", kind="tool"), follow=(F("sticker-audit-hit", 0.56),)),
        severity=4,
    ),
    D(
        "vendor-rep-on-site", "A vendor specialist is available today", "A vendor specialist is unexpectedly available for a limited window.", "workcenter",
        C("Use them on setup", "Accelerate a difficult setup with a short lead-operator diversion.", E("recover", selector="target", shifts=(1, 2), count=1, component="setup"), E("worker_load", amount=1)),
        C("Use them on troubleshooting", "Reduce process risk without changing today's queue speed.", E("risk", selector="family", delta=-10), E("resource", action="service", kind="tool")),
        C("Let them go", "Keep the shop undisturbed and give up the temporary opportunity."),
        severity=2,
    ),
    D(
        "training-run", "A newer operator can train on live work", "A newer operator can qualify on live work, slowing the current station but adding flexibility.", "worker",
        C("Train on low-risk work", "Use a forgiving job for qualification and improve future coverage.", E("delay", selector="low_risk", shifts=1, count=1), E("worker_load", amount=1), follow=(F("operator-qualified", 0.72),)),
        C("Train on urgent work", "Keep the urgent path staffed and accept added execution risk.", E("replace_worker", selector="critical"), E("risk", selector="critical", delta=8)),
        C("Postpone training", "Avoid today's slowdown and keep staffing flexibility unchanged."),
        severity=2,
    ),
    D(
        "off-peak-utility-slot", "An off-peak utility slot is open", "An extra utility-dependent process window can be used if the board is rearranged.", "batch",
        C("Run critical work off-peak", "Accelerate the riskiest compatible job and slow the next setup.", E("recover", selector="critical", shifts=1, count=1), E("delay", selector="next_shift", shifts=1, count=1), E("resource", action="reserve", kind="utility slot")),
        C("Run batch work off-peak", "Accelerate compatible work while locking it into one sequence.", E("batch", selector="family", count=4), E("recover", selector="family", shifts=1, count=3, mode="total"), E("reschedule", count=1)),
        C("Skip the slot", "Keep the plan simple and leave the extra capacity unused."),
    ),
    D(
        "floor-walk-insight", "A floor walk found a faster method", "A small method improvement can remove wasted motion from matching work.", "family",
        C("Apply it today", "Pause one station and establish the improved method for later work.", E("downtime", selector="target_workcenters", shifts=1, count=1), E("document", action="publish_method"), follow=(F("process-tweak-validated", 0.7),)),
        C("Apply only to new starts", "Avoid interrupting running work and take a smaller future improvement.", E("recover", selector="ready_family", shifts=1, count=2, mode="total")),
        C("Keep the old method", "Preserve the current sequence without changing standard work."),
    ),
    D(
        "wash-tank-chemistry", "A wash tank is drifting out of range", "A preparation tank is moving out of its controlled process range.", "batch",
        C("Change the bath", "Take the tank offline and restore process confidence.", E("resource", action="service", kind="wash tank", shifts=(1, 2)), E("block", selector="family", shifts=(1, 2), count=3), E("risk", selector="family", delta=-9), follow=(F("finish-window-restored", 0.65),)),
        C("Send work to another prep route", "Protect urgent starts by crowding an alternate route.", E("reroute", selector="target", count=3), E("delay", selector="receiving", shifts=1, count=2), E("reschedule", count=1)),
        C("Keep running light work", "Allow low-risk starts and hold sensitive work.", E("queue_front", selector="low_risk", count=2), E("block", selector="critical", shifts=2, count=2)),
        severity=4,
    ),
    D(
        "rack-shortage", "Parts have nowhere safe to stage", "Finished and in-process parts cannot safely move or stage because racks are full.", "staging",
        C("Clear old racks", "Prioritize closing and moving existing WIP, delaying new starts.", E("release", selector="near_complete", count=3), E("queue_back", selector="ready_shop", count=3), E("resource", action="open", kind="rack")),
        C("Build temporary racks", "Use shop support now to restore staging capacity.", E("delay", selector="shop", shifts=1, count=2), E("resource", action="temporary_rack"), follow=(F("rack-recovery-sprint", 0.66),)),
        C("Keep parts at stations", "Avoid support work and let completed WIP tie up production stations.", E("downtime", selector="target_workcenters", shifts=2, count=2), E("resource", action="hold", kind="rack", shifts=2)),
        severity=4,
    ),
    D(
        "safety-drill", "A required safety drill interrupts work", "A required emergency drill interrupts production across the site.", "global",
        C("Acknowledge", "Absorb the interruption and resume after the all-clear."),
        severity=3, unavoidable=(E("downtime", selector="all_active_workcenters", shifts=1, count=99, status="blocked"),),
    ),
    D(
        "access-badge-failure", "Secure-area access is blocked", "A secure-area badge reader is preventing normal shift-start access.", "controlled",
        C("Wait for security", "Hold secure-area work and preserve the planned sequence.", E("block", selector="controlled", shifts=1, count=3)),
        C("Pull open-area work", "Keep accessible shops productive and defer secure-area dependencies.", E("queue_front", selector="open_area", count=3), E("queue_back", selector="controlled", count=2), E("reschedule", count=1)),
        C("Escort critical staff", "Keep one critical station moving and slow support response elsewhere.", E("release", selector="critical", count=1), E("delay", selector="donor_shop", shifts=1, count=2), E("worker_load", amount=1)),
    ),
    D(
        "reference-sample-missing", "A reference sample is missing", "Work needing visual or fit comparison cannot be accepted without its reference artifact.", "inspection",
        C("Search now", "Pause the affected work and recover the normal acceptance path.", E("hold", selector="target", shifts=1, count=1), E("resource", action="open", kind="reference sample")),
        C("Borrow a sister sample", "Keep work moving and carry acceptance uncertainty.", E("resource", action="borrow", kind="reference sample"), E("risk", selector="target", delta=7)),
        C("Switch to measured criteria", "Use metrology capacity and reduce subjective acceptance risk.", E("reroute", selector="inspection", count=2), E("delay", selector="receiving", shifts=1, count=2), E("risk", selector="target", delta=-4), follow=(F("gauge-method-locked", 0.64),)),
    ),
    D(
        "staging-map-reset", "Staging locations need to be reset", "A large movement has invalidated planned WIP locations and access paths.", "staging",
        C("Redraw staging now", "Resequence the area and prevent later access conflicts.", E("reschedule", count=1), E("resource", action="service", kind="staging lane"), follow=(F("aisles-cleared", 0.64),)),
        C("Move only critical WIP", "Protect the most important material paths and leave routine work harder to reach.", E("queue_front", selector="critical", count=2), E("delay", selector="low_priority", shifts=1, count=3)),
        C("Let shops improvise", "Avoid an immediate board change and accept searching and idle-time exposure.", E("delay", selector="shop", shifts=1, count=3), E("risk", selector="shop", delta=5)),
    ),
)


FOLLOW_UP_DEFINITIONS = (
    D(
        "narrow-drift-found", "The measurement issue is limited", "Recalibration shows the measurement concern was limited to one reference.", "inspection",
        C("Release quarantined work", "Release the held measurement family and recover the broad review delay.", E("release", selector="family", count=5), E("recover", selector="family", shifts=(3, 5), count=5, mode="total"), E("inspection", action="release_all")),
        C("Release only critical work", "Recover the highest-pressure measured work and keep routine jobs under review.", E("release", selector="critical", count=3), E("recover", selector="critical", shifts=(2, 3), count=3, mode="total")),
        C("Keep everything quarantined", "Preserve the broad hold and give up the schedule recovery."),
        severity=3, is_follow_up=True,
    ),
    D(
        "route-shortcut-approved", "Engineering approved a route shortcut", "Engineering confirms that a copied route step is unnecessary for this work family.", "family",
        C("Apply the shortcut broadly", "Update matching routes and pull their completions forward.", E("recover", selector="family", shifts=1, count=5, mode="each"), E("approve", selector="family_documents"), E("reschedule", count=1)),
        C("Apply it only here", "Use the approved shortcut only on the disputed path.", E("recover", selector="target", shifts=2, count=1, mode="total"), E("approve", selector="target_document")),
        C("Keep the old route", "Avoid changing active instructions and leave the extra step in place."),
        is_follow_up=True,
    ),
    D(
        "spare-fixture-certified", "A spare fixture passed certification", "The alternate fixture passed its checks and can become a qualified resource.", "fixture",
        C("Certify it for the family", "Complete the review and open lasting fixture capacity for matching work.", E("delay", selector="target", shifts=1, count=1), E("resource", action="certify", kind="fixture"), E("open_capacity", selector="family", shifts=(4, 6), count=6, mode="total")),
        C("Use it only on low-risk jobs", "Open limited parallel capacity without putting critical work on the alternate fixture.", E("resource", action="certify_limited", kind="fixture"), E("recover", selector="low_risk", shifts=(2, 3), count=3, mode="total")),
        C("Retire the fixture", "Avoid certification work and leave fixture capacity unchanged."),
        severity=3, is_follow_up=True,
    ),
    D(
        "family-run-unlocked", "A station can run similar jobs together", "The station is now established for a family of similar work.", "family",
        C("Pull the whole family forward", "Use the live setup across matching work and lock it into this queue.", E("recover", selector="family", shifts=(3, 5), count=6, mode="total"), E("queue_front", selector="family", count=6), E("resource", action="reserve", kind="fixture"), E("reschedule", count=1)),
        C("Pull only critical matches", "Use the setup on the highest-risk matching work and preserve flexibility elsewhere.", E("recover", selector="critical_family", shifts=(2, 3), count=3, mode="total"), E("queue_front", selector="critical_family", count=3)),
        C("Tear down after this job", "Return to the original queue and give up the family setup benefit."),
        is_follow_up=True,
    ),
    D(
        "bulk-lot-released", "The delayed material lot is released", "The delayed restock arrives as a verified lot with matched paperwork.", "material",
        C("Run the full lot immediately", "Release paused work and share setup across the full material family.", E("verify", selector="target_material"), E("release", selector="family", count=6), E("recover", selector="family", shifts=(3, 4), count=6, mode="total"), E("delay", selector="shop", shifts=1, count=2), E("reschedule", count=1)),
        C("Feed only due work", "Recover the nearest-due material paths and preserve stock for later.", E("verify", selector="target_material"), E("release", selector="near_due", count=3), E("recover", selector="near_due", shifts=2, count=3, mode="total")),
        C("Stage it normally", "Restore verified stock without changing today's queue.", E("verify", selector="target_material"), E("release", selector="target", count=1), score=0),
        is_follow_up=True,
    ),
    D(
        "clean-packet-release", "Closeout paperwork is ready", "Official labels and packets are ready for controlled batch closeout.", "document",
        C("Close the whole backlog", "Release the held completion backlog as a controlled group.", E("approve", selector="held_documents"), E("release", selector="near_complete", count=6), E("recover", selector="near_complete", shifts=(3, 5), count=6, mode="total")),
        C("Close only due jobs", "Release the completion holds where schedule pressure is highest.", E("approve", selector="due_documents"), E("release", selector="near_due", count=3), E("recover", selector="near_due", shifts=2, count=3, mode="total")),
        C("Keep reviewing one by one", "Preserve the individual review sequence without a catch-up release."),
        is_follow_up=True,
    ),
    D(
        "finish-window-restored", "Finish quality is restored", "The serviced process is holding finish quality better than expected.", "workcenter",
        C("Run precision work through it", "Use the stable window across sensitive work and pull it into this queue.", E("recover", selector="precision", shifts=1, count=5, mode="each"), E("queue_front", selector="precision", count=5), E("reschedule", count=1)),
        C("Run only the critical job", "Apply the restored window to the highest-risk finish path.", E("recover", selector="critical", shifts=2, count=1, mode="total"), E("queue_front", selector="critical", count=1)),
        C("Return to normal dispatch", "Keep the stable queue and leave the extra process window unused."),
        is_follow_up=True,
    ),
    D(
        "combined-lift", "One crane window can move several jobs", "The delayed crane window is long enough to move several staged jobs together.", "crane",
        C("Combine all lifts", "Group staged heavy moves and recover the original wait plus additional handoff time.", E("batch", selector="shop", count=4), E("recover", selector="handoff", shifts=(3, 4), count=4, mode="total"), E("resource", action="reserve", kind="crane")),
        C("Combine critical lifts", "Use the shared lift on the riskiest handoffs only.", E("recover", selector="critical", shifts=2, count=3, mode="total"), E("queue_front", selector="critical", count=3)),
        C("Move only the original job", "Keep staging simple and recover only the original move.", E("release", selector="target", count=1), E("recover", selector="target", shifts=1, count=1)),
        is_follow_up=True,
    ),
    D(
        "setup-library-update", "A setup sheet can become reusable", "The validated setup sheet can now become controlled reusable shop knowledge.", "document",
        C("Publish it for every matching station", "Give matching routes the setup improvement with a small rollout risk.", E("document", action="publish_setup"), E("recover", selector="family", shifts=1, count=5, mode="each"), E("risk", selector="family", delta=3)),
        C("Give it to one station", "Capture a smaller setup recovery with limited rollout exposure.", E("document", action="publish_setup_limited"), E("recover", selector="family", shifts=(2, 3), count=3, mode="total")),
        C("Archive it as reference only", "Keep the validation record without changing production setups."),
        is_follow_up=True,
    ),
    D(
        "aisles-cleared", "Staging aisles are clear again", "The floor reset has restored clean movement and findable WIP.", "staging",
        C("Restart with a clean pull list", "Use the clear lanes to accelerate handoffs and reopen blocked stations.", E("resource", action="open", kind="staging lane"), E("release", selector="shop", count=5), E("recover", selector="shop", shifts=(3, 4), count=5, mode="total"), E("reschedule", count=1)),
        C("Restart only critical lanes", "Use the clear paths on the highest-risk work first.", E("release", selector="critical", count=3), E("recover", selector="critical", shifts=2, count=3, mode="total")),
        C("Resume the old queue", "Keep dispatch stable and recover only the physical access." , E("resource", action="open", kind="staging lane"), score=0),
        is_follow_up=True,
    ),
    D(
        "clean-room-cleared", "The clean area is requalified", "The reset has requalified the controlled area for clean release.", "controlled",
        C("Release all controlled work", "Open the area broadly and accelerate its held work.", E("resource", action="open", kind="controlled area"), E("release", selector="controlled", count=6), E("recover", selector="controlled", shifts=(4, 5), count=6, mode="total")),
        C("Release the critical path only", "Recover the controlled-area work with the most schedule pressure.", E("release", selector="critical", count=3), E("recover", selector="critical", shifts=(2, 3), count=3, mode="total")),
        C("Keep normal release checks", "Preserve the standard review cadence without schedule recovery."),
        is_follow_up=True,
    ),
    D(
        "program-template-saved", "A reusable program template is ready", "The reserved programming window produced a reusable controlled template.", "software",
        C("Reuse it broadly", "Apply the template across similar jobs with added version-control exposure.", E("document", action="publish_program"), E("recover", selector="family", shifts=(3, 5), count=5, mode="total"), E("risk", selector="family", delta=5)),
        C("Reuse it only on matching jobs", "Apply the template where family matching is strongest.", E("document", action="publish_program_limited"), E("recover", selector="family", shifts=(2, 3), count=3, mode="total")),
        C("Do not reuse it", "Keep the program isolated and leave future verification unchanged."),
        is_follow_up=True,
    ),
    D(
        "gauge-method-locked", "A trusted gauge method is approved", "The extra measurement work produced an accepted method for the feature family.", "gauge",
        C("Standardize the method", "Publish the accepted method and accelerate matching acceptance work.", E("inspection", action="standardize"), E("recover", selector="family", shifts=1, count=5, mode="each"), E("reschedule", count=1)),
        C("Use it on late jobs", "Apply the method only where lateness pressure is highest.", E("inspection", action="standardize_limited"), E("recover", selector="near_due", shifts=2, count=3, mode="total")),
        C("File the study only", "Keep the documentation without changing the current acceptance route."),
        is_follow_up=True,
    ),
    D(
        "operator-qualified", "A new operator is qualified", "The newer operator can now cover the same capability independently.", "worker",
        C("Open a second lane", "Use the new qualification for parallel compatible work with temporary supervision load.", E("qualify", selector="target_worker"), E("open_capacity", selector="family", shifts=(3, 5), count=5, mode="total"), E("worker_load", amount=2)),
        C("Use them as relief", "Add resilient coverage and prevent the next staffing absence from stopping work.", E("qualify", selector="target_worker"), E("worker", action="relief"), E("recover", selector="target", shifts=1, count=1)),
        C("Keep them shadowing", "Retain the qualification record without opening near-term capacity.", E("qualify", selector="target_worker"), score=0),
        is_follow_up=True,
    ),
    D(
        "process-tweak-validated", "A process improvement worked", "The method improvement worked and can be extended to similar stations.", "family",
        C("Roll it out now", "Apply the improvement broadly with a brief station-level adoption cost.", E("delay", selector="family", shifts=1, count=2), E("recover", selector="family", shifts=1, count=6, mode="each"), E("document", action="publish_method")),
        C("Roll it out to one bottleneck", "Capture a focused recovery with little disruption elsewhere.", E("recover", selector="critical_family", shifts=(2, 3), count=3, mode="total"), E("document", action="publish_method_limited")),
        C("Keep it local", "Leave the improvement at the original station."),
        is_follow_up=True,
    ),
    D(
        "rack-recovery-sprint", "Temporary racks opened space", "Temporary racks created a clean lane for closing and moving finished WIP.", "staging",
        C("Clear finished WIP first", "Release tied-up stations and recover broad movement capacity.", E("resource", action="open", kind="rack"), E("release", selector="near_complete", count=5), E("recover", selector="near_complete", shifts=(3, 4), count=5, mode="total"), E("delay", selector="ready_shop", shifts=1, count=2)),
        C("Clear critical WIP first", "Recover the risky path while leaving some routine crowding.", E("release", selector="critical", count=3), E("recover", selector="critical", shifts=2, count=3, mode="total")),
        C("Leave racks as overflow", "Prevent more crowding without recovering the earlier support effort.", E("resource", action="open", kind="rack"), score=0),
        is_follow_up=True,
    ),
    D(
        "batch-data-accepted", "The batch record is accepted", "The batch record supports accepting the grouped work together.", "batch",
        C("Close the batch as one", "Release the whole compatible group through one acceptance path.", E("approve", selector="family_documents"), E("release", selector="family", count=5), E("recover", selector="family", shifts=(2, 3), count=5, mode="total")),
        C("Split only the urgent pieces", "Release the due subset and keep the rest on normal closeout.", E("release", selector="near_due", count=3), E("recover", selector="near_due", shifts=(1, 2), count=3, mode="total")),
        C("Recheck each piece", "Keep individual traceability and give up the grouped closeout benefit."),
        is_follow_up=True,
    ),
    D(
        "clamp-marks-found", "Parts show clamp marks", "Running through weak air pressure left visible marks on affected work.", "shop",
        C("Rework affected parts", "Correct the marked work before final inspection.", E("rework", selector="target", shifts=(2, 4), count=3), E("risk", selector="target", delta=-7)),
        C("Sort only critical parts", "Correct the riskiest subset and leave routine work under review.", E("rework", selector="critical", shifts=(1, 2), count=2), E("risk", selector="other_family", delta=5)),
        C("Accept the marks", "Avoid immediate rework and carry a larger final-inspection exposure.", E("risk", selector="target", delta=15), E("hold", selector="near_complete", shifts=2, count=2)),
        severity=5, is_follow_up=True,
    ),
    D(
        "covered-work-reopened", "Covered work must be reopened", "Inspectors require covered work to be reopened before acceptance.", "controlled",
        C("Reopen everything", "Inspect the affected area broadly and clear the acceptance risk.", E("hold", selector="controlled", shifts=(3, 4), count=4), E("inspection", action="reopen_all"), E("risk", selector="controlled", delta=-8)),
        C("Reopen only due work", "Inspect the most urgent covered work and defer routine acceptance.", E("hold", selector="near_due", shifts=2, count=3), E("inspection", action="reopen_limited")),
        C("Argue the containment", "Avoid immediate shop work and carry audit exposure into final closeout.", E("risk", selector="controlled", delta=14), E("document", action="audit_flag")),
        severity=5, is_follow_up=True,
    ),
    D(
        "wrong-revision-loaded", "The wrong document revision was used", "A cached or floor-controlled file was not the current revision.", "document",
        C("Correct the affected work", "Fix the stale-file job and prevent the error from spreading.", E("rework", selector="target", shifts=(2, 3), count=1), E("approve", selector="target_document"), E("risk", selector="target", delta=-6)),
        C("Stop the whole family", "Hold matching work while every local file is confirmed.", E("block", selector="family", shifts=2, count=4), E("approve", selector="family_documents")),
        C("Patch only the next step", "Limit today's delay and leave a later rework tail.", E("delay", selector="target", shifts=1, count=1), E("risk", selector="family", delta=9)),
        severity=5, is_follow_up=True,
    ),
    D(
        "phantom-stock-confirmed", "Expected stock is missing", "The missing inventory is real and the family cannot support every planned start.", "material",
        C("Strip parts from slack jobs", "Protect urgent work by taking stock from lower-pressure jobs.", E("material_transfer", selector="critical", quantity=2), E("delay", selector="low_priority", shifts=(2, 4), count=3)),
        C("Stop the affected family", "Block matching starts until replenishment arrives.", E("block", selector="family", shifts=3, count=4), E("material", action="unverified")),
        C("Keep searching", "Spend more time looking while the same shortage risk remains.", E("delay", selector="target", shifts=1, count=2), E("risk", selector="family", delta=4)),
        severity=5, is_follow_up=True,
    ),
    D(
        "fit-check-failed", "A downstream fit check failed", "Downstream fitting found that rough release damaged the planned fit sequence.", "family",
        C("Pull it back for cleanup", "Return the work for correction and protect later assembly.", E("rework", selector="target", shifts=(2, 3), count=1), E("delay", selector="dependent", shifts=1, count=1), E("risk", selector="dependent", delta=-5)),
        C("Clean at the fitting station", "Use the fitting lane for cleanup and avoid another transport move.", E("downtime", selector="receiving_workcenter", shifts=2, count=1), E("delay", selector="receiving", shifts=2, count=2)),
        C("Force the fit", "Avoid a correction now and carry alignment rework exposure.", E("risk", selector="dependent", delta=14)),
        severity=5, is_follow_up=True,
    ),
    D(
        "cure-failure-found", "A cured part failed inspection", "The forced part failed a later cure or bond check.", "family",
        C("Strip and redo", "Return the part to a clean process route.", E("rework", selector="target", shifts=(3, 5), count=1), E("risk", selector="target", delta=-8)),
        C("Add a repair patch", "Take a shorter repair and add inspection burden later.", E("rework", selector="target", shifts=2, count=1), E("hold", selector="target", shifts=1, count=1), E("risk", selector="target", delta=5)),
        C("Keep building over it", "Avoid immediate lost work and carry severe final rework exposure.", E("risk", selector="target", delta=20), E("hold", selector="near_complete", shifts=3, count=1)),
        severity=5, is_follow_up=True,
    ),
    D(
        "vacuum-trace-failed", "The vacuum trace crossed the limit", "The monitoring record crossed the allowed process limit.", "fixture",
        C("Scrap and restart the setup", "Rebuild the process from a clean setup and clear the risk tail.", E("rework", selector="target", shifts=(3, 4), count=1), E("resource", action="service", kind="fixture"), E("risk", selector="target", delta=-10)),
        C("Rework the suspect zone", "Take a smaller correction and retain some acceptance exposure.", E("rework", selector="target", shifts=2, count=1), E("risk", selector="target", delta=5)),
        C("Ask for a deviation", "Avoid immediate rework and risk an audit or customer hold.", E("document", action="deviation"), E("risk", selector="target", delta=15), E("hold", selector="near_complete", shifts=2, count=1)),
        severity=5, is_follow_up=True,
    ),
    D(
        "waste-lane-blocked", "Waste carts are blocking movement", "Interim carts now obstruct material movement through the shop.", "waste",
        C("Stop and clear the lane", "Pause the affected shop and restore normal movement.", E("block", selector="shop", shifts=2, count=4), E("resource", action="open", kind="staging lane")),
        C("Move the carts outside", "Clear the lane sooner and carry compliance exposure.", E("block", selector="shop", shifts=1, count=3), E("resource", action="open", kind="staging lane"), E("risk", selector="shop", delta=7)),
        C("Work around the lane", "Keep some work moving with added transport on every affected handoff.", E("delay", selector="shop", shifts=1, count=5), E("risk", selector="shop", delta=4)),
        severity=5, is_follow_up=True,
    ),
    D(
        "sticker-audit-hit", "A tool sticker audit found a problem", "A calibration-sticker problem was found after work had already moved on.", "tool",
        C("Reinspect affected work", "Hold and reinspect the affected family to clear the documentation issue.", E("hold", selector="family", shifts=(2, 3), count=4), E("inspection", action="reinspect_all"), E("resource", action="calibrate", kind="tool")),
        C("Reinspect only critical work", "Clear the critical subset and leave routine work flagged.", E("hold", selector="critical", shifts=(1, 2), count=3), E("inspection", action="reinspect_limited"), E("risk", selector="low_priority", delta=5)),
        C("Contest the audit", "Avoid immediate reinspection and carry certification exposure toward closeout.", E("document", action="audit_flag"), E("risk", selector="family", delta=15)),
        severity=5, is_follow_up=True,
    ),
    D(
        "weather-cleared-early", "Weather cleared earlier than expected", "The exposed stations can reopen sooner than the revised weather plan expected.", "workcenter",
        C("Restart the held work first", "Recover the waiting jobs quickly and accept a short queue surge.", E("release", selector="target", count=4), E("recover", selector="target", shifts=(2, 4), count=4, mode="total"), E("delay", selector="receiving", shifts=1, count=2), E("reschedule", count=1)),
        C("Restart critical work only", "Use the early opening on the riskiest held jobs.", E("release", selector="critical", count=2), E("recover", selector="critical", shifts=(1, 2), count=2, mode="total")),
        C("Keep the revised queue", "Avoid another reshuffle and leave most of the early opening unused."),
        is_follow_up=True,
    ),
    D(
        "setup-mismatch-found", "The moved setup does not match", "The receiving machine's setup datum does not match the moved work's plan.", "workcenter",
        C("Rework the moved setup", "Correct the alternate setup and keep the new route usable.", E("rework", selector="target", shifts=(2, 3), count=1), E("resource", action="service", kind="fixture")),
        C("Move the work back", "Return to the original machine after repair and avoid alternate-route setup rework.", E("reroute", selector="target", count=1, prefer_original=True), E("block", selector="target", shifts=2, count=1), E("reschedule", count=1)),
        C("Shim the mismatch", "Take a smaller setup delay and carry inspection exposure.", E("delay", selector="target", shifts=1, count=1), E("risk", selector="target", delta=9), E("hold", selector="near_complete", shifts=1, count=1)),
        severity=5, is_follow_up=True,
    ),
    D(
        "echo-slack-pocket-found", "The process optimization tool found hidden slack", "The reshuffle exposed useful idle capacity hidden by the old queue.", "critical",
        C("Trust the full reshuffle", "Use the whole opening across several jobs and accept visible queue churn.", E("recover", selector="all_active", shifts=(4, 6), count=8, mode="total"), E("queue_front", selector="critical", count=4), E("reschedule", count=3), score=3.0),
        C("Use only the safe moves", "Capture the clearest savings without committing to the full board change.", E("recover", selector="critical", shifts=(2, 3), count=4, mode="total"), E("reschedule", count=1)),
        C("Roll back the advice", "Restore the earlier dispatch plan and leave the reshuffle cost unrecovered.", E("reschedule", count=2)),
        is_follow_up=True,
    ),
    D(
        "replacement-handoff-check", "Replacement work needs a handoff check", "The replacement operator's work needs review before the next dependency trusts it.", "worker",
        C("Check the handoff now", "Pause briefly and clear the handoff before downstream release.", E("hold", selector="target", shifts=1, count=1), E("inspection", action="handoff_check"), E("risk", selector="target", delta=-6)),
        C("Let the replacement continue", "Avoid a stop and carry a possible misunderstanding into later work.", E("risk", selector="target", delta=10), E("rework", selector="target", shifts=(2, 3), count=1, probability=0.5)),
        C("Pair the replacement with a lead", "Keep the target moving while slowing another station's support.", E("replace_worker", selector="target", paired=True), E("delay", selector="donor", shifts=1, count=1), E("worker_load", amount=2)),
        severity=4, is_follow_up=True,
    ),
    D(
        "returning-worker-shortcut", "The returning operator knows a shortcut", "The returning operator knows a faster safe setup for the paused work.", "worker",
        C("Use the shortcut", "Recover the absence and take an additional setup saving while keeping this route assigned to the worker.", E("release", selector="target", count=1), E("recover", selector="target", shifts=(2, 3), count=1, mode="total"), E("resource", action="reserve_worker")),
        C("Use only part of it", "Recover the absence without committing the full route.", E("release", selector="target", count=1), E("recover", selector="target", shifts=1, count=1, mode="total")),
        C("Resume normally", "Return to the original setup and leave the absence delay in place.", E("release", selector="target", count=1), score=0),
        is_follow_up=True,
    ),
)


ALL_DEFINITIONS = (*BASE_DEFINITIONS, *FOLLOW_UP_DEFINITIONS)
DEFINITIONS_BY_ID = {definition.id: definition for definition in ALL_DEFINITIONS}


def get_decision_definitions() -> dict[str, DecisionDefinition]:
    """Return the stable named definition catalog."""
    return dict(DEFINITIONS_BY_ID)


def choice_schedule_score(definition: DecisionDefinition, choice: CatalogChoice) -> float:
    """Collapse the old rich effect mix into one signed schedule value."""
    unavoidable_score = _effect_score(definition.unavoidable_effects)
    return round(max(-5.0, min(5.0, choice.score_delta + unavoidable_score)), 2)


def definition_schedule_score(definition: DecisionDefinition) -> float:
    """Return the average signed schedule direction across a definition's choices."""
    if not definition.choices:
        return 0.0
    values = [choice_schedule_score(definition, choice) for choice in definition.choices]
    return round(sum(values) / len(values), 2)
