# Live (real-money) trading through TWS

Status: built (Phase F3), **locked until the user authorises it in the app**
(Brokerage → Live → Step 4) for their live account.

## Decisions record (2026-10-09, from the user)

- "we need a way to buy for real without paper … some portfolios we might
  want to test on paper first, but some we want it for real". Each portfolio
  chooses paper **or** real money when it is bought; a real-money portfolio
  does not have to run on paper first.
- Prices: "as close to real prices as possible". Live orders use **real-time**
  TWS prices only (never delayed). The user has no ASX market-data
  subscription yet (screenshot 2026-10-09); IBKR lists ASX Total at about
  A$25/month for non-professionals. Until it is active, live orders are
  refused with an explanation.
- Levels: semi-automatic (Sapient proposes, the user approves each trade) and
  fully automatic (no approval) — chosen per portfolio.
- Starting limits: A$1,000 per order, A$5,000 per day (editable in the app).
- Live account named by the user: U29239702 (billable account in their IBKR
  settings). The in-app authorisation statement must still be ticked for it.

## How it fits together

- `core/tws/environments.py` defines `paper` and `live`: separate TWS login
  settings/status/snapshots (`tws_live_*`), authorisation (`live_binding`),
  order-id high-water (`live_order_ids`, ids start at 1,000,000,001 so they
  never clash with paper ids), portfolio column `live_started_at`.
- Orders for both live in `paper_orders` with `environment`; every query,
  readiness check, limit, unknown-outcome block and external-order block is
  per environment. Portfolios carry `trading_environment` and only ever trade
  in that one.
- A second connector process (`sapient-api --worker --profile live`, started by
  Electron) owns the live TWS socket (default port 7496, client ID 72). It is
  read-only until live is authorised for exactly the connected, user-confirmed
  account; a DU (paper) account can never be confirmed or bound as live.
- Admission (`core.tws.paper.admit(..., env="live")`) applies all paper rules
  plus the live limits. Sending (`PaperExecutor(env="live")`) asks TWS for
  real-time data (`reqMarketDataType(1)`); if TWS answers with anything but
  real-time, nothing is sent. Limit = real-time ask (buy, rounded up to the
  tick) or bid (sell, rounded down), refused beyond the price check vs Yahoo
  (default 2%). Persist-before-send, unknown-never-resent and own-id-only
  cancels are identical to paper.
- The Emergency stop halts paper **and** live and cancels Sapient's working
  orders in both.
- "Buy for real & manage" (Portfolio Detail) = one `entry` BUY per holding in
  the live account + portfolio AI mode (approve each / fully automatic).
  Fully automatic live trading also needs "Allow fully automatic real-money
  orders" ticked, global AI mode Autonomous and automatic checks on.

## Tests

`tests/test_live.py`: separate authorisation, DU refused on live, unseen or
unconfirmed account refused, live limits and account data, live readiness
independent of paper, real-time-only pricing, live id range, paper/live
executors ignore each other's orders, Emergency stop covers both, buy-for-real
sets environment and mode, approvals of live portfolios go to live, live
worker read-only until authorised.

## US shares (G4, user decision 2026-10-09)

US portfolios trade like ASX ones, in USD on IBKR's SMART routing to the
stock's US primary listing, during US hours (Sydney night time). Rules:

- US buys need **US dollars already in the account**. Sapient never borrows
  and never converts A$ to US$ itself: convert in TWS first (Forex trade or
  IBKR's currency conversion).
- Your limits stay in A$; Sapient converts with TWS's own exchange rate.
- Real-money US orders need US real-time market data in IBKR (for example the
  "US Securities Snapshot and Futures Value Bundle", about US$10/month, often
  waived when monthly commissions reach US$30). Without it, live US orders are
  refused with an explanation. Paper uses free delayed data.
- Automatic checks for US portfolios run during US market hours, so Sapient
  (and TWS) must be running overnight Australian time for them.

## Limits apply to buying only (user decision 2026-10-09)

"should be buys only": the per-order value, daily value, daily order count and
the % of the account limit buys. Sells (stop-loss, take-profit, RSI exits,
rebalance sells, your own tickets) are not money-limited, so a whole holding can
be sold at once; they are still limited to shares actually held (for a
portfolio: shares Sapient bought for it), the price check, market hours and the
Emergency stop.
