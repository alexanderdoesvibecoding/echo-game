"""Scenario construction for shops, pieces, jobs, dependencies, and events."""

from __future__ import annotations

import copy
import random

from .config import GameConfig
from .decisions import generate_campaign_decision_graph
from .enums import JobStatus
from .events import generate_event_timeline
from .models import Job, PuzzlePiece, Scenario, Shop, SimulationState, WorkCenter


SHOP_BLUEPRINTS = [
    ("Fabrication Gallery", ["forming", "cutting", "bonding", "tooling"]),
    ("Precision Machining", ["milling", "turning", "boring", "finishing"]),
    ("Composite Cell", ["layup", "bonding", "curing", "inspection"]),
    ("Coating Studio", ["coating", "surface_prep", "curing", "finishing"]),
    ("Assembly Hall", ["assembly", "fitting", "fastening", "tooling"]),
    ("Calibration Lab", ["calibration", "metrology", "inspection", "systems_fit"]),
    ("Systems Assembly", ["systems_fit", "wiring", "calibration", "assembly"]),
    ("Metrology Loft", ["inspection", "metrology", "alignment", "certification"]),
    ("Tooling Annex", ["tooling", "fixture", "forming", "alignment"]),
]

PIECE_NAMES = [
    "Aster",
    "Beacon",
    "Cinder",
    "Delta",
    "Ember",
    "Flux",
    "Garnet",
    "Helio",
    "Ion",
    "Juniper",
    "Kestrel",
    "Lumen",
    "Mosaic",
    "Nimbus",
    "Orchid",
    "Pioneer",
    "Quasar",
    "Relay",
    "Solace",
    "Tangent",
    "Umber",
    "Vector",
    "Willow",
    "Xylo",
    "Yarrow",
    "Zenith",
    "Atlas",
    "Briar",
    "Copper",
    "Drift",
]


def generate_scenario(config: GameConfig) -> Scenario:
    """Generate and validate one deterministic scenario from the config seed."""
    seed = config.seed if config.seed is not None else 0
    rng = random.Random(seed)
    shops, workcenters = _generate_shops_and_workcenters(config, rng)
    pieces, jobs = _generate_pieces_and_jobs(config, rng, shops, workcenters)
    _assign_planned_completion_rework(config, rng, jobs)
    dependencies = {job.id: list(job.dependency_ids) for job in jobs.values()}
    events = generate_event_timeline(rng, config, shops, workcenters, pieces, jobs)
    scenario = Scenario(
        scenario_id=f"SCN-{seed % 1_000_000:06d}",
        seed=seed,
        shops=shops,
        workcenters=workcenters,
        pieces=pieces,
        jobs=jobs,
        dependencies=dependencies,
        event_timeline=events,
        deadline_shift=config.deadline_shift,
    )
    validate_scenario(scenario, config)
    graph_state = SimulationState(
        scenario_id=scenario.scenario_id,
        seed=scenario.seed,
        deadline_shift=scenario.deadline_shift,
        shifts_per_day=config.shifts_per_day,
        shops=copy.deepcopy(scenario.shops),
        workcenters=copy.deepcopy(scenario.workcenters),
        pieces=copy.deepcopy(scenario.pieces),
        jobs=copy.deepcopy(scenario.jobs),
        event_timeline=copy.deepcopy(scenario.event_timeline),
    )
    (
        scenario.decision_cards,
        scenario.campaign_decision_graph,
        scenario.daily_decision_roots,
        scenario.daily_decision_counts,
    ) = generate_campaign_decision_graph(graph_state, config)
    return scenario


def _assign_planned_completion_rework(
    config: GameConfig,
    rng: random.Random,
    jobs: dict[str, Job],
) -> None:
    """Preassign completion rework so player and ECHO share the same defects."""
    if config.completion_rework_probability <= 0.0:
        return
    for job in jobs.values():
        if rng.random() < config.completion_rework_probability:
            job.planned_completion_rework_shifts = rng.randint(
                config.min_completion_rework_shifts,
                config.max_completion_rework_shifts,
            )


