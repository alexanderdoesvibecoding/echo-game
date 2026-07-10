"""Parameterized manufacturing decision effect engine."""

from __future__ import annotations

import hashlib

from ..enums import JobStatus, ResourceKind, ResourceStatus, WorkCenterStatus
from ..metrics import update_state_metrics
from ..models import (
    DecisionCard,
    DecisionChoice,
    DecisionEffect,
    DecisionRecord,
    Job,
    SharedResource,
    SimulationState,
)
from .graph import apply_campaign_choice
from .scoring import select_echo_choice


def apply_choice(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    actor: str = "player",
    echo_choice: DecisionChoice | None = None,
) -> str:
    """Apply card-level and selected effects through the same deterministic path."""
    if echo_choice is None:
        echo_choice = select_echo_choice(card, state.decision_cards)

    if card.id not in state.activated_decision_card_ids:
        _apply_effects(state, card, choice, card.unavoidable_effects, namespace="card")
        state.activated_decision_card_ids.add(card.id)
    _apply_effects(state, card, choice, choice.effects, namespace="choice")
    apply_campaign_choice(state, card, choice)

    note = "Response recorded; the affected schedule and shop constraints were updated."
    state.daily_notes.append(f"{card.title}: {note}")
    state.decision_history.append(
        DecisionRecord(
            day=state.current_day,
            card_id=card.id,
            card_title=card.title,
            actor=actor,
            choice_id=choice.id,
            choice_label=choice.label,
            echo_choice_id=echo_choice.id if echo_choice else None,
            echo_choice_label=echo_choice.label if echo_choice else None,
            aligned_with_echo=bool(echo_choice and echo_choice.id == choice.id),
            note=note,
        )
    )
    update_state_metrics(state)
    return note


def _apply_effects(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    effects: list[DecisionEffect],
    namespace: str,
) -> None:
    for index, effect in enumerate(effects):
        key = f"{namespace}:{index}:{effect.kind}"
        probability = float(effect.params.get("probability", 1.0))
        if probability < 1.0 and _stable_fraction(state, card, choice, key) >= probability:
            continue
        _apply_effect(state, card, choice, effect, key)


def _apply_effect(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    effect: DecisionEffect,
    key: str,
) -> None:
    params = effect.params
    selector = str(params.get("selector", "target"))
    count = _resolved_value(state, card, choice, key, params.get("count", 1), suffix="count")
    shifts = _resolved_value(state, card, choice, key, params.get("shifts", 0), suffix="shifts")
    jobs = _select_jobs(state, card, selector, count)

    if effect.kind in {"delay", "rework"}:
        _change_job_duration(state, jobs, shifts, increase=True, total=params.get("mode") == "total")
        if effect.kind == "rework":
            for job in jobs:
                job.rework_count += 1
                if not job.block_reason:
                    job.status = JobStatus.REWORK_REQUIRED
    elif effect.kind in {"recover", "open_capacity"}:
        _change_job_duration(state, jobs, shifts, increase=False, total=params.get("mode") == "total", component=params.get("component"))
        if effect.kind == "open_capacity":
            for resource in _select_resources(state, card, params.get("kind")):
                resource.available_capacity = min(resource.capacity + 1, resource.available_capacity + 1)
    elif effect.kind == "block":
        for job in jobs:
            _block_job(state, job, shifts, "manufacturing constraint")
    elif effect.kind == "release":
        for job in jobs:
            _release_job(state, job)
    elif effect.kind == "hold":
        for job in jobs:
            job.acceptance_hold = True
            job.acceptance_hold_until = max(job.acceptance_hold_until, state.current_shift + max(1, shifts))
            if job.document_id and job.document_id in state.documents:
                document = state.documents[job.document_id]
                if job.id not in document.held_job_ids:
                    document.held_job_ids.append(job.id)
    elif effect.kind == "downtime":
        workcenters = _select_workcenters(state, card, selector, count)
        reason = str(params.get("status", "blocked"))
        for wc in workcenters:
            wc.decision_downtime_until = max(wc.decision_downtime_until, state.current_shift + max(1, shifts))
            wc.decision_downtime_reason = reason
            wc.blocked_reason = f"Decision: {reason}"
            wc.status = WorkCenterStatus.WEATHER_IMPACTED if reason == "weather" else WorkCenterStatus.DOWN if reason == "down" else WorkCenterStatus.BLOCKED
            if wc.current_job_id and wc.current_job_id in state.jobs:
                state.jobs[wc.current_job_id].status = JobStatus.PAUSED
    elif effect.kind == "reroute":
        for job in jobs:
            _reroute_job(state, job, prefer_original=bool(params.get("prefer_original")))
    elif effect.kind in {"queue_front", "queue_back"}:
        for job in jobs:
            _queue_job(state, job, front=effect.kind == "queue_front")
    elif effect.kind == "risk":
        delta = int(params.get("delta", 0))
        for job in jobs:
            job.risk_score = max(0.0, min(100.0, job.risk_score + delta))
    elif effect.kind == "priority":
        delta = int(params.get("delta", 0))
        for job in jobs:
            job.priority = max(1, min(100, job.priority + delta))
    elif effect.kind == "reschedule":
        state.reschedule_count += max(0, int(params.get("count", 1)))
    elif effect.kind == "resource":
        _apply_resource_effect(state, card, jobs, params, shifts)
    elif effect.kind in {"material", "material_transfer", "verify"}:
        _apply_material_effect(state, card, jobs, effect.kind, params)
    elif effect.kind in {"document", "approve"}:
        _apply_document_effect(state, card, jobs, effect.kind, params, shifts)
    elif effect.kind == "inspection":
        _apply_inspection_effect(state, card, jobs, str(params.get("action", "review")))
    elif effect.kind in {"worker_unavailable", "replace_worker", "worker_load", "worker", "qualify"}:
        _apply_worker_effect(state, card, jobs, effect.kind, params, shifts)
    elif effect.kind in {"batch", "nest"}:
        _group_jobs_on_route(state, jobs)


