# Sapient trading workflow — RSI portfolio lifecycle

Date: 2026-10-09. Status: **partly built.** Done (no orders): market calendar,
stop-loss/take-profit/RSI rules, whole-share sizing, market-hours scheduler,
answer-by expiry. Not yet: entry batches, broker-backed holdings, paper orders.
Companion to [desktop-migration-plan.md](desktop-migration-plan.md). Safety rules in
[ibkr-architecture.md](ibkr-architecture.md) override anything here.

## 1. The workflow in plain language

1. **Find** stocks that look cheap right now (RSI oversold), optionally filtered
   by fundamentals/CAPM.
2. **Build** a portfolio from them; Sapient works out the best weights
   (maximum Sharpe ratio within your risk limits) and turns your cash budget
   into share quantities.
3. **Buy** through Interactive Brokers (paper or real account), with you
   approving first or automatically, depending on your autonomy setting.
4. **Watch** every held stock during market hours.
5. **Sell** when RSI says overbought (or a stop-loss/take-profit rule triggers).
6. **Recycle** the cash: find new oversold candidates, re-optimise, buy again,
   and rebalance when weights drift — on an ongoing basis.

The same steps run identically in **Simulation** (no TWS), **TWS Paper** and
**TWS Live**; only the account the portfolio is bound to differs.

## 2. What exists today vs what is missing

| Step | Today | Gap |
|---|---|---|
| Find | RSI screener (`/api/indicators/rsi-screener`), fundamentals & CAPM scans | Screener isn't saved as a reusable "strategy universe" |
| Build | Manual/Auto/CAPM builders → `optimize_portfolio` (max Sharpe, risk caps) → save | Quantities computed from yfinance prices at save time; saving creates *model* holdings as if already bought |
| Buy | None. `execute-rebalance` only covers drift; intents are simulation-only and never sent | Initial-entry order batch, TWS quotes, whole-share sizing, cash checks, real submission |
| Watch | `ai_engine.scan_portfolio` — runs only when the user clicks scan (HTTP-triggered) | Scheduler during market hours, market calendars |
| Sell | Engine proposes SELL when RSI ≥ sell threshold for held shares | Stop-loss/take-profit, partial exits, broker-backed holdings |
| Recycle | Engine proposes BUY only for already-held symbols | Candidate discovery, re-optimisation with freed cash, periodic rebalance |
| Autonomy | Global + per-portfolio mode off/suggestions/autonomous, guardrails, kill switch | Semi-autonomous with alerts/timeouts, per-environment settings, desktop notifications |

## 3. Lifecycle state machine (per portfolio)

```text
DRAFT ──optimise──► PROPOSED ──bind account + fund──► READY_TO_ENTER
   ▲                                                  │ entry batch
   │                                                  ▼
 ARCHIVED ◄──close all── MANAGING ◄──fills reconciled── ENTERING
                          │  ▲
            signals/rebal │  │ fills reconciled
                          ▼  │
                       TRADING
   any state ──halt / kill switch / recovery──► PAUSED (resume = explicit user action)
```

- **DRAFT/PROPOSED**: research only, nothing at the broker. Model weights shown.
- **READY_TO_ENTER**: bound to one account (`SIM`, `TWS paper DU…`, or
  `TWS live U…`) and a cash budget. Binding is a deliberate step, never a toggle.
- **ENTERING/TRADING**: order batches in flight via the safety admission
  (`IntentService`) → worker → TWS.
- **MANAGING**: holdings come **only from broker fills** (broker-backed ledger),
  not from the model. The scheduler evaluates rules.
- **PAUSED**: no new orders; existing working orders shown with their real state.

## 4. Step-by-step design

### 4.1 Find (universe + entry screen)
- Strategy universe: ASX200, S&P 500, or a custom watchlist (per portfolio).
- Entry screen: RSI(period, default 14) on **daily closes** ≤ entry threshold
  (default 30); optional MACD bullish confirmation, minimum liquidity
  (avg daily volume/value), fundamentals/CAPM score floor, sector exclusions.
- Data: yfinance for screening (research data). Results are candidates, not orders.

### 4.2 Build (optimise → weights → allocation → quantities)
1. Candidates → `PortfolioOptimizerService.optimize_portfolio` (max Sharpe,
   geometric returns, risk-tolerance cap per stock, market risk-free rate).
2. Weights × **investable cash** (budget − cash buffer %, default 2%) → target $.
3. Quantities = `floor(target $ / execution price)` whole shares, where the
   execution price is a **fresh TWS quote** at order time (≤5 s old), not yfinance.
   Leftover cash is reported; optional second pass tops up the most
   under-weighted names while cash allows.
