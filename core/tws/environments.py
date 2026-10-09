"""The two TWS trading environments Sapient can send orders to.

paper  TWS paper login (port 7497 by default). Authorised 2026-10-09; delayed
       prices allowed, cautious limits.
live   TWS live login (port 7496 by default) — REAL MONEY. Requested by the
       user 2026-10-09 (account U29239702) with real-time prices only and
       limits the user sets. Orders still need the in-app live authorisation.

Each environment has its own TWS connection settings/status/snapshots, its own
authorisation ("binding"), its own order-id range and its own portfolios.
Orders for both live in ``paper_orders`` with an ``environment`` column.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Env:
    name: str
    label: str                  # for messages: "paper" / "live (real money)"
    binding_table: str
    settings_table: str
    status_table: str
    snapshots_table: str
    ids_table: str
    confirm_field: str          # settings column: the user confirmed which kind of account this is
    started_column: str         # portfolios column set by "Buy … & manage"
    order_id_base: int          # live ids live in their own range so they never clash with paper ids
    realtime_required: bool     # live orders need a fresh real-time TWS quote
    authorisation_text: str
    default_port: int
    default_client_id: int


PAPER = Env(
    name="paper", label="paper", binding_table="paper_binding", settings_table="tws_settings",
    status_table="tws_status", snapshots_table="tws_snapshots", ids_table="paper_order_ids",
    confirm_field="paper_confirmed", started_column="paper_started_at", order_id_base=0,
    realtime_required=False,
    authorisation_text=("I authorise Sapient to send practice (paper) orders to Interactive Brokers paper "
                        "account {account}. Orders use TWS delayed prices as cautious limit orders. "
                        "No real money is used."),
    default_port=7497, default_client_id=71,
)

LIVE = Env(
    name="live", label="live (real money)", binding_table="live_binding", settings_table="tws_live_settings",
    status_table="tws_live_status", snapshots_table="tws_live_snapshots", ids_table="live_order_ids",
    confirm_field="live_confirmed", started_column="live_started_at", order_id_base=1_000_000_000,
    realtime_required=True,
    authorisation_text=("I authorise Sapient to place REAL-MONEY orders in my Interactive Brokers live account "
                        "{account}, within the limits I set, using real-time prices. I understand these trades "
                        "use my own money and that I can lose money."),
    default_port=7496, default_client_id=72,
)

ENVS = {"paper": PAPER, "live": LIVE}


def get(name: str | None) -> Env:
    try:
        return ENVS[name or "paper"]
    except KeyError:
        raise ValueError(f"Unknown trading environment {name!r}")
