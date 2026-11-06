"""Time helpers. Tests patch `utcnow`; "today" is always evaluated in the org time zone."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(UTC)


def org_today(tz_name: str) -> date:
    return utcnow().astimezone(ZoneInfo(tz_name)).date()
