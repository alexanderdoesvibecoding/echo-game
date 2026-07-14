"""Statuses used by the jobs-only simulation."""

from enum import Enum


class JobStatus(str, Enum):
    IN_PROGRESS = "In Progress"
    COMPLETE = "Complete"


class DecisionType(str, Enum):
    DELAY = "Schedule delay"
    OPPORTUNITY = "Schedule opportunity"
    NEUTRAL = "Schedule tradeoff"