def _change_job_duration(
    state: SimulationState,
    jobs: list[Job],
    shifts: int,
    *,
    increase: bool,
    total: bool,
    component: object = None,
) -> None:
    if shifts <= 0 or not jobs:
        return
    allocations: list[tuple[Job, int]] = []
    if total:
        remaining = shifts
        index = 0
        while remaining > 0 and jobs:
            allocations.append((jobs[index % len(jobs)], 1))
            remaining -= 1
            index += 1
    else:
        allocations = [(job, shifts) for job in jobs]
    for job, amount in allocations:
        if job.is_complete:
            continue
        if increase:
            if not job.started_once:
                if component == "setup":
                    job.setup_time_shifts += amount
                else:
                    job.base_duration_shifts += amount
            job.remaining_duration_shifts += amount
            continue
        _recover_job_duration(state, job, amount, component)


def _recover_job_duration(state: SimulationState, job: Job, amount: int, component: object) -> None:
    if job.started_once:
        job.remaining_duration_shifts = max(0, job.remaining_duration_shifts - amount)
        if job.remaining_duration_shifts == 0 and not job.acceptance_hold:
            from ..simulation import complete_job

            complete_job(state, job.id)
        return
    remaining = amount
    if component == "setup" or job.setup_time_shifts:
        used = min(job.setup_time_shifts, remaining)
        job.setup_time_shifts -= used
        remaining -= used
    if remaining:
        used = min(job.transport_delay_shifts, remaining)
        job.transport_delay_shifts -= used
        remaining -= used
    if remaining:
        job.base_duration_shifts = max(0, job.base_duration_shifts - remaining)
    job.remaining_duration_shifts = max(0, job.remaining_duration_shifts - amount)


def _block_job(state: SimulationState, job: Job, shifts: int, reason: str) -> None:
    if job.is_complete:
        return
    duration = max(1, shifts)
    job.decision_blocked_until = max(job.decision_blocked_until, state.current_shift + duration)
    job.decision_block_reason = reason
    job.block_reason = f"Decision: {reason}"
    job.status = JobStatus.BLOCKED
    state.blocked_jobs.add(job.id)
    state.remove_job_from_queues(job.id)
    for wc in state.workcenters.values():
        if wc.current_job_id == job.id:
            wc.current_job_id = None
            if not wc.is_disrupted:
                wc.status = WorkCenterStatus.AVAILABLE


