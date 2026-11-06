"""U1-U9: day counting and the consecutive-day chain (PRD 5.1)."""

from datetime import date

import pytest

from app.domain.calendar import Span, compute_streak, first_overlap, inclusive_days


def d(s: str) -> date:
    return date.fromisoformat(s)


def span(a: str, b: str) -> Span:
    return Span(d(a), d(b))


@pytest.mark.parametrize(
    ("start", "end", "days", "extended"),
    [
        ("2026-11-01", "2026-11-01", 1, False),  # U1
        ("2026-11-01", "2026-11-03", 3, False),  # U2: exactly 3 is NOT extended
        ("2026-11-01", "2026-11-04", 4, True),  # U3: boundary
        ("2026-11-01", "2026-11-05", 5, True),  # U4
        ("2028-02-28", "2028-03-01", 3, False),  # U5: leap day counted
        ("2026-12-30", "2027-01-02", 4, True),  # U5: year end
    ],
)
def test_single_request_boundaries(start: str, end: str, days: int, extended: bool) -> None:
    r = compute_streak(d(start), d(end), [])
    assert (r.days, r.streak, r.is_extended) == (days, days, extended)


def test_inclusive_days() -> None:
    assert inclusive_days(d("2026-11-01"), d("2026-11-01")) == 1


def test_u6_adjacent_previous_request_chains() -> None:
    r = compute_streak(d("2026-11-01"), d("2026-11-02"), [span("2026-10-30", "2026-10-31")])
    assert (r.days, r.streak, r.is_extended) == (2, 4, True)


def test_u6b_adjacent_following_request_chains() -> None:
    r = compute_streak(d("2026-11-01"), d("2026-11-02"), [span("2026-11-03", "2026-11-04")])
    assert r.streak == 4 and r.is_extended


def test_u7_one_day_gap_does_not_chain() -> None:
    r = compute_streak(d("2026-11-01"), d("2026-11-01"), [span("2026-10-28", "2026-10-29")])
    assert (r.streak, r.is_extended) == (1, False)


def test_u8_three_back_to_back_two_day_requests() -> None:
    others = [span("2026-11-01", "2026-11-02"), span("2026-11-03", "2026-11-04")]
    r = compute_streak(d("2026-11-05"), d("2026-11-06"), others)
    assert (r.days, r.streak, r.is_extended) == (2, 6, True)
    assert len(r.chain) == 3


def test_chain_is_transitive_regardless_of_input_order() -> None:
    others = [span("2026-11-07", "2026-11-08"), span("2026-11-03", "2026-11-04")]
    r = compute_streak(d("2026-11-05"), d("2026-11-06"), others)
    assert r.streak == 6  # 3-4, 5-6 (new) and 7-8 join into one chain: 3 Nov to 8 Nov
    assert r.chain[0].from_date == d("2026-11-03")


def test_unrelated_far_request_is_ignored() -> None:
    r = compute_streak(d("2026-11-01"), d("2026-11-03"), [span("2026-12-01", "2026-12-10")])
    assert r.streak == 3 and not r.is_extended and len(r.chain) == 1


def test_first_overlap() -> None:
    others = [(7, span("2026-11-10", "2026-11-12")), (9, span("2026-11-20", "2026-11-21"))]
    assert first_overlap(span("2026-11-12", "2026-11-14"), others) == (
        7,
        span("2026-11-10", "2026-11-12"),
    )
    assert first_overlap(span("2026-11-13", "2026-11-14"), others) is None
    assert first_overlap(span("2026-11-21", "2026-11-25"), others) is not None