4. Lot/tick rules per exchange; minimum order value (skip tiny legs).
5. Show a preview: weights, $, shares, limit prices, est. fees, cash left, FX need
   (no automatic FX conversion — buying US stocks needs USD available).

### 4.3 Buy (entry batch)
- One batch of BUY intents through `IntentService.admit_batch` (origin
  `entry`, a new origin added beside manual/ai_approval/ai_autonomous/rebalance).
- Limit orders, DAY, limit = ask + configurable offset (default 0.2%, capped);
  intents expire after the configured window (default 30 s to submit).
- Partial fills are normal; unfilled remainder at day end is reported, and the
  next cycle re-plans from actual holdings — never assumes the order filled.

### 4.4 Watch (scheduler)
- Runs inside the desktop app (worker side) only while the PC is awake,
  the worker is READY and the market is open (exchange calendars for ASX and
  NYSE/Nasdaq, incl. holidays and half days).
- Evaluation times (configurable): e.g. 15 min after open and 30 min before
  close; RSI from the latest daily bars (+ optional intraday mode later).
- Each run gets a unique `(portfolio, window)` key so a restart never double-runs.

### 4.5 Sell (exit rules, any of)
- RSI ≥ exit threshold (default 70) → sell `exit_fraction` (default 100%).
- Optional stop-loss % from average cost, take-profit %, trailing stop %.
- Optional "hold minimum N days" to avoid churn.
- Sells are long-only: never more than broker-confirmed, allocated shares.

### 4.6 Recycle (re-entry + rebalance)
- Cash freed by sells is only spendable once fills are confirmed.
- Re-entry: run the entry screen again; if new candidates qualify and the
  portfolio is below `max_positions`, re-optimise across holdings + candidates
  and propose BUYs for the gap (sells first, buys after confirmed proceeds).
- Rebalance: when any weight drifts > threshold (default 5 pp, today 1.5 pp) or
  on a calendar (monthly/quarterly), propose trim/add legs.

## 5. Autonomy — user configurable

| Level | What happens | Alerts |
|---|---|---|
| **Off** | No scanning. | — |
| **Suggest only** | Proposals appear in the AI Inbox; you place/approve each yourself. | Desktop notification per new proposal (batched) |
| **Semi-autonomous** (approve-before-trade) | Sapient prepares the exact orders and **asks you first**; you approve/reject/edit. Unanswered requests **expire** (default 15 min, or end of window) — never executed by default. | Windows toast with Approve / Review buttons, tray badge, optional sound; optional email later |
| **Autonomous within limits** | Trades inside the guardrails go automatically; anything outside (size, new symbol, live account above $X, first trade of the day, etc.) **escalates to approval**. | Notification after each trade and a daily summary |

Settings, per portfolio with global defaults; the **most restrictive** of global
and portfolio wins (existing rule):
- Autonomy level, approval timeout, which actions need approval
  (entries / exits / rebalances / stop-loss exits).
- Strategy: universe, RSI period, entry/exit thresholds, MACD confirmation,
  stop-loss/take-profit/trailing, exit fraction, max positions, cash buffer,
  rebalance rule, evaluation times, limit offset.
- Guardrails (existing): max trade %, max daily trades, max daily turnover %,
  sector cap, loss/volatility/news breakers (fail closed if no data).
- Kill switch (existing): durable halt, 24 h cooldown, explicit resume.

## 6. Paper vs live

- Same code path; environment comes from the **bound account**, verified at
  connect time (not from a port number or a toggle).
- Separate settings per environment, with **stricter live defaults**: autonomy
  capped at Semi-autonomous until you explicitly enable more; lower absolute $ caps;
  first live week manual approval only.
- Moving a portfolio from paper to live = new binding + fresh entry plan;
  queued paper intents never carry over.
- UI badge on every screen and notification: `SIMULATION`, `TWS PAPER`, `TWS LIVE`.
- Live trading needs explicit sign-off after the paper qualification gate
  (IBKR roadmap phases 5–6).

## 7. Where it runs in the desktop architecture

```text
Scheduler (worker) ─► Strategy engine (core, SDK-independent)
        │                 uses: yfinance bars (signals), TWS quotes (prices),
        │                       broker-backed holdings, strategy settings
        ▼
  Proposals ─► Autonomy gate ─► (approval needed?) ─► Notification ─► user
        │                              │ approved / auto
        ▼                              ▼
  IntentService.admit[_batch]  (policy, reservations, idempotency, halt)
        ▼
  Worker submit protocol ─► TWS ─► IBKR
        ▼
  Fills/commissions ─► broker-backed ledger ─► portfolio MANAGING state
```