def _release_job(state: SimulationState, job: Job) -> None:
    if job.is_complete:
        return
    prior_status = job.status
    job.decision_blocked_until = 0
    job.decision_block_reason = None
    job.acceptance_hold = False
    job.acceptance_hold_until = 0
    if job.block_reason and job.block_reason.startswith("Decision:"):
        job.block_reason = None
    state.blocked_jobs.discard(job.id)
    if job.document_id and job.document_id in state.documents:
        document = state.documents[job.document_id]
        document.held_job_ids = [job_id for job_id in document.held_job_ids if job_id != job.id]
    if job.remaining_duration_shifts <= 0:
        from ..simulation import complete_job

        complete_job(state, job.id)
    elif prior_status not in {JobStatus.RUNNING, JobStatus.QUEUED, JobStatus.REWORK_REQUIRED}:
        job.status = JobStatus.READY if state.is_dependency_complete(job.id) else JobStatus.NOT_READY


def _reroute_job(state: SimulationState, job: Job, prefer_original: bool = False) -> None:
    if job.is_complete:
        return
    candidates = [
        state.workcenters[wc_id]
        for wc_id in job.candidate_workcenter_ids
        if wc_id in state.workcenters
        and job.required_capability in state.workcenters[wc_id].capabilities
        and not state.workcenters[wc_id].is_disrupted
    ]
    if not candidates:
        return
    if prefer_original:
        target = candidates[0]
    else:
        alternatives = [wc for wc in candidates if wc.id != job.assigned_workcenter_id]
        target = min(alternatives or candidates, key=lambda wc: (wc.load, -wc.efficiency, wc.id))
    if state.assign_job(job.id, target.id, front=job.critical_path):
        state.reschedule_count += 1


def _queue_job(state: SimulationState, job: Job, front: bool) -> None:
    if job.is_complete or job.block_reason:
        return
    wc_id = job.assigned_workcenter_id or (job.candidate_workcenter_ids[0] if job.candidate_workcenter_ids else None)
    if wc_id and wc_id in state.workcenters:
        state.assign_job(job.id, wc_id, front=front)
        if not front:
            wc = state.workcenters[wc_id]
            wc.queue = [job_id for job_id in wc.queue if job_id != job.id] + [job.id]


def _apply_resource_effect(
    state: SimulationState,
    card: DecisionCard,
    jobs: list[Job],
    params: dict[str, object],
    shifts: int,
) -> None:
    action = str(params.get("action", "reserve"))
    kind = params.get("kind")
    if action == "reserve_worker":
        for job in jobs:
            if job.worker_id and job.worker_id in state.workers:
                state.workers[job.worker_id].assigned_job_id = job.id
        return
    resources = _select_resources(state, card, kind)
    if action in {"temporary_fixture", "temporary_rack"}:
        source = resources[0] if resources else next(iter(state.shared_resources.values()), None)
        if source:
            new_id = f"{source.id}-TEMP-{len(state.shared_resources) + 1:03d}"
            new_kind = ResourceKind.FIXTURE if action == "temporary_fixture" else ResourceKind.RACK
            state.shared_resources[new_id] = SharedResource(
                id=new_id,
                name=f"Temporary {new_kind.value}",
                kind=new_kind,
                shop_id=jobs[0].shop_id if jobs else source.shop_id,
                capabilities=list(source.capabilities),
                certified=False if new_kind == ResourceKind.FIXTURE else True,
                condition="temporary",
            )
        return
    for resource in resources:
        if action in {"unavailable", "hold", "needs_review"}:
            resource.status = ResourceStatus.NEEDS_REVIEW if action == "needs_review" else ResourceStatus.UNAVAILABLE if action == "unavailable" else ResourceStatus.HELD
            resource.unavailable_until = max(resource.unavailable_until, state.current_shift + max(1, shifts or 1))
            resource.condition = action
        elif action in {"open", "service", "calibrate"}:
            resource.status = ResourceStatus.AVAILABLE
            resource.unavailable_until = 0
            resource.available_capacity = resource.capacity
            resource.condition = "ready"
            if action == "calibrate":
                resource.calibrated = True
        elif action in {"certify", "certify_limited"}:
            resource.certified = True
            resource.status = ResourceStatus.AVAILABLE
            if action == "certify":
                resource.capacity += 1
                resource.available_capacity += 1
        elif action == "borrow":
            resource.status = ResourceStatus.RESERVED
            resource.condition = "borrowed"
        elif action == "reserve":
            resource.status = ResourceStatus.RESERVED
            for job in jobs:
                if job.id not in resource.holder_job_ids:
                    resource.holder_job_ids.append(job.id)


