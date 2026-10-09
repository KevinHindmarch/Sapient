"""Automatic RSI checks during market hours.

Twice per trading day per portfolio (after the open and before the close, both
configurable) the scheduler runs `ai_engine.scan_portfolio`. Each check has a
unique (portfolio, window) row in `scheduler_runs`, so a restart or a second
copy of the connector never runs the same check twice. If the PC was asleep
and several checks were missed, only the latest one still inside market hours
runs; the others are recorded as missed. Every tick also expires unanswered
proposals whose answer-by time has passed.

Proposals become orders only through core.tws.paper.admit, in the account the
portfolio was bought in: when you approve them, or automatically in fully
automatic mode if you allowed automatic orders for that account.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from core import db
from core.strategy import calendar

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Window:
    name: str           # after_open | before_close
    at: datetime        # UTC time the check becomes due
    close: datetime     # UTC market close (end of the window)
    key: str            # e.g. "ASX:2026-10-12:after_open"


def windows(market: calendar.Market, now: datetime, settings: dict) -> list[Window]:
    day = calendar.local_date(market, now)
    hours = calendar.session(market, day)
    if not hours:
        return []
    opens, closes = hours
    after_open = opens + timedelta(minutes=int(settings.get("check_after_open_minutes") or 15))
    before_close = closes - timedelta(minutes=int(settings.get("check_before_close_minutes") or 30))
    found = [Window("after_open", after_open, closes, f"{market.code}:{day}:after_open")]
    if before_close > after_open:
        found.append(Window("before_close", before_close, closes, f"{market.code}:{day}:before_close"))
    return found


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Scheduler:
    def __init__(self, scan: Callable | None = None, now: Callable[[], datetime] = _utc_now):
        if scan is None:
            from core.ai_engine import scan_portfolio as scan
        self.scan = scan
        self.now = now

    # -- state ------------------------------------------------------------
    def _claim(self, portfolio_id: int, key: str, outcome: str = "running") -> int | None:
        """Insert the run row; None if this window was already handled."""
        with db.transaction() as (cur, _):
            cur.execute("""INSERT INTO scheduler_runs(portfolio_id, window_key, outcome, finished_at)
                           VALUES (%s, %s, %s, %s)
                           ON CONFLICT(portfolio_id, window_key) DO NOTHING RETURNING id""",
                        (portfolio_id, key, outcome, None if outcome == "running" else self.now()))
            row = cur.fetchone()
        return row["id"] if row else None

    def _finish(self, run_id: int, outcome: str, result: dict) -> None:
        with db.transaction() as (cur, _):
            cur.execute("UPDATE scheduler_runs SET outcome=%s, result=%s, finished_at=%s WHERE id=%s",
                        (outcome, result, self.now(), run_id))

    def _status(self, detail: str, next_check: datetime | None) -> None:
        with db.transaction() as (cur, _):
            cur.execute("UPDATE scheduler_status SET heartbeat_at=%s, detail=%s, next_check_at=%s WHERE id=1",
                        (self.now(), detail, next_check))

    def abandon_running(self) -> None:
        """A crash mid-check leaves 'running' rows; they are never retried."""
        with db.transaction() as (cur, _):
            cur.execute("""UPDATE scheduler_runs SET outcome='abandoned', finished_at=%s
                           WHERE outcome='running'""", (self.now(),))

    # -- work -------------------------------------------------------------
    def tick(self) -> list[dict]:
        from core.database import AISignalService, AITradingSettingsService, UserService
        now = self.now()
        expired = AISignalService.expire_stale(now)
        if expired:
            log.info("expired %d unanswered proposals", len(expired))

        user = UserService.get_local_user()
        if not user:
            self._status("Waiting for setup.", None)
            return []
        settings = AITradingSettingsService.get(user["id"])
        mode = (settings.get("mode") or "off").lower()
        if not settings.get("scheduler_enabled"):
            self._status("Automatic checks are off.", None)
            return []
        if mode == "off":
            self._status("AI Trading is off.", None)
            return []

        with db.transaction() as (cur, _):
            cur.execute("""SELECT id, name, market FROM portfolios
                           WHERE user_id=%s AND COALESCE(ai_mode,'off') <> 'off' ORDER BY id""",
                        (user["id"],))
            portfolios = [dict(r) for r in cur.fetchall()]
        if not portfolios:
            self._status("No portfolio has AI Trading switched on.", None)
            return []

        runs, upcoming = [], []
        timeout = timedelta(minutes=int(settings.get("approval_timeout_minutes") or 15))
        for portfolio in portfolios:
            market = calendar.market_for(portfolio.get("market"))
            todays = windows(market, now, settings)
            due = [w for w in todays if w.at <= now < w.close]
            upcoming += [w.at for w in todays if w.at > now]
            if not todays or now >= todays[-1].close:
                nxt = calendar.next_open(market, now)
                if nxt:
                    upcoming.append(nxt + timedelta(minutes=int(settings.get("check_after_open_minutes") or 15)))
            if not due:
                continue
            for missed in due[:-1]:
                self._claim(portfolio["id"], missed.key, outcome="missed")
            window = due[-1]
            run_id = self._claim(portfolio["id"], window.key)
            if run_id is None:
                continue
            answer_by = min(now + timeout, window.close)
            try:
                result = self.scan(user["id"], portfolio["id"], expires_at=answer_by)
                summary = {"new_signals": len(result.get("new_signals") or []),
                           "skipped": result.get("skipped") or [],
                           "scanned_symbols": result.get("scanned_symbols", 0)}
                self._finish(run_id, "done", summary)
                runs.append({"portfolio_id": portfolio["id"], "window": window.key, **summary})
            except Exception as exc:  # one portfolio failing must not stop the rest
                log.exception("scheduled check failed for portfolio %s", portfolio["id"])
                self._finish(run_id, "failed", {"error": str(exc)})
                runs.append({"portfolio_id": portfolio["id"], "window": window.key, "error": str(exc)})

        next_check = min(upcoming) if upcoming else None
        self._status(f"Watching {len(portfolios)} portfolio(s).", next_check)
        return runs


def run_forever(should_stop: Callable[[], bool], interval: float = 30.0, sleep=None) -> None:
    import time
    sleep = sleep or time.sleep
    scheduler = Scheduler()
    scheduler.abandon_running()
    while not should_stop():
        try:
            scheduler.tick()
        except Exception:
            log.exception("scheduler tick failed")
        sleep(interval)
