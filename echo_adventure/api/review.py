"""Final player-versus-ECHO explanation."""

from __future__ import annotations

from typing import Any


class ReviewMixin:
    def _final_review_payload(self) -> dict[str, Any]:
        player_day = self.player_state.completion_day or self.player_state.current_day
        echo_day = self.automated_state.completion_day or self.automated_state.current_day
        delta = player_day - echo_day
        if delta < 0:
            headline = f"You finished all 20 jobs {abs(delta)} day(s) earlier than ECHO."
            outcome = "ahead"
        elif delta > 0:
            headline = f"ECHO finished all 20 jobs {delta} day(s) earlier."
            outcome = "behind"
        else:
            headline = "You and ECHO finished all 20 jobs on the same day."
            outcome = "tied"

        player_records = [record for record in self.player_state.decision_history if record.actor == "player"]
        aligned = sum(1 for record in player_records if record.aligned_with_echo)
        reasons = [
            f"You completed the project on day {player_day}; ECHO completed it on day {echo_day}.",
            f"You chose ECHO's preferred response on {aligned} of {len(player_records)} questions.",
            f"Your decision score was {self.player_state.decision_score:.0f}; ECHO's was {self.automated_state.decision_score:.0f}.",
        ]
        return {
            "outcome": outcome,
            "headline": headline,
            "reasons": reasons,
            "decisionReview": {
                "totalChoices": len(player_records),
                "alignedChoices": aligned,
                "divergentChoices": len(player_records) - aligned,
            },
        }
