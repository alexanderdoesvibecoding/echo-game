"""Job status used by the jobs-only simulation."""

from enum import Enum


class JobStatus(str, Enum):
    """Enumerate the only lifecycle states a job may occupy."""
    IN_PROGRESS = "In Progress"
    COMPLETE = "Complete"
