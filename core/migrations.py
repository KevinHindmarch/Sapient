"""Versioned, checksummed SQLite schema migrations.

Applied at application startup by ``migrate()``: an existing database is backed
up first, applied versions must match their recorded checksums, and a database
written by a newer Sapient (unknown versions) is refused rather than modified.
Migrations are additive; never edit an applied migration — add a new one.
"""

from datetime import datetime, timezone
import hashlib
import sqlite3

from core import db

# Default for UTCTIME columns: UTC with millisecond precision, same text
# ordering as core.db.utc_text().
_NOW = "(strftime('%Y-%m-%d %H:%M:%f','now'))"

CORE_V1 = f"""
CREATE TABLE users (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 email VARCHAR(255) UNIQUE NOT NULL,
 password_hash VARCHAR(255) NOT NULL,
 display_name VARCHAR(100),
 created_at UTCTIME DEFAULT {_NOW},
 last_login UTCTIME
);
CREATE TABLE portfolios (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
 name VARCHAR(255) NOT NULL,
 mode VARCHAR(20) DEFAULT 'auto',
 initial_investment DECNUM(15, 2) NOT NULL,
 created_at UTCTIME DEFAULT {_NOW},
 status VARCHAR(20) DEFAULT 'active',
 benchmark_symbol VARCHAR(20) DEFAULT '^AXJO',
 expected_return DECNUM(8, 4),
 expected_volatility DECNUM(8, 4),
 expected_sharpe DECNUM(8, 4),
 expected_dividend_yield DECNUM(8, 4),
 risk_tolerance VARCHAR(20) DEFAULT 'moderate',
 market VARCHAR(10) DEFAULT 'ASX',
 ai_mode VARCHAR(20) DEFAULT 'off'
);
CREATE TABLE portfolio_positions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
 symbol VARCHAR(20) NOT NULL,
 quantity DECNUM(15, 6) NOT NULL,
 avg_cost DECNUM(15, 4) NOT NULL,
 weight_at_creation DECNUM(8, 4),
 allocation_amount DECNUM(15, 2),
 status VARCHAR(20) DEFAULT 'active',
 created_at UTCTIME DEFAULT {_NOW},
 closed_at UTCTIME
);
CREATE TABLE portfolio_snapshots (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
 snapshot_date ISODATE NOT NULL,
 total_value DECNUM(15, 2),
 cash_balance DECNUM(15, 2) DEFAULT 0,
 daily_return DECNUM(8, 4),
 cumulative_return DECNUM(8, 4),
 benchmark_return DECNUM(8, 4),
 created_at UTCTIME DEFAULT {_NOW},
 UNIQUE(portfolio_id, snapshot_date)
);
CREATE TABLE position_snapshots (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 portfolio_position_id INTEGER REFERENCES portfolio_positions(id) ON DELETE CASCADE,
 snapshot_date ISODATE NOT NULL,
 price DECNUM(15, 4),
 market_value DECNUM(15, 2),
 return_pct DECNUM(8, 4),
 created_at UTCTIME DEFAULT {_NOW},
 UNIQUE(portfolio_position_id, snapshot_date)
);
CREATE TABLE transactions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
 portfolio_position_id INTEGER REFERENCES portfolio_positions(id) ON DELETE SET NULL,
 txn_type VARCHAR(20) NOT NULL,
 symbol VARCHAR(20) NOT NULL,
 quantity DECNUM(15, 6) NOT NULL,
 price DECNUM(15, 4) NOT NULL,
 total_amount DECNUM(15, 2) NOT NULL,
 fees DECNUM(10, 2) DEFAULT 0,
 notes TEXT,
 txn_time UTCTIME DEFAULT {_NOW}
);
CREATE TABLE strategy_signals (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
 symbol VARCHAR(20) NOT NULL,
 indicator VARCHAR(20) NOT NULL,
 signal VARCHAR(20) NOT NULL,
 indicator_value DECNUM(15, 4),
 price_at_signal DECNUM(15, 4),
 generated_at UTCTIME DEFAULT {_NOW},
 acknowledged FLAG DEFAULT FALSE,
 notes TEXT
);
CREATE INDEX idx_portfolios_user_id ON portfolios(user_id);
CREATE INDEX idx_positions_portfolio_id ON portfolio_positions(portfolio_id);
CREATE INDEX idx_snapshots_portfolio_date ON portfolio_snapshots(portfolio_id, snapshot_date);
CREATE INDEX idx_transactions_portfolio_id ON transactions(portfolio_id);
CREATE INDEX idx_signals_portfolio_id ON strategy_signals(portfolio_id);

CREATE TABLE broker_credentials (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
 broker VARCHAR(20) NOT NULL DEFAULT 'IBKR',
 environment VARCHAR(10) NOT NULL DEFAULT 'paper',
 consumer_key_enc TEXT NOT NULL,
 access_token_enc TEXT NOT NULL,
 access_token_secret_enc TEXT NOT NULL,
 private_key_pem_enc TEXT NOT NULL,
 consumer_key_masked VARCHAR(64),
 connected_at UTCTIME DEFAULT {_NOW},
 last_test_at UTCTIME,
 last_test_ok FLAG
);
CREATE TABLE ai_trading_settings (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
 mode VARCHAR(20) DEFAULT 'off',
 rsi_buy_threshold DECNUM(5, 2) DEFAULT 30.00,
 rsi_sell_threshold DECNUM(5, 2) DEFAULT 70.00,
 max_trade_pct DECNUM(5, 2) DEFAULT 5.00,
 max_daily_trades INTEGER DEFAULT 8,
 max_daily_turnover_pct DECNUM(5, 2) DEFAULT 20.00,
 sector_cap_pct DECNUM(5, 2) DEFAULT 35.00,
 paper_only FLAG DEFAULT TRUE,
 breaker_on_loss_pct DECNUM(5, 2) DEFAULT 3.00,
 breaker_on_volatility_spike FLAG DEFAULT TRUE,
 breaker_on_news_event FLAG DEFAULT TRUE,
 last_kill_switch_at UTCTIME,
 updated_at UTCTIME DEFAULT {_NOW}
);
CREATE TABLE ai_signals (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
 portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
 symbol VARCHAR(20) NOT NULL,
 company_name VARCHAR(255),
 market VARCHAR(10) DEFAULT 'ASX',
 action VARCHAR(8) NOT NULL,
 quantity DECNUM(15, 6) NOT NULL,
 price_at_signal DECNUM(15, 4) NOT NULL,
 confidence DECNUM(4, 3) DEFAULT 0.5,
 rationale JSONTEXT DEFAULT '{{}}',
 rule_summary TEXT,
 status VARCHAR(20) DEFAULT 'pending',
 generated_at UTCTIME DEFAULT {_NOW},
 decided_at UTCTIME,
 decided_by VARCHAR(20),
 expires_at UTCTIME,
 executed_order_id INTEGER
);
CREATE TABLE broker_orders (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
 portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE SET NULL,
 signal_id INTEGER REFERENCES ai_signals(id) ON DELETE SET NULL,
 broker_order_id VARCHAR(64) NOT NULL,
 broker VARCHAR(20) DEFAULT 'IBKR',
 account_id VARCHAR(32),
 symbol VARCHAR(20) NOT NULL,
 side VARCHAR(8) NOT NULL,
 quantity DECNUM(15, 6) NOT NULL,
 order_type VARCHAR(8) NOT NULL,
 limit_price DECNUM(15, 4),
 status VARCHAR(20) DEFAULT 'Submitted',
 filled_qty DECNUM(15, 6) DEFAULT 0,
 avg_fill_price DECNUM(15, 4),
 fees DECNUM(10, 2) DEFAULT 0,
 sim FLAG DEFAULT TRUE,
 submitted_at UTCTIME DEFAULT {_NOW},
 updated_at UTCTIME DEFAULT {_NOW}
);
CREATE TABLE ai_audit_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
 event_type VARCHAR(40) NOT NULL,
 portfolio_id INTEGER,
 signal_id INTEGER,
 order_id INTEGER,
 payload JSONTEXT DEFAULT '{{}}',
 created_at UTCTIME DEFAULT {_NOW}
);
CREATE INDEX idx_ai_signals_user_status ON ai_signals(user_id, status);
CREATE INDEX idx_ai_signals_portfolio ON ai_signals(portfolio_id);
CREATE INDEX idx_broker_orders_user ON broker_orders(user_id, submitted_at DESC);
CREATE INDEX idx_broker_orders_portfolio ON broker_orders(portfolio_id);
CREATE INDEX idx_audit_user_created ON ai_audit_log(user_id, created_at DESC);
"""

