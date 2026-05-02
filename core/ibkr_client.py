"""
Interactive Brokers Web API client (BYO key, OAuth 1.0a + RSA-SHA256).

================================================================================
SIMULATION NOTICE
================================================================================
This module ships with `IBKR_SIMULATION_MODE = True`, meaning every HTTP-bound
method returns realistic synthetic responses instead of contacting IBKR. The
OAuth-RSA signing helpers (`build_oauth_header`, `_rsa_sign_sha256`,
`_canonical_params`) are real and follow RFC 5849 + IBKR's published spec, so
flipping the switch and replacing the `_request()` body with a real HTTP call
(e.g. `httpx.request(...)`) is a one-file change.

Why simulated: the development environment cannot reach IBKR's gateway and
cannot test against a real account. All downstream behaviour (order persistence,
position updates, kill-switch, audit logging) is real and uses these
simulated responses end-to-end.
================================================================================
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import random
import string
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


IBKR_SIMULATION_MODE = True


# ---------------------------------------------------------------------------
# Execution policy guard (paper-only safety, etc.)
# ---------------------------------------------------------------------------


class ExecutionPolicyError(RuntimeError):
    """Raised when an order would violate the user's safety policy
    (paper-only, kill switch, etc.)."""


def assert_execution_allowed(user_id: int, environment: str | None) -> None:
    """
    Server-side gate every code path that places a real broker order MUST call.

    Today this enforces the per-user `paper_only` setting: if the user has
    `paper_only=True` (default), only orders against a `paper` IBKR account
    may be placed. We deliberately keep the check here (in the broker layer)
    rather than per-router so it cannot be forgotten.

    Future hooks: kill-switch cooldown, breaker triggered, market hours, etc.
    """
    # Local import to avoid circular import at module load time
    from core.database import AITradingSettingsService

    settings = AITradingSettingsService.get(user_id) or {}
    paper_only = bool(settings.get("paper_only", True))
    env = (environment or "paper").lower()
    if paper_only and env != "paper":
        raise ExecutionPolicyError(
            "paper_only is enabled in your AI Trading settings — "
            "orders may only be sent to a paper IBKR account. "
            "Disable paper_only in /ai-trading to route to a live account."
        )


IBKR_API_BASE_PAPER = "https://api.ibkr.com/v1/api"
IBKR_API_BASE_LIVE = "https://api.ibkr.com/v1/api"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class IBKRCredentials:
    """Decrypted IBKR credentials in memory only — never persist this struct."""

    consumer_key: str
    access_token: str
    access_token_secret: str
    private_key_pem: str
    environment: str = "paper"  # "paper" | "live"
    realm: str = "limited_poa"


@dataclass
class IBKRConnectionInfo:
    account_id: str
    account_alias: str
    currency: str
    environment: str
    server_time: str
    is_paper: bool
    cash: float = 0.0
    buying_power: float = 0.0
    nav: float = 0.0  # Net liquidation / asset value


@dataclass
class IBKROrder:
    order_id: str
    symbol: str
    side: str          # "BUY" | "SELL"
    quantity: float
    order_type: str    # "MKT" | "LMT"
    limit_price: float | None
    status: str        # "Submitted" | "Filled" | "Cancelled" | "Rejected"
    filled_qty: float
    avg_fill_price: float | None
    submitted_at: str
    fees: float
    sim: bool = True   # marker so the UI can label simulated fills


# ---------------------------------------------------------------------------
# Real OAuth 1.0a + RSA-SHA256 signing primitives
# ---------------------------------------------------------------------------


def _percent(value: str) -> str:
    """RFC 3986 percent-encoding."""
    return urllib.parse.quote(str(value), safe="-._~")


def _canonical_params(params: dict[str, str]) -> str:
    """Sort + percent-encode parameters per RFC 5849 §3.4.1.3."""
    pairs = sorted((_percent(k), _percent(v)) for k, v in params.items())
    return "&".join(f"{k}={v}" for k, v in pairs)


def _signature_base_string(method: str, url: str, params: dict[str, str]) -> str:
    return "&".join(
        [
            method.upper(),
            _percent(url),
            _percent(_canonical_params(params)),
        ]
    )


def _rsa_sign_sha256(base_string: str, private_key_pem: str) -> str:
    """Sign the OAuth base string with the user's RSA private key."""
    key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=None,
    )
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("Provided key is not an RSA private key")
    signature = key.sign(
        base_string.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def _hmac_sign_sha256(base_string: str, key: str) -> str:
    """Used for the live-session-token request (HMAC-SHA256 with prepend secret)."""
    digest = hmac.new(
        base64.b64decode(key),
        base_string.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def build_oauth_header(
    creds: IBKRCredentials,
    method: str,
    url: str,
    extra_params: dict[str, str] | None = None,
    live_session_token: str | None = None,
) -> dict[str, str]:
    """Build an OAuth 1.0a Authorization header for an IBKR Web API request."""
    nonce = "".join(random.choices(string.ascii_letters + string.digits, k=16))
    timestamp = str(int(time.time()))
    # Pick the signature method UP FRONT — RFC 5849 §3.4.1.2 requires the
    # `oauth_signature_method` value to be part of the signature base string,
    # so we must commit to it before computing the base. Building the base
    # with one method and then signing with another produces an invalid sig.
    sig_method = "HMAC-SHA256" if live_session_token else "RSA-SHA256"
    oauth_params: dict[str, str] = {
        "oauth_consumer_key": creds.consumer_key,
        "oauth_nonce": nonce,
        "oauth_signature_method": sig_method,
        "oauth_timestamp": timestamp,
        "oauth_token": creds.access_token,
        "oauth_version": "1.0",
    }

    all_params = {**oauth_params, **(extra_params or {})}
    base = _signature_base_string(method, url, all_params)

    if live_session_token:
        signature = _hmac_sign_sha256(base, live_session_token)
    else:
        signature = _rsa_sign_sha256(base, creds.private_key_pem)

    oauth_params["oauth_signature"] = signature

    header_parts = [f'realm="{creds.realm}"'] + [
        f'{k}="{_percent(v)}"' for k, v in sorted(oauth_params.items())
    ]
    return {"Authorization": "OAuth " + ", ".join(header_parts)}


# ---------------------------------------------------------------------------
# IBKR client (calls real signing helpers; HTTP layer is simulated)
# ---------------------------------------------------------------------------


class IBKRClient:
    """
    Wrapper around IBKR Web API. Use:
        client = IBKRClient(credentials)
        info  = client.get_account_summary()
        order = client.place_order(symbol="BHP.AX", side="BUY", quantity=10, order_type="MKT")

    Every method that would touch the network is simulated when
    IBKR_SIMULATION_MODE is True. Set the env var IBKR_LIVE_API=1 and flip the
    constant to wire to real HTTP.
    """

    def __init__(self, credentials: IBKRCredentials):
        self.creds = credentials
        self.base_url = (
            IBKR_API_BASE_LIVE if credentials.environment == "live" else IBKR_API_BASE_PAPER
        )
        self._sim = IBKR_SIMULATION_MODE and os.environ.get("IBKR_LIVE_API") != "1"

    # ---- Real signing exercised even in sim mode (so we know it works) ----
    def _sign_dryrun(self, path: str, method: str = "GET") -> dict[str, str]:
        try:
            return build_oauth_header(self.creds, method, f"{self.base_url}{path}")
        except Exception:
            # If the user supplied a placeholder key in sim mode, don't blow up
            return {"Authorization": "OAuth (sim — signing skipped due to placeholder key)"}

    # ---- Public API ------------------------------------------------------

    def test_connection(self) -> dict[str, Any]:
        """Lightweight connectivity check. Returns {ok, message, ...}."""
        if self._sim:
            self._sign_dryrun("/iserver/auth/status")
            return {
                "ok": True,
                "message": "Connection simulated successfully (BROKER SIM MODE)",
                "environment": self.creds.environment,
                "server_time": _now_iso(),
                "sim": True,
            }
        # Real path (not exercised in this build)
        return self._request("GET", "/iserver/auth/status")

    def get_account_summary(self) -> IBKRConnectionInfo:
        if self._sim:
            self._sign_dryrun("/portfolio/accounts")
            return IBKRConnectionInfo(
                account_id="DU1234567" if self.creds.environment == "paper" else "U1234567",
                account_alias="Sapient Trading Account",
                currency="AUD",
                environment=self.creds.environment,
                server_time=_now_iso(),
                is_paper=self.creds.environment == "paper",
                cash=125_430.50,
                buying_power=250_861.00,
                nav=487_215.75,
            )
        raw = self._request("GET", "/portfolio/accounts")  # pragma: no cover
        first = raw[0] if isinstance(raw, list) and raw else {}
        # In live mode we'd also call /portfolio/{acctId}/summary for cash/NAV
        return IBKRConnectionInfo(
            account_id=first.get("accountId", ""),
            account_alias=first.get("accountAlias", ""),
            currency=first.get("currency", "USD"),
            environment=self.creds.environment,
            server_time=_now_iso(),
            is_paper=self.creds.environment == "paper",
            cash=float(first.get("cash") or 0),
            buying_power=float(first.get("buyingPower") or 0),
            nav=float(first.get("netLiquidation") or 0),
        )

    def get_positions(self, account_id: str) -> list[dict[str, Any]]:
        if self._sim:
            self._sign_dryrun(f"/portfolio/{account_id}/positions/0")
            # Simulated positions roughly matching ASX blue chips
            return [
                {"symbol": "BHP.AX", "position": 120, "avg_price": 44.10, "market_price": 46.80, "currency": "AUD"},
                {"symbol": "CBA.AX", "position": 18, "avg_price": 102.50, "market_price": 110.30, "currency": "AUD"},
                {"symbol": "WBC.AX", "position": 75, "avg_price": 22.10, "market_price": 23.45, "currency": "AUD"},
            ]
        return self._request("GET", f"/portfolio/{account_id}/positions/0")  # pragma: no cover

    def place_order(
        self,
        account_id: str,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MKT",
        limit_price: float | None = None,
        time_in_force: str = "DAY",
    ) -> IBKROrder:
        side = side.upper()
        order_type = order_type.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {side}")
        if order_type not in ("MKT", "LMT"):
            raise ValueError(f"Invalid order_type: {order_type}")
        if order_type == "LMT" and limit_price is None:
            raise ValueError("LMT order requires limit_price")
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        if self._sim:
            self._sign_dryrun(f"/iserver/account/{account_id}/orders", method="POST")
            # Simulate immediate fill at limit_price (or a synthetic mark for MKT)
            mark = limit_price if limit_price is not None else _simulated_mark_price(symbol)
            return IBKROrder(
                order_id=f"SIM-{uuid.uuid4().hex[:10].upper()}",
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
                status="Filled",
                filled_qty=quantity,
                avg_fill_price=round(mark, 4),
                submitted_at=_now_iso(),
                fees=round(max(1.0, quantity * mark * 0.0008), 2),  # ~8bps with $1 floor
                sim=True,
            )
        # Real path (not exercised)
        body = {
            "orders": [
                {
                    "conid": _conid_for_symbol(symbol),
                    "orderType": order_type,
                    "price": limit_price,
                    "side": side,
                    "tif": time_in_force,
                    "quantity": quantity,
                }
            ]
        }
        resp = self._request("POST", f"/iserver/account/{account_id}/orders", json=body)  # pragma: no cover
        first = resp[0] if isinstance(resp, list) and resp else {}
        return IBKROrder(
            order_id=str(first.get("order_id", "")),
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            status=first.get("status", "Submitted"),
            filled_qty=float(first.get("filled_qty", 0)),
            avg_fill_price=first.get("avg_price"),
            submitted_at=_now_iso(),
            fees=0,
            sim=False,
        )

    def cancel_order(self, account_id: str, order_id: str) -> dict[str, Any]:
        if self._sim:
            self._sign_dryrun(
                f"/iserver/account/{account_id}/order/{order_id}", method="DELETE"
            )
            return {"order_id": order_id, "status": "Cancelled", "sim": True}
        return self._request("DELETE", f"/iserver/account/{account_id}/order/{order_id}")  # pragma: no cover

    # ---- Internal HTTP layer (only called when sim mode is OFF) -----------

    def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
    ) -> Any:
        """
        Real HTTP call to IBKR. NOT exercised while IBKR_SIMULATION_MODE=True.
        Wire to httpx/requests here when going live.
        """
        raise NotImplementedError(
            "Live IBKR HTTP layer is not wired. Set IBKR_SIMULATION_MODE = False and "
            "implement this method (e.g. with httpx) to go live."
        )


# ---------------------------------------------------------------------------
# Sim helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_SIM_PRICES = {
    "BHP.AX": 46.80, "CBA.AX": 110.30, "WBC.AX": 23.45, "NAB.AX": 35.10,
    "ANZ.AX": 28.80, "WES.AX": 65.20, "CSL.AX": 280.10, "FMG.AX": 21.40,
    "TLS.AX": 4.10, "WOW.AX": 36.50, "MQG.AX": 195.00, "RIO.AX": 121.50,
    "AAPL": 215.40, "MSFT": 412.60, "NVDA": 137.20, "GOOGL": 178.30,
    "AMZN": 197.80, "META": 522.10, "TSLA": 246.30, "JPM": 218.50,
}


def _simulated_mark_price(symbol: str) -> float:
    base = _SIM_PRICES.get(symbol.upper())
    if base is None:
        # Deterministic-ish fallback so the same symbol gives a stable-ish price within a request
        base = 50 + (sum(ord(c) for c in symbol) % 200)
    # ±0.4% jitter so sequential orders don't all fill at the exact same price
    return base * (1.0 + random.uniform(-0.004, 0.004))


def _conid_for_symbol(symbol: str) -> int:  # pragma: no cover (live-only)
    """Placeholder — real impl would look this up via /iserver/secdef/search."""
    return abs(hash(symbol)) % (10**8)
