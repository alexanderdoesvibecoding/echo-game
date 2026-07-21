from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from echo_adventure.api.session import GameSession


def finish_campaign(session: GameSession, first_choice_id: str | None = None) -> dict:
    first = True
    guard = 0
    while not session.player_state.final_item_completed:
        guard += 1
        assert guard < 250
        assert len(session.current_cards) == 1
        card = session.current_cards[0]
        choice_id = first_choice_id if first and first_choice_id else card.echo_choice_id
        session.apply_choice(card.id, choice_id)
        first = False
        if session.ready_to_advance():
            session.advance_day()
    return session.state_payload()["finalReveal"]


def run_full_campaign_case(seed: int, diverge: bool) -> dict[str, object]:
    """Run one real default campaign inside a process-pool worker."""
    session = GameSession(seed=seed)
    assert len(session.scenario.jobs) == 20
    assert all(5 <= job.initial_duration_days <= 15 for job in session.scenario.jobs.values())
    assert session.decision_web.optimal_completion_day < session.config.max_campaign_day
    assert all(2 <= count <= 4 for count in session.decision_web.question_counts.values())

    divergent_choice: str | None = None
    if diverge:
        first_card = session.current_cards[0]
        divergent_choice = next(
            choice.id for choice in first_card.choices if choice.id != first_card.echo_choice_id
        )
    final = finish_campaign(session, first_choice_id=divergent_choice)

    decisions_by_day = Counter(record.day for record in session.player_state.decision_history)
    assert all(
        decisions_by_day[day] == session.decision_web.question_count(day)
        for day in decisions_by_day
        if day < min(
            session.player_state.completion_day or session.config.max_campaign_day,
            session.config.max_campaign_day,
        )
    )
    return {
        "outcome": final["review"]["outcome"],
        "headline": final["review"]["headline"],
        "divergent_choices": sum(
            not record.aligned_with_echo
            for record in session.player_state.decision_history
        ),
        "player_day": session.player_state.completion_day,
        "echo_day": session.automated_state.completion_day,
        "player_score": session.player_state.decision_score,
        "echo_score": session.automated_state.decision_score,
        "optimal_day": session.decision_web.optimal_completion_day,
        "player_completed": len(session.player_state.completed_jobs),
        "echo_completed": len(session.automated_state.completed_jobs),
        "player_in_overtime": session.player_in_overtime,
        "all_aligned": all(record.aligned_with_echo for record in session.player_state.decision_history),
    }


def test_full_default_campaigns_run_exact_and_divergent_paths_in_parallel() -> None:
    with ProcessPoolExecutor(max_workers=2) as executor:
        exact_future = executor.submit(run_full_campaign_case, 12345, False)
        divergent_future = executor.submit(run_full_campaign_case, 24680, True)
        exact = exact_future.result(timeout=180)
        divergent = divergent_future.result(timeout=180)

    assert exact["outcome"] == "tied"
    assert exact["player_in_overtime"] is False
    assert exact["player_day"] == exact["echo_day"] == exact["optimal_day"]
    assert exact["player_score"] == exact["echo_score"]
    assert exact["player_completed"] == exact["echo_completed"] == 20
    assert exact["all_aligned"] is True

    assert divergent["outcome"] == "behind"
    assert divergent["divergent_choices"] >= 1
    assert divergent["player_completed"] == divergent["echo_completed"] == 20
    assert (
        divergent["player_day"] > divergent["echo_day"]
        or divergent["player_score"] < divergent["echo_score"]
        or divergent["headline"] == "ECHO won the stable path tiebreak after your route diverged."
    )
