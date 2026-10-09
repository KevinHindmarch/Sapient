"""Market hours for the ASX and US (NYSE/Nasdaq) regular sessions.

Holidays and early closes are listed per year. For a year that is not listed
yet, weekdays count as trading days and `known_year()` is False, so the UI can
say the calendar needs updating. Times are local exchange time; callers work
in UTC.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Market:
    code: str
    name: str
    tz: ZoneInfo
    open: time
    close: time
    holidays: frozenset[date]
    early_close: dict[date, time] = field(default_factory=dict)
    years: frozenset[int] = frozenset()


def _days(*values: str) -> frozenset[date]:
    return frozenset(date.fromisoformat(v) for v in values)


ASX = Market(
    code="ASX", name="ASX", tz=ZoneInfo("Australia/Sydney"),
    open=time(10, 0), close=time(16, 0),
    holidays=_days(
        "2026-01-01", "2026-01-26", "2026-04-03", "2026-04-06", "2026-06-08",
        "2026-12-25", "2026-12-28",
        "2027-01-01", "2027-01-26", "2027-03-26", "2027-03-29", "2027-06-14",
        "2027-12-27", "2027-12-28",
    ),
    early_close={date(2026, 12, 24): time(14, 10), date(2026, 12, 31): time(14, 10),
                 date(2027, 12, 24): time(14, 10), date(2027, 12, 31): time(14, 10)},
    years=frozenset({2026, 2027}),
)

US = Market(
    code="US", name="US (NYSE/Nasdaq)", tz=ZoneInfo("America/New_York"),
    open=time(9, 30), close=time(16, 0),
    holidays=_days(
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
        "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
        "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
        "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    ),
    early_close={date(2026, 11, 27): time(13, 0), date(2026, 12, 24): time(13, 0),
                 date(2027, 11, 26): time(13, 0)},
    years=frozenset({2026, 2027}),
)

MARKETS = {"ASX": ASX, "US": US}


def market_for(code: str | None) -> Market:
    """Portfolio `market` values are 'ASX' (default) or 'US'."""
    return MARKETS.get((code or "ASX").upper(), ASX)


def known_year(market: Market, day: date) -> bool:
    return day.year in market.years


def is_trading_day(market: Market, day: date) -> bool:
    return day.weekday() < 5 and day not in market.holidays


def session(market: Market, day: date) -> tuple[datetime, datetime] | None:
    """(open, close) in UTC for the exchange-local `day`, or None if closed."""
    if not is_trading_day(market, day):
        return None
    close = market.early_close.get(day, market.close)
    opens = datetime.combine(day, market.open, market.tz).astimezone(timezone.utc)
    closes = datetime.combine(day, close, market.tz).astimezone(timezone.utc)
    return opens, closes


def local_date(market: Market, now: datetime) -> date:
    return now.astimezone(market.tz).date()


def is_open(market: Market, now: datetime) -> bool:
    hours = session(market, local_date(market, now))
    return bool(hours and hours[0] <= now < hours[1])


def next_open(market: Market, now: datetime, horizon_days: int = 14) -> datetime | None:
    """The next session start strictly after `now`."""
    day = local_date(market, now)
    for offset in range(horizon_days):
        hours = session(market, day + timedelta(days=offset))
        if hours and hours[0] > now:
            return hours[0]
    return None
