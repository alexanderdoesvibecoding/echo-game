"""Convert raw schedule points into the public 0-100 decision score."""

from __future__ import annotations


NEUTRAL_PUBLIC_SCORE = 50.0
_PUBLIC_SCORE_HALF_RANGE = 50.0
_RAW_POINTS_FOR_HALF_SWING = 10.0


def public_score(raw_score: float) -> float:
    """Map unbounded raw schedule points onto a monotonic 0-100 scale."""
    raw = float(raw_score)
    scaled = NEUTRAL_PUBLIC_SCORE + (
        _PUBLIC_SCORE_HALF_RANGE * raw / (abs(raw) + _RAW_POINTS_FOR_HALF_SWING)
    )
    return round(max(0.0, min(100.0, scaled)), 2)


def public_score_delta(previous_raw_score: float, raw_score: float) -> float:
    """Return the public score change between two raw cumulative scores."""
    previous = _public_score_unrounded(previous_raw_score)
    current = _public_score_unrounded(raw_score)
    return round(current - previous, 2)


def _public_score_unrounded(raw_score: float) -> float:
    raw = float(raw_score)
    scaled = NEUTRAL_PUBLIC_SCORE + (
        _PUBLIC_SCORE_HALF_RANGE * raw / (abs(raw) + _RAW_POINTS_FOR_HALF_SWING)
    )
    return max(0.0, min(100.0, scaled))