def validate_scenario(scenario: Scenario, config: GameConfig) -> None:
    """Check generated objects for configured counts and dependency validity."""
    if len(scenario.pieces) != config.piece_count:
        raise ValueError(f"Scenario must contain exactly {config.piece_count} jobs.")
    if len(scenario.shops) != config.shop_count:
        raise ValueError(f"Scenario must contain exactly {config.shop_count} shops.")
    for shop in scenario.shops.values():
        if not config.min_workcenters_per_shop <= len(shop.workcenter_ids) <= config.max_workcenters_per_shop:
            raise ValueError(f"{shop.id} workcenter count outside configured range.")
    for piece in scenario.pieces.values():
        if not config.min_jobs_per_piece <= piece.total_job_count <= config.max_jobs_per_piece:
            raise ValueError(f"{piece.id} subjob count outside configured range.")
    for job in scenario.jobs.values():
        if not job.candidate_workcenter_ids:
            raise ValueError(f"{job.id} has no capable workcenter.")
        for dep_id in job.dependency_ids:
            if dep_id not in scenario.jobs:
                raise ValueError(f"{job.id} depends on unknown job {dep_id}.")
    _assert_acyclic(scenario.jobs)


def _generate_shops_and_workcenters(
    config: GameConfig,
    rng: random.Random,
) -> tuple[dict[str, Shop], dict[str, WorkCenter]]:
    """Create shop blueprints and a varied number of capable workcenters."""
    shops: dict[str, Shop] = {}
    workcenters: dict[str, WorkCenter] = {}

    # Shop size mapping: larger shops have more workcenters, smaller specialized shops have fewer
    shop_size_factors = {
        0: (4, 6),    # Fabrication Gallery - large
        1: (4, 6),    # Precision Machining - large
        2: (3, 5),    # Composite Cell - medium
        3: (3, 5),    # Coating Studio - medium
        4: (4, 6),    # Assembly Hall - large
        5: (2, 3),    # Calibration Lab - small specialized
        6: (3, 4),    # Systems Assembly - medium
        7: (2, 3),    # Metrology Loft - small specialized
        8: (2, 3),    # Tooling Annex - small specialized
    }

    for zero_index in range(config.shop_count):
        index = zero_index + 1
        blueprint_index = zero_index % len(SHOP_BLUEPRINTS)
        blueprint_cycle = zero_index // len(SHOP_BLUEPRINTS)
        name, capabilities = SHOP_BLUEPRINTS[blueprint_index]
        display_name = name if blueprint_cycle == 0 else f"{name} Extension {blueprint_cycle + 1}"
        shop_id = f"SHOP-{index:02d}"
        configured_min = config.min_workcenters_per_shop
        configured_max = config.max_workcenters_per_shop

        blueprint_min, blueprint_max = shop_size_factors.get(blueprint_index, (3, 4))

        min_count = max(configured_min, min(blueprint_min, configured_max))
        max_count = min(configured_max, max(blueprint_max, min_count))

        count = rng.randint(min_count, max_count)
        workcenter_ids: list[str] = []
        for wc_index in range(1, count + 1):
            wc_id = f"WC-{index:02d}-{wc_index:03d}"
            # Give every workcenter a primary capability, then sprinkle in
            # secondary capabilities to create routing alternatives.
            primary_cap = capabilities[(wc_index - 1) % len(capabilities)]
            extra_caps = rng.sample(capabilities, k=rng.randint(0, min(2, len(capabilities) - 1)))
            wc_caps = sorted(set([primary_cap] + extra_caps))
            suffix = primary_cap.replace("_", " ").title()
            workcenters[wc_id] = WorkCenter(
                id=wc_id,
                shop_id=shop_id,
                name=f"{suffix} Workcenter {wc_index:03d}",
                capabilities=wc_caps,
                efficiency=round(rng.uniform(0.85, 1.2), 2),
            )
            workcenter_ids.append(wc_id)
        shop_capabilities = sorted(
            {
                capability
                for workcenter_id in workcenter_ids
                for capability in workcenters[workcenter_id].capabilities
            }
        )
        shops[shop_id] = Shop(
            id=shop_id,
            name=display_name,
            capabilities=shop_capabilities,
            workcenter_ids=workcenter_ids,
        )
    _ensure_capability_coverage(config, rng, shops, workcenters)
    _refresh_shop_capabilities(shops, workcenters)
    return shops, workcenters


