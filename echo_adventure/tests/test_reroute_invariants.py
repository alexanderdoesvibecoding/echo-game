from echo_adventure.enums import EventType, JobStatus, TargetType, WorkCenterStatus
from echo_adventure.events import resolve_event
from echo_adventure.models import Event, Job, PuzzlePiece, Shop, SimulationState, WorkCenter
from echo_adventure.simulation import complete_job
from echo_adventure.ui.server import GameSession


def make_state():
    shop = Shop(
        id="SHOP-1",
        name="Shop 1",
        capabilities=["weld"],
        workcenter_ids=["WC-1", "WC-2"],
    )
    wc1 = WorkCenter(
        id="WC-1",
        shop_id="SHOP-1",
        name="WC 1",
        capabilities=["weld"],
        efficiency=1.0,
    )
    wc2 = WorkCenter(
        id="WC-2",
        shop_id="SHOP-1",
        name="WC 2",
        capabilities=["weld"],
        efficiency=1.0,
    )
    piece = PuzzlePiece(
        id="PIECE-1",
        name="Piece 1",
        job_ids=["JOB-1"],
        total_job_count=1,
    )
    job = Job(
        id="JOB-1",
        piece_id="PIECE-1",
        shop_id="SHOP-1",
        required_capability="weld",
        candidate_workcenter_ids=["WC-1", "WC-2"],
        assigned_workcenter_id="WC-1",
        base_duration_shifts=2,
        remaining_duration_shifts=2,
        setup_time_shifts=0,
        transport_delay_shifts=0,
        dependency_ids=[],
        status=JobStatus.PAUSED,
        started_once=True,
    )

    return SimulationState(
        scenario_id="test",
        seed=1,
        deadline_shift=10,
        shifts_per_day=3,
        shops={shop.id: shop},
        workcenters={wc1.id: wc1, wc2.id: wc2},
        pieces={piece.id: piece},
        jobs={job.id: job},
        event_timeline=[],
    )


def assert_job_has_single_location(state, job_id):
    current_locations = [
        wc.id
        for wc in state.workcenters.values()
        if wc.current_job_id == job_id
    ]
    queued_locations = [
        wc.id
        for wc in state.workcenters.values()
        if job_id in wc.queue
    ]

    assert len(current_locations) + len(queued_locations) <= 1, (
        current_locations,
        queued_locations,
    )


def make_completion_rework_state(current_shift):
    shop = Shop(
        id="SHOP-1",
        name="Shop 1",
        capabilities=["weld"],
        workcenter_ids=["WC-1"],
    )
    wc = WorkCenter(
        id="WC-1",
        shop_id="SHOP-1",
        name="WC 1",
        capabilities=["weld"],
        efficiency=1.0,
        current_job_id="JOB-01-001",
    )
    piece = PuzzlePiece(
        id="PIECE-01",
        name="Job 01 - Aster",
        job_ids=["JOB-01-001"],
        total_job_count=1,
    )
    job = Job(
        id="JOB-01-001",
        piece_id="PIECE-01",
        shop_id="SHOP-1",
        required_capability="weld",
        candidate_workcenter_ids=["WC-1"],
        assigned_workcenter_id="WC-1",
        base_duration_shifts=1,
        remaining_duration_shifts=0,
        setup_time_shifts=0,
        transport_delay_shifts=0,
        dependency_ids=[],
        status=JobStatus.RUNNING,
        started_once=True,
        planned_completion_rework_shifts=2,
    )
    return SimulationState(
        scenario_id="rework-test",
        seed=1,
        deadline_shift=12,
        shifts_per_day=3,
        shops={shop.id: shop},
        workcenters={wc.id: wc},
        pieces={piece.id: piece},
        jobs={job.id: job},
        event_timeline=[],
        current_shift=current_shift,
    )


def test_rerouting_paused_job_clears_old_disrupted_current_slot():
    state = make_state()

    wc1 = state.workcenters["WC-1"]
    wc1.status = WorkCenterStatus.WEATHER_IMPACTED
    wc1.current_job_id = "JOB-1"
    wc1.downtime_remaining = 3
    wc1.blocked_reason = "EVT-1: Weather event"

    assert state.assign_job("JOB-1", "WC-2", front=True)

    assert state.jobs["JOB-1"].assigned_workcenter_id == "WC-2"
    assert state.jobs["JOB-1"].status == JobStatus.QUEUED

    assert state.workcenters["WC-1"].current_job_id is None
    assert state.workcenters["WC-1"].status == WorkCenterStatus.WEATHER_IMPACTED
    assert state.workcenters["WC-1"].blocked_reason == "EVT-1: Weather event"

    assert state.workcenters["WC-2"].queue == ["JOB-1"]

    assert_job_has_single_location(state, "JOB-1")


