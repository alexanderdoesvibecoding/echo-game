"""Final player-versus-ECHO explanation."""

from __future__ import annotations

from typing import Any


class ReviewMixin:
    def _final_review_payload(self) -> dict[str, Any]:
        player_day = self.player_state.completion_day or self.player_state.current_day
        echo_day = self.automated_state.completion_day or self.automated_state.current_day
        player_records = [
            record for record in self.player_state.decision_history if record.actor == "player"
        ]
        preplanned_records = [
            record for record in player_records if record.day < self.config.max_campaign_day
        ]
        overtime_records = [
            record for record in player_records if record.day >= self.config.max_campaign_day
        ]
        preplanned_aligned = sum(
            1 for record in preplanned_records if record.aligned_with_echo
        )
        aligned = sum(1 for record in player_records if record.aligned_with_echo)
        echo_records = [
            record for record in self.automated_state.decision_history if record.actor == "ECHO"
        ]
        identical_optimal_path = (
            not overtime_records
            and preplanned_aligned == len(preplanned_records) == len(echo_records)
        )
        player_score = round(self.player_state.decision_score, 2)
        echo_score = round(self.automated_state.decision_score, 2)

        if identical_optimal_path:
            headline = "You reproduced ECHO's exact optimal path, so the run is tied."
            outcome = "tied"
        elif player_day > echo_day:
            headline = f"ECHO finished all 20 jobs {player_day - echo_day} day(s) earlier."
            outcome = "behind"
        elif player_day == echo_day and player_score < echo_score:
            headline = "You matched ECHO's completion day, but ECHO achieved the higher score."
            outcome = "behind"
        elif player_day == echo_day and player_score == echo_score:
            headline = "ECHO won the stable path tiebreak after your route diverged."
            outcome = "behind"
        else:
            raise RuntimeError("A player route surpassed the globally solved ECHO route.")

        reasons = [
            f"You completed the project on day {player_day}; ECHO completed it on day {echo_day}.",
            f"You chose ECHO's preferred response on {aligned} of {len(player_records)} questions.",
            f"Your decision score was {self.player_state.decision_score:.0f}; ECHO's was {self.automated_state.decision_score:.0f}.",
        ]
        return {
            "outcome": outcome,
            "headline": headline,
            "reasons": reasons,
        }