def _generate_pieces_and_jobs(
    config: GameConfig,
    rng: random.Random,
    shops: dict[str, Shop],
    workcenters: dict[str, WorkCenter],
) -> tuple[dict[str, PuzzlePiece], dict[str, Job]]:
    """Create top-level jobs and their dependency-linked subjob chains."""
    pieces: dict[str, PuzzlePiece] = {}
    jobs: dict[str, Job] = {}
    shop_ids = list(shops.keys())
    for piece_index in range(1, config.piece_count + 1):
        piece_id = f"PIECE-{piece_index:02d}"
        max_piece_shop_count = min(5, len(shop_ids))
        min_piece_shop_count = min(2, max_piece_shop_count)
        piece_shop_count = rng.randint(min_piece_shop_count, max_piece_shop_count)
        if rng.random() < 0.32:
            piece_shop_count = min_piece_shop_count
        piece_shops = rng.sample(shop_ids, k=piece_shop_count)
        dominant_shop = rng.choice(piece_shops)
        job_count = rng.randint(config.min_jobs_per_piece, config.max_jobs_per_piece)
        piece_job_ids: list[str] = []
        previous_job_ids: list[str] = []
        previous_shop_id: str | None = None
        for job_index in range(1, job_count + 1):
            # Top-level jobs usually cluster around a dominant shop, but occasional
            # cross-shop work creates transport delays and scheduling tradeoffs.
            shop_id = dominant_shop if rng.random() < 0.45 else rng.choice(piece_shops)
            shop = shops[shop_id]
            capability = rng.choice(shop.capabilities)
            candidate_ids = _candidate_workcenters(capability, shop_id, workcenters, rng, config)
            job_id = f"JOB-{piece_index:02d}-{job_index:03d}"
            dependencies: list[str] = []
            if previous_job_ids:
                # Each piece is mostly linear, with occasional extra links to
                # make the critical path more interesting than a simple chain.
                dependencies.append(previous_job_ids[-1])
                if len(previous_job_ids) > 2 and rng.random() < 0.25:
                    dependencies.append(rng.choice(previous_job_ids[:-1]))
            base_duration = rng.randint(config.min_job_duration_shifts, config.max_job_duration_shifts)
            setup = rng.choice(config.setup_time_choices)
            transport = (
                1
                if previous_shop_id
                and previous_shop_id != shop_id
                and rng.random() < config.transport_delay_probability
                else 0
            )
            due_shift = min(
                config.deadline_shift - 4,
                4 + int((job_index / job_count) * (config.deadline_shift - 8)) + rng.randint(-2, 3),
            )
            duration = base_duration + setup + transport
            job = Job(
                id=job_id,
                piece_id=piece_id,
                shop_id=shop_id,
                required_capability=capability,
                candidate_workcenter_ids=candidate_ids,
                assigned_workcenter_id=None,
                base_duration_shifts=base_duration,
                remaining_duration_shifts=duration,
                setup_time_shifts=setup,
                transport_delay_shifts=transport,
                dependency_ids=dependencies,
                status=JobStatus.NOT_READY,
                priority=rng.randint(35, 75),
                due_shift=max(2, due_shift),
                risk_score=float(rng.randint(8, 30)),
                original_duration_shifts=duration,
            )
            jobs[job_id] = job
            for dep_id in dependencies:
                jobs[dep_id].dependent_job_ids.append(job_id)
            previous_job_ids.append(job_id)
            piece_job_ids.append(job_id)
            previous_shop_id = shop_id
        base_piece_name = PIECE_NAMES[(piece_index - 1) % len(PIECE_NAMES)]
        piece_name_cycle = (piece_index - 1) // len(PIECE_NAMES)
        piece_name = base_piece_name if piece_name_cycle == 0 else f"{base_piece_name} {piece_name_cycle + 1}"
        pieces[piece_id] = PuzzlePiece(
            id=piece_id,
            name=f"Job {piece_index:02d} - {piece_name}",
            job_ids=piece_job_ids,
            total_job_count=len(piece_job_ids),
        )
    return pieces, jobs


