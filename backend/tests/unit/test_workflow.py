"""W1-W15: the approval state machine, including the extended-leave (Manager -> HOD) rule."""

import random
from dataclasses import replace
from uuid import uuid4

import pytest

from app.domain.errors import (
    DocumentRequired,
    Forbidden,
    InvalidTransition,
    NotFound,
    StaleVersion,
    ValidationFailed,
)
from app.domain.types import Action, Role, Route, Stage, Status
from app.domain.workflow import (
    Actor,
    RequestState,
    initial_status,
    route_for,
    transition,
)

EMP, MGR, HOD, OTHER_MGR, OTHER_EMP = (uuid4() for _ in range(5))

employee = Actor(EMP, Role.EMPLOYEE)
manager = Actor(MGR, Role.MANAGER)
hod = Actor(HOD, Role.HOD)
other_manager = Actor(OTHER_MGR, Role.MANAGER)
other_employee = Actor(OTHER_EMP, Role.EMPLOYEE)


def state(**kw: object) -> RequestState:
    base = RequestState(
        employee_id=EMP,
        status=Status.PENDING_MANAGER,
        resume_status=None,
        route=Route.MANAGER_ONLY,
        is_extended=False,
        version=1,
        manager_id=MGR,
        hod_id=HOD,
        document_count=0,
    )
    return replace(base, **kw)  # type: ignore[arg-type]


def extended(**kw: object) -> RequestState:
    return state(route=Route.MANAGER_THEN_HOD, is_extended=True, document_count=1, **kw)


def go(s: RequestState, actor: Actor, action: Action, **kw: object):  # type: ignore[no-untyped-def]
    return transition(s, actor, action, expected_version=kw.pop("version", s.version), **kw)  # type: ignore[arg-type]


# --- happy paths ---------------------------------------------------------------------------------
def test_w1_standard_manager_approve_is_final() -> None:
    r = go(state(), manager, Action.APPROVE, comment="Enjoy")
    assert (r.to_status, r.stage, r.comment) == (Status.APPROVED, Stage.MANAGER, "Enjoy")


def test_w2_extended_manager_approve_goes_to_hod_not_final() -> None:
    r = go(extended(), manager, Action.APPROVE)
    assert r.to_status is Status.PENDING_HOD


def test_w3_hod_final_approval() -> None:
    r = go(extended(status=Status.PENDING_HOD), hod, Action.APPROVE)
    assert (r.to_status, r.stage) == (Status.APPROVED, Stage.HOD)


# --- wrong turn / no skipping --------------------------------------------------------------------
def test_w4_manager_cannot_act_in_hod_stage() -> None:
    with pytest.raises(InvalidTransition, match="HOD"):
        go(extended(status=Status.PENDING_HOD), manager, Action.APPROVE)


def test_w5_hod_cannot_skip_the_manager_stage() -> None:
    with pytest.raises(InvalidTransition, match="Manager"):
        go(extended(), hod, Action.APPROVE)


# --- reject / comments ---------------------------------------------------------------------------
def test_w6_reject_needs_comment_and_is_final() -> None:
    with pytest.raises(ValidationFailed):
        go(state(), manager, Action.REJECT)
    with pytest.raises(ValidationFailed):
        go(state(), manager, Action.REJECT, comment="no")
    r = go(state(), manager, Action.REJECT, comment="Team is short-staffed")
    assert r.to_status is Status.REJECTED


def test_reject_at_hod_stage() -> None:
    r = go(extended(status=Status.PENDING_HOD), hod, Action.REJECT, comment="Dates clash")
    assert (r.to_status, r.stage) == (Status.REJECTED, Stage.HOD)


# --- request-info loop ---------------------------------------------------------------------------
def test_w7_info_loop_returns_to_manager_stage() -> None:
    ask = go(state(), manager, Action.REQUEST_INFO, comment="Please attach a certificate")
    assert (ask.to_status, ask.resume_status) == (Status.NEEDS_INFO, Status.PENDING_MANAGER)
    waiting = state(status=Status.NEEDS_INFO, resume_status=Status.PENDING_MANAGER)
    back = go(waiting, employee, Action.RESPOND, comment="Attached")
    assert (back.to_status, back.resume_status, back.stage) == (
        Status.PENDING_MANAGER,
        None,
        Stage.EMPLOYEE,
    )


def test_w8_info_loop_at_hod_returns_to_hod_not_manager() -> None:
    s = extended(status=Status.PENDING_HOD)
    ask = go(s, hod, Action.REQUEST_INFO, comment="Need the discharge summary")
    assert ask.resume_status is Status.PENDING_HOD
    waiting = extended(status=Status.NEEDS_INFO, resume_status=Status.PENDING_HOD)
    assert (
        go(waiting, employee, Action.RESPOND, new_document_count=1).to_status is Status.PENDING_HOD
    )


def test_respond_needs_text_or_document() -> None:
    waiting = state(status=Status.NEEDS_INFO, resume_status=Status.PENDING_MANAGER)
    with pytest.raises(ValidationFailed):
        go(waiting, employee, Action.RESPOND)
    assert go(waiting, employee, Action.RESPOND, new_document_count=1)


