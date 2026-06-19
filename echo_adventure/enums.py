from __future__ import annotations

from enum import Enum


class WorkCenterStatus(str, Enum):
    AVAILABLE = "Available"
    BUSY = "Busy"
    DOWN = "Down"
    BLOCKED = "Blocked"
    IDLE = "Idle"
    WAITING_ON_MATERIAL = "Waiting on material"
    WAITING_ON_INSPECTION = "Waiting on inspection"
    WAITING_ON_ENGINEERING = "Waiting on engineering"
    WEATHER_IMPACTED = "Weather impacted"


class JobStatus(str, Enum):
    NOT_READY = "Not Ready"
    READY = "Ready"
    QUEUED = "Queued"
    SCHEDULED = "Scheduled"
    RUNNING = "Running"
    PAUSED = "Paused"
    BLOCKED = "Blocked"
    COMPLETE = "Complete"
    LATE = "Late"
    REWORK_REQUIRED = "Rework Required"
    CANCELLED = "Cancelled / Superseded"


class PieceStatus(str, Enum):
    NOT_STARTED = "Not Started"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    AT_RISK = "At Risk"
    COMPLETE = "Complete"
    READY_FOR_INTEGRATION = "Ready for Integration"
    INTEGRATED = "Integrated"


class EventType(str, Enum):
    MISSING_MATERIAL = "Missing material"
    DELAYED_MATERIAL = "Delayed material"
    MACHINE_DOWN = "Machine or workcenter down"
    QUALITY_REWORK = "Quality rework"
    PRIORITY_CHANGE = "Priority change"
    INSPECTION_DELAY = "Inspection delay"
    ENGINEERING_HOLD = "Engineering hold"
    URGENT_JOB = "Urgent new job inserted"
    WEATHER = "Weather event"
    FACILITY_OUTAGE = "Facility outage"
    SUPPLIER_ESCALATION = "Supplier escalation"
    LOGISTICS_BACKLOG = "Logistics backlog"
    TOOLING_DAMAGE = "Tooling damage"
    CREW_SHORTAGE = "Crew shortage"
    REWORK_SPILLOVER = "Rework spillover"
    CERTIFICATION_AUDIT = "Certification audit"
    ENGINEERING_DATA_REVISION = "Engineering data revision"


class TargetType(str, Enum):
    SHOP = "shop"
    WORKCENTER = "workcenter"
    JOB = "job"
    PIECE = "piece"
    CAPABILITY = "capability"


class DecisionType(str, Enum):
    MACHINE_DOWN = "Machine or workcenter down"
    MISSING_MATERIAL = "Missing or delayed material"
    QUALITY_REWORK = "Quality rework"
    PRIORITY_CHANGE = "Priority change"
    INSPECTION_DELAY = "Inspection delay"
    ENGINEERING_HOLD = "Engineering hold"
    URGENT_JOB = "Urgent new job inserted"
    WEATHER = "Weather or facility outage"
    BOTTLENECK = "Bottleneck overload"
    CRITICAL_PATH = "Critical path slippage"
    IDLE_WORKCENTER = "Workcenter idle despite available work"
    ALTERNATE_ROUTING = "Alternate routing opportunity"
    QUEUE_CONGESTION = "Queue congestion"
    FINAL_INTEGRATION = "Final integration risk"
    STRATEGIC_PRIORITY = "Strategic prioritization"
