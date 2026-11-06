"""Enumerations shared by the domain, models and API. Values are the strings stored in Postgres."""

from enum import StrEnum


class Role(StrEnum):
    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"
    HOD = "HOD"


class Status(StrEnum):
    PENDING_MANAGER = "PENDING_MANAGER"
    PENDING_HOD = "PENDING_HOD"
    NEEDS_INFO = "NEEDS_INFO"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class Action(StrEnum):
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_INFO = "REQUEST_INFO"
    RESPOND = "RESPOND"
    CANCEL = "CANCEL"


class Stage(StrEnum):
    MANAGER = "MANAGER"
    HOD = "HOD"
    EMPLOYEE = "EMPLOYEE"


class Route(StrEnum):
    """Who must approve. Fixed at submit time (ARCHITECTURE section 7)."""

    MANAGER_ONLY = "MANAGER_ONLY"  # standard leave
    MANAGER_THEN_HOD = "MANAGER_THEN_HOD"  # extended leave (> 3 consecutive days)
    HOD_ONLY = "HOD_ONLY"  # a manager's own leave


class LeaveType(StrEnum):
    ANNUAL = "ANNUAL"
    SICK = "SICK"
    CASUAL = "CASUAL"
    OTHER = "OTHER"


PENDING_STATUSES = frozenset({Status.PENDING_MANAGER, Status.PENDING_HOD})
# Requests that block the dates (overlap) and join a consecutive-day chain.
ACTIVE_STATUSES = frozenset(
    {Status.PENDING_MANAGER, Status.PENDING_HOD, Status.NEEDS_INFO, Status.APPROVED}
)
# Requests the employee can still cancel / that are not final.
OPEN_STATUSES = frozenset({Status.PENDING_MANAGER, Status.PENDING_HOD, Status.NEEDS_INFO})
