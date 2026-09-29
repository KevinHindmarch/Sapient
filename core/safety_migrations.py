"""Explicit, additive migrations for disposable development/test databases only.

Not called by application startup. No downgrade drops financial history.
"""
import hashlib


SCHEMA_V1 = """
CREATE TABLE safety_accounts (
 user_id INTEGER PRIMARY KEY REFERENCES users(id),
 account_id TEXT NOT NULL UNIQUE,
 environment TEXT NOT NULL CHECK (environment = 'simulation'),
 halted BOOLEAN NOT NULL DEFAULT TRUE,
 halted_at TIMESTAMPTZ,
 recovery_required BOOLEAN NOT NULL DEFAULT TRUE,
 incarnation TEXT NOT NULL,
 policy_revision INTEGER NOT NULL DEFAULT 1,
 policy JSONB NOT NULL DEFAULT '{}',
 facts JSONB NOT NULL DEFAULT '{}',
 facts_until TIMESTAMPTZ,
 epoch BIGINT NOT NULL DEFAULT 0
);
CREATE TABLE safety_intents (
 id TEXT PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 account_id TEXT NOT NULL,
 origin TEXT NOT NULL CHECK(origin IN ('manual','ai_approval','ai_autonomous','rebalance')),
 idempotency_key TEXT NOT NULL,
 payload JSONB NOT NULL,
 payload_hash TEXT NOT NULL,
 portfolio_id INTEGER REFERENCES portfolios(id),
 signal_id INTEGER UNIQUE REFERENCES ai_signals(id),
 state TEXT NOT NULL DEFAULT 'QUEUED',
 policy_revision INTEGER NOT NULL,
 incarnation TEXT NOT NULL,
 notional NUMERIC(28,8) NOT NULL CHECK(notional > 0),
 expires_at TIMESTAMPTZ NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(user_id,idempotency_key)
);
CREATE TABLE safety_reservations (
 intent_id TEXT PRIMARY KEY REFERENCES safety_intents(id),
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 symbol TEXT NOT NULL,
 side TEXT NOT NULL,
 quantity NUMERIC(28,8) NOT NULL,
 notional NUMERIC(28,8) NOT NULL,
 released_at TIMESTAMPTZ
);
CREATE TABLE safety_batches (
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 idempotency_key TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 intent_ids TEXT[] NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(user_id,idempotency_key)
);
CREATE TABLE safety_outbox (
 id BIGSERIAL PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 intent_id TEXT REFERENCES safety_intents(id),
 kind TEXT NOT NULL,
 payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 delivered_at TIMESTAMPTZ
);
CREATE TABLE safety_audit (
 id BIGSERIAL PRIMARY KEY,
 user_id INTEGER NOT NULL,
 kind TEXT NOT NULL,
 payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE safety_pairings (
 token_hash TEXT PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 expires_at TIMESTAMPTZ NOT NULL,
 used_at TIMESTAMPTZ
);
CREATE TABLE safety_devices (
 id TEXT PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 token_hash TEXT NOT NULL UNIQUE,
 scopes TEXT[] NOT NULL,
 revoked_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE safety_leases (
 user_id INTEGER PRIMARY KEY REFERENCES safety_accounts(user_id),
 device_id TEXT NOT NULL REFERENCES safety_devices(id),
 epoch BIGINT NOT NULL,
 incarnation TEXT NOT NULL,
 expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE safety_evidence (
 id BIGSERIAL PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES safety_accounts(user_id),
 device_id TEXT NOT NULL REFERENCES safety_devices(id),
 journal_incarnation TEXT NOT NULL,
 sequence BIGINT NOT NULL CHECK(sequence > 0),
 payload_hash TEXT NOT NULL,
 payload JSONB NOT NULL,
 quarantined BOOLEAN NOT NULL DEFAULT TRUE,
 received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(device_id,journal_incarnation,sequence)
);
CREATE INDEX safety_intents_daily ON safety_intents(user_id,created_at);
CREATE INDEX safety_outbox_pending ON safety_outbox(user_id,id) WHERE delivered_at IS NULL;
"""


def apply_migrations(connection, *, disposable=False):
    """Apply v1 transactionally. Caller must explicitly attest disposable database.

    Inject an already-open psycopg2 connection. Never consult production env vars.
    Existing legacy tables are prerequisites and remain byte-for-byte untouched.
    """
    if disposable is not True:
        raise ValueError("Safety migrations are restricted to explicit disposable databases")
    checksum = hashlib.sha256(SCHEMA_V1.encode()).hexdigest()
    with connection:
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(739201844)")
            cur.execute("""CREATE TABLE IF NOT EXISTS safety_schema_versions (
                version INTEGER PRIMARY KEY, checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp())""")
            cur.execute("SELECT checksum FROM safety_schema_versions WHERE version=1")
            row = cur.fetchone()
            if row:
                if row[0] != checksum:
                    raise ValueError("Safety migration checksum mismatch")
                return
            cur.execute(SCHEMA_V1)
            cur.execute("INSERT INTO safety_schema_versions(version,checksum) VALUES (1,%s)", (checksum,))