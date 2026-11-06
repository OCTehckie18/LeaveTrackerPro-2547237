"""Consecutive-day maths (PRD section 5.1). Pure functions, no I/O.

Calendar days, inclusive, weekends and holidays count. A request is chained with the employee's other
active/approved requests that touch it, so 3 + 3 + 3 day requests cannot dodge the "more than 3" rule.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

EXTENDED_THRESHOLD = 3  # more than this many consecutive days = extended leave
_ONE_DAY = timedelta(days=1)


@dataclass(frozen=True, order=True)
class Span:
    from_date: date
    to_date: date

    @property
    def days(self) -> int:
        return inclusive_days(self.from_date, self.to_date)


@dataclass(frozen=True)
class StreakResult:
    days: int  # length of this request alone
    streak: int  # length of the whole consecutive chain it belongs to
    is_extended: bool
    chain: tuple[Span, ...]  # all spans in the chain, sorted, including this request


def inclusive_days(from_date: date, to_date: date) -> int:
    return (to_date - from_date).days + 1


def compute_streak(from_date: date, to_date: date, others: Iterable[Span]) -> StreakResult:
    """Merge the new request with every span that touches it (directly or through other spans).

    `others` must already be filtered to the employee's ACTIVE statuses by the caller.
    """
    current = Span(from_date, to_date)
    lo, hi = from_date, to_date
    chain = [current]
    remaining = sorted(others)
    grew = True
    while grew:
        grew = False
        for span in list(remaining):
            # touches or overlaps [lo, hi]: starts by hi+1 and ends no earlier than lo-1
            if span.from_date <= hi + _ONE_DAY and span.to_date >= lo - _ONE_DAY:
                chain.append(span)
                remaining.remove(span)
                lo, hi = min(lo, span.from_date), max(hi, span.to_date)
                grew = True
    streak = inclusive_days(lo, hi)
    return StreakResult(
        days=current.days,
        streak=streak,
        is_extended=streak > EXTENDED_THRESHOLD,
        chain=tuple(sorted(chain)),
    )


def first_overlap[T](span: Span, others: Sequence[tuple[T, Span]]) -> tuple[T, Span] | None:
    """Return the first (id, span) that shares at least one day with `span`."""
    for ident, other in others:
        if other.from_date <= span.to_date and other.to_date >= span.from_date:
            return ident, other
    return None