def _candidate_workcenters(
    capability: str,
    primary_shop_id: str,
    workcenters: dict[str, WorkCenter],
    rng: random.Random,
    config: GameConfig,
) -> list[str]:
    """Return primary and alternate workcenters that can perform a capability."""
    primary = [wc.id for wc in workcenters.values() if wc.shop_id == primary_shop_id and capability in wc.capabilities]
    alternates = [wc.id for wc in workcenters.values() if wc.shop_id != primary_shop_id and capability in wc.capabilities]
    rng.shuffle(primary)
    rng.shuffle(alternates)
    candidate_ids: list[str] = []
    target_count = min(config.max_candidate_workcenters_per_job, max(config.min_candidate_workcenters_per_job, len(primary)))
    if primary:
        primary_count = min(len(primary), target_count)
        candidate_ids.extend(primary[:primary_count])
    needed = max(0, config.min_candidate_workcenters_per_job - len(candidate_ids))
    alternate_limit = min(config.max_alternate_workcenters_per_job, len(alternates))
    if alternate_limit:
        alternate_count = rng.randint(min(needed, alternate_limit), alternate_limit)
        candidate_ids.extend(alternates[:alternate_count])
    if not candidate_ids:
        candidate_ids = [wc.id for wc in workcenters.values() if capability in wc.capabilities]
    if not candidate_ids:
        candidate_ids = [wc.id for wc in workcenters.values() if wc.shop_id == primary_shop_id]
    if not candidate_ids:
        candidate_ids = list(workcenters.keys())
    return candidate_ids[: config.max_candidate_workcenters_per_job]


def _ensure_capability_coverage(
    config: GameConfig,
    rng: random.Random,
    shops: dict[str, Shop],
    workcenters: dict[str, WorkCenter],
) -> None:
    """Make generated capacity broad enough for larger scenarios to stay playable."""
    target_count = min(config.min_capable_workcenters_per_capability, len(workcenters))
    if target_count <= 1:
        return
    all_capabilities = sorted(
        {
            capability
            for zero_index in range(config.shop_count)
            for capability in SHOP_BLUEPRINTS[zero_index % len(SHOP_BLUEPRINTS)][1]
        }
    )
    for capability in all_capabilities:
        capable = [wc for wc in workcenters.values() if capability in wc.capabilities]
        if len(capable) >= target_count:
            continue
        candidates = [
            wc
            for wc in workcenters.values()
            if capability not in wc.capabilities
        ]
        rng.shuffle(candidates)
        candidates.sort(key=lambda wc: (_capability_affinity(capability, wc), len(wc.capabilities), wc.id))
        for wc in candidates[: max(0, target_count - len(capable))]:
            wc.capabilities = sorted(set(wc.capabilities + [capability]))
            capable.append(wc)


def _capability_affinity(capability: str, workcenter: WorkCenter) -> int:
    """Return a low score when a workcenter is a plausible alternate for a capability."""
    related = {
        "fixture": {"tooling", "fitting", "alignment"},
        "tooling": {"fixture", "forming", "fitting"},
        "certification": {"inspection", "metrology", "calibration"},
        "inspection": {"certification", "metrology", "calibration"},
        "systems_fit": {"assembly", "wiring", "calibration"},
        "wiring": {"systems_fit", "assembly", "calibration"},
        "curing": {"bonding", "coating", "layup"},
        "bonding": {"curing", "layup", "forming"},
        "alignment": {"metrology", "fixture", "fitting"},
    }
    if capability in workcenter.capabilities:
        return 0
    if related.get(capability, set()) & set(workcenter.capabilities):
        return 1
    return 2


def _refresh_shop_capabilities(
    shops: dict[str, Shop],
    workcenters: dict[str, WorkCenter],
) -> None:
    """Refresh shop capability rollups after coverage adjustments."""
    for shop in shops.values():
        shop.capabilities = sorted(
            {
                capability
                for workcenter_id in shop.workcenter_ids
                for capability in workcenters[workcenter_id].capabilities
            }
        )


def _assert_acyclic(jobs: dict[str, Job]) -> None:
    """Raise if generated job dependencies contain a cycle."""
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(job_id: str) -> None:
        if job_id in visited:
            return
        if job_id in visiting:
            raise ValueError("Generated dependency graph contains a cycle.")
        visiting.add(job_id)
        for dep_id in jobs[job_id].dependency_ids:
            visit(dep_id)
        visiting.remove(job_id)
        visited.add(job_id)

    for job_id in jobs:
        visit(job_id)
