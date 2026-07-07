"""Final review and win/loss explanation text for the browser UI."""

from __future__ import annotations

from typing import Any

from ..enums import JobStatus
from ..models import MetricSnapshot, SimulationState


class ReviewMixin:
    """Build final-review explanations from a GameSession."""

    def _final_review_payload(
        self,
        player_snapshot: MetricSnapshot,
        automated_snapshot: MetricSnapshot,
    ) -> dict[str, Any]:
        """Explain the main reasons the player won or lost."""
        player_won = player_snapshot.deadline_met
        echo_won = automated_snapshot.deadline_met

        player_complete_label = (
            self.config.date_label_for_shift(self.player_state.completion_shift)
            if self.player_state.completion_shift
            else "not completed"
        )

        if player_won:
            headline = f"You won: the project finished by the deadline at {player_complete_label}."
            outcome = "won"
        else:
            headline = f"You lost: the project did not finish by the deadline. Final status was {player_complete_label}."
            outcome = "lost"

        reasons: list[str] = []

        if player_won:
            reasons.extend(self._win_reasons(player_snapshot, automated_snapshot))
        else:
            reasons.extend(self._loss_reasons(player_snapshot, automated_snapshot))

        # Always include the benchmark comparison when it is meaningful.
        if echo_won and not player_won:
            reasons.append(
                "ECHO met the deadline while your schedule did not, mainly by protecting critical-path work "
                "and reducing queue pressure earlier."
            )
        elif player_won and not echo_won:
            reasons.append("You beat the benchmark: your schedule met the deadline while ECHO's benchmark run did not.")
        elif player_won and echo_won:
            if self.player_state.completion_shift and self.automated_state.completion_shift:
                delta = self.player_state.completion_shift - self.automated_state.completion_shift
                if delta < 0:
                    reasons.append(f"You finished {abs(delta)} work period(s) earlier than ECHO.")
                elif delta > 0:
                    reasons.append(f"You met the deadline, but ECHO finished {delta} work period(s) earlier.")
                else:
                    reasons.append("You and ECHO finished in the same work period.")

        return {
            "outcome": outcome,
            "headline": headline,
            "reasons": reasons[:8],
        }

    def _loss_reasons(
        self,
        player_snapshot: MetricSnapshot,
        automated_snapshot: MetricSnapshot,
    ) -> list[str]:
        """Build specific reasons for a missed-deadline run."""
        reasons: list[str] = []

        incomplete_jobs = [
            job
            for job in self.player_state.jobs.values()
            if not job.is_complete
        ]
        late_jobs = [
            job
            for job in self.player_state.jobs.values()
            if _job_was_late(self.player_state, job)
        ]
        critical_late = [
            job
            for job in late_jobs
            if job.critical_path
        ]
        blocked_jobs = self.player_state.get_blocked_jobs()
        rework_jobs = [
            job
            for job in self.player_state.jobs.values()
            if job.rework_count > 0 or job.status == JobStatus.REWORK_REQUIRED
        ]

        if incomplete_jobs:
            reasons.append(f"{len(incomplete_jobs)} subjob(s) were still incomplete when the deadline arrived.")

        if critical_late:
            reasons.append(
                f"{len(critical_late)} critical-path subjob(s) were late, "
                "which directly pushed the project finish out."
            )

        if late_jobs:
            reasons.append(f"{len(late_jobs)} total subjob(s) were late by the end of the run.")

        if blocked_jobs:
            reasons.append(f"{len(blocked_jobs)} subjob(s) were still blocked or waiting on dependencies.")

        bottlenecks = self.player_state.get_bottleneck_shops(2)
        if bottlenecks:
            bottleneck_text = ", ".join(shop.name for shop in bottlenecks)
            reasons.append(f"The largest remaining bottleneck pressure was in: {bottleneck_text}.")

        if rework_jobs:
            reasons.append(f"Quality/rework affected {len(rework_jobs)} subjob(s), adding extra schedule pressure.")

        if player_snapshot.schedule_risk >= 70:
            reasons.append(f"End-of-run schedule risk stayed high at {round(player_snapshot.schedule_risk)}/100.")

        if player_snapshot.jobs_late > automated_snapshot.jobs_late:
            delta = player_snapshot.jobs_late - automated_snapshot.jobs_late
            reasons.append(f"Your schedule had {delta} more late subjob(s) than ECHO's benchmark.")

        return reasons or ["The project missed the deadline because remaining work exceeded the available work periods."]

    def _win_reasons(
        self,
        player_snapshot: MetricSnapshot,
        automated_snapshot: MetricSnapshot,
    ) -> list[str]:
        """Build specific reasons for a successful run."""
        reasons: list[str] = []

        if self.player_state.completion_shift:
            margin = self.player_state.deadline_shift - self.player_state.completion_shift
            if margin > 0:
                reasons.append(f"You finished with {margin} work period(s) of deadline margin.")
            else:
                reasons.append("You finished exactly at the deadline.")

        critical_remaining = [
            job
            for job in self.player_state.jobs.values()
            if job.critical_path and not job.is_complete
        ]
        if not critical_remaining:
            reasons.append("All critical-path work was completed before the final review.")

        if player_snapshot.jobs_late == 0:
            reasons.append("No subjobs were late at the end of the run.")
        else:
            reasons.append(
                f"You still had {player_snapshot.jobs_late} late subjob(s), "
                "but recovered enough downstream work to finish."
            )

        bottlenecks = self.player_state.get_bottleneck_shops(2)
        if bottlenecks:
            bottleneck_text = ", ".join(shop.name for shop in bottlenecks)
            reasons.append(f"You finished despite bottleneck pressure in: {bottleneck_text}.")

        if player_snapshot.schedule_risk < automated_snapshot.schedule_risk:
            reasons.append("Your final schedule risk was lower than ECHO's benchmark.")
        elif player_snapshot.schedule_risk < 45:
            reasons.append(f"Final schedule risk was controlled at {round(player_snapshot.schedule_risk)}/100.")

        return reasons or ["You won because all required jobs were completed before the deadline."]


def _job_was_late(state: SimulationState, job) -> bool:
    """Return whether a subjob finished late or is currently past due."""
    if job.is_complete:
        return job.completed_shift is not None and job.completed_shift > job.due_shift
    return job.due_shift < state.current_shift
