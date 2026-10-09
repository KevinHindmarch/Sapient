"""Signal lab (H2): which trading signals really beat simply holding a stock?

Each signal is a long-only rule (Sapient never shorts) that decides at each
day's close whether to hold the stock tomorrow. It is judged only on what it
adds over buy-and-hold, after trading costs:

    edge_t = position_{t-1} * return_t - cost * |change in position|_t - return_t

A signal "passes" for a stock when all three hold:

1. its average edge over the test period (default 5 years of daily prices) is
   positive and statistically significant: one-sided p-value from a t-test
   with Newey-West (HAC) standard errors, because daily edges are
   autocorrelated while a position is held;
2. that p-value survives the Benjamini-Hochberg correction across every
   stock x signal tested together (false discovery rate ``FDR``), so testing
   many signals doesn't manufacture winners by luck;
3. it still beats holding over the most recent ``RECENT_YEARS``.

Rules use standard textbook parameters and are never tuned to the data, so
there is no in-sample fitting to overfit. Too few trades means "can't tell",
never "passes". Yahoo prices are research data (CLAUDE.md), so results guide
decisions; they are not execution evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Callable

import numpy as np
import pandas as pd

from core.indicators import TechnicalIndicatorService as TI

TRADING_DAYS = 252
COST_PER_TRADE = 0.0015       # each buy or sell: ~0.10% commission + ~0.05% slippage
FDR = 0.10                    # Benjamini-Hochberg false discovery rate
RECENT_YEARS = 2
MIN_TRADES = 6                # fewer position changes than this: not enough evidence
HAC_LAGS = 10


# ---- signals: 1 = hold the stock tomorrow, 0 = don't ---------------------------------
def _stateful(enter: pd.Series, leave: pd.Series) -> pd.Series:
    """Hold from an `enter` day until a `leave` day (enter wins on a tie)."""
    held, out = False, []
    for e, l in zip(enter.fillna(False).to_numpy(), leave.fillna(False).to_numpy()):
        if e:
            held = True
        elif l:
            held = False
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=enter.index)


def rsi_reversion(df: pd.DataFrame) -> pd.Series:
    rsi = TI.calculate_rsi(df["Close"], 14)
    return _stateful(rsi < 30, rsi > 55)


def macd_trend(df: pd.DataFrame) -> pd.Series:
    macd = TI.calculate_macd(df["Close"])
    line, signal = (macd[0], macd[1]) if isinstance(macd, tuple) else (macd["macd"], macd["signal"])
    return (line > signal).astype(float).where(line.notna() & signal.notna(), 0.0)


def above_200_day_average(df: pd.DataFrame) -> pd.Series:
    sma = df["Close"].rolling(200).mean()
    return (df["Close"] > sma).astype(float).where(sma.notna(), 0.0)


def golden_cross(df: pd.DataFrame) -> pd.Series:
    fast, slow = df["Close"].rolling(50).mean(), df["Close"].rolling(200).mean()
    return (fast > slow).astype(float).where(slow.notna(), 0.0)


def bollinger_reversion(df: pd.DataFrame) -> pd.Series:
    mid = df["Close"].rolling(20).mean()
    lower = mid - 2 * df["Close"].rolling(20).std()
    return _stateful(df["Close"] < lower, df["Close"] > mid)


def momentum_12_1(df: pd.DataFrame) -> pd.Series:
    past = df["Close"].shift(21) / df["Close"].shift(252) - 1
    return (past > 0).astype(float).where(past.notna(), 0.0)


def volume_breakout(df: pd.DataFrame) -> pd.Series:
    high = df["Close"].rolling(55).max()
    busy = df["Volume"] > 1.5 * df["Volume"].rolling(50).mean()
    trigger = ((df["Close"] >= high) & busy).to_numpy()
    out, left = [], 0
    for t in trigger:
        left = 20 if t else max(left - 1, 0)   # hold 20 trading days after a breakout
        out.append(1.0 if left else 0.0)
    return pd.Series(out, index=df.index)


SIGNALS: dict[str, tuple[str, Callable[[pd.DataFrame], pd.Series]]] = {
    "rsi_reversion": ("RSI dip: buy below 30, sell above 55", rsi_reversion),
    "macd_trend": ("MACD above its signal line", macd_trend),
    "above_200_day_average": ("Price above its 200-day average", above_200_day_average),
    "golden_cross": ("50-day average above the 200-day", golden_cross),
    "bollinger_reversion": ("Bollinger dip: buy below the lower band, sell at the middle", bollinger_reversion),
    "momentum_12_1": ("12-month momentum (skipping the last month) positive", momentum_12_1),
    "volume_breakout": ("55-day high on heavy volume, hold 20 days", volume_breakout),
}


# ---- statistics --------------------------------------------------------------------
def hac_t(x: np.ndarray, lags: int = HAC_LAGS) -> float:
    """t-statistic of mean(x) with a Newey-West (Bartlett) standard error."""
    n = len(x)
    if n < 30:
        return 0.0
    e = x - x.mean()
    var = float(e @ e) / n
    for lag in range(1, min(lags, n - 1) + 1):
        var += 2 * (1 - lag / (lags + 1)) * float(e[lag:] @ e[:-lag]) / n
    if var <= 0:
        return 0.0
    return float(x.mean() / math.sqrt(var / n))


def p_one_sided(t: float) -> float:
    """P(T >= t) under the null of no edge (normal approximation; n is in the hundreds)."""
    return 0.5 * math.erfc(t / math.sqrt(2))


def benjamini_hochberg(p_values: list[float], q: float = FDR) -> list[bool]:
    """Which hypotheses are discoveries at false discovery rate q."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    cutoff = -1
    for rank, i in enumerate(order, start=1):
        if p_values[i] <= q * rank / m:
            cutoff = rank
    keep = set(order[:cutoff]) if cutoff > 0 else set()
    return [i in keep for i in range(m)]


