"""Phase G4: US shares on paper and live (SMART/USD, US hours, US$ cash, A$ limits via TWS's rate)."""

from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest import mock

from core.tws import markets, paper, store
from core.tws.execution import choose_limit

import test_paper
from test_paper import ACCOUNT, PaperFakeTws

PaperTestCase = test_paper.PaperTestCase


def ledger(usd_cash="5000", rate="1.5"):
    return {"NetLiquidation": {"value": "1000000", "currency": "AUD"},
            "TotalCashValue": {"value": "50000", "currency": "AUD"},
            "CashBalance:AUD": {"value": "42500", "currency": "AUD"},
            "CashBalance:USD": {"value": usd_cash, "currency": "USD"},
            "ExchangeRate:USD": {"value": rate, "currency": "USD"}}


class MarketTests(unittest.TestCase):
    def test_symbols_ticks_and_names(self):
        self.assertEqual(markets.for_symbol("BHP.AX"), markets.ASX)
        self.assertEqual(markets.for_symbol("brk-b"), markets.US)
        self.assertIsNone(markets.for_symbol("NOT A STOCK"))
        self.assertEqual(markets.ib_symbol("BRK-B"), "BRK B")
        self.assertEqual(markets.tick(markets.US, Decimal("0.5")), Decimal("0.0001"))
        limit, _ = choose_limit("BUY", {"68": 187.456}, Decimal("187.40"), Decimal("3"), markets.US)
        self.assertEqual(limit, Decimal("187.45"))