SAFETY_V1 = f"""
CREATE TABLE safety_accounts (
 user_id INTEGER PRIMARY KEY REFERENCES users(id),
 account_id TEXT NOT NULL UNIQUE,
 environment TEXT NOT NULL CHECK (environment = 'simulation'),
 halted FLAG NOT NULL DEFAULT TRUE,
 halted_at UTCTIME,
 recovery_required FLAG NOT NULL DEFAULT TRUE,
 incarnation TEXT NOT NULL,
 policy_revision INTEGER NOT NULL DEFAULT 1,
 policy JSONTEXT NOT NULL DEFAULT '{{}}',
 facts JSONTEXT NOT NULL DEFAULT '{{}}',
 facts_until UTCTIME,
 epoch INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE safety_intents (
 id TEXT PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 account_id TEXT NOT NULL,
 origin TEXT NOT NULL CHECK(origin IN ('manual','ai_approval','ai_autonomous','rebalance')),
 idempotency_key TEXT NOT NULL,
 payload JSONTEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 portfolio_id INTEGER REFERENCES portfolios(id),
 signal_id INTEGER UNIQUE REFERENCES ai_signals(id),
 state TEXT NOT NULL DEFAULT 'QUEUED',
 policy_revision INTEGER NOT NULL,
 incarnation TEXT NOT NULL,
 notional DECTEXT NOT NULL CHECK(CAST(notional AS REAL) > 0),
 expires_at UTCTIME NOT NULL,
 created_at UTCTIME NOT NULL DEFAULT {_NOW},
 UNIQUE(user_id,idempotency_key)
);
CREATE TABLE safety_reservations (
 intent_id TEXT PRIMARY KEY REFERENCES safety_intents(id),
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 symbol TEXT NOT NULL,
 side TEXT NOT NULL,
 quantity DECTEXT NOT NULL,
 notional DECTEXT NOT NULL,
 released_at UTCTIME
);
CREATE TABLE safety_batches (
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 idempotency_key TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 intent_ids JSONTEXT NOT NULL,
 created_at UTCTIME NOT NULL DEFAULT {_NOW},
 PRIMARY KEY(user_id,idempotency_key)
);
CREATE TABLE safety_outbox (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 intent_id TEXT REFERENCES safety_intents(id),
 kind TEXT NOT NULL,
 payload JSONTEXT NOT NULL,
 created_at UTCTIME NOT NULL DEFAULT {_NOW},
 delivered_at UTCTIME
);
CREATE TABLE safety_audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL,
 kind TEXT NOT NULL,
 payload JSONTEXT NOT NULL,
 created_at UTCTIME NOT NULL DEFAULT {_NOW}
);
CREATE TABLE safety_pairings (
 token_hash TEXT PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 expires_at UTCTIME NOT NULL,
 used_at UTCTIME
);
CREATE TABLE safety_devices (
 id TEXT PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 token_hash TEXT NOT NULL UNIQUE,
 scopes JSONTEXT NOT NULL,
 revoked_at UTCTIME,
 created_at UTCTIME NOT NULL DEFAULT {_NOW}
);
CREATE TABLE safety_leases (
 user_id INTEGER PRIMARY KEY REFERENCES safety_accounts(user_id),
 device_id TEXT NOT NULL REFERENCES safety_devices(id),
 epoch INTEGER NOT NULL,
 incarnation TEXT NOT NULL,
 expires_at UTCTIME NOT NULL
);
CREATE TABLE safety_evidence (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 device_id TEXT NOT NULL REFERENCES safety_devices(id),
 journal_incarnation TEXT NOT NULL,
 sequence INTEGER NOT NULL CHECK(sequence > 0),
 payload_hash TEXT NOT NULL,
 payload JSONTEXT NOT NULL,
 quarantined FLAG NOT NULL DEFAULT TRUE,
 received_at UTCTIME NOT NULL DEFAULT {_NOW},
 UNIQUE(device_id,journal_incarnation,sequence)
);
CREATE INDEX safety_intents_daily ON safety_intents(user_id,created_at);
CREATE INDEX safety_outbox_pending ON safety_outbox(user_id,id) WHERE delivered_at IS NULL;
"""

