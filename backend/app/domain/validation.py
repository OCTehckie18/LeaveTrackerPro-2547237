"""Business validation with friendly messages (PRD section 5.2). Pure functions, no I/O.

Type/format problems (e.g. "2026-02-30") are caught earlier by the Pydantic schemas; these functions
enforce the *rules*. Each raises ValidationFailed with per-field messages.
"""

import unicodedata
from datetime import date, timedelta

from app.domain.calendar import inclusive_days
from app.domain.errors import ValidationFailed

MAX_DAYS = 60
REASON_MIN, REASON_MAX = 10, 500
COMMENT_MIN_REQUIRED, COMMENT_MAX = 5, 1000

# Rejected: Cc (control, incl. tab), Cs (surrogates), Co (private use), Cn (unassigned).
# Allowed on purpose: Cf (format). Zero-width (non-)joiners are essential in Bengali/Hindi and emoji.
_BAD_CATEGORIES = frozenset({"Cc", "Cs", "Co", "Cn"})


def _add_one_year(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year + 1, day=28)


def clean_text(value: str) -> str | None:
    """NFC-normalise, unify newlines and strip. Returns None if a forbidden character is present."""
    text = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n").strip()
    for ch in text:
        if ch != "\n" and unicodedata.category(ch) in _BAD_CATEGORIES:
            return None
    return text


def validate_leave_dates(from_date: date, to_date: date, today: date) -> int:
    """Return the number of days, or raise ValidationFailed. `today` is in the org time zone."""
    errors: dict[str, str] = {}
    if from_date < today:
        errors["fromDate"] = "Start date can't be in the past."
    if to_date < from_date:
        errors["toDate"] = "End date must be on or after the start date."
    else:
        days = inclusive_days(from_date, to_date)
        if days > MAX_DAYS:
            errors["toDate"] = f"Leave can't exceed {MAX_DAYS} days in one request."
        elif to_date > _add_one_year(today):
            errors["toDate"] = "Leave can't be booked more than 12 months ahead."
    if errors:
        raise ValidationFailed(errors)
    return inclusive_days(from_date, to_date)


def validate_reason(reason: str) -> str:
    text = clean_text(reason)
    if text is None or not (REASON_MIN <= len(text) <= REASON_MAX):
        raise ValidationFailed(
            {"reason": f"Please describe the reason ({REASON_MIN}–{REASON_MAX} characters)."}
        )
    return text


def validate_comment(comment: str | None, *, required: bool) -> str | None:
    """Decision/response comment. Required (>= 5 chars) for REJECT and REQUEST_INFO."""
    text = clean_text(comment) if comment is not None else ""
    if text is None:
        raise ValidationFailed({"comment": "Comments can't contain special control characters."})
    if len(text) > COMMENT_MAX:
        raise ValidationFailed({"comment": f"Comments can be up to {COMMENT_MAX} characters."})
    if required and len(text) < COMMENT_MIN_REQUIRED:
        raise ValidationFailed({"comment": "Please tell the employee why."})
    return text or None


def check_employee_name(supplied: str | None, actual: str) -> None:
    """The logged-in user is authoritative; a mismatching `employeeName` is rejected (and audited)."""
    if supplied is None or not supplied.strip():
        return

    def norm(s: str) -> str:
        return unicodedata.normalize("NFC", s).strip().casefold()

    if norm(supplied) != norm(actual):
        raise ValidationFailed(
            {
                "employeeName": f"This request is filed under your account ({actual}). "
                "Please leave the name as it is."
            }
        )


def today_window(today: date) -> tuple[date, date]:
    """Earliest and latest bookable start dates (used by the UI date pickers)."""
    return today, today + timedelta(days=365)
