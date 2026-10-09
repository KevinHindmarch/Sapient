"""Durable phase-one admission control. No broker transport or fill projector.

Only explicitly identified simulation accounts can be admitted. Queueing is not
execution; outbox commands cannot be sent by this phase. Every service call runs
in one SQLite BEGIN IMMEDIATE transaction, so all mutations (halt, admission,
pairing, lease changes) are serialized.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import secrets
import uuid

from core import db
from core.migrations import SAFETY_SCHEMA_VERSION


class SafetyError(ValueError):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__(message or code)


def _decimal(value, name, *, zero=False):
    if isinstance(value, bool):
        raise SafetyError("invalid_" + name)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise SafetyError("invalid_" + name)
    if not number.is_finite() or number < 0 or (not zero and number == 0) or number > Decimal("1000000000"):
        raise SafetyError("invalid_" + name)
    return number


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise SafetyError("invalid_" + name)
    return value


def _date(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        raise SafetyError("invalid_expiry")


def normalize_request(request):
    required = {"origin", "idempotency_key", "environment", "account_id",
                "symbol", "side", "quantity", "limit_price", "expires_at"}
    optional = {"portfolio_id", "signal_id", "order_type", "time_in_force"}
    if not isinstance(request, dict) or not required <= request.keys() or request.keys() - required - optional:
        raise SafetyError("invalid_contract", "Missing or unknown intent fields")
    r = dict(request)
    if r["environment"] != "simulation":
        raise SafetyError("real_execution_disabled", "Paper and live execution remain refused")
    if r["origin"] not in ("manual", "ai_approval", "ai_autonomous", "rebalance"):
        raise SafetyError("invalid_origin")
    for field in ("idempotency_key", "account_id", "symbol"):
        _text(r[field], field)
    r["symbol"] = r["symbol"].upper()
    if r["side"] not in ("BUY", "SELL"):
        raise SafetyError("invalid_side")
    r["order_type"] = r.get("order_type", "LMT")
    r["time_in_force"] = r.get("time_in_force", "DAY")
    if r["order_type"] != "LMT" or r["time_in_force"] != "DAY":
        raise SafetyError("limit_day_required")
    qty = _decimal(r["quantity"], "quantity")
    if qty != qty.to_integral_value():
        raise SafetyError("whole_shares_required")
    r["quantity"] = format(qty.normalize(), "f")
    r["limit_price"] = format(_decimal(r["limit_price"], "limit_price").normalize(), "f")
    r["expires_at"] = _date(r["expires_at"]).isoformat()
    for field in ("portfolio_id", "signal_id"):
        r.setdefault(field, None)
        if r[field] is not None and (type(r[field]) is not int or r[field] <= 0):
            raise SafetyError("invalid_" + field)
    if r["origin"].startswith("ai_") and (not r["signal_id"] or not r["portfolio_id"]):
        raise SafetyError("signal_and_portfolio_required")
    if r["origin"] == "rebalance" and not r["portfolio_id"]:
        raise SafetyError("portfolio_required")
    return r


def signal_request(user_id, signal, *, origin):
    expiry = signal.get("expires_at")
    if not isinstance(expiry, datetime):
        raise SafetyError("signal_expiry_required")
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return {"origin": origin, "idempotency_key": f"signal:{signal['id']}:{origin}",
            "environment": "simulation", "account_id": f"SIM:{user_id}",
            "portfolio_id": signal["portfolio_id"], "signal_id": signal["id"],
            "symbol": signal["symbol"], "side": signal["action"],
            "quantity": str(signal["quantity"]), "limit_price": str(signal["price_at_signal"]),
            "expires_at": expiry.isoformat(), "order_type": "LMT", "time_in_force": "DAY"}


class IntentService:
    def __init__(self, connection_factory=None):
        if connection_factory is None:
            from core.database import get_db_connection
            connection_factory = get_db_connection
        self.connection_factory = connection_factory

    @contextmanager
    def _tx(self):
        conn = self.connection_factory()
        try:
            with conn:
                with conn.cursor() as cur:
                    if not db.table_exists(cur, "schema_versions"):
                        raise SafetyError("migration_required", "Safety schema unavailable; execution refused")
                    cur.execute("SELECT version FROM schema_versions WHERE version=%s",
                                (SAFETY_SCHEMA_VERSION,))
                    if not cur.fetchone():
                        raise SafetyError("migration_required")
                    yield cur
        finally:
            conn.close()

    def _account(self, cur, user_id):
        cur.execute("SELECT * FROM safety_accounts WHERE user_id=%s", (user_id,))
        account = cur.fetchone()
        if not account:
            raise SafetyError("account_not_bound", "Explicit simulation account binding required")
        return account

    @staticmethod
    def _audit(cur, user_id, kind, payload):
        cur.execute("INSERT INTO safety_audit(user_id,kind,payload) VALUES(%s,%s,%s)",
                    (user_id, kind, payload))

    @staticmethod
    def _now(cur):
        return datetime.now(timezone.utc)

    def bind_simulation(self, user_id):
        """Explicit simulation identity; never converts a legacy paper/live row."""
        with self._tx() as cur:
            cur.execute("""INSERT INTO safety_accounts(user_id,account_id,environment,incarnation)
                VALUES(%s,%s,'simulation',%s) ON CONFLICT(user_id) DO NOTHING""",
                        (user_id, f"SIM:{user_id}", str(uuid.uuid4())))
            return dict(self._account(cur, user_id))

    def configure_simulation(self, user_id, *, policy, facts, valid_until):
        """Trusted server/test simulation setup, NOT exposed to device tokens.

        Facts are explicitly synthetic and must be complete. Enabled protections
        lacking reliable inputs fail closed at admission. Reconfiguration blocks
        queued intents, never silently widens a legacy policy.
        """
        expiry = _date(valid_until)
        with self._tx() as cur:
            self._account(cur, user_id)
            if expiry <= self._now(cur):
                raise SafetyError("stale_facts")
            self._invalidate(cur, user_id)
            cur.execute("""UPDATE safety_accounts SET policy=%s,facts=%s,
                facts_until=%s,policy_revision=policy_revision+1,halted=TRUE,recovery_required=TRUE
                WHERE user_id=%s""", (policy, facts, expiry, user_id))
            self._audit(cur, user_id, "simulation_policy_configured", {})

    def _owned(self, cur, user_id, r, *, retry=False):
        portfolio = None
        if r["portfolio_id"]:
            cur.execute("SELECT * FROM portfolios WHERE id=%s AND user_id=%s",
                        (r["portfolio_id"], user_id))
            portfolio = cur.fetchone()
            if not portfolio:
                raise SafetyError("portfolio_not_owned")
            if portfolio.get("status", "active") != "active":
                raise SafetyError("portfolio_inactive")
        if r["signal_id"]:
            cur.execute("SELECT * FROM ai_signals WHERE id=%s AND user_id=%s",
                        (r["signal_id"], user_id))
            signal = cur.fetchone()
            if not signal or signal["portfolio_id"] != r["portfolio_id"]:
                raise SafetyError("signal_not_owned")
            if (signal["symbol"].upper() != r["symbol"] or signal["action"].upper() != r["side"]
                    or Decimal(str(signal["quantity"])) != Decimal(r["quantity"])
                    or Decimal(str(signal["price_at_signal"])) != Decimal(r["limit_price"])):
                raise SafetyError("signal_payload_mismatch")
            if not retry:
                if signal["status"] not in ("pending", "snoozed"):
                    raise SafetyError("signal_already_claimed")
                expiry = signal["expires_at"]
                if not expiry:
                    raise SafetyError("signal_expiry_required")
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry <= self._now(cur):
                    raise SafetyError("signal_expired")
                if _date(r["expires_at"]) > expiry:
                    raise SafetyError("intent_outlives_signal")
        return portfolio

    def _policy(self, cur, user_id, account, r, portfolio, notional, now):
        if account["halted"]:
            raise SafetyError("account_halted")
        if account["recovery_required"]:
            raise SafetyError("recovery_required")
        if not account["facts_until"] or account["facts_until"] <= now:
            raise SafetyError("stale_facts")
        p, f = account["policy"], account["facts"]
        for flag in ("reconciled", "market_open", "quote_fresh", "contract_qualified",
                     "cash_settled", "fx_fresh", "loss_ok", "news_ok", "volatility_ok", "sector_ok"):
            if f.get(flag) is not True:
                raise SafetyError("protection_unavailable", flag + " is missing or unsafe")
        cur.execute("SELECT * FROM ai_trading_settings WHERE user_id=%s", (user_id,))
        legacy = cur.fetchone()
        if not legacy:
            raise SafetyError("legacy_policy_missing")
        if r["origin"].startswith("ai_"):
            modes = (legacy["mode"], portfolio["ai_mode"])
            if "off" in modes or any(m not in ("suggestions", "autonomous") for m in modes):
                raise SafetyError("ai_mode_disabled")
            if r["origin"] == "ai_autonomous" and modes != ("autonomous", "autonomous"):
                raise SafetyError("autonomy_disabled")
        if legacy["last_kill_switch_at"]:
            killed = legacy["last_kill_switch_at"].replace(tzinfo=timezone.utc)
            if (now - killed).total_seconds() < 86400:
                raise SafetyError("kill_cooldown")
        # Explicitly require policy inputs; never infer disabled protections.
        nav = _decimal(f.get("nav"), "nav")
        cash = _decimal(f.get("cash"), "cash", zero=True)
        max_count = min(int(_decimal(p.get("max_daily_trades"), "max_daily_trades", zero=True)),
                        int(_decimal(legacy["max_daily_trades"], "legacy_max_daily_trades", zero=True)))
        pct = min(_decimal(p.get("max_trade_pct"), "max_trade_pct", zero=True),
                  _decimal(legacy["max_trade_pct"], "legacy_max_trade_pct", zero=True))
        cap = nav * pct / 100
        if portfolio:
            allocated = _decimal(f.get("portfolio_values", {}).get(str(portfolio["id"])), "portfolio_value")
            cap = min(cap, allocated * pct / 100)
        if notional > cap:
            raise SafetyError("trade_limit")
        today = now.astimezone(timezone.utc).date().isoformat()
        cur.execute("""SELECT count(*) AS n,coalesce(decimal_sum(notional),'0') AS turnover
            FROM safety_intents WHERE user_id=%s AND substr(created_at,1,10)=%s""", (user_id, today))
        day = cur.fetchone()
        # Preserve the legacy user-wide scope conservatively. Historical orders
        # are evidence, never rewritten/reclassified into the simulation account.
        cur.execute("""SELECT count(*) AS n,
            coalesce(decimal_sum(abs(quantity)*coalesce(limit_price,avg_fill_price)),'0') AS turnover,
            count(*) FILTER(WHERE limit_price IS NULL AND avg_fill_price IS NULL) AS unknown
            FROM broker_orders WHERE user_id=%s AND substr(submitted_at,1,10)=%s""", (user_id, today))
        historical = cur.fetchone()
        if historical["unknown"]:
            raise SafetyError("legacy_turnover_unknown")
        if day["n"] + historical["n"] >= max_count:
            raise SafetyError("daily_trade_limit")
        turnover_pct = min(_decimal(p.get("max_daily_turnover_pct"), "turnover_pct", zero=True),
                           _decimal(legacy["max_daily_turnover_pct"], "legacy_turnover_pct", zero=True))
        if (Decimal(day["turnover"]) + Decimal(historical["turnover"]) + notional
                > nav * turnover_pct / 100):
            raise SafetyError("daily_turnover_limit")
        cur.execute("""SELECT coalesce(decimal_sum(notional) FILTER(WHERE side='BUY'),'0') AS cash,
            coalesce(decimal_sum(quantity) FILTER(WHERE side='SELL' AND symbol=%s),'0') AS shares
            FROM safety_reservations WHERE user_id=%s AND released_at IS NULL""", (r["symbol"], user_id))
        reserved = {k: Decimal(v) for k, v in cur.fetchone().items()}
        if r["side"] == "BUY" and reserved["cash"] + notional > cash:
            raise SafetyError("insufficient_cash")
        if r["side"] == "SELL":
            shares = _decimal(f.get("positions", {}).get(r["symbol"]), "available_shares", zero=True)
            if reserved["shares"] + Decimal(r["quantity"]) > shares:
                raise SafetyError("insufficient_shares")

    def admit(self, user_id, request):
        r = normalize_request(request)
        digest = hashlib.sha256(json.dumps(r, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self._tx() as cur:
            account = self._account(cur, user_id)
            if r["account_id"] != account["account_id"]:
                raise SafetyError("account_not_owned")
            cur.execute("SELECT * FROM safety_intents WHERE user_id=%s AND idempotency_key=%s",
                        (user_id, r["idempotency_key"]))
            existing = cur.fetchone()
            portfolio = self._owned(cur, user_id, r, retry=bool(existing))
            if existing:
                if existing["payload_hash"] != digest:
                    raise SafetyError("idempotency_conflict")
                return dict(existing)
            now = self._now(cur)
            if _date(r["expires_at"]) <= now:
                raise SafetyError("intent_expired")
            notional = Decimal(r["quantity"]) * Decimal(r["limit_price"])
            self._policy(cur, user_id, account, r, portfolio, notional, now)
            intent_id = str(uuid.uuid4())
            cur.execute("""INSERT INTO safety_intents(id,user_id,account_id,origin,idempotency_key,
                payload,payload_hash,portfolio_id,signal_id,policy_revision,incarnation,notional,expires_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                        (intent_id, user_id, account["account_id"], r["origin"], r["idempotency_key"],
                         r, digest, r["portfolio_id"], r["signal_id"], account["policy_revision"],
                         account["incarnation"], notional, _date(r["expires_at"])))
            result = dict(cur.fetchone())
            cur.execute("""INSERT INTO safety_reservations(intent_id,user_id,symbol,side,quantity,notional)
                VALUES(%s,%s,%s,%s,%s,%s)""",
                        (intent_id, user_id, r["symbol"], r["side"], r["quantity"], notional))
            cur.execute("INSERT INTO safety_outbox(user_id,intent_id,kind,payload) VALUES(%s,%s,'intent',%s)",
                        (user_id, intent_id, {"intent_id": intent_id, "execution_enabled": False}))
            if r["signal_id"]:
                cur.execute("""UPDATE ai_signals SET status='claimed',decided_at=clock_timestamp(),
                    decided_by='intent_service' WHERE id=%s""", (r["signal_id"],))
            self._audit(cur, user_id, "intent_admitted", {"intent_id": intent_id, "origin": r["origin"]})
            return result

    def _invalidate(self, cur, user_id):
        cur.execute("UPDATE safety_intents SET state='BLOCKED' WHERE user_id=%s AND state='QUEUED'", (user_id,))
        cur.execute("""UPDATE safety_reservations SET released_at=clock_timestamp()
            WHERE user_id=%s AND released_at IS NULL AND intent_id IN
            (SELECT id FROM safety_intents WHERE user_id=%s AND state='BLOCKED')""", (user_id, user_id))

    def admit_batch(self, user_id, idempotency_key, requests):
        """One transaction/lock covers the reviewed plan and every leg reservation."""
        _text(idempotency_key, "batch_key")
        if not isinstance(requests, list) or not 1 <= len(requests) <= 100:
            raise SafetyError("invalid_batch")
        normalized = [normalize_request(r) for r in requests]
        if len({r["idempotency_key"] for r in normalized}) != len(normalized):
            raise SafetyError("duplicate_batch_leg")
        digest = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
        with self._tx() as cur:
            self._account(cur, user_id)
            cur.execute("SELECT * FROM safety_batches WHERE user_id=%s AND idempotency_key=%s",
                        (user_id, idempotency_key))
            old = cur.fetchone()
            if old and old["payload_hash"] != digest:
                raise SafetyError("batch_idempotency_conflict")
            # Transaction-scoped adapter reuses exactly this cursor; no nested
            # connection, commit or rollback. Any leg error rolls back the plan.
            class TransactionService(IntentService):
                @contextmanager
                def _tx(inner):
                    yield cur
            scoped = TransactionService(self.connection_factory)
            results = [scoped.admit(user_id, r) for r in normalized]
            if not old:
                for intent in results:
                    cur.execute("""SELECT 1 FROM safety_batches, json_each(safety_batches.intent_ids) AS leg
                        WHERE safety_batches.user_id=%s AND leg.value=%s""", (user_id, intent["id"]))
                    if cur.fetchone():
                        raise SafetyError("leg_already_in_batch")
                cur.execute("""INSERT INTO safety_batches(user_id,idempotency_key,payload_hash,intent_ids)
                    VALUES(%s,%s,%s,%s)""", (user_id, idempotency_key, digest, [r["id"] for r in results]))
                self._audit(cur, user_id, "batch_admitted", {"key": idempotency_key, "count": len(results)})
            return results

    def halt(self, user_id):
        with self._tx() as cur:
            # Halt also persists before the first simulation bind.
            cur.execute("""INSERT INTO safety_accounts(user_id,account_id,environment,incarnation)
                VALUES(%s,%s,'simulation',%s) ON CONFLICT(user_id) DO NOTHING""",
                        (user_id, f"SIM:{user_id}", str(uuid.uuid4())))
            self._account(cur, user_id)
            cur.execute("""UPDATE safety_accounts SET halted=TRUE,halted_at=clock_timestamp(),
                epoch=epoch+1 WHERE user_id=%s""", (user_id,))
            self._invalidate(cur, user_id)
            cur.execute("""UPDATE ai_signals SET status='expired',decided_at=clock_timestamp(),
                decided_by='kill_switch' WHERE user_id=%s AND status IN ('pending','snoozed','claimed')
                RETURNING id""", (user_id,))
            signals = len(cur.fetchall())
            cur.execute("""INSERT INTO ai_trading_settings(user_id) VALUES(%s)
                ON CONFLICT(user_id) DO NOTHING""", (user_id,))
            cur.execute("""UPDATE ai_trading_settings SET mode='off',last_kill_switch_at=clock_timestamp(),
                updated_at=clock_timestamp() WHERE user_id=%s""", (user_id,))
            cur.execute("UPDATE portfolios SET ai_mode='off' WHERE user_id=%s", (user_id,))
            cur.execute("""INSERT INTO safety_outbox(user_id,kind,payload)
                VALUES(%s,'halt',%s)""", (user_id, {"cancel_owned_orders": True}))
            cur.execute("""SELECT count(*) AS n FROM broker_orders WHERE user_id=%s
                AND status IN ('Submitted','PendingSubmit','PreSubmitted','PartiallyFilled')""", (user_id,))
            residual = cur.fetchone()["n"]
            from core.tws import paper
            paper_working = paper.halt(cur)  # stop paper trading; cancel Sapient's own working paper orders
            self._audit(cur, user_id, "halt_persisted", {"legacy_unconfirmed_orders": residual,
                                                         "paper_orders_to_cancel": paper_working})
            message = "Halt persisted. No broker cancellations confirmed. Use TWS/IBKR for broker orders."
            if paper_working:
                message = (f"Halt persisted. Cancel requested for {paper_working} working paper order(s); "
                           "TWS confirms each cancel separately (see Paper orders). Orders can fill before "
                           "the cancel arrives. Check TWS if in doubt.")
            return {"halt_persisted": True, "worker_acknowledged": False,
                    "cancel_requested": True, "broker_confirmed": False,
                    "cancelled_signals": signals, "cancelled_orders": 0,
                    "paper_orders_cancel_requested": paper_working,
                    "remaining_unconfirmed_orders": residual + paper_working,
                    "cancellation_available": paper_working > 0,
                    "message": message}

    def resume(self, user_id):
        with self._tx() as cur:
            a = self._account(cur, user_id)
            now = self._now(cur)
            if a["halted_at"] and (now-a["halted_at"]).total_seconds() < 86400:
                raise SafetyError("kill_cooldown")
            if a["recovery_required"] or a["facts"].get("reconciled") is not True:
                raise SafetyError("recovery_required")
            if not a["facts_until"] or a["facts_until"] <= now:
                raise SafetyError("stale_facts")
            cur.execute("UPDATE safety_accounts SET halted=FALSE WHERE user_id=%s", (user_id,))
            self._audit(cur, user_id, "explicit_resume", {})
            return {"halted": False, "execution_enabled": False}

    def reconcile_simulation(self, user_id, *, expected_incarnation):
        """Trusted explicit simulation review; never a broker reconciliation claim."""
        with self._tx() as cur:
            a = self._account(cur, user_id)
            if a["incarnation"] != expected_incarnation or a["facts"].get("reconciled") is not True:
                raise SafetyError("recovery_required")
            cur.execute("UPDATE safety_accounts SET recovery_required=FALSE WHERE user_id=%s", (user_id,))
            self._audit(cur, user_id, "simulation_reconciled", {"incarnation": expected_incarnation})

    def restore_lock(self, user_id):
        """Required operator restore hook: rotates identity and invalidates authority."""
        with self._tx() as cur:
            self._account(cur, user_id)
            incarnation = str(uuid.uuid4())
            cur.execute("""UPDATE safety_accounts SET halted=TRUE,recovery_required=TRUE,
                incarnation=%s,epoch=epoch+1 WHERE user_id=%s""", (incarnation, user_id))
            self._invalidate(cur, user_id)
            cur.execute("UPDATE safety_devices SET revoked_at=clock_timestamp() WHERE user_id=%s", (user_id,))
            cur.execute("DELETE FROM safety_leases WHERE user_id=%s", (user_id,))
            self._audit(cur, user_id, "restore_lock", {"incarnation": incarnation})
            return {"incarnation": incarnation, "recovery_required": True}

    def cancel(self, user_id, intent_id):
        with self._tx() as cur:
            self._account(cur, user_id)
            cur.execute("SELECT * FROM safety_intents WHERE id=%s AND user_id=%s", (intent_id, user_id))
            intent = cur.fetchone()
            if not intent:
                raise SafetyError("intent_not_owned")
            if intent["state"] == "QUEUED":
                cur.execute("UPDATE safety_intents SET state='BLOCKED' WHERE id=%s", (intent_id,))
                cur.execute("UPDATE safety_reservations SET released_at=clock_timestamp() WHERE intent_id=%s",
                            (intent_id,))
            else:
                cur.execute("INSERT INTO safety_outbox(user_id,intent_id,kind,payload) VALUES(%s,%s,'cancel',%s)",
                            (user_id, intent_id, {"broker_confirmed": False}))
            self._audit(cur, user_id, "cancel_requested", {"intent_id": intent_id})
            return {"intent_id": intent_id, "cancel_requested": True, "broker_confirmed": False}

    def list_intents(self, user_id):
        with self._tx() as cur:
            cur.execute("SELECT * FROM safety_intents WHERE user_id=%s ORDER BY created_at DESC LIMIT 200", (user_id,))
            return [dict(row) for row in cur.fetchall()]

    def create_pairing(self, user_id):
        token = secrets.token_urlsafe(32)
        with self._tx() as cur:
            self._account(cur, user_id)
            cur.execute("""INSERT INTO safety_pairings(token_hash,user_id,expires_at)
                VALUES(%s,%s,%s)""", (hashlib.sha256(token.encode()).hexdigest(), user_id,
                                      self._now(cur) + timedelta(minutes=5)))
            self._audit(cur, user_id, "pairing_created", {})
        return {"pairing_token": token, "expires_in": 300}

    def pair_device(self, user_id, pairing_token):
        device_id, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
        with self._tx() as cur:
            self._account(cur, user_id)
            cur.execute("""UPDATE safety_pairings SET used_at=clock_timestamp()
                WHERE token_hash=%s AND user_id=%s AND used_at IS NULL
                AND expires_at>clock_timestamp() RETURNING user_id""",
                        (hashlib.sha256(pairing_token.encode()).hexdigest(), user_id))
            if not cur.fetchone():
                raise SafetyError("pairing_invalid")
            cur.execute("""INSERT INTO safety_devices(id,user_id,token_hash,scopes)
                VALUES(%s,%s,%s,%s)""", (device_id, user_id, hashlib.sha256(token.encode()).hexdigest(),
                                       ["events:write", "commands:read", "lease:renew"]))
            self._audit(cur, user_id, "device_paired", {"device_id": device_id})
        return {"device_id": device_id, "device_token": token}

    def _device(self, cur, user_id, token, scope):
        cur.execute("""SELECT * FROM safety_devices WHERE user_id=%s AND token_hash=%s
            AND revoked_at IS NULL""", (user_id, hashlib.sha256(token.encode()).hexdigest()))
        device = cur.fetchone()
        if not device or scope not in device["scopes"]:
            raise SafetyError("device_scope_denied")
        return device

    def revoke_device(self, user_id, device_id):
        with self._tx() as cur:
            self._account(cur, user_id)
            cur.execute("""UPDATE safety_devices SET revoked_at=clock_timestamp()
                WHERE id=%s AND user_id=%s RETURNING id""", (device_id, user_id))
            if not cur.fetchone():
                raise SafetyError("device_not_owned")
            cur.execute("""UPDATE safety_accounts SET halted=TRUE,recovery_required=TRUE,
                epoch=epoch+1 WHERE user_id=%s""", (user_id,))
            self._invalidate(cur, user_id)
            self._audit(cur, user_id, "device_revoked", {"device_id": device_id})
            return {"revoked": True, "recovery_required": True, "broker_confirmed": False}

    def renew_lease(self, user_id, device_token, *, incarnation, epoch=None):
        with self._tx() as cur:
            a = self._account(cur, user_id)
            d = self._device(cur, user_id, device_token, "lease:renew")
            if a["halted"] or a["recovery_required"] or incarnation != a["incarnation"]:
                raise SafetyError("lease_refused")
            cur.execute("SELECT * FROM safety_leases WHERE user_id=%s", (user_id,))
            old = cur.fetchone()
            if old and (old["device_id"] != d["id"] or old["epoch"] != a["epoch"]
                        or epoch != old["epoch"] or old["expires_at"] <= self._now(cur)):
                # Expiry is NOT isolation evidence. No takeover or expired renewal.
                raise SafetyError("executor_isolation_required")
            cur.execute("""INSERT INTO safety_leases(user_id,device_id,epoch,incarnation,expires_at)
                VALUES(%s,%s,%s,%s,%s)
                ON CONFLICT(user_id) DO UPDATE SET expires_at=EXCLUDED.expires_at RETURNING *""",
                        (user_id, d["id"], a["epoch"], incarnation, self._now(cur) + timedelta(seconds=30)))
            result = dict(cur.fetchone())
            result["execution_enabled"] = False
            return result

    def poll_commands(self, user_id, device_token):
        """Narrow scope; phase one only delivers stop, never executable orders."""
        with self._tx() as cur:
            self._account(cur, user_id)
            self._device(cur, user_id, device_token, "commands:read")
            cur.execute("""SELECT * FROM safety_outbox WHERE user_id=%s AND kind IN ('halt','cancel')
                AND delivered_at IS NULL ORDER BY CASE WHEN kind='halt' THEN 0 ELSE 1 END,id LIMIT 100""",
                        (user_id,))
            return [dict(r) for r in cur.fetchall()]

    def upload_evidence(self, user_id, device_token, evidence):
        """Durable authenticated quarantine only, never an economic projection.

        Revocation removes command authority but retains provenance for late
        evidence. Acknowledgement means cloud storage committed, not broker
        confirmation or permission to resume.
        """
        if not isinstance(evidence, dict) or set(evidence) != {
                "journal_incarnation", "sequence", "epoch", "account_id", "kind", "data"}:
            raise SafetyError("invalid_evidence_contract")
        _text(evidence["journal_incarnation"], "journal_incarnation")
        if type(evidence["sequence"]) is not int or evidence["sequence"] <= 0:
            raise SafetyError("invalid_sequence")
        if type(evidence["epoch"]) is not int or evidence["epoch"] < 0:
            raise SafetyError("invalid_epoch")
        if evidence["kind"] not in ("acknowledgement", "fill", "cancellation", "halt_ack"):
            raise SafetyError("invalid_evidence_kind")
        encoded = json.dumps(evidence, sort_keys=True, allow_nan=False)
        if len(encoded) > 65536:
            raise SafetyError("evidence_too_large")
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self._tx() as cur:
            a = self._account(cur, user_id)
            cur.execute("SELECT * FROM safety_devices WHERE user_id=%s AND token_hash=%s",
                        (user_id, hashlib.sha256(device_token.encode()).hexdigest()))
            d = cur.fetchone()
            if not d or "events:write" not in d["scopes"]:
                raise SafetyError("device_scope_denied")
            if evidence["account_id"] != a["account_id"]:
                raise SafetyError("account_not_owned")
            cur.execute("""SELECT * FROM safety_evidence WHERE device_id=%s
                AND journal_incarnation=%s AND sequence=%s""",
                        (d["id"], evidence["journal_incarnation"], evidence["sequence"]))
            old = cur.fetchone()
            if old:
                if old["payload_hash"] != digest:
                    raise SafetyError("evidence_conflict")
                return {"stored": True, "sequence": evidence["sequence"], "quarantined": True}
            cur.execute("""SELECT coalesce(max(sequence),0) AS sequence FROM safety_evidence
                WHERE device_id=%s AND journal_incarnation=%s""", (d["id"], evidence["journal_incarnation"]))
            if cur.fetchone()["sequence"] + 1 != evidence["sequence"]:
                raise SafetyError("evidence_sequence_gap")
            cur.execute("""INSERT INTO safety_evidence(user_id,device_id,journal_incarnation,sequence,
                payload_hash,payload) VALUES(%s,%s,%s,%s,%s,%s)""",
                        (user_id, d["id"], evidence["journal_incarnation"], evidence["sequence"],
                         digest, evidence))
            self._audit(cur, user_id, "evidence_quarantined",
                        {"device_id": d["id"], "sequence": evidence["sequence"]})
            return {"stored": True, "sequence": evidence["sequence"], "quarantined": True}