TWS_V1 = f"""
CREATE TABLE tws_settings (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 enabled FLAG NOT NULL DEFAULT FALSE,
 port INTEGER NOT NULL DEFAULT 7497 CHECK (port BETWEEN 1 AND 65535),
 client_id INTEGER NOT NULL DEFAULT 71 CHECK (client_id > 0),
 expected_account TEXT,
 paper_confirmed FLAG NOT NULL DEFAULT FALSE,
 sdk_folder TEXT,
 updated_at UTCTIME NOT NULL DEFAULT {_NOW}
);
INSERT INTO tws_settings(id) VALUES (1);
CREATE TABLE tws_status (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 state TEXT NOT NULL DEFAULT 'NOT_CONFIGURED',
 detail TEXT,
 account TEXT,
 server_version INTEGER,
 sdk_version TEXT,
 ib_connected FLAG,
 connected_since UTCTIME,
 last_sync_at UTCTIME,
 worker_heartbeat_at UTCTIME,
 updated_at UTCTIME NOT NULL DEFAULT {_NOW}
);
INSERT INTO tws_status(id) VALUES (1);
CREATE TABLE tws_snapshots (
 kind TEXT PRIMARY KEY,
 data JSONTEXT NOT NULL,
 taken_at UTCTIME NOT NULL DEFAULT {_NOW}
);
CREATE TABLE tws_commands (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 kind TEXT NOT NULL CHECK (kind IN ('test_connection','reconnect')),
 status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','done','failed')),
 result JSONTEXT,
 created_at UTCTIME NOT NULL DEFAULT {_NOW},
 started_at UTCTIME,
 finished_at UTCTIME
);
CREATE INDEX tws_commands_pending ON tws_commands(id) WHERE status = 'pending';
"""