Code changes this implies (scheduled in migration Phases E–F):
- `core/strategy/` new: `rsi_strategy.py` (entry/exit/recycle rules, pure functions),
  `sizing.py` (weights→shares), `calendar.py` (market hours/holidays).
- `core/ai_engine.py` refactored into the strategy engine + autonomy gate;
  add candidate discovery and stop-loss/take-profit.
- New tables: `strategy_settings` (per portfolio/environment),
  `approval_requests` (with expiry), `scheduler_runs` (unique window key),
  broker-backed `holdings`/`fills` (architecture §8).
- Electron: native notifications with actions → API approve/reject; tray
  badge; "Pending approvals" view.
- Frontend: portfolio wizard step "Bind account & fund", strategy settings
  panel, lifecycle status, approval centre.

## 8. Acceptance scenarios (add to the test plan)

1. RSI oversold screen → optimise → entry batch → partial fills → holdings
   equal fills, not the model.
2. Held stock RSI ≥ 70 → semi-autonomous approval request → user ignores →
   request expires, no order.
3. Same in autonomous mode within limits → order sent once; restart mid-run
   does not send a second order.
4. Sell fills → cash confirmed → new oversold candidate → re-optimised buy.
5. Stop-loss hit while PC asleep → on wake: recovery first, re-evaluate with
   fresh data, no stale order.
6. Live account with autonomy set to autonomous → capped to semi until
   explicitly enabled.
7. Kill switch during entry batch → unsent legs blocked, working orders cancel
   requested, outcome reported honestly.
8. Market closed / holiday → no proposals.

## Buying on an RSI dip (H1, user decisions 2026-10-10)

"Buy … & manage" offers two ways to buy:

- **Now:** buys all holdings straight away.
- **When each stock is cheap:** buys nothing straight away.

With **When each stock is cheap**:
- Each holding's planned whole shares are recorded (`planned_quantity`), and the holding is marked `entry_state='waiting'`.
- At each scheduled check, twice per trading day, `core.ai_engine._dip_entry` checks each waiting stock's RSI(14).
- If the RSI is below the portfolio's level (`entry_rsi_below`, default **30**), it proposes buying all the missing planned shares in one go.
  - **Fully automatic:** the purchase is placed straight away.
  - **Semi-automatic:** it waits in the AI Inbox for approval.
- A buy for the plan is not reduced by the per-trade AI guardrails; the account's own limits still apply when the order is admitted.
- A stock that hasn't dipped by the deadline (`entry_deadline`, default 20 trading days) becomes `entry_state='skipped'` and is never bought.
- The normal RSI/MACD rules never buy a waiting or skipped stock.
- Pressing **Buy now** later ends the wait for the stocks it buys.

The checks stay twice a day (user decision).

## Signal lab and lab-vote trading (H2/H3, user decisions 2026-10-10)

**The lab** (`core/signals.py`; `GET /api/signals/portfolio/{id}`; the "Signal lab" card on each portfolio page) tests 7 long-only signals on each holding, using 5 years of daily Yahoo prices:
- RSI dip;
- MACD above its signal line;
- price above its 200-day average;
- golden cross;
- Bollinger dip;
- 12-1 month momentum;
- 55-day high on heavy volume.

**How each signal is tested:**
- Its position is decided at the close and applied from the next day, so it never sees the future.
- Its edge is its daily return minus buy-and-hold's, after 0.15% per buy or sell.

A signal **passes** for a stock only when all four hold:
1. its edge is significantly positive: one-sided t-test with Newey-West standard errors;
2. it survives the Benjamini–Hochberg correction at a 10% false discovery rate across every stock × signal tested together;
3. it still beats holding over the last 2 years;
4. it has enough trades and history to judge.

Parameters are textbook values and never tuned.

**Lab-vote trading:** on the same card, the user can choose how AI Trading decides for each portfolio:
- **Simple rules** (default): RSI with MACD, as before.
- **Signal lab:**
  - At each scheduled check the lab is re-run, and each stock's passing signals vote, weighted by their t-statistic.
  - A score of 0.6 or more means **hold**. If nothing is held, Sapient buys the planned shares back; this buy is not cut down by the per-trade size limit.
  - A score of 0.4 or less means **out**: Sapient sells the whole holding. Risk-reducing sells are not size-limited.
  - Anything in between, or a stock with no passing signal, changes nothing.
  - Stop-loss and take-profit are always checked first.
  - Account limits, cash, the per-stock cap, the daily trade count and turnover still apply.

No strategy wins every day. The lab only reduces the chance of trading on luck. New portfolios should run on paper first.
