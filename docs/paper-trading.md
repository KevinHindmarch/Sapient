# Paper trading through TWS

Status: built (Phase F2). **Paper only; live trading does not exist.**

## Authorisation record

- 2026-10-09: the user tested the read-only connection on their PC (TWS paper
  account `DUT146393`, IBKR API 10.51, all steps passed; market data showed
  "no price", so prices are delayed) and wrote: *"use delayed prices … I
  authorise paper trading"*.
- Decision: use TWS's free **delayed** prices (15–20 minutes old) with
  **cautious limit orders**. This replaces the architecture default of a quote
  under 5 seconds old for paper trading only; live trading would need fresh
  quotes and a separate sign-off.
- In the app the user still has to tick the authorisation statement on
  Brokerage → Step 4 for the exact account (`core.tws.paper.AUTHORISATION_TEXT`).
  Changing the TWS account or un-confirming paper drops order mode.

## What the user does

1. TWS logged in with Paper Trading; **untick Read-Only API** (paper login only).
2. Brokerage → Step 4: set limits, tick the statement, Authorise.
3. Approve proposals in the AI Inbox, or use the ticket on **Paper orders**.
4. Emergency stop (tray or AI Trading) switches paper trading off, blocks
   queued orders and cancels Sapient's own working orders.

## Rules (enforced in code)

Admission (`core/tws/paper.py`, one SQLite transaction, all origins):
- Authorised + switched on + not halted; TWS READY on the bound account,
  connector heartbeat fresh, account data < 3 minutes old; TWS settings still
  name the bound account as confirmed paper.
- ASX only (`.AX`), whole shares, long-only, ASX trading hours.
- No order while another order's outcome is unknown; no order while TWS shows
  open orders Sapient did not place.
- Kill-switch 24 h cooldown.
- Per-order A$ limit (worst case at the allowed price gap), the AI settings'
  max trade % of NAV, orders/day (also the AI max daily trades), A$/day.
- Cash: open buys (+10% margin of safety) + this order ≤ TotalCashValue (no
  borrowing). Sells: broker position − shares already being sold.
- AI orders: AI mode on for both global and portfolio; autonomous needs both
  autonomous **and** "allow automatic paper orders".
- Idempotency: same key + same request returns the same order; different
  request → conflict.

Sending (`core/tws/execution.py`, connector process, one at a time):
- Order-capable transport only for the authorised account
  (`IbapiTransport(allow_orders=True)`); `reqGlobalCancel`/`reqAutoOpenOrders`
  are never callable.
- Re-check, qualify ASX contract, delayed snapshot. BUY limit = min(last, ask)
  rounded down to the ASX tick; SELL = max(last, bid) rounded up. No last
  price → not sent. More than the allowed gap (default 3%) from the Yahoo
  reference price → not sent.
- Order id = max(TWS next id, stored high-water + 1, every used id + 1);
  stored as SUBMITTING before `placeOrder` is called exactly once; DAY LMT,
  explicit account, `orderRef = sapient:<id>`, regular hours only.
- No confirmation within 10 s, an exception during send, or a restart while
  SUBMITTING → UNKNOWN. Never resent. Resolved by broker evidence (openOrder /
  orderStatus / executions on the next sync) or by the user confirming in the
  UI that the order is not in TWS (audited).
- Fills come from execDetails (deduplicated by execId, only the latest
  correction revision counts) and orderStatus; commissions from
  commission(AndFees)Report. Error 321/read-only → rejected with the TWS fix.
- Cancels target only Sapient's own order ids. Emergency stop also cancels
  UNKNOWN orders by id.

## Portfolios on paper and fully automatic trading

Requested by the user on 2026-10-09: "make sure the autonomous mode works where
the portfolio is being actively managed and traded against without human
interaction if granted that level of permission".

- **Start paper trading this portfolio** (Portfolio Detail, explicit click):
  one `entry` BUY per listed holding (whole shares). Refused legs are reported,
  not forced. Sets `portfolios.paper_started_at`.
- **Fills update the portfolio** (`PaperExecutor._project_to_portfolio`):
  BUY adds shares and re-averages cost, SELL removes shares, entry fills set
  the real average cost without adding shares twice. Applied once per
  execution family (`paper_portfolio_fills`); corrections apply only their
  difference. Each fill writes a `transactions` row noted "Paper fill in …".
- **Autonomous orders** need all of: paper trading on, "allow automatic paper
  orders" ticked, global AI mode Autonomous, automatic checks on, portfolio AI
  mode Autonomous, portfolio started on paper, ASX. The checklist on the AI
  Trading page (`GET /api/paper/autonomy`) shows what is missing.
- Then the scheduler's market-hours checks turn rule hits (RSI, stop-loss,
  take-profit) straight into paper orders, sent by the connector, with every
  admission limit applied. Desktop notifications announce each automatic order
  and each fill, refusal or unknown outcome; the tray Emergency stop halts it.
- Tested end-to-end without a person in `tests/test_paper.py`
  (`test_fully_automatic_cycle_without_a_person`).

## Not yet

US shares (needs USD/FX handling); two portfolios holding the same stock are
not separately allocated (the account-level long-only check still prevents
selling more than the account holds); finding new candidates outside a
portfolio's holdings; rebalance batches to paper; live trading (separate
explicit authorisation after a paper trial).

## Additions in G1 (October 2026 audit)

- A portfolio may only sell shares that filled for it in that account
  (`portfolio_shares`); your own manual tickets are checked against the account.
- DAY orders that TWS no longer lists after the ASX close become EXPIRED (fills
  kept). If Sapient wasn't connected on the order's own trading day the order
  becomes UNKNOWN for you to check, because that day's fills are no longer visible.
- A cancel that TWS no longer lists 30 s later becomes CANCELLED.
- Emergency stop also cancels orders that were mid-send when it was pressed.
- A connection drop while waiting for TWS's answer makes the order UNKNOWN.
- Broker messages for another API client's order id (or another permId) are ignored.
- Market-data refusals (354, 10089, 10090, 10091, 10168, 10186, 10197) are
  explained instead of "no price in time".

- Limits apply to buying only (user decision 2026-10-09); see docs/live-trading.md.
