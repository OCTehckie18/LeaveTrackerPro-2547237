"""The approval state machine (PRD section 5.3). A pure function: no DB, no HTTP, no clock.

    transition(state, actor, action, expected_version=..., comment=..., new_document_count=...)
        -> TransitionResult     (what the service must persist)
        -> raises DomainError   (NotFound / Forbidden / StaleVersion / InvalidTransition / ...)

Order of checks matters: relation first (so strangers learn nothing: 404), then version (a stale
click gets "just updated", not "invalid"), then state, then comment/document rules.
"""

from dataclasses import dataclass
from uuid import UUID

from app.domain.errors import (
    DocumentRequired,
    Forbidden,
    InvalidTransition,
    NotFound,
    StaleVersion,
    ValidationFailed,
)
from app.domain.types import (
    OPEN_STATUSES,
    PENDING_STATUSES,
    Action,
    Role,
    Route,
    Stage,
    Status,
)
from app.domain.validation import validate_comment

APPROVER_ACTIONS = frozenset({Action.APPROVE, Action.REJECT, Action.REQUEST_INFO})
_NEEDS_COMMENT = frozenset({Action.REJECT, Action.REQUEST_INFO})


@dataclass(frozen=True)
class Actor:
    id: UUID
    role: Role


@dataclass(frozen=True)
class RequestState:
    """Everything the state machine needs to know about a request and its approval chain."""

    employee_id: UUID
    status: Status
    resume_status: Status | None
    route: Route
    is_extended: bool
    version: int
    manager_id: UUID | None  # the employee's direct manager (for a manager's own leave: the HOD)
    hod_id: UUID | None  # the manager's manager; None for HOD_ONLY requests
    document_count: int


@dataclass(frozen=True)
class TransitionResult:
    action: Action
    stage: Stage
    from_status: Status
    to_status: Status
    resume_status: Status | None
    comment: str | None


def route_for(*, is_extended: bool, employee_role: Role) -> Route:
    """Approval route, fixed at submit. HODs have nobody above them, so they cannot apply."""
    if employee_role is Role.HOD:
        raise ValidationFailed(
            {
                "fromDate": "Heads of Department can't submit leave here: there is no approver above you."
            }
        )
    if employee_role is Role.MANAGER:
        return Route.HOD_ONLY
    return Route.MANAGER_THEN_HOD if is_extended else Route.MANAGER_ONLY


def initial_status(route: Route) -> Status:
    return Status.PENDING_HOD if route is Route.HOD_ONLY else Status.PENDING_MANAGER


def approver_for(state: RequestState, status: Status) -> UUID | None:
    """Who must act while the request is in `status`."""
    if status is Status.PENDING_MANAGER:
        return state.manager_id
    if status is Status.PENDING_HOD:
        return state.hod_id if state.route is Route.MANAGER_THEN_HOD else state.manager_id
    return None


def _stage_for(status: Status) -> Stage:
    return Stage.MANAGER if status is Status.PENDING_MANAGER else Stage.HOD


def _waiting_for(status: Status) -> str:
    return "the Manager" if status is Status.PENDING_MANAGER else "the HOD"


def transition(
    state: RequestState,
    actor: Actor,
    action: Action,
    *,
    expected_version: int,
    comment: str | None = None,
    new_document_count: int = 0,
) -> TransitionResult:
    if action in APPROVER_ACTIONS:
        return _approver_action(state, actor, action, expected_version, comment)
    if action in (Action.RESPOND, Action.CANCEL):
        return _owner_action(state, actor, action, expected_version, comment, new_document_count)
    raise InvalidTransition("That action isn't available for this request.")


def _check_version(state: RequestState, expected_version: int) -> None:
    if state.version != expected_version:
        raise StaleVersion("This request was just updated by someone else. Please refresh.")


def _approver_action(
    state: RequestState, actor: Actor, action: Action, expected_version: int, comment: str | None
) -> TransitionResult:
    if actor.id == state.employee_id:
        raise Forbidden("You can't decide on your own leave request.")  # self-approval
    if actor.id not in {state.manager_id, state.hod_id}:
        raise NotFound("We couldn't find that leave request.")  # 404: no enumeration
    _check_version(state, expected_version)

    if state.status not in PENDING_STATUSES:
        raise InvalidTransition(
            f"This request is already {state.status.value.replace('_', ' ').lower()}."
        )
    required_role = Role.MANAGER if state.status is Status.PENDING_MANAGER else Role.HOD
    if actor.id != approver_for(state, state.status) or actor.role is not required_role:
        raise InvalidTransition(
            f"It isn't your turn: this request is waiting for {_waiting_for(state.status)}."
        )

    clean_comment = validate_comment(comment, required=action in _NEEDS_COMMENT)
    stage = _stage_for(state.status)

    if action is Action.REJECT:
        return TransitionResult(action, stage, state.status, Status.REJECTED, None, clean_comment)
    if action is Action.REQUEST_INFO:
        return TransitionResult(
            action, stage, state.status, Status.NEEDS_INFO, state.status, clean_comment
        )

    # APPROVE
    if state.is_extended and state.document_count == 0:  # defence in depth (PRD rule 5)
        raise DocumentRequired(
            "Leave over 3 days needs at least one supporting document before it can be approved."
        )
    if state.status is Status.PENDING_MANAGER and state.route is Route.MANAGER_THEN_HOD:
        to_status = Status.PENDING_HOD  # first of two approvals: NOT final
    else:
        to_status = Status.APPROVED
    return TransitionResult(action, stage, state.status, to_status, None, clean_comment)


def _owner_action(
    state: RequestState,
    actor: Actor,
    action: Action,
    expected_version: int,
    comment: str | None,
    new_document_count: int,
) -> TransitionResult:
    if actor.id != state.employee_id:
        raise NotFound("We couldn't find that leave request.")
    _check_version(state, expected_version)

    if action is Action.CANCEL:
        if state.status not in OPEN_STATUSES:
            raise InvalidTransition("Only requests that are still open can be cancelled.")
        clean = validate_comment(comment, required=False)
        return TransitionResult(action, Stage.EMPLOYEE, state.status, Status.CANCELLED, None, clean)

    # RESPOND
    if state.status is not Status.NEEDS_INFO or state.resume_status is None:
        raise InvalidTransition("There's no information request waiting for your reply.")
    clean = validate_comment(comment, required=False)
    if clean is None and new_document_count == 0:
        raise ValidationFailed({"comment": "Add a reply or attach a document."})
    return TransitionResult(
        action, Stage.EMPLOYEE, Status.NEEDS_INFO, state.resume_status, None, clean
    )