def _apply_material_effect(
    state: SimulationState,
    card: DecisionCard,
    jobs: list[Job],
    effect_kind: str,
    params: dict[str, object],
) -> None:
    stocks = _select_materials(state, card, jobs)
    if not stocks:
        return
    target = stocks[0]
    quantity = max(1, int(params.get("quantity", 1)))
    action = str(params.get("action", "verify"))
    if effect_kind == "verify":
        target.verified = True
        target.quantity = max(target.quantity, quantity)
    elif effect_kind == "material_transfer":
        donors = [stock for stock in state.material_stocks.values() if stock.id != target.id and stock.quantity > quantity]
        if donors:
            donor = max(donors, key=lambda stock: (stock.quantity, stock.id))
            donor.quantity -= quantity
            target.quantity += quantity
            target.donor_material_id = donor.id
    elif action == "consume":
        target.quantity = max(0, target.quantity - quantity)
    elif action == "unverified":
        target.verified = False


def _apply_document_effect(
    state: SimulationState,
    card: DecisionCard,
    jobs: list[Job],
    effect_kind: str,
    params: dict[str, object],
    shifts: int,
) -> None:
    documents = _select_documents(state, card, jobs)
    action = str(params.get("action", "approve"))
    for document in documents:
        if effect_kind == "approve":
            document.available = True
            document.approved = True
            document.held_job_ids.clear()
            continue
        if action == "offline":
            document.available = False
            document.unavailable_until = max(document.unavailable_until, state.current_shift + max(1, shifts or 2))
        elif action == "use_stale":
            document.available = True
            document.approved = True
            document.revision = max(0, document.revision - 1)
        elif action in {"publish_setup", "publish_setup_limited", "publish_program", "publish_program_limited", "publish_method", "publish_method_limited"}:
            document.available = True
            document.approved = True
            document.reusable = True
            document.revision += 1
            document.kind = action.replace("publish_", "")
        elif action == "manual_label":
            document.kind = "controlled manual label"
            document.available = True
            document.approved = True
        elif action in {"audit_flag", "deviation"}:
            document.kind = f"{document.kind} ({action.replace('_', ' ')})"


def _apply_inspection_effect(
    state: SimulationState,
    card: DecisionCard,
    jobs: list[Job],
    action: str,
) -> None:
    method_ids = {target_id for target_id in card.target_ids if target_id in state.inspection_methods}
    method_ids.update(job.inspection_method_id for job in jobs if job.inspection_method_id)
    for method_id in method_ids:
        method = state.inspection_methods.get(method_id)
        if not method:
            continue
        if action == "drift":
            method.calibrated = False
            method.accepted = False
            method.drift_level += 2
            method.quarantined_job_ids = [job.id for job in jobs]
        elif action in {"recalibrate", "cross_check", "formal_study", "standardize", "standardize_limited", "handoff_check", "reinspect_all", "reinspect_limited", "reopen_all", "reopen_limited", "release_all"}:
            method.calibrated = True
            method.accepted = True
            method.drift_level = 0
            if action in {"release_all", "reinspect_all", "reopen_all", "standardize"}:
                method.quarantined_job_ids.clear()


def _apply_worker_effect(
    state: SimulationState,
    card: DecisionCard,
    jobs: list[Job],
    effect_kind: str,
    params: dict[str, object],
    shifts: int,
) -> None:
    workers = [state.workers[target_id] for target_id in card.target_ids if target_id in state.workers]
    if not workers and jobs:
        workers = [state.workers[job.worker_id] for job in jobs if job.worker_id in state.workers]
    if effect_kind == "worker_unavailable":
        for worker in workers:
            worker.available = False
            worker.unavailable_until = max(worker.unavailable_until, state.current_shift + max(1, shifts))
        for job in jobs:
            _block_job(state, job, max(1, shifts), "assigned worker unavailable")
    elif effect_kind == "replace_worker":
        for job in jobs:
            replacements = [
                worker for worker in state.workers.values()
                if worker.available and job.required_capability in worker.skills and worker.id != job.worker_id
            ]
            if replacements:
                replacement = min(replacements, key=lambda worker: (worker.support_load, worker.fatigue, worker.id))
                job.worker_id = replacement.id
                replacement.assigned_job_id = job.id
                replacement.support_load += 1 if params.get("paired") else 0
                _release_job(state, job)
    elif effect_kind == "worker_load":
        amount = max(1, int(params.get("amount", 1)))
        for worker in workers:
            worker.fatigue += amount
            worker.support_load += amount
    elif effect_kind == "qualify":
        for worker in workers:
            worker.available = True
            for job in jobs:
                if job.family not in worker.qualified_families:
                    worker.qualified_families.append(job.family)
                if job.required_capability not in worker.skills:
                    worker.skills.append(job.required_capability)
    elif effect_kind == "worker" and params.get("action") == "relief":
        for worker in workers:
            worker.fatigue = 0
            worker.support_load = 0


