"""U10-U11 and the field rules in PRD 5.2."""

from datetime import date

import pytest

from app.domain.errors import ValidationFailed
from app.domain.validation import (
    check_employee_name,
    validate_comment,
    validate_leave_dates,
    validate_reason,
)

TODAY = date(2026, 11, 6)


def fields(call, *args, **kwargs) -> dict[str, str]:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationFailed) as exc:
        call(*args, **kwargs)
    return exc.value.fields


def test_valid_dates_return_day_count() -> None:
    assert validate_leave_dates(date(2026, 11, 6), date(2026, 11, 10), TODAY) == 5  # today allowed


def test_start_in_the_past() -> None:
    f = fields(validate_leave_dates, date(2026, 11, 5), date(2026, 11, 7), TODAY)
    assert f == {"fromDate": "Start date can't be in the past."}


def test_end_before_start() -> None:
    f = fields(validate_leave_dates, date(2026, 11, 10), date(2026, 11, 9), TODAY)
    assert f == {"toDate": "End date must be on or after the start date."}


def test_exactly_60_days_ok_61_rejected() -> None:
    assert validate_leave_dates(date(2026, 11, 10), date(2027, 1, 8), TODAY) == 60
    f = fields(validate_leave_dates, date(2026, 11, 10), date(2027, 1, 9), TODAY)
    assert "60 days" in f["toDate"]


def test_more_than_12_months_ahead() -> None:
    assert validate_leave_dates(date(2027, 11, 5), date(2027, 11, 6), TODAY) == 2
    f = fields(validate_leave_dates, date(2027, 11, 6), date(2027, 11, 7), TODAY)
    assert "12 months" in f["toDate"]


def test_leap_day_today_horizon_does_not_crash() -> None:
    assert validate_leave_dates(date(2028, 2, 29), date(2028, 3, 1), date(2028, 2, 29)) == 2


def test_reason_is_trimmed_and_bounded() -> None:
    assert validate_reason("   Family vacation   ") == "Family vacation"
    assert "reason" in fields(validate_reason, "short")
    assert "reason" in fields(validate_reason, "x" * 501)
    assert validate_reason("x" * 500) == "x" * 500
    assert "reason" in fields(validate_reason, "          ")  # whitespace only


def test_reason_rejects_control_characters_but_allows_newlines() -> None:
    assert validate_reason("Line one\nLine two is here") == "Line one\nLine two is here"
    assert "reason" in fields(validate_reason, "Hello\x00 world, long enough")
    assert "reason" in fields(validate_reason, "Tab\tseparated reason text")


def test_reason_allows_indic_scripts_with_zero_width_joiners() -> None:
    bengali = "পারিবারিক অনুষ্ঠানে যোগ দিতে‌ হবে"  # contains ZWNJ
    assert validate_reason(bengali) == bengali


@pytest.mark.parametrize("action_required", [True])
def test_comment_required_rules(action_required: bool) -> None:
    assert fields(validate_comment, None, required=action_required) == {
        "comment": "Please tell the employee why."
    }
    assert "comment" in fields(validate_comment, "abcd", required=True)
    assert validate_comment("abcde", required=True) == "abcde"


def test_comment_optional_and_bounded() -> None:
    assert validate_comment(None, required=False) is None
    assert validate_comment("   ", required=False) is None
    assert "1000" in fields(validate_comment, "x" * 1001, required=False)["comment"]


def test_employee_name_must_match_account() -> None:
    check_employee_name(None, "John Doe")
    check_employee_name("  john doe ", "John Doe")
    assert "employeeName" in fields(check_employee_name, "Jane", "John Doe")