class UsAdmissionTests(PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise(max_order_value=2000, max_value_per_day=100000)
        store.save_snapshot("summary", ledger())

    def test_limits_in_aud_and_usd_cash(self):
        order = self.order(key="u1", symbol="AAPL", quantity=6, price="200")       # 6x200x1.03x1.5 = A$1,854
        self.assertEqual((order["exchange"], order["currency"]), ("SMART", "USD"))
        error = self.refused("order_too_large", self.order, key="u2", symbol="AAPL", quantity=7, price="200")
        self.assertIn("US$", str(error))
        store.save_snapshot("summary", ledger(usd_cash="100"))
        error = self.refused("insufficient_cash", self.order, key="u3", symbol="MSFT", quantity=1, price="400")
        self.assertIn("Convert A$ to US$ in TWS", str(error))
        summary = ledger()
        del summary["CashBalance:USD"]
        summary["_cash_source"] = {"value": "none", "currency": None, "detail": "ledger: 3 values, cash in AUD"}
        store.save_snapshot("summary", summary)
        error = self.refused("no_account_values", self.order, key="u4", symbol="MSFT", quantity=1, price="400")
        self.assertIn("What TWS sent: ledger: 3 values, cash in AUD", str(error))

    def test_us_hours_apply_to_us_orders(self):
        with mock.patch("core.tws.paper.calendar.is_open", side_effect=lambda m, now: m.name == "ASX"):
            self.order(key="a1", symbol="CBA.AX", quantity=2, price="45")
            self.refused("market_closed", self.order, key="u4", symbol="AAPL", quantity=1, price="200")


class ExchangeRateFallbackTests(PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise(max_order_value=2000, max_value_per_day=100000)
        summary = ledger()
        del summary["ExchangeRate:USD"]                                     # TWS sent no rate
        store.save_snapshot("summary", summary)

    def test_yahoo_rate_with_a_cautious_margin_when_tws_sends_none(self):
        with mock.patch("core.yahoo.Ticker") as ticker:
            import pandas as pd
            ticker.return_value.history.return_value = pd.DataFrame({"Close": [0.65]})
            rate = markets.yahoo_rate_to_aud("USD")
            self.assertEqual(rate, (Decimal(1) / Decimal("0.65") * Decimal("1.02")).quantize(Decimal("0.000001")))
            self.order(key="u1", symbol="AAPL", quantity=5, price="200")      # 5x200x1.03x1.569 ~ A$1,616
            self.refused("order_too_large", self.order, key="u2", symbol="AAPL", quantity=7, price="200")
        with mock.patch("core.tws.markets.yahoo_rate_to_aud", return_value=None):
            self.refused("no_exchange_rate", self.order, key="u3", symbol="AAPL", quantity=1, price="200")


class UsTicketRouteTests(PaperTestCase):
    def test_short_us_codes_are_accepted_by_the_ticket(self):
        import os
        from fastapi.testclient import TestClient
        from backend.main import app
        self.authorise(max_order_value=2000, max_value_per_day=100000)
        store.save_snapshot("summary", ledger())
        token = "u" * 40
        with mock.patch.dict(os.environ, {"SAPIENT_API_TOKEN": token, "SAPIENT_SKIP_MIGRATIONS": "1"}), \
                mock.patch("backend.routers.paper._reference_price", return_value=120.0):
            client = TestClient(app, base_url="http://127.0.0.1")
            placed = client.post("/api/paper/orders", headers={"Authorization": f"Bearer {token}"},
                                 json={"symbol": "MS", "side": "BUY", "quantity": 5})
        self.assertEqual(placed.status_code, 202, placed.text)
        self.assertEqual((placed.json()["symbol"], placed.json()["currency"]), ("MS", "USD"))


class LedgerRequestTests(unittest.TestCase):
    def test_ledger_is_asked_for_separately_and_keyed_by_currency(self):
        from core.tws.session import TwsSession

        class Ledger(PaperFakeTws):
            def request(self, name, *args):
                if name == "reqAccountSummary":
                    self.summary_tags.append(args[2])
                    self.summary_ids.append(args[0])
                    req = args[0]
                    if args[2] == "$LEDGER:ALL":
                        for cur, cash, rate in (("AUD", "1000", "1"), ("USD", "2787", "1.53")):
                            self.emit("accountSummary", reqId=req, account=ACCOUNT, tag="CashBalance", value=cash, currency=cur)
                            self.emit("accountSummary", reqId=req, account=ACCOUNT, tag="ExchangeRate", value=rate, currency=cur)
                    else:
                        self.emit("accountSummary", reqId=req, account=ACCOUNT, tag="NetLiquidation", value="5000", currency="AUD")
                    self.emit("accountSummaryEnd", reqId=req)
                    return
                super().request(name, *args)
        fake = Ledger()
        fake.summary_tags, fake.summary_ids = [], []
        session = TwsSession(fake)
        session.connect(7497, 71)
        values = session.account_summary()
        self.assertEqual(fake.summary_tags[-1], "$LEDGER:ALL")
        self.assertNotIn("$LEDGER", fake.summary_tags[0])
        self.assertEqual((values["CashBalance:USD"]["value"], values["ExchangeRate:USD"]["value"],
                          values["NetLiquidation"]["value"]), ("2787", "1.53", "5000"))
        self.assertEqual(len(set(fake.summary_ids)), 2)                      # the ledger has its own request id
        self.assertNotIn("reqAccountUpdates", fake.requests)

    def test_account_updates_fill_in_when_tws_refuses_the_ledger(self):
        from core.tws.session import TwsSession

        class NoLedger(PaperFakeTws):
            def request(self, name, *args):
                if name == "reqAccountSummary" and args[2] == "$LEDGER:ALL":
                    self.emit("error", reqId=args[0], errorCode=322, errorString="Duplicate ticker id")
                    return
                if name == "reqAccountUpdates" and args[0]:
                    self.requests.append(name)
                    for key, value, cur in (("CashBalance", "23704", "USD"), ("ExchangeRate", "1.434", "USD"),
                                            ("CashBalance", "1.2", "BASE"), ("NetLiquidation", "9", "AUD")):
                        self.emit("updateAccountValue", key=key, val=value, currency=cur, accountName=ACCOUNT)
                    self.emit("accountDownloadEnd", accountName=ACCOUNT)
                    return
                super().request(name, *args)
        fake = NoLedger()
        session = TwsSession(fake)
        session.connect(7497, 71)
        values = session.account_summary(timeout=2)
        self.assertEqual((values["CashBalance:USD"]["value"], values["ExchangeRate:USD"]["value"]), ("23704", "1.434"))
        self.assertNotIn("CashBalance:BASE", values)
        self.assertEqual(values["_cash_source"]["value"], "account_updates")
        self.assertIn("ledger: TWS refused", values["_cash_source"]["detail"])
        self.assertNotIn("NetLiquidation:AUD", values)
        self.assertEqual(values["NetLiquidation"]["value"], "1000000")


class LedgerPrefixTests(unittest.TestCase):
    """TWS setting "Prepend $LEDGER- prefix to per-currency account values" (default for new TWS users)."""

    def session_with(self, ledger_rows, update_rows):
        from core.tws.session import TwsSession

        class Prefixed(PaperFakeTws):
            def request(self, name, *args):
                if name == "reqAccountSummary" and args[2] == "$LEDGER:ALL":
                    for tag, value, cur in ledger_rows:
                        self.emit("accountSummary", reqId=args[0], account=ACCOUNT, tag=tag, value=value, currency=cur)
                    self.emit("accountSummaryEnd", reqId=args[0])
                    return
                if name == "reqAccountUpdates" and args[0]:
                    for key, value, cur in update_rows:
                        self.emit("updateAccountValue", key=key, val=value, currency=cur, accountName=ACCOUNT)
                    self.emit("accountDownloadEnd", accountName=ACCOUNT)
                    return
                super().request(name, *args)
        session = TwsSession(Prefixed())
        session.connect(7497, 71)
        return session.account_summary(timeout=2)

    def test_prefixed_ledger_summary_rows(self):
        values = self.session_with([("$LEDGER-CashBalance", "23704", "USD"), ("$LEDGER-ExchangeRate", "1.434", "USD")], [])
        self.assertEqual((values["CashBalance:USD"]["value"], values["ExchangeRate:USD"]["value"]), ("23704", "1.434"))
        self.assertEqual(values["_cash_source"]["value"], "ledger")

    def test_prefixed_account_updates_win_over_account_totals(self):
        values = self.session_with([], [("CashBalance", "990802", "USD"),              # account-level total
                                        ("$LEDGER-CashBalance", "23704", "USD"),
                                        ("$LEDGER-ExchangeRate", "1.434", "USD")])
        self.assertEqual((values["CashBalance:USD"]["value"], values["ExchangeRate:USD"]["value"]), ("23704", "1.434"))
        self.assertEqual(values["_cash_source"]["value"], "account_updates")


class UsExecutorTests(PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise(max_order_value=2000, max_value_per_day=100000)
        store.save_snapshot("summary", ledger())

    def test_sent_smart_in_usd_to_the_primary_listing(self):
        class TwoListings(PaperFakeTws):
            def request(self, name, *args):
                if name == "reqContractDetails":
                    self.requests.append(name)
                    for primary in ("NASDAQ", "MEXI"):
                        details = SimpleNamespace(contract=SimpleNamespace(
                            conId=265598 if primary == "NASDAQ" else 1, symbol="AAPL", secType="STK", exchange="SMART",
                            primaryExchange=primary, currency="USD", localSymbol="AAPL"))
                        self.emit("contractDetails", reqId=args[0], contractDetails=details)
                    self.emit("contractDetailsEnd", reqId=args[0])
                    return
                super().request(name, *args)
        fake = TwoListings(last=187.456)
        self.order(key="u5", symbol="AAPL", quantity=3, price="187.40")
        test_paper.ExecutorTests.executor(self, fake).step()
        order_id, contract, ib_order = fake.placed[0]
        self.assertEqual((contract.exchange, contract.currency, contract.primaryExchange, contract.conId),
                         ("SMART", "USD", "NASDAQ", 265598))
        self.assertEqual(ib_order.lmtPrice, 187.45)
        sent = paper.list_orders()[0]
        self.assertEqual((sent["limit_price"], sent["currency"], sent["state"]), (Decimal("187.45"), "USD", "SUBMITTED"))


if __name__ == "__main__":
    unittest.main()