def test_resolving_old_event_does_not_resume_job_rerouted_elsewhere():
    state = make_state()

    old_event = Event(
        id="EVT-1",
        type=EventType.WEATHER,
        target_type=TargetType.SHOP,
        target_id="SHOP-1",
        start_shift=0,
        duration_shifts=3,
        severity=2,
        has_advance_warning=False,
        warning_shift=None,
        description="Weather",
        effects={"workcenter_ids": ["WC-1"]},
        started=True,
    )

    state.event_timeline = [old_event]
    state.active_events = [old_event.id]

    wc1 = state.workcenters["WC-1"]
    wc1.status = WorkCenterStatus.WEATHER_IMPACTED
    wc1.current_job_id = "JOB-1"
    wc1.downtime_remaining = 3
    wc1.blocked_reason = "EVT-1: Weather event"

    assert state.assign_job("JOB-1", "WC-2", front=True)
    resolve_event(state, old_event)

    assert state.workcenters["WC-1"].current_job_id is None
    assert state.workcenters["WC-1"].status == WorkCenterStatus.AVAILABLE

    assert state.jobs["JOB-1"].status == JobStatus.QUEUED
    assert state.workcenters["WC-2"].queue == ["JOB-1"]

    assert_job_has_single_location(state, "JOB-1")


def test_resolving_one_event_keeps_overlapping_disruption_active():
    state = make_state()

    evt1 = Event(
        id="EVT-1",
        type=EventType.WEATHER,
        target_type=TargetType.SHOP,
        target_id="SHOP-1",
        start_shift=0,
        duration_shifts=2,
        severity=2,
        has_advance_warning=False,
        warning_shift=None,
        description="Weather",
        effects={"workcenter_ids": ["WC-1"]},
        started=True,
    )
    evt2 = Event(
        id="EVT-2",
        type=EventType.FACILITY_OUTAGE,
        target_type=TargetType.SHOP,
        target_id="SHOP-1",
        start_shift=1,
        duration_shifts=5,
        severity=3,
        has_advance_warning=False,
        warning_shift=None,
        description="Facility outage",
        effects={"workcenter_ids": ["WC-1"]},
        started=True,
    )

    state.current_shift = 2
    state.event_timeline = [evt1, evt2]
    state.active_events = [evt1.id, evt2.id]

    wc1 = state.workcenters["WC-1"]
    wc1.status = WorkCenterStatus.BLOCKED
    wc1.downtime_remaining = 4
    wc1.blocked_reason = "EVT-2: Facility outage"

    resolve_event(state, evt1)

    assert state.workcenters["WC-1"].status == WorkCenterStatus.BLOCKED
    assert state.workcenters["WC-1"].blocked_reason == "EVT-2: Facility outage"
    assert state.workcenters["WC-1"].downtime_remaining == 4


def test_completion_rework_is_same_for_same_job_at_different_shifts():
    early_state = make_completion_rework_state(current_shift=2)
    later_state = make_completion_rework_state(current_shift=9)

    complete_job(early_state, "JOB-01-001")
    complete_job(later_state, "JOB-01-001")

    early_job = early_state.jobs["JOB-01-001"]
    later_job = later_state.jobs["JOB-01-001"]

    assert early_job.status == JobStatus.REWORK_REQUIRED
    assert later_job.status == JobStatus.REWORK_REQUIRED
    assert early_job.remaining_duration_shifts == later_job.remaining_duration_shifts
    assert "JOB-01-001" not in early_state.completed_jobs
    assert "JOB-01-001" not in later_state.completed_jobs


def test_finish_automated_does_not_force_incomplete_benchmark_to_win():
    session = GameSession(seed=1, demo=True)
    session.automated_state.current_shift = session.automated_state.deadline_shift
    session.automated_state.final_item_completed = False
    session.automated_state.completion_shift = None
    session.automated_state.completed_jobs.clear()
    for piece in session.automated_state.pieces.values():
        piece.completed = False
        piece.completed_job_count = 0
    for job in session.automated_state.jobs.values():
        job.status = JobStatus.NOT_READY
        job.completed_shift = None

    session._finish_automated()

    assert not session.automated_state.final_item_completed
    assert session.automated_state.completion_shift is None
    assert not session.automated_state.completed_jobs