def test_w15_respond_when_not_needs_info() -> None:
    with pytest.raises(InvalidTransition):
        go(state(), employee, Action.RESPOND, comment="hello")


# --- authorisation -------------------------------------------------------------------------------
def test_w9_self_approval_is_forbidden() -> None:
    own = state(
        employee_id=MGR,
        manager_id=HOD,
        hod_id=None,
        route=Route.HOD_ONLY,
        status=Status.PENDING_HOD,
    )
    with pytest.raises(Forbidden):
        go(own, manager, Action.APPROVE)


def test_w10_unrelated_manager_gets_not_found() -> None:
    with pytest.raises(NotFound):
        go(state(), other_manager, Action.APPROVE)
    with pytest.raises(NotFound):
        go(state(), other_employee, Action.CANCEL)
    with pytest.raises(NotFound):
        go(state(), other_employee, Action.APPROVE)


def test_employee_cannot_approve_own_or_decide() -> None:
    with pytest.raises(Forbidden):
        go(state(), employee, Action.APPROVE)


def test_manager_own_leave_goes_to_hod_only() -> None:
    assert route_for(is_extended=False, employee_role=Role.MANAGER) is Route.HOD_ONLY
    assert route_for(is_extended=True, employee_role=Role.MANAGER) is Route.HOD_ONLY
    assert initial_status(Route.HOD_ONLY) is Status.PENDING_HOD
    own = state(
        employee_id=MGR,
        manager_id=HOD,
        hod_id=None,
        route=Route.HOD_ONLY,
        status=Status.PENDING_HOD,
    )
    assert go(own, hod, Action.APPROVE).to_status is Status.APPROVED


def test_route_selection_for_employees_and_hod() -> None:
    assert route_for(is_extended=False, employee_role=Role.EMPLOYEE) is Route.MANAGER_ONLY
    assert route_for(is_extended=True, employee_role=Role.EMPLOYEE) is Route.MANAGER_THEN_HOD
    with pytest.raises(ValidationFailed):
        route_for(is_extended=False, employee_role=Role.HOD)


# --- documents -----------------------------------------------------------------------------------
def test_w11_extended_without_documents_cannot_be_approved() -> None:
    s = state(route=Route.MANAGER_THEN_HOD, is_extended=True, document_count=0)
    with pytest.raises(DocumentRequired):
        go(s, manager, Action.APPROVE)
    with pytest.raises(DocumentRequired):
        go(replace(s, status=Status.PENDING_HOD), hod, Action.APPROVE)
    # rejecting or asking for info does not need documents
    assert go(s, manager, Action.REQUEST_INFO, comment="Please add documents")


# --- terminal states, versions, cancel -----------------------------------------------------------
@pytest.mark.parametrize("final", [Status.APPROVED, Status.REJECTED, Status.CANCELLED])
def test_w12_nothing_works_on_a_final_request(final: Status) -> None:
    s = state(status=final)
    for actor, action in [
        (manager, Action.APPROVE),
        (manager, Action.REJECT),
        (employee, Action.CANCEL),
        (employee, Action.RESPOND),
    ]:
        with pytest.raises(InvalidTransition):
            go(s, actor, action, comment="whatever works")


def test_w13_stale_version() -> None:
    with pytest.raises(StaleVersion, match="just updated"):
        go(state(version=3), manager, Action.APPROVE, version=2)
    with pytest.raises(StaleVersion):
        go(state(version=3), employee, Action.CANCEL, version=1)


@pytest.mark.parametrize(
    "open_state",
    [Status.PENDING_MANAGER, Status.PENDING_HOD],
)
def test_w14_cancel_open_states(open_state: Status) -> None:
    assert go(state(status=open_state), employee, Action.CANCEL).to_status is Status.CANCELLED


def test_w14_cancel_while_needs_info() -> None:
    s = state(status=Status.NEEDS_INFO, resume_status=Status.PENDING_MANAGER)
    assert go(s, employee, Action.CANCEL).to_status is Status.CANCELLED


# --- property test: extended leave is never approved without the HOD ----------------------------
def test_property_extended_leave_never_approved_without_hod_approval() -> None:
    rng = random.Random(1234)
    actors = [employee, manager, hod, other_manager, other_employee]
    actions = list(Action)
    for _ in range(300):
        s = extended()
        hod_approved = False
        for _step in range(12):
            actor, action = rng.choice(actors), rng.choice(actions)
            try:
                r = transition(
                    s,
                    actor,
                    action,
                    expected_version=s.version,
                    comment="a valid comment",
                    new_document_count=rng.choice([0, 1]),
                )
            except Exception:
                continue
            if r.action is Action.APPROVE and r.stage is Stage.HOD:
                hod_approved = True
            s = replace(s, status=r.to_status, resume_status=r.resume_status, version=s.version + 1)
            if s.status is Status.APPROVED:
                assert hod_approved, "extended leave reached APPROVED without a HOD approval"
