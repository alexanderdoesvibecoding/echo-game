from __future__ import annotations

from random import Random
import unittest

from echo_adventure.enums import EventType, JobStatus, TargetType, WorkCenterStatus
from echo_adventure.events import (
    EVENT_SEQUENCE,
    MAX_EVENT_CHAIN_DEPTH,
    _duration_for,
    _target_for,
    apply_event_start,
    insert_unexpected_job,
    resolve_event,
    schedule_follow_on_event,
)

from .helpers import make_event, make_state


class EventGenerationHelperTests(unittest.TestCase):
    def test_duration_for_every_event_type_is_positive_and_capped(self):
        rng = Random(123)

        for event_type in list(EVENT_SEQUENCE) + [EventType.ECHO_RECOMMENDATION]:
            with self.subTest(event_type=event_type):
                duration = _duration_for(event_type, severity=5, rng=rng)
                self.assertGreaterEqual(duration, 1)
                self.assertLessEqual(duration, 8)

    def test_target_for_event_types_chooses_compatible_domain_objects(self):
        state = make_state()
        rng = Random(4)
        jobs = list(state.jobs.values())
        cases = [
            (EventType.MACHINE_DOWN, TargetType.WORKCENTER, set(state.workcenters)),
            (EventType.WEATHER, TargetType.SHOP, set(state.shops)),
            (EventType.ENGINEERING_HOLD, TargetType.PIECE, set(state.pieces)),
            (EventType.URGENT_JOB, TargetType.PIECE, set(state.pieces)),
            (EventType.ECHO_RECOMMENDATION, TargetType.CAPABILITY, {"ECHO"}),
            (EventType.UNEXPECTED_JOB, TargetType.CAPABILITY, {"NEW_JOB"}),
            (EventType.MISSING_MATERIAL, TargetType.JOB, set(state.jobs)),
        ]

        for event_type, expected_target_type, valid_ids in cases:
            with self.subTest(event_type=event_type):
                target_type, target_id = _target_for(
                    event_type,
                    rng,
                    state.shops,
                    state.workcenters,
                    state.pieces,
                    jobs,
                )
                self.assertEqual(target_type, expected_target_type)
                self.assertIn(target_id, valid_ids)


