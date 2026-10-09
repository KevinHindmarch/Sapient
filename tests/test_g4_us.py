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


class LedgerRequestTests(unittest.TestCase):
    def test_ledger_is_asked_for_separately_and_keyed_by_currency(self):
        from core.tws.session import TwsSession

        class Ledger(PaperFakeTws):
            def request(self, name, *args):
                if name == "reqAccountSummary":
                    self.summary_tags.append(args[2])
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
        fake.summary_tags = []
        session = TwsSession(fake)
        session.connect(7497, 71)
        values = session.account_summary()
        self.assertEqual(fake.summary_tags[-1], "$LEDGER:ALL")
        self.assertNotIn("$LEDGER", fake.summary_tags[0])
        self.assertEqual((values["CashBalance:USD"]["value"], values["ExchangeRate:USD"]["value"],
                          values["NetLiquidation"]["value"]), ("2787", "1.53", "5000"))


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
