"""Cached drop-in for the parts of yfinance Sapient uses.

``from core import yahoo as yf`` then ``yf.Ticker(sym).history(...)``,
``.info``, ``.income_stmt`` and ``yf.download(...)`` behave like yfinance but
results are cached in ``<data>/market_cache.db`` with a time-to-live, and
concurrent Yahoo requests are limited. Research data only, never execution prices.

The cache stores pickled pandas objects written by this process only; it lives
in the user's own data folder and is safe to delete at any time.
"""

from contextlib import contextmanager
import hashlib
import json
import logging
import pickle
import sqlite3
import threading
import time

import yfinance as _yf

from core import db

log = logging.getLogger(__name__)

INTRADAY_TTL = 15 * 60          # short periods change during the trading day
HISTORY_TTL = 6 * 60 * 60       # multi-month daily history
INFO_TTL = 24 * 60 * 60         # company profile, dividends, ratios
STATEMENT_TTL = 7 * 24 * 60 * 60

_SHORT_PERIODS = {"1d", "5d", "1mo"}
_MAX_CONCURRENT = 8
_slots = threading.BoundedSemaphore(_MAX_CONCURRENT)
_lock = threading.RLock()  # _get/_put hold it while _conn() may initialise
_cache_conn = None


def _conn():
    global _cache_conn
    with _lock:
        if _cache_conn is None:
            conn = sqlite3.connect(str(db.data_dir() / "market_cache.db"),
                                   check_same_thread=False, timeout=30, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY, stored_at REAL NOT NULL, value BLOB NOT NULL)""")
            _cache_conn = conn
        return _cache_conn


def _key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _get(key, ttl):
    try:
        with _lock:
            row = _conn().execute("SELECT stored_at, value FROM cache WHERE key=?", (key,)).fetchone()
        if row and time.time() - row[0] < ttl:
            return True, pickle.loads(row[1])
    except Exception:  # a corrupt or locked cache must never break research features
        log.warning("market cache read failed", exc_info=True)
    return False, None


def _put(key, value):
    try:
        blob = pickle.dumps(value)
        with _lock:
            _conn().execute("INSERT OR REPLACE INTO cache(key, stored_at, value) VALUES(?,?,?)",
                            (key, time.time(), blob))
    except Exception:
        log.warning("market cache write failed", exc_info=True)


@contextmanager
def _slot():
    with _slots:
        yield


class YahooUnavailable(RuntimeError):
    """Yahoo is rate-limiting or unreachable and there is no earlier copy of the data."""


STALE_LIMIT = 7 * 24 * 60 * 60   # an older copy beats nothing when Yahoo fails
NEGATIVE_TTL = 10 * 60           # "Yahoo had nothing" is remembered briefly so scans don't hammer it
RATE_LIMIT_PAUSE = 60.0
_paused_until = 0.0


def _is_rate_limit(exc: Exception) -> bool:
    text = f"{exc.__class__.__name__} {exc}".lower()
    return "ratelimit" in text or "rate limit" in text or "too many requests" in text or "429" in text


def _cached(key, ttl, fetch, keep):
    """Fresh cache, else Yahoo, else the last good copy (up to a week old)."""
    global _paused_until
    hit, value = _get(key, ttl)
    if hit:
        return value
    empty_hit, empty = _get("empty:" + key, NEGATIVE_TTL)
    if empty_hit or time.time() < _paused_until:
        stale_hit, stale = _get(key, STALE_LIMIT)
        if stale_hit:
            return stale
        if empty_hit:
            return empty
        raise YahooUnavailable("Yahoo Finance is limiting requests; try again in a minute.")
    try:
        with _slot():
            value = fetch()
    except Exception as exc:
        if _is_rate_limit(exc):
            _paused_until = time.time() + RATE_LIMIT_PAUSE
            log.warning("Yahoo rate limit: pausing requests for %.0f s", RATE_LIMIT_PAUSE)
        stale_hit, stale = _get(key, STALE_LIMIT)
        if stale_hit:
            return stale
        raise
    if keep(value):
        _put(key, value)
        return value
    stale_hit, stale = _get(key, STALE_LIMIT)
    if stale_hit:
        return stale
    _put("empty:" + key, value)
    return value


def prune(max_age: float = 30 * 24 * 60 * 60) -> int:
    """Delete cache rows older than ``max_age`` seconds (the file never grows without bound)."""
    try:
        with _lock:
            cur = _conn().execute("DELETE FROM cache WHERE stored_at < ?", (time.time() - max_age,))
            return cur.rowcount
    except Exception:
        log.warning("market cache prune failed", exc_info=True)
        return 0


def _non_empty(value):
    if value is None:
        return False
    if hasattr(value, "empty"):  # pandas objects
        return not value.empty
    return bool(value)


def _history_ttl(period):
    return INTRADAY_TTL if period in _SHORT_PERIODS else HISTORY_TTL


class Ticker:
    def __init__(self, symbol):
        self.symbol = symbol
        self._ticker = _yf.Ticker(symbol)

    def history(self, period="1mo", **kwargs):
        return _cached(_key("history", self.symbol, period, kwargs), _history_ttl(period),
                       lambda: self._ticker.history(period=period, **kwargs), _non_empty)

    @property
    def info(self):
        return _cached(_key("info", self.symbol), INFO_TTL,
                       lambda: self._ticker.info, lambda v: bool(v))

    @property
    def income_stmt(self):
        return _cached(_key("income_stmt", self.symbol), STATEMENT_TTL,
                       lambda: self._ticker.income_stmt, _non_empty)

    @property
    def balance_sheet(self):
        return _cached(_key("balance_sheet", self.symbol), STATEMENT_TTL,
                       lambda: self._ticker.balance_sheet, _non_empty)

    def __getattr__(self, name):  # anything else goes straight to yfinance, uncached
        return getattr(self._ticker, name)


def download(tickers, period="1mo", **kwargs):
    return _cached(_key("download", tickers, period, kwargs), _history_ttl(period),
                   lambda: _yf.download(tickers, period=period, **kwargs), _non_empty)


def clear_cache():
    with _lock:
        _conn().execute("DELETE FROM cache")