# A profile that already exists when this runs belongs to someone upgrading:
# never show them the first-run wizard again. Fresh installs create the profile
# after migrating, so they get the wizard.
PROFILE_V1 = """
-- NULL = never saved here (upgrades from 0.1.0 keep the theme the app already shows).
ALTER TABLE users ADD COLUMN theme TEXT CHECK (theme IS NULL OR theme IN ('light','dark'));
ALTER TABLE users ADD COLUMN onboarded_at UTCTIME;
UPDATE users SET onboarded_at = COALESCE(created_at, strftime('%Y-%m-%d %H:%M:%f','now'))
"""

STRATEGY_V1 = f"""
ALTER TABLE ai_trading_settings ADD COLUMN stop_loss_pct DECNUM(5, 2);
ALTER TABLE ai_trading_settings ADD COLUMN take_profit_pct DECNUM(5, 2);
ALTER TABLE ai_trading_settings ADD COLUMN approval_timeout_minutes INTEGER NOT NULL DEFAULT 15
  CHECK (approval_timeout_minutes BETWEEN 1 AND 1440);
ALTER TABLE ai_trading_settings ADD COLUMN scheduler_enabled FLAG NOT NULL DEFAULT FALSE;
ALTER TABLE ai_trading_settings ADD COLUMN check_after_open_minutes INTEGER NOT NULL DEFAULT 15
  CHECK (check_after_open_minutes BETWEEN 0 AND 300);
ALTER TABLE ai_trading_settings ADD COLUMN check_before_close_minutes INTEGER NOT NULL DEFAULT 30
  CHECK (check_before_close_minutes BETWEEN 5 AND 300);
CREATE TABLE scheduler_runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
 window_key TEXT NOT NULL,
 outcome TEXT NOT NULL DEFAULT 'running'
   CHECK (outcome IN ('running','done','failed','missed','abandoned')),
 result JSONTEXT,
 started_at UTCTIME NOT NULL DEFAULT {_NOW},
 finished_at UTCTIME,
 UNIQUE (portfolio_id, window_key)
);
CREATE TABLE scheduler_status (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 heartbeat_at UTCTIME,
 detail TEXT,
 next_check_at UTCTIME
);
INSERT INTO scheduler_status(id) VALUES (1);
CREATE INDEX ai_signals_open ON ai_signals(expires_at) WHERE status IN ('pending','snoozed');
"""