def _group_jobs_on_route(state: SimulationState, jobs: list[Job]) -> None:
    if not jobs:
        return
    lead = jobs[0]
    wc_id = lead.assigned_workcenter_id or (lead.candidate_workcenter_ids[0] if lead.candidate_workcenter_ids else None)
    if not wc_id:
        return
    for job in jobs:
        if wc_id in job.candidate_workcenter_ids:
            state.assign_job(job.id, wc_id, front=False)


def _select_jobs(state: SimulationState, card: DecisionCard, selector: str, count: int) -> list[Job]:
    incomplete = [job for job in state.jobs.values() if not job.is_complete]
    targets = [state.jobs[target_id] for target_id in card.target_ids if target_id in state.jobs and not state.jobs[target_id].is_complete]
    anchor = targets[0] if targets else (min(incomplete, key=lambda job: (job.due_shift, job.id)) if incomplete else None)
    if not anchor:
        return []
    family = anchor.family
    shop_id = anchor.shop_id
    selected = targets
    if selector in {"family", "ready_family", "critical_family", "family_documents"}:
        selected = [job for job in incomplete if job.family == family]
        if selector == "ready_family":
            selected = [job for job in selected if state.is_dependency_complete(job.id)]
        elif selector == "critical_family":
            selected = [job for job in selected if job.critical_path] or selected
    elif selector == "held_documents":
        selected = [
            job for job in incomplete
            if job.document_id in state.documents and job.id in state.documents[job.document_id].held_job_ids
        ]
    elif selector == "due_documents":
        selected = sorted(incomplete, key=lambda job: (job.due_shift, -job.priority, job.id))
    elif selector in {"shop", "ready_shop", "controlled"}:
        selected = [job for job in incomplete if job.shop_id == shop_id]
        if selector == "ready_shop":
            selected = [job for job in selected if state.is_dependency_complete(job.id)]
        elif selector == "controlled":
            selected = [job for job in selected if job.area_id == anchor.area_id]
    elif selector in {"critical", "near_due"}:
        selected = [job for job in incomplete if job.critical_path] or incomplete
    elif selector in {"low_priority", "low_risk"}:
        selected = sorted(incomplete, key=lambda job: (job.priority if selector == "low_priority" else job.risk_score, job.due_shift, job.id))
    elif selector == "short":
        selected = sorted(incomplete, key=lambda job: (job.remaining_duration_shifts, job.due_shift, job.id))
    elif selector in {"ready", "parallel", "open_area", "verified_material"}:
        selected = [job for job in incomplete if state.is_dependency_complete(job.id) and not job.block_reason]
        if selector == "open_area":
            selected = [job for job in selected if job.area_id != anchor.area_id]
        if selector == "verified_material":
            selected = [job for job in selected if job.material_id in state.material_stocks and state.material_stocks[job.material_id].verified]
    elif selector == "all_active":
        selected = [job for job in incomplete if job.status in {JobStatus.RUNNING, JobStatus.QUEUED, JobStatus.READY}]
    elif selector in {"receiving", "donor", "donor_shop", "other_family", "next_shift"}:
        selected = [job for job in incomplete if job.id != anchor.id]
        if selector == "donor_shop":
            selected = [job for job in selected if job.shop_id != shop_id]
        elif selector == "other_family":
            selected = [job for job in selected if job.family != family]
    elif selector == "dependent":
        selected = [state.jobs[job_id] for job_id in anchor.dependent_job_ids if job_id in state.jobs and not state.jobs[job_id].is_complete]
    elif selector == "handoff":
        selected = [job for job in incomplete if job.transport_delay_shifts or job.dependency_ids]
    elif selector == "precision":
        selected = [job for job in incomplete if job.required_capability in {"finishing", "inspection", "metrology", "calibration", "alignment"}]
    elif selector in {"inspection", "tool_dependent"}:
        caps = {"inspection", "metrology", "calibration", "certification"} if selector == "inspection" else {"tooling", "fixture", "fitting", "alignment", "forming"}
        selected = [job for job in incomplete if job.required_capability in caps]
    elif selector == "near_complete":
        selected = sorted(incomplete, key=lambda job: (job.remaining_duration_shifts, job.due_shift, job.id))
    selected = selected or targets or incomplete
    selected = sorted(dict.fromkeys(job.id for job in selected))
    jobs_by_id = state.jobs
    result = [jobs_by_id[job_id] for job_id in selected]
    if selector in {"critical", "near_due", "critical_family"}:
        result.sort(key=lambda job: (not job.critical_path, job.due_shift, -job.priority, job.id))
    elif selector in {"low_priority", "donor", "donor_shop"}:
        result.sort(key=lambda job: (job.priority, job.risk_score, job.id))
    else:
        result.sort(key=lambda job: (job.due_shift, -job.priority, job.id))
    return result[: max(0, count)] if count > 0 else result