@dataclass
class SignalTest:
    symbol: str
    signal: str
    label: str
    days: int
    trades: int
    time_in_market: float        # share of days holding
    edge_per_year: float         # average yearly return over holding (after costs), e.g. 0.031 = +3.1%
    strategy_per_year: float
    holding_per_year: float
    t_stat: float
    p_value: float
    recent_edge_per_year: float
    holding_now: bool            # what the signal says today
    passed: bool = False
    verdict: str = ""


def test_signal(symbol: str, df: pd.DataFrame, name: str, cost: float = COST_PER_TRADE) -> SignalTest:
    label, rule = SIGNALS[name]
    close = df["Close"].astype(float)
    position = rule(df).reindex(close.index).fillna(0.0).clip(0, 1)
    returns = close.pct_change().fillna(0.0)
    held = position.shift(1).fillna(0.0)          # decided at yesterday's close: no look-ahead
    costs = cost * held.diff().abs().fillna(held.iloc[0] if len(held) else 0.0)
    strategy = held * returns - costs
    edge = (strategy - returns).to_numpy()[1:]
    recent = edge[-RECENT_YEARS * TRADING_DAYS:]
    t = hac_t(edge)
    trades = int((held.diff().abs() > 0).sum())
    return SignalTest(
        symbol=symbol, signal=name, label=label, days=len(edge), trades=trades,
        time_in_market=round(float(held.mean()), 3),
        edge_per_year=round(float(edge.mean()) * TRADING_DAYS, 4) if len(edge) else 0.0,
        strategy_per_year=round(float(strategy.to_numpy()[1:].mean()) * TRADING_DAYS, 4) if len(edge) else 0.0,
        holding_per_year=round(float(returns.to_numpy()[1:].mean()) * TRADING_DAYS, 4) if len(edge) else 0.0,
        t_stat=round(t, 2), p_value=round(p_one_sided(t), 4),
        recent_edge_per_year=round(float(recent.mean()) * TRADING_DAYS, 4) if len(recent) else 0.0,
        holding_now=bool(position.iloc[-1] > 0) if len(position) else False,
    )


def judge(tests: list[SignalTest], q: float = FDR) -> list[SignalTest]:
    """Apply the three pass conditions across one batch (BH needs the whole batch)."""
    testable = [t for t in tests if t.trades >= MIN_TRADES and t.days >= TRADING_DAYS * 2]
    discoveries = dict(zip((id(t) for t in testable), benjamini_hochberg([t.p_value for t in testable], q)))
    for t in tests:
        if id(t) not in discoveries:
            t.passed, t.verdict = False, "not enough trades or history to tell"
        elif not discoveries[id(t)]:
            t.passed, t.verdict = False, ("doesn't beat holding" if t.edge_per_year <= 0
                                          else "may be luck (not significant after correction)")
        elif t.recent_edge_per_year <= 0:
            t.passed, t.verdict = False, f"stopped working in the last {RECENT_YEARS} years"
        else:
            t.passed, t.verdict = True, "beats holding, significant, still working"
    return tests


def history(symbol: str, years: int = 5) -> pd.DataFrame:
    from core import yahoo as yf
    df = yf.Ticker(symbol).history(period=f"{years}y")
    if df is None or df.empty or "Close" not in df:
        raise ValueError(f"No price history for {symbol}")
    return df


def run_lab(symbols: list[str], years: int = 5, q: float = FDR,
            loader: Callable[[str, int], pd.DataFrame] = history) -> dict:
    """Test every signal on every stock, then judge them together."""
    tests: list[SignalTest] = []
    errors: dict[str, str] = {}
    for symbol in symbols:
        try:
            df = loader(symbol, years)
        except Exception as exc:  # one stock without data must not stop the rest
            errors[symbol] = str(exc)
            continue
        tests += [test_signal(symbol, df, name) for name in SIGNALS]
    judge(tests, q)
    return {"years": years, "fdr": q, "cost_per_trade": COST_PER_TRADE, "recent_years": RECENT_YEARS,
            "tests": [asdict(t) for t in tests], "errors": errors}


# ---- combined decision (H3) ----------------------------------------------------------
BUY_SCORE = 0.6     # hold the stock when at least 60% of the evidence-weighted votes say hold
SELL_SCORE = 0.4    # sell all of it when 40% or less do; in between nothing changes (no churn)


def vote(tests: list[dict], symbol: str) -> dict | None:
    """Evidence-weighted vote of the signals that passed for one stock, or None if none passed.

    Each passing signal votes "hold" or "out" from what it says today; its
    weight is its t-statistic (stronger evidence counts more).
    """
    passed = [t for t in tests if t["symbol"] == symbol and t["passed"]]
    if not passed:
        return None
    weights = [max(t["t_stat"], 0.0) or 1.0 for t in passed]
    score = sum(w for w, t in zip(weights, passed) if t["holding_now"]) / sum(weights)
    says = "hold" if score >= BUY_SCORE else "out" if score <= SELL_SCORE else "no change"
    return {"symbol": symbol, "score": round(score, 3), "says": says,
            "signals": [{"signal": t["signal"], "label": t["label"], "holding_now": t["holding_now"],
                         "edge_per_year": t["edge_per_year"], "p_value": t["p_value"]} for t in passed]}