PAPER_V1 = f"""
CREATE TABLE paper_binding (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 account_id TEXT,
 enabled FLAG NOT NULL DEFAULT FALSE,
 authorised_at UTCTIME,
 authorised_text TEXT,
 halted FLAG NOT NULL DEFAULT FALSE,
 halted_at UTCTIME,
 max_order_value DECNUM(15, 2) NOT NULL DEFAULT 2000 CHECK (max_order_value > 0),
 max_orders_per_day INTEGER NOT NULL DEFAULT 10 CHECK (max_orders_per_day >= 0),
 max_value_per_day DECNUM(15, 2) NOT NULL DEFAULT 10000 CHECK (max_value_per_day >= 0),
 max_price_gap_pct DECNUM(5, 2) NOT NULL DEFAULT 3 CHECK (max_price_gap_pct > 0 AND max_price_gap_pct <= 10),
 autonomous_allowed FLAG NOT NULL DEFAULT FALSE,
 updated_at UTCTIME NOT NULL DEFAULT {_NOW}
);
INSERT INTO paper_binding(id) VALUES (1);
CREATE TABLE paper_orders (
 id TEXT PRIMARY KEY,
 idempotency_key TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL,
 origin TEXT NOT NULL CHECK (origin IN ('manual','ai_approval','ai_autonomous','entry')),
 account_id TEXT NOT NULL,
 portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE SET NULL,
 signal_id INTEGER UNIQUE REFERENCES ai_signals(id) ON DELETE SET NULL,
 symbol TEXT NOT NULL,
 side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
 quantity DECTEXT NOT NULL,
 reference_price DECTEXT NOT NULL,
 limit_price DECTEXT,
 quote JSONTEXT,
 state TEXT NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED','SUBMITTING','SUBMITTED',
   'PARTIALLY_FILLED','FILLED','CANCEL_REQUESTED','CANCELLED','REJECTED','EXPIRED','BLOCKED','UNKNOWN')),
 detail TEXT,
 api_order_id INTEGER UNIQUE,
 perm_id INTEGER,
 order_ref TEXT UNIQUE,
 con_id INTEGER,
 exchange TEXT,
 currency TEXT,
 filled_quantity DECTEXT NOT NULL DEFAULT '0',
 avg_fill_price DECTEXT,
 broker_status TEXT,
 cancel_sent_at UTCTIME,
 created_at UTCTIME NOT NULL DEFAULT {_NOW},
 expires_at UTCTIME NOT NULL,
 submitted_at UTCTIME,
 updated_at UTCTIME NOT NULL DEFAULT {_NOW}
);
CREATE INDEX paper_orders_state ON paper_orders(state);
CREATE TABLE paper_executions (
 exec_id TEXT PRIMARY KEY,
 paper_order_id TEXT REFERENCES paper_orders(id),
 api_order_id INTEGER,
 perm_id INTEGER,
 order_ref TEXT,
 account_id TEXT,
 symbol TEXT,
 side TEXT,
 shares DECTEXT,
 price DECTEXT,
 exec_time TEXT,
 commission DECTEXT,
 commission_currency TEXT,
 received_at UTCTIME NOT NULL DEFAULT {_NOW}
);
-- Fills applied to a portfolio's positions, once per execution family (corrections
-- apply only their difference).
CREATE TABLE paper_portfolio_fills (
 exec_family TEXT PRIMARY KEY,
 paper_order_id TEXT NOT NULL REFERENCES paper_orders(id),
 portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
 shares DECTEXT NOT NULL,
 price DECTEXT NOT NULL,
 applied_at UTCTIME NOT NULL DEFAULT {_NOW}
);
ALTER TABLE portfolios ADD COLUMN paper_started_at UTCTIME;
CREATE TABLE paper_order_ids (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 high_water INTEGER NOT NULL DEFAULT 0
);
INSERT INTO paper_order_ids(id) VALUES (1);
CREATE TABLE paper_audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 kind TEXT NOT NULL,
 paper_order_id TEXT,
 payload JSONTEXT,
 created_at UTCTIME NOT NULL DEFAULT {_NOW}
);
"""

