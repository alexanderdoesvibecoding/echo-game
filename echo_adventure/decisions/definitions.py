"""Decision catalog and explicit schedule scores for the job-day simulation."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class FollowUpEdge:
    """A possible later question tied to the job that caused it."""

    target_definition_id: str
    probability: float
    delay_days: int = 3


@dataclass(frozen=True)
class CatalogChoice:
    label: str
    follow_up_edges: tuple[FollowUpEdge, ...]
    score_delta: float
    icon_key: str = ""


@dataclass(frozen=True)
class FollowUpResult:
    """An alternate startup-selected result for one follow-up definition."""

    title: str
    description: str
    choices: tuple[CatalogChoice, ...]


@dataclass(frozen=True)
class DecisionDefinition:
    id: str
    title: str
    description: str
    choices: tuple[CatalogChoice, ...]
    is_follow_up: bool = False
    shared_across_routes: bool = False
    unavoidable_follow_up_edges: tuple[FollowUpEdge, ...] = ()
    alternate_results: tuple[FollowUpResult, ...] = ()


def F(target: str, probability: float, delay_days: int = 3) -> FollowUpEdge:
    return FollowUpEdge(target, probability, delay_days)


def C(
    label: str,
    *,
    score: float,
    follow: tuple[FollowUpEdge, ...] = (),
) -> CatalogChoice:
    return CatalogChoice(
        label=label,
        follow_up_edges=follow,
        score_delta=score,
    )


def R(
    title: str,
    description: str,
    *choices: CatalogChoice,
) -> FollowUpResult:
    return FollowUpResult(title=title, description=description, choices=choices)


def D(
    definition_id: str,
    title: str,
    description: str,
    *choices: CatalogChoice,
    is_follow_up: bool = False,
    shared: bool = False,
    card_follow: tuple[FollowUpEdge, ...] = (),
    alternate_results: tuple[FollowUpResult, ...] = (),
) -> DecisionDefinition:
    icon_keys = DECISION_CHOICE_ICON_KEYS.get(definition_id)
    if icon_keys is None or len(icon_keys) != len(choices):
        raise ValueError(f"Decision {definition_id!r} must define one icon key per choice.")
    if len(set(icon_keys)) != len(icon_keys):
        raise ValueError(f"Decision {definition_id!r} cannot repeat an icon key.")
    unknown_icon_keys = set(icon_keys) - SUPPORTED_CHOICE_ICON_KEYS
    if unknown_icon_keys:
        raise ValueError(f"Decision {definition_id!r} uses unknown icon keys: {sorted(unknown_icon_keys)}")
    if alternate_results and not is_follow_up:
        raise ValueError(f"Decision {definition_id!r} cannot vary a base-question result.")

    def choices_with_icons(result_choices: tuple[CatalogChoice, ...]) -> tuple[CatalogChoice, ...]:
        if len(result_choices) != len(icon_keys):
            raise ValueError(
                f"Decision {definition_id!r} must keep the same choice count in every result."
            )
        return tuple(
            replace(choice, icon_key=icon_key)
            for choice, icon_key in zip(result_choices, icon_keys, strict=True)
        )

    results_with_icons = tuple(
        replace(result, choices=choices_with_icons(result.choices))
        for result in alternate_results
    )
    return DecisionDefinition(
        id=definition_id,
        title=title,
        description=description,
        choices=choices_with_icons(choices),
        is_follow_up=is_follow_up,
        shared_across_routes=shared,
        unavoidable_follow_up_edges=card_follow,
        alternate_results=results_with_icons,
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
        "weather", "Exposed work areas are closed by weather", "Severe weather has closed exposed work areas, pausing affected jobs.",
        C("Reroute exposed work", score=-2.39),
        C("Wait it out", follow=(F("weather-cleared-early", 0.62),), score=-2.33),
        shared=True,
    ),
    D(
        "workstation-breakdown", "A workstation has stopped working", "An unexpected workstation fault has stopped the job currently running there.",
        C("Move affected subjobs", follow=(F("setup-mismatch-found", 0.48),), score=-1.76),
        C("Wait for repair", score=-3.3),
    ),
    D(
        "materials-not-here", "Required material has not arrived", "Required material has not arrived at the planned workstation.",
        C("Wait for materials", follow=(F("bulk-lot-released", 0.58),), score=-0.55),
        C("Use another subjob's material", follow=(F("phantom-stock-confirmed", 0.46),), score=-0.28),
        C("Switch to verified work", score=-0.43),
    ),
    D(
        "echo-recommendation", "A third-party process optimization tool sees a possible schedule move", "A third-party process optimization tool recommends a disruptive, board-wide reshuffle whose benefit may not be immediately visible.",
        C("Take advice", follow=(F("echo-slack-pocket-found", 0.68),), score=-1.5),
        C("Ignore the tool", score=0.0),
    ),
    D(
        "worker-off-day", "The assigned operator is unavailable", "The operator assigned to this job is unavailable today.",
        C("Find a replacement", follow=(F("replacement-handoff-check", 0.52),), score=0.17),
        C("Hold until the worker returns", follow=(F("returning-worker-shortcut", 0.58),), score=-0.28),
    ),
    D(
        "calibration-drift", "Measurements may be unreliable", "Recent measurement work is suspect until the measurement chain is trusted again.",
        C("Recalibrate now", follow=(F("narrow-drift-found", 0.64),), score=0.09),
        C("Add witness checks", score=-0.14),
        C("Send checks elsewhere", score=0.01),
    ),
    D(
        "traveler-mismatch", "The job instructions do not match", "The paper traveler and digital route disagree about the next operation.",
        C("Stop and reconcile it", follow=(F("route-shortcut-approved", 0.62),), score=-0.05),
        C("Use the floor copy", follow=(F("wrong-revision-loaded", 0.48),), score=-0.28),
        C("Start only the unaffected steps", score=-0.15),
    ),
    D(
        "shared-fixture-claim", "Two jobs need the same key fixture", "Two ready jobs need the same qualified fixture at the same time.",
        C("Give it to the tightest job", score=-0.44),
        C("Build a temporary fixture", follow=(F("spare-fixture-certified", 0.61),), score=-0.27),
        C("Keep the original sequence", score=-0.69),
    ),
    D(
        "changeover-drag", "A changeover is taking longer than planned", "A family changeover is taking longer than the dispatch plan allowed.",
        C("Finish similar work first", score=0.56),
        C("Pay the changeover now", follow=(F("family-run-unlocked", 0.65),), score=-0.34),
        C("Move the odd job", score=-0.08),
    ),
    D(
        "batch-window-opens", "An early batch window is available", "A shared process window is available earlier than expected.",
        C("Fill the batch", follow=(F("batch-data-accepted", 0.63),), score=0.9),
        C("Reserve it for critical work", score=0.12),
        C("Ignore the window", score=0.0),
    ),
    D(
        "consumables-short", "Shop supplies are running low", "A shop's working stock is too low to sustain every planned start.",
        C("Ration to due work", score=-0.41),
        C("Borrow from another shop", score=-0.14),
        C("Wait for restock", follow=(F("bulk-lot-released", 0.6),), score=-1.19),
    ),
    D(
        "label-printer-outage", "Finished work cannot be labeled", "Completed work cannot receive controlled labels at the release desk.",
        C("Handwrite controlled labels", score=-0.9),
        C("Borrow a printer", score=-1.26),
        C("Hold completions", follow=(F("clean-packet-release", 0.64),), score=-1.59),
    ),
    D(
        "shop-air-pressure-dip", "Shop air is weakening tools and clamps", "Pneumatic tools and clamps are running below normal reliability.",
        C("Throttle noncritical work", score=-0.6),
        C("Move hand-tool work forward", score=0.22),
        C("Run through it", follow=(F("clamp-marks-found", 0.49),), score=-1.22),
        shared=True,
    ),
    D(
        "coolant-change-due", "A machine needs coolant service", "A cutting or machining station is approaching its finish-quality limit.",
        C("Service it now", follow=(F("finish-window-restored", 0.66),), score=0.27),
        C("Run one more shift", follow=(F("finish-window-restored", 0.62),), score=-0.54),
        C("Move precision work away", score=0.21),
    ),
    D(
        "fod-sweep", "A controlled area needs a debris sweep", "Foreign object debris requires a controlled-area sweep before work resumes.",
        C("Acknowledge", score=-1.12),
        card_follow=(F("covered-work-reopened", 0.42),),
    ),
    D(
        "handoff-window-missed", "A handoff missed its receiving window", "A cross-shop move missed the receiving station's planned intake window.",
        C("Hold the receiving slot", score=-0.28),
        C("Release the slot", score=-0.15),
        C("Pull a substitute subjob", score=0.12),
    ),
    D(
        "crane-reservation-conflict", "The crane is booked elsewhere", "A shared heavy-lift resource is committed to another shop.",
        C("Wait for the crane", follow=(F("combined-lift", 0.62),), score=-0.41),
        C("Swap in bench work", score=0.18),
        C("Use the off-shift slot", score=-0.42),
    ),
    D(
        "nesting-opportunity", "Similar jobs can share setup", "Compatible work can share a setup, fixture, program, or batch.",
        C("Nest the jobs", score=0.7),
        C("Nest only low-risk work", score=0.5),
        C("Keep them separate", score=0.0),
    ),
    D(
        "old-setup-sheet", "An old setup sheet might help", "A proven setup sheet exists for similar work, but its applicability is not yet controlled.",
        C("Use it as-is", follow=(F("wrong-revision-loaded", 0.52),), score=0.18),
        C("Validate first", follow=(F("setup-library-update", 0.67),), score=-0.05),
        C("Ignore it", score=0.0),
    ),
    D(
        "wip-crowding", "Work in progress is crowding the floor", "Staging space, carts, and access lanes are constraining work in progress.",
        C("Freeze new starts", follow=(F("aisles-cleared", 0.65),), score=-0.78),
        C("Clear shortest work first", score=0.22),
        C("Move WIP to overflow", score=-0.45),
    ),
    D(
        "cleanliness-breach", "A clean area failed inspection", "A controlled area failed its cleanliness check while work was open.",
        C("Full reset", follow=(F("clean-room-cleared", 0.69),), score=-0.89),
        C("Isolate the zone", score=-1.15),
        C("Continue under covers", follow=(F("covered-work-reopened", 0.52),), score=-0.64),
        shared=True,
    ),
    D(
        "software-seat-conflict", "Programming seats are full", "Programming-dependent work cannot release while all software seats are occupied.",
        C("Reserve the next seat", follow=(F("program-template-saved", 0.66),), score=-0.19),
        C("Borrow after hours", score=-0.59),
        C("Run a manual fallback", score=-0.28),
    ),
    D(
        "network-folder-offline", "Shop files are temporarily offline", "Current programs and acceptance files are temporarily unreachable.",
        C("Use cached copies", follow=(F("wrong-revision-loaded", 0.51),), score=-0.17),
        C("Start independent work", score=0.29),
        C("Wait for IT", score=-0.64),
        shared=True,
    ),
    D(
        "gauge-dispute", "Two gauges disagree", "Two gauges disagree and the affected feature cannot be accepted yet.",
        C("Cross-check quickly", score=-0.12),
        C("Run a formal study", follow=(F("gauge-method-locked", 0.7),), score=-0.63),
        C("Accept the trusted gauge", score=-0.13),
    ),
    D(
        "count-variance", "Inventory counts do not match", "System inventory and the floor count disagree about available stock.",
        C("Cycle count now", score=-0.3),
        C("Consume visible stock", follow=(F("phantom-stock-confirmed", 0.54),), score=0.03),
        C("Reassign starts", score=0.22),
    ),
    D(
        "burr-cleanup", "Parts need extra cleanup", "Cut or machined parts need more cleanup than the downstream plan allowed.",
        C("Clean before release", score=-0.21),
        C("Send to finishing early", score=-0.11),
        C("Release rough", follow=(F("fit-check-failed", 0.52),), score=-0.4),
    ),
    D(
        "cure-clock", "A process cure is not finished", "The next dependency cannot safely begin until a process dwell completes.",
        C("Wait the clock out", score=-0.41),
        C("Pull parallel work", score=0.18),
        C("Force the next step", follow=(F("cure-failure-found", 0.55),), score=-0.32),
    ),
    D(
        "vacuum-leak-chase", "A setup will not hold vacuum", "A bag, seal, or holding fixture will not maintain process pressure.",
        C("Chase the leak", score=-0.05),
        C("Rebuild the setup", score=0.22),
        C("Run with monitoring", follow=(F("vacuum-trace-failed", 0.54),), score=-0.54),
    ),
    D(
        "tool-crib-hold", "Calibrated tools are held up", "Calibrated hand tools are waiting on controlled crib release.",
        C("Wait for release", score=-0.48),
        C("Borrow substitutes", follow=(F("sticker-audit-hit", 0.46),), score=-0.23),
        C("Split the queue", score=-0.17),
    ),
    D(
        "fixture-soak", "A fixture is not ready yet", "A large fixture has not reached its required process condition.",
        C("Wait for soak", score=-0.28),
        C("Preheat a second fixture", score=0.33),
        C("Switch to a ready fixture", follow=(F("spare-fixture-certified", 0.58),), score=-0.08),
    ),
    D(
        "shift-overlap-bonus", "Extra crew overlap is available", "An unexpected overlap creates a short window of extra coordination.",
        C("Use it for a handoff", score=0.33),
        C("Use it for short jobs", score=0.64),
        C("Use it for setup prep", score=0.33),
        shared=True,
    ),
    D(
        "waste-container-full", "Waste containers are full", "Affected stations cannot continue producing until waste flow is restored.",
        C("Empty containers now", score=-0.25),
        C("Use small interim carts", follow=(F("waste-lane-blocked", 0.5),), score=-1.15),
        C("Divert to another area", score=-0.16),
        shared=True,
    ),
    D(
        "preapproved-package", "Approved paperwork can close similar work", "One work family already has an accepted closeout package.",
        C("Pull matching work forward", score=0.78),
        C("Use it on near-complete jobs", follow=(F("clean-packet-release", 0.62),), score=1.13),
        C("Save the package", score=0.0),
    ),
    D(
        "expired-stickers", "Tool calibration stickers are expired", "Calibration stickers on several hand tools are out of date.",
        C("Audit and resticker", score=-0.25),
        C("Swap tools", score=-0.1),
        C("Keep using them", follow=(F("sticker-audit-hit", 0.56),), score=-0.67),
    ),
    D(
        "vendor-rep-on-site", "A vendor specialist is available today", "A vendor specialist is unexpectedly available for a limited window.",
        C("Use them on setup", score=0.44),
        C("Use them on troubleshooting", score=0.67),
        C("Let them go", score=0.0),
        shared=True,
    ),
    D(
        "training-run", "A newer operator can train on live work", "A newer operator can qualify on live work, slowing the current station but adding flexibility.",
        C("Train on low-risk work", follow=(F("operator-qualified", 0.72),), score=-0.28),
        C("Train on urgent work", score=-0.18),
        C("Postpone training", score=0.0),
    ),
    D(
        "off-peak-utility-slot", "An off-peak utility slot is open", "An extra utility-dependent process window can be used if the board is rearranged.",
        C("Run critical work off-peak", score=0.1),
        C("Run batch work off-peak", score=0.57),
        C("Skip the slot", score=0.0),
        shared=True,
    ),
    D(
        "floor-walk-insight", "A floor walk found a faster method", "A small method improvement can remove wasted motion from matching work.",
        C("Apply it today", follow=(F("process-tweak-validated", 0.7),), score=-0.2),
        C("Apply only to new starts", score=0.33),
        C("Keep the old method", score=0.0),
    ),
    D(
        "wash-tank-chemistry", "A wash tank is drifting out of range", "A preparation tank is moving out of its controlled process range.",
        C("Change the bath", follow=(F("finish-window-restored", 0.65),), score=-0.08),
        C("Send work to another prep route", score=-0.06),
        C("Keep running light work", score=-0.6),
    ),
    D(
        "rack-shortage", "Parts have nowhere safe to stage", "Finished and in-process parts cannot safely move or stage because racks are full.",
        C("Clear old racks", score=0.61),
        C("Build temporary racks", follow=(F("rack-recovery-sprint", 0.66),), score=-0.09),
        C("Keep parts at stations", score=-1.15),
    ),
    D(
        "safety-drill", "A required safety drill interrupts work", "A required emergency drill interrupts production across the site.",
        C("Acknowledge", score=-0.83),
        shared=True,
    ),
    D(
        "access-badge-failure", "Secure-area access is blocked", "A secure-area badge reader is preventing normal shift-start access.",
        C("Wait for security", score=-0.48),
        C("Pull open-area work", score=0.22),
        C("Escort critical staff", score=-0.14),
        shared=True,
    ),
    D(
        "reference-sample-missing", "A reference sample is missing", "Work needing visual or fit comparison cannot be accepted without its reference artifact.",
        C("Search now", score=0.02),
        C("Borrow a sister sample", score=-0.32),
        C("Switch to measured criteria", follow=(F("gauge-method-locked", 0.64),), score=0.07),
    ),
    D(
        "staging-map-reset", "Staging locations need to be reset", "A large movement has invalidated planned WIP locations and access paths.",
        C("Redraw staging now", follow=(F("aisles-cleared", 0.64),), score=0.23),
        C("Move only critical WIP", score=-0.21),
        C("Let shops improvise", score=-0.61),
    ),
)


FOLLOW_UP_DEFINITIONS = (
    D(
        "narrow-drift-found", "The measurement issue is limited", "Recalibration shows the measurement concern was limited to one reference.",
        C("Release quarantined work", score=1.88),
        C("Release only critical work", score=1.2),
        C("Keep everything quarantined", score=0.0),
        is_follow_up=True,
    ),
    D(
        "route-shortcut-approved", "Engineering approved a route shortcut", "Engineering confirms that a copied route step is unnecessary for this work family.",
        C("Apply the shortcut broadly", score=0.9),
        C("Apply it only here", score=0.82),
        C("Keep the old route", score=0.0),
        is_follow_up=True,
    ),
    D(
        "spare-fixture-certified", "A spare fixture passed certification", "The alternate fixture passed its checks and can become a qualified resource.",
        C("Certify it for the family", score=1.62),
        C("Use it only on low-risk jobs", score=0.81),
        C("Retire the fixture", score=0.0),
        is_follow_up=True,
    ),
    D(
        "family-run-unlocked", "A station can run similar jobs together", "The station is now established for a family of similar work.",
        C("Pull the whole family forward", score=1.61),
        C("Pull only critical matches", score=1.03),
        C("Tear down after this job", score=0.0),
        is_follow_up=True,
    ),
    D(
        "bulk-lot-released", "The delayed material lot is released", "The delayed restock arrives as a verified lot with matched paperwork.",
        C("Run the full lot immediately", score=1.55),
        C("Feed only due work", score=1.21),
        C("Stage it normally", score=0.0),
        is_follow_up=True,
    ),
    D(
        "clean-packet-release", "Closeout paperwork is ready", "Official labels and packets are ready for controlled batch closeout.",
        C("Close the whole backlog", score=2.03),
        C("Close only due jobs", score=1.21),
        C("Keep reviewing one by one", score=0.0),
        is_follow_up=True,
    ),
    D(
        "finish-window-restored", "Finish quality is holding", "The process is holding finish quality better than expected.",
        C("Run precision work through it", score=1.01),
        C("Run only the critical job", score=0.78),
        C("Return to normal dispatch", score=0.0),
        is_follow_up=True,
        alternate_results=(
            R(
                "The finish limit was exceeded",
                "The process check found that finish quality deteriorated before the next planned service.",
                C("Rework all affected parts", score=-1.42),
                C("Recheck only precision work", score=-0.91),
                C("Hold the machine for review", score=-0.43),
            ),
        ),
    ),
    D(
        "combined-lift", "One crane window can move several jobs", "The delayed crane window is long enough to move several staged jobs together.",
        C("Combine all lifts", score=1.39),
        C("Combine critical lifts", score=0.87),
        C("Move only the original job", score=0.55),
        is_follow_up=True,
    ),
    D(
        "setup-library-update", "A setup sheet can become reusable", "The validated setup sheet can now become controlled reusable shop knowledge.",
        C("Publish it for every matching station", score=0.67),
        C("Give it to one station", score=0.89),
        C("Archive it as reference only", score=0.0),
        is_follow_up=True,
    ),
    D(
        "aisles-cleared", "Staging aisles are clear again", "The floor reset has restored clean movement and findable WIP.",
        C("Restart with a clean pull list", score=1.87),
        C("Restart only critical lanes", score=1.04),
        C("Resume the old queue", score=0.0),
        is_follow_up=True,
    ),
    D(
        "clean-room-cleared", "The clean area is requalified", "The reset has requalified the controlled area for clean release.",
        C("Release all controlled work", score=2.24),
        C("Release the critical path only", score=1.2),
        C("Keep normal release checks", score=0.0),
        is_follow_up=True,
    ),
    D(
        "program-template-saved", "A reusable program template is ready", "The reserved programming window produced a reusable controlled template.",
        C("Reuse it broadly", score=1.15),
        C("Reuse it only on matching jobs", score=0.89),
        C("Do not reuse it", score=0.0),
        is_follow_up=True,
    ),
    D(
        "gauge-method-locked", "A trusted gauge method is approved", "The extra measurement work produced an accepted method for the feature family.",
        C("Standardize the method", score=0.8),
        C("Use it on late jobs", score=0.72),
        C("File the study only", score=0.0),
        is_follow_up=True,
    ),
    D(
        "operator-qualified", "A new operator is qualified", "The newer operator can now cover the same capability independently.",
        C("Open a second lane", score=1.38),
        C("Use them as relief", score=0.57),
        C("Keep them shadowing", score=0.0),
        is_follow_up=True,
    ),
    D(
        "process-tweak-validated", "A process improvement worked", "The method improvement worked and can be extended to similar stations.",
        C("Roll it out now", score=0.55),
        C("Roll it out to one bottleneck", score=0.89),
        C("Keep it local", score=0.0),
        is_follow_up=True,
    ),
    D(
        "rack-recovery-sprint", "Temporary racks opened space", "Temporary racks created a clean lane for closing and moving finished WIP.",
        C("Clear finished WIP first", score=1.55),
        C("Clear critical WIP first", score=1.04),
        C("Leave racks as overflow", score=0.0),
        is_follow_up=True,
    ),
    D(
        "batch-data-accepted", "The batch record is accepted", "The batch record supports accepting the grouped work together.",
        C("Close the batch as one", score=1.49),
        C("Split only the urgent pieces", score=0.88),
        C("Recheck each piece", score=0.0),
        is_follow_up=True,
    ),
    D(
        "clamp-marks-found", "Parts show clamp marks", "Running through weak air pressure left visible marks on affected work.",
        C("Rework affected parts", score=-1.63),
        C("Sort only critical parts", score=-1.02),
        C("Accept the marks", score=-1.24),
        is_follow_up=True,
        alternate_results=(
            R(
                "Air pressure recovered before parts were marked",
                "The monitored pressure recovered and the held work shows no clamp damage.",
                C("Release all held work", score=1.24),
                C("Release only critical work", score=0.7),
                C("Keep the original queue", score=0.0),
            ),
        ),
    ),
    D(
        "covered-work-reopened", "Covered work must be reopened", "Inspectors require covered work to be reopened before acceptance.",
        C("Reopen everything", score=-0.97),
        C("Reopen only due work", score=-0.62),
        C("Argue the containment", score=-0.56),
        is_follow_up=True,
        alternate_results=(
            R(
                "Covered work passed containment review",
                "Inspectors accepted the containment record without reopening the protected work.",
                C("Release all covered work", score=1.27),
                C("Release only due work", score=0.74),
                C("Keep the covers in place", score=0.0),
            ),
        ),
    ),
    D(
        "wrong-revision-loaded", "The wrong document revision was used", "A cached or floor-controlled file was not the current revision.",
        C("Correct the affected work", score=-0.49),
        C("Stop the whole family", score=-0.93),
        C("Patch only the next step", score=-0.63),
        is_follow_up=True,
        alternate_results=(
            R(
                "The uncontrolled copy matches the current revision",
                "Document control confirmed that the working copy contains the currently approved instructions.",
                C("Release the affected family", score=1.03),
                C("Release only current work", score=0.61),
                C("Return to controlled copies", score=0.0),
            ),
        ),
    ),
    D(
        "phantom-stock-confirmed", "Expected stock is missing", "The missing inventory is real and the family cannot support every planned start.",
        C("Strip parts from slack jobs", score=-0.99),
        C("Stop the affected family", score=-1.58),
        C("Keep searching", score=-0.5),
        is_follow_up=True,
    ),
    D(
        "fit-check-failed", "A downstream fit check failed", "Downstream fitting found that rough release damaged the planned fit sequence.",
        C("Pull it back for cleanup", score=-0.94),
        C("Clean at the fitting station", score=-1.19),
        C("Force the fit", score=-0.63),
        is_follow_up=True,
        alternate_results=(
            R(
                "The rough release passed its fit check",
                "Downstream fitting confirmed that the released surfaces still meet the planned fit.",
                C("Release the matching batch", score=1.12),
                C("Release only the checked work", score=0.69),
                C("Keep normal cleanup", score=0.0),
            ),
        ),
    ),
    D(
        "cure-failure-found", "A cured part failed inspection", "The forced part failed a later cure or bond check.",
        C("Strip and redo", score=-1.14),
        C("Add a repair patch", score=-1.17),
        C("Keep building over it", score=-1.5),
        is_follow_up=True,
        alternate_results=(
            R(
                "The accelerated cure met its acceptance margin",
                "Inspection confirmed that the forced process step still achieved an acceptable cure.",
                C("Release matching cured work", score=1.02),
                C("Release only the tested part", score=0.62),
                C("Keep the standard dwell", score=0.0),
            ),
        ),
    ),
    D(
        "vacuum-trace-failed", "The vacuum trace crossed the limit", "The monitoring record crossed the allowed process limit.",
        C("Scrap and restart the setup", score=-0.64),
        C("Rework the suspect zone", score=-0.97),
        C("Ask for a deviation", score=-1.0),
        is_follow_up=True,
        alternate_results=(
            R(
                "The monitored vacuum stayed within its limit",
                "The complete pressure trace shows that the monitored setup remained acceptable.",
                C("Release the monitored work", score=0.94),
                C("Release only the critical part", score=0.56),
                C("Retain the extra monitoring", score=0.0),
            ),
        ),
    ),
    D(
        "waste-lane-blocked", "Waste carts are blocking movement", "Interim carts now obstruct material movement through the shop.",
        C("Stop and clear the lane", score=-0.88),
        C("Move the carts outside", score=-0.57),
        C("Work around the lane", score=-0.68),
        is_follow_up=True,
    ),
    D(
        "sticker-audit-hit", "A tool sticker audit found a problem", "A calibration-sticker problem was found after work had already moved on.",
        C("Reinspect affected work", score=-0.7),
        C("Reinspect only critical work", score=-0.67),
        C("Contest the audit", score=-0.6),
        is_follow_up=True,
        alternate_results=(
            R(
                "Calibration records clear the expired tool tags",
                "The controlled records show that the tools remained calibrated despite their outdated stickers.",
                C("Release all affected work", score=1.08),
                C("Release only critical work", score=0.64),
                C("Resticker before release", score=0.0),
            ),
        ),
    ),
    D(
        "weather-cleared-early", "Weather cleared earlier than expected", "The exposed stations can reopen sooner than the revised weather plan expected.",
        C("Restart the held work first", score=1.11),
        C("Restart critical work only", score=0.81),
        C("Keep the revised queue", score=0.0),
        is_follow_up=True,
        alternate_results=(
            R(
                "The weather closure lasted longer than forecast",
                "Exposed stations remain closed and the revised indoor queue is beginning to back up.",
                C("Keep all exposed work held", score=-1.43),
                C("Move critical work inside", score=-0.82),
                C("Rebuild tomorrow's queue", score=-0.34),
            ),
        ),
    ),
    D(
        "setup-mismatch-found", "The moved setup does not match", "The receiving machine's setup datum does not match the moved work's plan.",
        C("Rework the moved setup", score=-0.71),
        C("Move the work back", score=-0.4),
        C("Shim the mismatch", score=-0.83),
        is_follow_up=True,
    ),
    D(
        "echo-slack-pocket-found", "The process optimization tool found hidden slack", "The reshuffle exposed useful idle capacity hidden by the old queue.",
        C("Trust the full reshuffle", score=3.0),
        C("Use only the safe moves", score=0.81),
        C("Roll back the advice", score=0.0),
        is_follow_up=True,
    ),
    D(
        "replacement-handoff-check", "Replacement work needs a handoff check", "The replacement operator's work needs review before the next dependency trusts it.",
        C("Check the handoff now", score=0.15),
        C("Let the replacement continue", score=-1.39),
        C("Pair the replacement with a lead", score=-0.15),
        is_follow_up=True,
    ),
    D(
        "returning-worker-shortcut", "The returning operator knows a shortcut", "The returning operator knows a faster safe setup for the paused work.",
        C("Use the shortcut", score=1.04),
        C("Use only part of it", score=0.55),
        C("Resume normally", score=0.0),
        is_follow_up=True,
    ),
)


DEFINITIONS_BY_ID = {
    definition.id: definition
    for definition in (*BASE_DEFINITIONS, *FOLLOW_UP_DEFINITIONS)
}
