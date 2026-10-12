# IBKR TWS API — facts Sapient relies on

IBKR's full TWS API guide can be downloaded locally with
`uv run python scripts/fetch_ibkr_docs.py`. It saves about 340 pages to `docs/ibkr-tws-api/`, which is
git-ignored because the pages are IBKR's copyright. Every page can also be read
online as Markdown by adding `.md` to its URL under
`https://www.interactivebrokers.com/docs/tws-api/`. The index is `llms.txt`. Check
the guide before guessing how TWS behaves.

## Account data (`core/tws/session.py`)

- **`reqAccountSummary(reqId, "All", tags)`:**
  - Only **two** account summary subscriptions can be active at once, so Sapient cancels each one after its `accountSummaryEnd`.
  - `$LEDGER:ALL` returns every cash balance tag (`CashBalance`, `ExchangeRate`, …) once per currency. `$LEDGER` returns base currency only, and `$LEDGER:USD` returns one currency.
  - Sapient asks for the ledger on its own request ID (`REQ_LEDGER`), separate from the totals.
  - *doc/account-portfolio-data/account-summary/requesting-account-summary, account-summary-tags*
- **TWS setting "Prepend `$LEDGER-` prefix to per-currency account values"** (File → Global Configuration → API → Settings):
  - It is **on by default for new TWS users** and off for upgraded users.
  - When on, per-currency values arrive as `$LEDGER-CashBalance`, `$LEDGER-ExchangeRate`, … and account-level keys are unchanged.
  - The setting applies to every API client of that TWS. Sapient reads both forms and never asks the user to change it.
  - This was the cause of "TWS hasn't sent your USD cash balance" (0.8.0–0.8.2).
  - *doc/tws-settings/per-currency-account-value-prefix*
- **`reqAccountUpdates(True, account)`:**
  - Only **one** account can be subscribed at a time; a second request silently replaces the first.
  - It sends everything once, ending with `accountDownloadEnd`. After that it only sends changes, at most every 3 minutes.
  - Sapient subscribes, reads until `accountDownloadEnd`, then unsubscribes. It uses this only when the ledger summary has no per-currency cash.
  - *doc/account-portfolio-data/account-updates/**

## Limits

- **Message rate:** at most 50 messages per second, or TWS may disconnect (error 100).
  - *doc/pacing-limitations/*, *doc/error-handling/error-codes*
- **Market data:**
  - Delayed data needs `reqMarketDataType(3)`.
  - Live data needs a paid subscription; without one, error 10089/10168 is reported.
  - *doc/market-data-delayed/*
- **Snapshots:** IBKR documents snapshots for accounts *with an exchange
  market-data subscription*; `reqMktData(snapshot=True)` returns only what ticks
  during the 11 seconds before `tickSnapshotEnd`.
  - In practice (October 2026) delayed ASX snapshots on the paper account often
    never sent `tickSnapshotEnd` at all, and delayed US snapshots were often empty.
  - So **delayed prices (paper) are always streamed**: `reqMktData(snapshot=False)`
    on its own request id, until a usable last price, or a bid and an ask, arrive
    (up to 15 seconds), then always `cancelMktData`.
  - TWS sends **-1** for "no price right now" (often the first delayed bid/ask/last
    ticks). 0.12.2 counted those as prices and stopped waiting, so ASX orders said
    "no price"; since 0.12.3 only positive prices count. The connector log records
    every price TWS sent for each order ("Prices for KAR (ASX, …)").
  - Real-time requests (live) still snapshot first and fall back to the same
    stream if the snapshot is empty or doesn't end within 15 seconds.
  - Message **10167** ("Requested market data is not subscribed. Displaying
    delayed market data") is informational: delayed data is coming. It is not a
    permission refusal (354, 10089–10091, 10168, 10186, 10197 are).
  - TWS messages are written to the connector log
    (`%APPDATA%\Sapient\logs\tws-connector.log`).
  - If there is no delayed last trade but there is a delayed bid and ask, the
    paper limit is the middle of the two, rounded down for a buy and up for a
    sell, and the 3% gap check against Yahoo's price still applies. With no bid or
    ask at all, yesterday's close (9 / delayed 75) is used, with the same gap check.
  - *doc/market-data-live/top-of-book-l-1/streaming-data-snapshots*,
    *available-tick-types* (delayed 66 bid, 67 ask, 68 last, 75 close).