LIVE_V1 = f"""
CREATE TABLE tws_live_settings (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 enabled FLAG NOT NULL DEFAULT FALSE,
 port INTEGER NOT NULL DEFAULT 7496 CHECK (port BETWEEN 1 AND 65535),
 client_id INTEGER NOT NULL DEFAULT 72 CHECK (client_id > 0),
 expected_account TEXT,
 live_confirmed FLAG NOT NULL DEFAULT FALSE,
 sdk_folder TEXT,
 updated_at UTCTIME NOT NULL DEFAULT {_NOW}
);
INSERT INTO tws_live_settings(id) VALUES (1);
CREATE TABLE tws_live_status (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 state TEXT NOT NULL DEFAULT 'NOT_CONFIGURED',
 detail TEXT,
 account TEXT,
 server_version INTEGER,
 sdk_version TEXT,
 ib_connected FLAG,
 connected_since UTCTIME,
 last_sync_at UTCTIME,
 worker_heartbeat_at UTCTIME,
 updated_at UTCTIME NOT NULL DEFAULT {_NOW}
);
INSERT INTO tws_live_status(id) VALUES (1);
CREATE TABLE tws_live_snapshots (
 kind TEXT PRIMARY KEY,
 data JSONTEXT NOT NULL,
 taken_at UTCTIME NOT NULL DEFAULT {_NOW}
);
ALTER TABLE tws_commands ADD COLUMN profile TEXT NOT NULL DEFAULT 'paper' CHECK (profile IN ('paper','live'));
CREATE TABLE live_binding (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 account_id TEXT,
 enabled FLAG NOT NULL DEFAULT FALSE,
 authorised_at UTCTIME,
 authorised_text TEXT,
 halted FLAG NOT NULL DEFAULT FALSE,
 halted_at UTCTIME,
 max_order_value DECNUM(15, 2) NOT NULL DEFAULT 1000 CHECK (max_order_value > 0),
 max_orders_per_day INTEGER NOT NULL DEFAULT 5 CHECK (max_orders_per_day >= 0),
 max_value_per_day DECNUM(15, 2) NOT NULL DEFAULT 5000 CHECK (max_value_per_day >= 0),
 max_price_gap_pct DECNUM(5, 2) NOT NULL DEFAULT 2 CHECK (max_price_gap_pct > 0 AND max_price_gap_pct <= 10),
 autonomous_allowed FLAG NOT NULL DEFAULT FALSE,
 updated_at UTCTIME NOT NULL DEFAULT {_NOW}
);
INSERT INTO live_binding(id) VALUES (1);
CREATE TABLE live_order_ids (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 high_water INTEGER NOT NULL DEFAULT 0
);
INSERT INTO live_order_ids(id) VALUES (1);
ALTER TABLE paper_orders ADD COLUMN environment TEXT NOT NULL DEFAULT 'paper' CHECK (environment IN ('paper','live'));
CREATE INDEX paper_orders_environment_state ON paper_orders(environment, state);
ALTER TABLE portfolios ADD COLUMN live_started_at UTCTIME;
ALTER TABLE portfolios ADD COLUMN trading_environment TEXT CHECK (trading_environment IS NULL OR trading_environment IN ('paper','live'));
UPDATE portfolios SET trading_environment='paper' WHERE paper_started_at IS NOT NULL
"""

# G2: holdings that match IBKR, cash and realised profit.
_FILLED_SHARES = """(SELECT sum(CASE o.side WHEN 'BUY' THEN CAST(f.shares AS REAL) ELSE -CAST(f.shares AS REAL) END)
   FROM paper_portfolio_fills f JOIN paper_orders o ON o.id = f.paper_order_id
   WHERE f.portfolio_id = portfolio_positions.portfolio_id AND o.symbol = portfolio_positions.symbol)"""