def _select_workcenters(state: SimulationState, card: DecisionCard, selector: str, count: int):
    if selector == "all_active_workcenters":
        selected = [wc for wc in state.workcenters.values() if wc.current_job_id or wc.queue]
        return sorted(selected, key=lambda wc: wc.id)[:count]
    targeted = [state.workcenters[target_id] for target_id in card.target_ids if target_id in state.workcenters]
    if targeted:
        if len(targeted) < count:
            shop_ids = {wc.shop_id for wc in targeted}
            extras = [
                wc for wc in state.workcenters.values()
                if wc.shop_id in shop_ids and wc.id not in {item.id for item in targeted}
            ]
            targeted.extend(sorted(extras, key=lambda wc: wc.id)[: count - len(targeted)])
        return targeted[:count]
    jobs = _select_jobs(state, card, "target", max(1, count))
    wc_ids: list[str] = []
    for job in jobs:
        wc_id = job.assigned_workcenter_id or (job.candidate_workcenter_ids[0] if job.candidate_workcenter_ids else None)
        if wc_id and wc_id in state.workcenters and wc_id not in wc_ids:
            wc_ids.append(wc_id)
    return [state.workcenters[wc_id] for wc_id in wc_ids[:count]]


def _select_resources(state: SimulationState, card: DecisionCard, kind_value: object):
    targeted = [state.shared_resources[target_id] for target_id in card.target_ids if target_id in state.shared_resources]
    kind_text = str(kind_value or "").lower()
    if kind_text:
        matching = [resource for resource in state.shared_resources.values() if resource.kind.value == kind_text or resource.kind.name.lower().replace("_", " ") == kind_text]
        targeted = [resource for resource in targeted if resource in matching] or matching
    return sorted(targeted, key=lambda resource: resource.id)


def _select_materials(state: SimulationState, card: DecisionCard, jobs: list[Job]):
    ids = [target_id for target_id in card.target_ids if target_id in state.material_stocks]
    ids.extend(job.material_id for job in jobs if job.material_id in state.material_stocks)
    return [state.material_stocks[material_id] for material_id in dict.fromkeys(ids)]


def _select_documents(state: SimulationState, card: DecisionCard, jobs: list[Job]):
    ids = [target_id for target_id in card.target_ids if target_id in state.documents]
    ids.extend(job.document_id for job in jobs if job.document_id in state.documents)
    return [state.documents[document_id] for document_id in dict.fromkeys(ids)]


def _resolved_value(
    state: SimulationState,
    card: DecisionCard,
    choice: DecisionChoice,
    key: str,
    value: object,
    *,
    suffix: str,
) -> int:
    if isinstance(value, (tuple, list)) and value:
        low = int(value[0])
        high = int(value[-1])
        if high < low:
            low, high = high, low
        span = high - low + 1
        return low + _stable_int(state, card, choice, f"{key}:{suffix}") % span
    return int(value or 0)


def _stable_fraction(state: SimulationState, card: DecisionCard, choice: DecisionChoice, key: str) -> float:
    return _stable_int(state, card, choice, key) / float(2**256 - 1)


def _stable_int(state: SimulationState, card: DecisionCard, choice: DecisionChoice, key: str) -> int:
    material = f"{state.seed}|{state.scenario_id}|{card.id}|{choice.id}|{key}"
    return int(hashlib.sha256(material.encode("utf-8")).hexdigest(), 16)
