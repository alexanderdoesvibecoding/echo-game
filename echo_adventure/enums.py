"""Job status used by the jobs-only simulation."""

from enum import Enum


class JobStatus(str, Enum):
    IN_PROGRESS = "In Progress"
    COMPLETE = "Complete"