_BUY_PRICE = """(SELECT sum(CAST(f.shares AS REAL) * CAST(f.price AS REAL)) / sum(CAST(f.shares AS REAL))
   FROM paper_portfolio_fills f JOIN paper_orders o ON o.id = f.paper_order_id
   WHERE f.portfolio_id = portfolio_positions.portfolio_id AND o.symbol = portfolio_positions.symbol
   AND o.side = 'BUY')"""
LEDGER_V1 = f"""
ALTER TABLE transactions ADD COLUMN realised_pnl DECNUM(15, 2);
ALTER TABLE transactions ADD COLUMN exec_family TEXT;
CREATE INDEX idx_transactions_exec_family ON transactions(exec_family);
ALTER TABLE portfolio_positions ADD COLUMN planned_quantity DECNUM(15, 6);
UPDATE portfolio_positions SET planned_quantity = quantity
 WHERE portfolio_id IN (SELECT id FROM portfolios WHERE trading_environment IS NOT NULL);
UPDATE portfolio_positions SET quantity = max(coalesce({_FILLED_SHARES}, 0), 0),
       avg_cost = coalesce({_BUY_PRICE}, avg_cost)
 WHERE status = 'active' AND portfolio_id IN (SELECT id FROM portfolios WHERE trading_environment IS NOT NULL)
"""

# (version, name, sql). Append only.
MIGRATIONS = (
    (1, "core", CORE_V1),
    (2, "safety", SAFETY_V1),
    (3, "tws", TWS_V1),
    (4, "profile", PROFILE_V1),
    (5, "strategy", STRATEGY_V1),
    (6, "paper", PAPER_V1),
    (7, "live", LIVE_V1),
    (8, "ledger", LEDGER_V1),
)
SAFETY_SCHEMA_VERSION = 2


class MigrationError(RuntimeError):
    pass


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode()).hexdigest()


def applied_versions(conn) -> dict:
    cur = conn.cursor()
    if not db.table_exists(cur, "schema_versions"):
        return {}
    cur.execute("SELECT version, checksum FROM schema_versions")
    return {row["version"]: row["checksum"] for row in cur.fetchall()}


def pending(conn) -> list:
    applied = applied_versions(conn)
    known = {version for version, _, _ in MIGRATIONS}
    unknown = sorted(set(applied) - known)
    if unknown:
        raise MigrationError(f"Database was created by a newer Sapient (schema {unknown}); refusing to modify it")
    for version, name, sql in MIGRATIONS:
        if version in applied and applied[version] != _checksum(sql):
            raise MigrationError(f"Schema migration {version} ({name}) checksum mismatch")
    return [m for m in MIGRATIONS if m[0] not in applied]


def backup(path, destination) -> None:
    """Consistent online copy using SQLite's backup API."""
    source = sqlite3.connect(str(path))
    try:
        target = sqlite3.connect(str(destination))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def apply(conn) -> list:
    """Apply pending migrations, each in its own BEGIN IMMEDIATE transaction."""
    done = []
    for version, name, sql in pending(conn):
        conn.begin()
        try:
            cur = conn.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS schema_versions (
                version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL,
                applied_at UTCTIME NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')))""")
            cur.execute("SELECT 1 FROM schema_versions WHERE version=%s", (version,))
            if cur.fetchone() is None:  # another process may have won the lock first
                for statement in sql.split(";"):
                    if statement.strip():
                        cur.execute(statement)
                cur.execute("INSERT INTO schema_versions(version, name, checksum) VALUES (%s, %s, %s)",
                            (version, name, _checksum(sql)))
                done.append(version)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    return done


def migrate(path=None) -> list:
    """Startup entry point: back up an existing database, then apply pending migrations."""
    path = path or db.db_path()
    conn = db.connect(path)
    try:
        todo = pending(conn)
        if todo and applied_versions(conn):
            backups = path.parent / "backups"
            backups.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup(path, backups / f"{path.stem}-pre-v{todo[0][0]}-{stamp}.db")
        return apply(conn)
    finally:
        conn.close()