class EventApplicationTests(unittest.TestCase):
    def test_apply_workcenter_event_sets_disrupted_status_and_pauses_running_job(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]
        job.status = JobStatus.RUNNING
        state.workcenters["WC-A1"].current_job_id = job.id
        event = make_event(
            "EVT-DOWN",
            event_type=EventType.MACHINE_DOWN,
            target_type=TargetType.WORKCENTER,
            target_id="WC-A1",
            duration_shifts=4,
        )

        apply_event_start(state, event)

        self.assertIn(event.id, state.active_events)
        self.assertEqual(state.workcenters["WC-A1"].status, WorkCenterStatus.DOWN)
        self.assertEqual(state.workcenters["WC-A1"].downtime_remaining, 4)
        self.assertEqual(job.status, JobStatus.PAUSED)
        self.assertEqual(event.effects["workcenter_ids"], ["WC-A1"])

    def test_resolve_workcenter_event_keeps_overlap_then_restores_running_job(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]
        job.status = JobStatus.RUNNING
        state.workcenters["WC-A1"].current_job_id = job.id
        machine = make_event(
            "EVT-MACHINE",
            event_type=EventType.MACHINE_DOWN,
            target_type=TargetType.WORKCENTER,
            target_id="WC-A1",
            start_shift=1,
            duration_shifts=5,
        )
        weather = make_event(
            "EVT-WEATHER",
            event_type=EventType.WEATHER,
            target_type=TargetType.SHOP,
            target_id="SHOP-A",
            start_shift=2,
            duration_shifts=2,
        )
        state.event_timeline = [machine, weather]
        state.current_shift = 2
        apply_event_start(state, machine)
        apply_event_start(state, weather)

        resolve_event(state, weather)

        self.assertEqual(state.workcenters["WC-A1"].status, WorkCenterStatus.DOWN)
        self.assertIn("EVT-MACHINE", state.workcenters["WC-A1"].blocked_reason)
        self.assertEqual(job.status, JobStatus.PAUSED)

        state.current_shift = 6
        resolve_event(state, machine)

        self.assertEqual(state.workcenters["WC-A1"].status, WorkCenterStatus.BUSY)
        self.assertEqual(job.status, JobStatus.RUNNING)

    def test_quality_rework_extends_incomplete_job(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]
        event = make_event(
            "EVT-REWORK",
            event_type=EventType.QUALITY_REWORK,
            target_type=TargetType.JOB,
            target_id=job.id,
            severity=2,
        )

        apply_event_start(state, event)

        self.assertEqual(job.rework_count, 1)
        self.assertEqual(job.remaining_duration_shifts, 4)
        self.assertEqual(job.status, JobStatus.REWORK_REQUIRED)

    def test_quality_rework_on_completed_job_inserts_follow_on_subjob(self):
        state = make_state()
        job = state.jobs["JOB-01-001"]
        job.status = JobStatus.COMPLETE
        job.completed_shift = 1
        state.completed_jobs.add(job.id)
        before_count = len(state.jobs)
        event = make_event(
            "EVT-REWORK",
            event_type=EventType.QUALITY_REWORK,
            target_type=TargetType.JOB,
            target_id=job.id,
            severity=2,
        )

        apply_event_start(state, event)

        self.assertEqual(len(state.jobs), before_count + 1)
        inserted_id = event.effects["inserted_job_ids"][0]
        self.assertEqual(state.jobs[inserted_id].dependency_ids, [job.id])
        self.assertEqual(state.jobs[inserted_id].rework_count, 1)
        self.assertIn(inserted_id, state.pieces[job.piece_id].job_ids)

    def test_priority_change_and_urgent_job_insert_mutate_piece_work(self):
        state = make_state()
        first = state.jobs["JOB-01-001"]
        old_priority = first.priority
        old_due = first.due_shift
        priority_event = make_event(
            "EVT-PRIO",
            event_type=EventType.PRIORITY_CHANGE,
            target_type=TargetType.PIECE,
            target_id="PIECE-01",
            severity=2,
        )

        apply_event_start(state, priority_event)

        self.assertGreater(first.priority, old_priority)
        self.assertLessEqual(first.due_shift, old_due)
        self.assertIn(first.id, priority_event.effects["priority_job_ids"])
        self.assertEqual(state.reschedule_count, 1)

        urgent_event = make_event(
            "EVT-URGENT",
            event_type=EventType.URGENT_JOB,
            target_type=TargetType.PIECE,
            target_id="PIECE-01",
            severity=3,
        )
        before_jobs = len(state.jobs)

        apply_event_start(state, urgent_event)

        self.assertEqual(len(state.jobs), before_jobs + 1)
        inserted_id = urgent_event.effects["inserted_job_ids"][0]
        self.assertIn(inserted_id, state.pieces["PIECE-01"].job_ids)
        self.assertGreaterEqual(state.jobs[inserted_id].priority, 85)

    def test_unexpected_job_insertion_is_idempotent_and_can_be_reprioritized(self):
        state = make_state()
        event = make_event(
            "EVT-NEW",
            event_type=EventType.UNEXPECTED_JOB,
            target_type=TargetType.CAPABILITY,
            target_id="NEW_JOB",
            severity=3,
        )

        piece_id = insert_unexpected_job(state, event, prioritize=False)
        original_job_ids = list(event.effects["inserted_job_ids"])
        first_priority = state.jobs[original_job_ids[0]].priority
        repeated_piece_id = insert_unexpected_job(state, event, prioritize=True)

        self.assertEqual(repeated_piece_id, piece_id)
        self.assertEqual(event.effects["inserted_job_ids"], original_job_ids)
        self.assertEqual(event.effects["priority_mode"], "prioritized")
        self.assertGreater(state.jobs[original_job_ids[0]].priority, first_priority)
        self.assertEqual(state.jobs[original_job_ids[0]].status, JobStatus.QUEUED)

    def test_schedule_follow_on_event_respects_depth_deadline_and_sorts(self):
        state = make_state()
        state.current_shift = 2
        state.event_timeline = [make_event("EVT-EXISTING", start_shift=9)]
        source = make_event(
            "EVT-SOURCE",
            start_shift=1,
            duration_shifts=2,
            chain_depth=1,
        )

        follow_on = schedule_follow_on_event(
            state,
            source,
            EventType.LOGISTICS_BACKLOG,
            TargetType.SHOP,
            "SHOP-A",
            delay_shifts=2,
            severity=9,
        )

        self.assertIsNotNone(follow_on)
        assert follow_on is not None
        self.assertEqual(follow_on.parent_event_id, source.id)
        self.assertEqual(follow_on.chain_depth, 2)
        self.assertEqual(follow_on.severity, 5)
        self.assertIn(follow_on.id, source.effects["follow_on_event_ids"])
        self.assertEqual([event.id for event in state.event_timeline], [follow_on.id, "EVT-EXISTING"])

        too_deep = make_event("EVT-DEEP", chain_depth=MAX_EVENT_CHAIN_DEPTH)
        self.assertIsNone(
            schedule_follow_on_event(
                state,
                too_deep,
                EventType.LOGISTICS_BACKLOG,
                TargetType.SHOP,
                "SHOP-A",
                delay_shifts=1,
                severity=3,
            )
        )

        state.current_shift = state.deadline_shift - 1
        near_deadline = make_event("EVT-LATE", start_shift=10, duration_shifts=1)
        self.assertIsNone(
            schedule_follow_on_event(
                state,
                near_deadline,
                EventType.LOGISTICS_BACKLOG,
                TargetType.SHOP,
                "SHOP-A",
                delay_shifts=2,
                severity=3,
            )
        )


if __name__ == "__main__":
    unittest.main()
