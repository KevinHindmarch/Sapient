"""
Core database module - shared between Streamlit and FastAPI
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from datetime import datetime
import bcrypt


def get_db_connection():
    """Get a database connection using environment variables."""
    return psycopg2.connect(
        host=os.environ.get('PGHOST'),
        database=os.environ.get('PGDATABASE'),
        user=os.environ.get('PGUSER'),
        password=os.environ.get('PGPASSWORD'),
        port=os.environ.get('PGPORT')
    )


@contextmanager
def get_db_cursor(dict_cursor=True):
    """Context manager for database cursor."""
    conn = get_db_connection()
    try:
        cursor_factory = RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=cursor_factory)
        yield cur, conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def init_database():
    """Initialize database schema."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            display_name VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS portfolios (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            mode VARCHAR(20) DEFAULT 'auto',
            initial_investment DECIMAL(15, 2) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'active',
            benchmark_symbol VARCHAR(20) DEFAULT '^AXJO',
            expected_return DECIMAL(8, 4),
            expected_volatility DECIMAL(8, 4),
            expected_sharpe DECIMAL(8, 4),
            expected_dividend_yield DECIMAL(8, 4),
            risk_tolerance VARCHAR(20) DEFAULT 'moderate',
            market VARCHAR(10) DEFAULT 'ASX'
        );
        
        CREATE TABLE IF NOT EXISTS portfolio_positions (
            id SERIAL PRIMARY KEY,
            portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
            symbol VARCHAR(20) NOT NULL,
            quantity DECIMAL(15, 6) NOT NULL,
            avg_cost DECIMAL(15, 4) NOT NULL,
            weight_at_creation DECIMAL(8, 4),
            allocation_amount DECIMAL(15, 2),
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id SERIAL PRIMARY KEY,
            portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
            snapshot_date DATE NOT NULL,
            total_value DECIMAL(15, 2),
            cash_balance DECIMAL(15, 2) DEFAULT 0,
            daily_return DECIMAL(8, 4),
            cumulative_return DECIMAL(8, 4),
            benchmark_return DECIMAL(8, 4),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(portfolio_id, snapshot_date)
        );
        
        CREATE TABLE IF NOT EXISTS position_snapshots (
            id SERIAL PRIMARY KEY,
            portfolio_position_id INTEGER REFERENCES portfolio_positions(id) ON DELETE CASCADE,
            snapshot_date DATE NOT NULL,
            price DECIMAL(15, 4),
            market_value DECIMAL(15, 2),
            return_pct DECIMAL(8, 4),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(portfolio_position_id, snapshot_date)
        );
        
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
            portfolio_position_id INTEGER REFERENCES portfolio_positions(id) ON DELETE SET NULL,
            txn_type VARCHAR(20) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            quantity DECIMAL(15, 6) NOT NULL,
            price DECIMAL(15, 4) NOT NULL,
            total_amount DECIMAL(15, 2) NOT NULL,
            fees DECIMAL(10, 2) DEFAULT 0,
            notes TEXT,
            txn_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS strategy_signals (
            id SERIAL PRIMARY KEY,
            portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
            symbol VARCHAR(20) NOT NULL,
            indicator VARCHAR(20) NOT NULL,
            signal VARCHAR(20) NOT NULL,
            indicator_value DECIMAL(15, 4),
            price_at_signal DECIMAL(15, 4),
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            acknowledged BOOLEAN DEFAULT FALSE,
            notes TEXT
        );
        
        CREATE INDEX IF NOT EXISTS idx_portfolios_user_id ON portfolios(user_id);
        CREATE INDEX IF NOT EXISTS idx_positions_portfolio_id ON portfolio_positions(portfolio_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_portfolio_date ON portfolio_snapshots(portfolio_id, snapshot_date);
        CREATE INDEX IF NOT EXISTS idx_transactions_portfolio_id ON transactions(portfolio_id);
        CREATE INDEX IF NOT EXISTS idx_signals_portfolio_id ON strategy_signals(portfolio_id);

        -- ============================================================
        -- IBKR / AI trading additions
        -- ============================================================

        ALTER TABLE portfolios
            ADD COLUMN IF NOT EXISTS ai_mode VARCHAR(20) DEFAULT 'off';

        CREATE TABLE IF NOT EXISTS broker_credentials (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE UNIQUE,
            broker VARCHAR(20) NOT NULL DEFAULT 'IBKR',
            environment VARCHAR(10) NOT NULL DEFAULT 'paper',
            consumer_key_enc TEXT NOT NULL,
            access_token_enc TEXT NOT NULL,
            access_token_secret_enc TEXT NOT NULL,
            private_key_pem_enc TEXT NOT NULL,
            consumer_key_masked VARCHAR(64),
            connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_test_at TIMESTAMP,
            last_test_ok BOOLEAN
        );

        CREATE TABLE IF NOT EXISTS ai_trading_settings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE UNIQUE,
            mode VARCHAR(20) DEFAULT 'off',
            rsi_buy_threshold DECIMAL(5, 2) DEFAULT 30.00,
            rsi_sell_threshold DECIMAL(5, 2) DEFAULT 70.00,
            max_trade_pct DECIMAL(5, 2) DEFAULT 5.00,
            max_daily_trades INTEGER DEFAULT 8,
            max_daily_turnover_pct DECIMAL(5, 2) DEFAULT 20.00,
            sector_cap_pct DECIMAL(5, 2) DEFAULT 35.00,
            paper_only BOOLEAN DEFAULT TRUE,
            breaker_on_loss_pct DECIMAL(5, 2) DEFAULT 3.00,
            breaker_on_volatility_spike BOOLEAN DEFAULT TRUE,
            breaker_on_news_event BOOLEAN DEFAULT TRUE,
            last_kill_switch_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ai_signals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
            symbol VARCHAR(20) NOT NULL,
            company_name VARCHAR(255),
            market VARCHAR(10) DEFAULT 'ASX',
            action VARCHAR(8) NOT NULL,
            quantity DECIMAL(15, 6) NOT NULL,
            price_at_signal DECIMAL(15, 4) NOT NULL,
            confidence DECIMAL(4, 3) DEFAULT 0.5,
            rationale JSONB DEFAULT '{}'::jsonb,
            rule_summary TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            decided_at TIMESTAMP,
            decided_by VARCHAR(20),
            expires_at TIMESTAMP,
            executed_order_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS broker_orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE SET NULL,
            signal_id INTEGER REFERENCES ai_signals(id) ON DELETE SET NULL,
            broker_order_id VARCHAR(64) NOT NULL,
            broker VARCHAR(20) DEFAULT 'IBKR',
            account_id VARCHAR(32),
            symbol VARCHAR(20) NOT NULL,
            side VARCHAR(8) NOT NULL,
            quantity DECIMAL(15, 6) NOT NULL,
            order_type VARCHAR(8) NOT NULL,
            limit_price DECIMAL(15, 4),
            status VARCHAR(20) DEFAULT 'Submitted',
            filled_qty DECIMAL(15, 6) DEFAULT 0,
            avg_fill_price DECIMAL(15, 4),
            fees DECIMAL(10, 2) DEFAULT 0,
            sim BOOLEAN DEFAULT TRUE,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ai_audit_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            event_type VARCHAR(40) NOT NULL,
            portfolio_id INTEGER,
            signal_id INTEGER,
            order_id INTEGER,
            payload JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_ai_signals_user_status ON ai_signals(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_ai_signals_portfolio ON ai_signals(portfolio_id);
        CREATE INDEX IF NOT EXISTS idx_broker_orders_user ON broker_orders(user_id, submitted_at DESC);
        CREATE INDEX IF NOT EXISTS idx_broker_orders_portfolio ON broker_orders(portfolio_id);
        CREATE INDEX IF NOT EXISTS idx_audit_user_created ON ai_audit_log(user_id, created_at DESC);
    """)
    
    conn.commit()
    cur.close()
    conn.close()


class UserService:
    """Handle user authentication and management."""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    @staticmethod
    def create_user(email: str, password: str, display_name: str = None) -> dict:
        """Create a new user account."""
        with get_db_cursor() as (cur, conn):
            try:
                password_hash = UserService.hash_password(password)
                cur.execute("""
                    INSERT INTO users (email, password_hash, display_name)
                    VALUES (%s, %s, %s)
                    RETURNING id, email, display_name, created_at
                """, (email.lower(), password_hash, display_name or email.split('@')[0]))
                
                user = dict(cur.fetchone())
                conn.commit()
                return {'success': True, 'user': user}
            except psycopg2.errors.UniqueViolation:
                return {'success': False, 'error': 'Email already registered'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
    
    @staticmethod
    def authenticate(email: str, password: str) -> dict:
        """Authenticate a user and return their info."""
        with get_db_cursor() as (cur, conn):
            try:
                cur.execute("""
                    SELECT id, email, password_hash, display_name, created_at
                    FROM users WHERE email = %s
                """, (email.lower(),))
                
                user = cur.fetchone()
                if not user:
                    return {'success': False, 'error': 'Invalid email or password'}
                
                if not UserService.verify_password(password, user['password_hash']):
                    return {'success': False, 'error': 'Invalid email or password'}
                
                cur.execute("""
                    UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s
                """, (user['id'],))
                conn.commit()
                
                user_dict = dict(user)
                del user_dict['password_hash']
                return {'success': True, 'user': user_dict}
            except Exception as e:
                return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_user_by_id(user_id: int) -> dict:
        """Get user by ID."""
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                SELECT id, email, display_name, created_at FROM users WHERE id = %s
            """, (user_id,))
            user = cur.fetchone()
            return dict(user) if user else None


class PortfolioService:
    """Handle portfolio CRUD operations."""
    
    @staticmethod
    def save_portfolio(user_id: int, name: str, optimization_results: dict, 
                       investment_amount: float, mode: str = 'auto',
                       risk_tolerance: str = 'moderate', market: str = 'ASX') -> dict:
        """Save a generated portfolio to the database."""
        import yfinance as yf
        
        with get_db_cursor() as (cur, conn):
            try:
                expected_return = float(optimization_results.get('expected_return', 0) or 0)
                volatility = float(optimization_results.get('volatility', 0) or 0)
                sharpe_ratio = float(optimization_results.get('sharpe_ratio', 0) or 0)
                dividend_yield = float(optimization_results.get('portfolio_dividend_yield', 0) or 0)
                
                cur.execute("""
                    INSERT INTO portfolios (
                        user_id, name, mode, initial_investment, 
                        expected_return, expected_volatility, expected_sharpe,
                        expected_dividend_yield, risk_tolerance, market
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    user_id, name, mode, float(investment_amount),
                    expected_return, volatility, sharpe_ratio, dividend_yield,
                    risk_tolerance, market
                ))
                
                portfolio_id = cur.fetchone()['id']
                
                weights = optimization_results.get('weights', {})
                
                actual_invested = 0.0
                failed_symbols = []
                
                for symbol, weight in weights.items():
                    weight_float = float(weight)
                    if weight_float < 0.001:
                        continue
                        
                    allocation_amount = weight_float * float(investment_amount)
                    
                    try:
                        ticker = yf.Ticker(symbol)
                        hist = ticker.history(period='1d')
                        current_price = float(hist['Close'].iloc[-1]) if not hist.empty else 0.0
                    except:
                        current_price = 0.0
                    
                    if current_price <= 0:
                        failed_symbols.append(symbol)
                        continue
                    
                    quantity = allocation_amount / current_price
                    actual_invested += allocation_amount
                    
                    cur.execute("""
                        INSERT INTO portfolio_positions (
                            portfolio_id, symbol, quantity, avg_cost,
                            weight_at_creation, allocation_amount, status
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, 'active')
                    """, (
                        portfolio_id, symbol, float(quantity), float(current_price),
                        float(weight_float), float(allocation_amount)
                    ))
                
                if actual_invested < float(investment_amount) * 0.99:
                    cur.execute("""
                        UPDATE portfolios SET initial_investment = %s WHERE id = %s
                    """, (actual_invested, portfolio_id))
                
                conn.commit()
                
                result = {'success': True, 'portfolio_id': portfolio_id}
                if failed_symbols:
                    result['warning'] = f"Could not fetch prices for: {', '.join(failed_symbols)}"
                    result['actual_invested'] = actual_invested
                return result
            except Exception as e:
                return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_user_portfolios(user_id: int) -> list:
        """Get all portfolios for a user."""
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                SELECT p.*, 
                       (SELECT COUNT(*) FROM portfolio_positions pp 
                        WHERE pp.portfolio_id = p.id AND pp.status = 'active') as position_count,
                       (SELECT MAX(snapshot_date) FROM portfolio_snapshots ps 
                        WHERE ps.portfolio_id = p.id) as last_snapshot
                FROM portfolios p
                WHERE p.user_id = %s
                ORDER BY p.created_at DESC
            """, (user_id,))
            
            return [dict(row) for row in cur.fetchall()]
    
    @staticmethod
    def get_portfolio_details(portfolio_id: int, user_id: int) -> dict:
        """Get detailed portfolio information including positions."""
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                SELECT * FROM portfolios WHERE id = %s AND user_id = %s
            """, (portfolio_id, user_id))
            
            portfolio = cur.fetchone()
            if not portfolio:
                return None
            
            cur.execute("""
                SELECT * FROM portfolio_positions 
                WHERE portfolio_id = %s
                ORDER BY allocation_amount DESC
            """, (portfolio_id,))
            positions = [dict(row) for row in cur.fetchall()]
            
            cur.execute("""
                SELECT * FROM portfolio_snapshots 
                WHERE portfolio_id = %s
                ORDER BY snapshot_date DESC
                LIMIT 30
            """, (portfolio_id,))
            snapshots = [dict(row) for row in cur.fetchall()]
            
            cur.execute("""
                SELECT * FROM transactions 
                WHERE portfolio_id = %s
                ORDER BY txn_time DESC
                LIMIT 50
            """, (portfolio_id,))
            transactions = [dict(row) for row in cur.fetchall()]
            
            return {
                'portfolio': dict(portfolio),
                'positions': positions,
                'snapshots': snapshots,
                'transactions': transactions
            }
    
    @staticmethod
    def execute_trade(portfolio_id: int, user_id: int, symbol: str, 
                      txn_type: str, quantity: float, price: float, notes: str = None) -> dict:
        """Execute a buy or sell trade."""
        with get_db_cursor() as (cur, conn):
            try:
                cur.execute("""
                    SELECT id FROM portfolios WHERE id = %s AND user_id = %s
                """, (portfolio_id, user_id))
                
                if not cur.fetchone():
                    return {'success': False, 'error': 'Portfolio not found'}
                
                total_amount = quantity * price
                
                if txn_type == 'sell':
                    cur.execute("""
                        SELECT id, quantity FROM portfolio_positions 
                        WHERE portfolio_id = %s AND symbol = %s AND status = 'active'
                    """, (portfolio_id, symbol))
                    
                    position = cur.fetchone()
                    if not position:
                        return {'success': False, 'error': f'No position found for {symbol}'}
                    
                    if float(position['quantity']) < quantity:
                        return {'success': False, 'error': f'Insufficient shares'}
                    
                    new_quantity = float(position['quantity']) - quantity
                    if new_quantity <= 0:
                        cur.execute("""
                            UPDATE portfolio_positions 
                            SET status = 'sold', quantity = 0, closed_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (position['id'],))
                    else:
                        cur.execute("""
                            UPDATE portfolio_positions SET quantity = %s WHERE id = %s
                        """, (new_quantity, position['id']))
                    
                    position_id = position['id']
                else:
                    cur.execute("""
                        SELECT id, quantity, avg_cost FROM portfolio_positions 
                        WHERE portfolio_id = %s AND symbol = %s AND status = 'active'
                    """, (portfolio_id, symbol))
                    
                    existing = cur.fetchone()
                    if existing:
                        old_qty = float(existing['quantity'])
                        old_cost = float(existing['avg_cost'])
                        new_qty = old_qty + quantity
                        new_avg_cost = ((old_qty * old_cost) + (quantity * price)) / new_qty
                        
                        cur.execute("""
                            UPDATE portfolio_positions 
                            SET quantity = %s, avg_cost = %s
                            WHERE id = %s
                        """, (new_qty, new_avg_cost, existing['id']))
                        position_id = existing['id']
                    else:
                        cur.execute("""
                            INSERT INTO portfolio_positions (portfolio_id, symbol, quantity, avg_cost, status)
                            VALUES (%s, %s, %s, %s, 'active')
                            RETURNING id
                        """, (portfolio_id, symbol, quantity, price))
                        position_id = cur.fetchone()['id']
                
                cur.execute("""
                    INSERT INTO transactions (
                        portfolio_id, portfolio_position_id, txn_type, symbol, 
                        quantity, price, total_amount, notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (portfolio_id, position_id, txn_type, symbol, quantity, price, total_amount, notes))
                
                if txn_type == 'buy':
                    cur.execute("""
                        UPDATE portfolios 
                        SET initial_investment = initial_investment + %s
                        WHERE id = %s
                    """, (total_amount, portfolio_id))
                
                conn.commit()
                return {'success': True, 'message': f'{txn_type.upper()} order executed'}
            except Exception as e:
                return {'success': False, 'error': str(e)}

    @staticmethod
    def update_position(portfolio_id: int, user_id: int, position_id: int, 
                        quantity: float, avg_cost: float = None) -> dict:
        """Update position quantity and optionally avg cost. Records adjustment transaction."""
        if quantity < 0:
            return {'success': False, 'error': 'Quantity cannot be negative'}
        if avg_cost is not None and avg_cost <= 0:
            return {'success': False, 'error': 'Average cost must be positive'}
            
        with get_db_cursor() as (cur, conn):
            try:
                cur.execute("""
                    SELECT pp.id, pp.quantity, pp.avg_cost, pp.symbol FROM portfolio_positions pp
                    JOIN portfolios p ON p.id = pp.portfolio_id
                    WHERE pp.id = %s AND pp.portfolio_id = %s AND p.user_id = %s AND pp.status = 'active'
                """, (position_id, portfolio_id, user_id))
                
                position = cur.fetchone()
                if not position:
                    return {'success': False, 'error': 'Position not found'}
                
                old_qty = float(position['quantity'])
                new_avg_cost = avg_cost if avg_cost is not None else float(position['avg_cost'])
                qty_diff = quantity - old_qty
                
                if quantity <= 0:
                    cur.execute("""
                        UPDATE portfolio_positions 
                        SET status = 'sold', quantity = 0, closed_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (position_id,))
                    txn_type = 'sell'
                    txn_qty = old_qty
                else:
                    cur.execute("""
                        UPDATE portfolio_positions 
                        SET quantity = %s, avg_cost = %s, allocation_amount = %s
                        WHERE id = %s
                    """, (quantity, new_avg_cost, quantity * new_avg_cost, position_id))
                    txn_type = 'buy' if qty_diff > 0 else 'sell'
                    txn_qty = abs(qty_diff) if qty_diff != 0 else 0
                
                if txn_qty > 0:
                    cur.execute("""
                        INSERT INTO transactions (
                            portfolio_id, portfolio_position_id, txn_type, symbol, 
                            quantity, price, total_amount, notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (portfolio_id, position_id, txn_type, position['symbol'], 
                          txn_qty, new_avg_cost, txn_qty * new_avg_cost, 'Position adjustment'))
                    
                    if txn_type == 'buy':
                        cur.execute("""
                            UPDATE portfolios 
                            SET initial_investment = initial_investment + %s
                            WHERE id = %s
                        """, (txn_qty * new_avg_cost, portfolio_id))
                
                conn.commit()
                return {'success': True, 'message': 'Position updated'}
            except Exception as e:
                return {'success': False, 'error': str(e)}

    @staticmethod
    def remove_position(portfolio_id: int, user_id: int, position_id: int) -> dict:
        """Remove a position from portfolio by marking as sold. Preserves audit trail."""
        with get_db_cursor() as (cur, conn):
            try:
                cur.execute("""
                    SELECT pp.id, pp.quantity, pp.avg_cost, pp.symbol FROM portfolio_positions pp
                    JOIN portfolios p ON p.id = pp.portfolio_id
                    WHERE pp.id = %s AND pp.portfolio_id = %s AND p.user_id = %s AND pp.status = 'active'
                """, (position_id, portfolio_id, user_id))
                
                position = cur.fetchone()
                if not position:
                    return {'success': False, 'error': 'Position not found'}
                
                cur.execute("""
                    UPDATE portfolio_positions 
                    SET status = 'sold', quantity = 0, closed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (position_id,))
                
                qty = float(position['quantity'])
                price = float(position['avg_cost'])
                cur.execute("""
                    INSERT INTO transactions (
                        portfolio_id, portfolio_position_id, txn_type, symbol, 
                        quantity, price, total_amount, notes
                    )
                    VALUES (%s, %s, 'sell', %s, %s, %s, %s, %s)
                """, (portfolio_id, position_id, position['symbol'], 
                      qty, price, qty * price, 'Position removed'))
                
                conn.commit()
                return {'success': True, 'message': 'Position removed'}
            except Exception as e:
                return {'success': False, 'error': str(e)}

    @staticmethod
    def delete_portfolio(portfolio_id: int, user_id: int) -> dict:
        """Delete a portfolio and all its associated data."""
        with get_db_cursor() as (cur, conn):
            try:
                cur.execute("""
                    SELECT id FROM portfolios WHERE id = %s AND user_id = %s
                """, (portfolio_id, user_id))
                
                if not cur.fetchone():
                    return {'success': False, 'error': 'Portfolio not found'}
                
                cur.execute("DELETE FROM portfolios WHERE id = %s AND user_id = %s", 
                            (portfolio_id, user_id))
                conn.commit()
                return {'success': True, 'message': 'Portfolio deleted'}
            except Exception as e:
                return {'success': False, 'error': str(e)}

    @staticmethod
    def add_stock_to_portfolio(portfolio_id: int, user_id: int, symbol: str, 
                               quantity: float, avg_cost: float) -> dict:
        """Add a new stock to an existing portfolio."""
        if quantity <= 0:
            return {'success': False, 'error': 'Quantity must be positive'}
        if avg_cost <= 0:
            return {'success': False, 'error': 'Price must be positive'}
        if not symbol or len(symbol) < 2:
            return {'success': False, 'error': 'Invalid stock symbol'}
            
        with get_db_cursor() as (cur, conn):
            try:
                cur.execute("""
                    SELECT id FROM portfolios WHERE id = %s AND user_id = %s
                """, (portfolio_id, user_id))
                
                if not cur.fetchone():
                    return {'success': False, 'error': 'Portfolio not found'}
                
                cur.execute("""
                    SELECT id FROM portfolio_positions 
                    WHERE portfolio_id = %s AND symbol = %s AND status = 'active'
                """, (portfolio_id, symbol))
                
                if cur.fetchone():
                    return {'success': False, 'error': f'{symbol} already exists in portfolio. Use edit to modify.'}
                
                cur.execute("""
                    INSERT INTO portfolio_positions (portfolio_id, symbol, quantity, avg_cost, allocation_amount, status)
                    VALUES (%s, %s, %s, %s, %s, 'active')
                    RETURNING id
                """, (portfolio_id, symbol, quantity, avg_cost, quantity * avg_cost))
                
                position_id = cur.fetchone()['id']
                
                cur.execute("""
                    INSERT INTO transactions (
                        portfolio_id, portfolio_position_id, txn_type, symbol, 
                        quantity, price, total_amount, notes
                    )
                    VALUES (%s, %s, 'buy', %s, %s, %s, %s, 'Stock added to portfolio')
                """, (portfolio_id, position_id, symbol, quantity, avg_cost, quantity * avg_cost))
                
                conn.commit()
                return {'success': True, 'message': 'Stock added to portfolio', 'position_id': position_id}
            except Exception as e:
                return {'success': False, 'error': str(e)}


# ============================================================================
# IBKR / AI trading service classes
# ============================================================================


class BrokerCredentialService:
    """Encrypted IBKR credentials per user."""

    @staticmethod
    def upsert(user_id: int, consumer_key: str, access_token: str,
               access_token_secret: str, private_key_pem: str,
               environment: str = 'paper') -> dict:
        from core.crypto import encrypt_str, mask_secret
        with get_db_cursor() as (cur, conn):
            try:
                cur.execute("""
                    INSERT INTO broker_credentials (
                        user_id, broker, environment,
                        consumer_key_enc, access_token_enc,
                        access_token_secret_enc, private_key_pem_enc,
                        consumer_key_masked
                    )
                    VALUES (%s, 'IBKR', %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        environment = EXCLUDED.environment,
                        consumer_key_enc = EXCLUDED.consumer_key_enc,
                        access_token_enc = EXCLUDED.access_token_enc,
                        access_token_secret_enc = EXCLUDED.access_token_secret_enc,
                        private_key_pem_enc = EXCLUDED.private_key_pem_enc,
                        consumer_key_masked = EXCLUDED.consumer_key_masked,
                        connected_at = CURRENT_TIMESTAMP
                    RETURNING id, environment, consumer_key_masked, connected_at
                """, (
                    user_id, environment,
                    encrypt_str(consumer_key),
                    encrypt_str(access_token),
                    encrypt_str(access_token_secret),
                    encrypt_str(private_key_pem),
                    mask_secret(consumer_key),
                ))
                row = dict(cur.fetchone())
                conn.commit()
                return {'success': True, **row}
            except Exception as e:
                return {'success': False, 'error': str(e)}

    @staticmethod
    def get_status(user_id: int) -> dict:
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                SELECT environment, consumer_key_masked, connected_at,
                       last_test_at, last_test_ok
                FROM broker_credentials WHERE user_id = %s
            """, (user_id,))
            row = cur.fetchone()
            if not row:
                return {'connected': False}
            return {'connected': True, **dict(row)}

    @staticmethod
    def get_decrypted(user_id: int):
        """Returns IBKRCredentials or None."""
        from core.crypto import decrypt_str
        from core.ibkr_client import IBKRCredentials
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                SELECT environment, consumer_key_enc, access_token_enc,
                       access_token_secret_enc, private_key_pem_enc
                FROM broker_credentials WHERE user_id = %s
            """, (user_id,))
            row = cur.fetchone()
            if not row:
                return None
            return IBKRCredentials(
                consumer_key=decrypt_str(row['consumer_key_enc']),
                access_token=decrypt_str(row['access_token_enc']),
                access_token_secret=decrypt_str(row['access_token_secret_enc']),
                private_key_pem=decrypt_str(row['private_key_pem_enc']),
                environment=row['environment'],
            )

    @staticmethod
    def record_test(user_id: int, ok: bool) -> None:
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                UPDATE broker_credentials
                SET last_test_at = CURRENT_TIMESTAMP, last_test_ok = %s
                WHERE user_id = %s
            """, (ok, user_id))
            conn.commit()

    @staticmethod
    def delete(user_id: int) -> dict:
        with get_db_cursor() as (cur, conn):
            cur.execute("DELETE FROM broker_credentials WHERE user_id = %s", (user_id,))
            conn.commit()
            return {'success': True}


class AITradingSettingsService:
    """Per-user AI trading settings."""

    DEFAULTS = {
        'mode': 'off',
        'rsi_buy_threshold': 30.0,
        'rsi_sell_threshold': 70.0,
        'max_trade_pct': 5.0,
        'max_daily_trades': 8,
        'max_daily_turnover_pct': 20.0,
        'sector_cap_pct': 35.0,
        'paper_only': True,
        'breaker_on_loss_pct': 3.0,
        'breaker_on_volatility_spike': True,
        'breaker_on_news_event': True,
        'last_kill_switch_at': None,
    }

    @staticmethod
    def _row_to_dict(row) -> dict:
        if row is None:
            return None
        d = dict(row)
        for k in ('rsi_buy_threshold', 'rsi_sell_threshold', 'max_trade_pct',
                  'max_daily_turnover_pct', 'sector_cap_pct', 'breaker_on_loss_pct'):
            if d.get(k) is not None:
                d[k] = float(d[k])
        return d

    @staticmethod
    def get(user_id: int) -> dict:
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                SELECT mode, rsi_buy_threshold, rsi_sell_threshold, max_trade_pct,
                       max_daily_trades, max_daily_turnover_pct, sector_cap_pct,
                       paper_only, breaker_on_loss_pct, breaker_on_volatility_spike,
                       breaker_on_news_event, last_kill_switch_at
                FROM ai_trading_settings WHERE user_id = %s
            """, (user_id,))
            row = cur.fetchone()
            if row is None:
                cur.execute("""
                    INSERT INTO ai_trading_settings (user_id) VALUES (%s)
                    RETURNING mode, rsi_buy_threshold, rsi_sell_threshold, max_trade_pct,
                              max_daily_trades, max_daily_turnover_pct, sector_cap_pct,
                              paper_only, breaker_on_loss_pct, breaker_on_volatility_spike,
                              breaker_on_news_event, last_kill_switch_at
                """, (user_id,))
                row = cur.fetchone()
                conn.commit()
            return AITradingSettingsService._row_to_dict(row)

    @staticmethod
    def update(user_id: int, updates: dict) -> dict:
        AITradingSettingsService.get(user_id)  # ensure row exists
        allowed = {
            'mode', 'rsi_buy_threshold', 'rsi_sell_threshold', 'max_trade_pct',
            'max_daily_trades', 'max_daily_turnover_pct', 'sector_cap_pct',
            'paper_only', 'breaker_on_loss_pct', 'breaker_on_volatility_spike',
            'breaker_on_news_event',
        }
        sets = []
        params = []
        for k, v in updates.items():
            if k in allowed and v is not None:
                sets.append(f"{k} = %s")
                params.append(v)
        if not sets:
            return AITradingSettingsService.get(user_id)
        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.append(user_id)
        with get_db_cursor() as (cur, conn):
            cur.execute(f"""
                UPDATE ai_trading_settings SET {', '.join(sets)}
                WHERE user_id = %s
            """, params)
            conn.commit()
        return AITradingSettingsService.get(user_id)

    @staticmethod
    def kill_switch(user_id: int) -> dict:
        """Set mode to off, expire all pending signals, mark broker_orders cancelled."""
        with get_db_cursor() as (cur, conn):
            AITradingSettingsService.get(user_id)  # ensure row exists
            cur.execute("""
                UPDATE ai_trading_settings
                SET mode = 'off', last_kill_switch_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
            """, (user_id,))
            cur.execute("""
                UPDATE ai_signals SET status = 'expired',
                    decided_at = CURRENT_TIMESTAMP, decided_by = 'kill_switch'
                WHERE user_id = %s AND status = 'pending'
                RETURNING id
            """, (user_id,))
            cancelled_signals = len(cur.fetchall())
            cur.execute("""
                UPDATE broker_orders SET status = 'Cancelled', updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND status IN ('Submitted','PendingSubmit','PreSubmitted')
                RETURNING id
            """, (user_id,))
            cancelled_orders = len(cur.fetchall())
            cur.execute("""
                UPDATE portfolios SET ai_mode = 'off' WHERE user_id = %s
            """, (user_id,))
            cur.execute("""
                INSERT INTO ai_audit_log (user_id, event_type, payload)
                VALUES (%s, 'kill_switch', %s)
            """, (user_id, '{}'))
            conn.commit()
            return {
                'cancelled_signals': cancelled_signals,
                'cancelled_orders': cancelled_orders,
            }


class AISignalService:
    """Pending and historical AI trading signals."""

    @staticmethod
    def _row_to_dict(row) -> dict:
        if row is None:
            return None
        d = dict(row)
        if d.get('quantity') is not None:
            d['quantity'] = float(d['quantity'])
        if d.get('price_at_signal') is not None:
            d['price_at_signal'] = float(d['price_at_signal'])
        if d.get('confidence') is not None:
            d['confidence'] = float(d['confidence'])
        d['estimated_value'] = (d.get('quantity') or 0) * (d.get('price_at_signal') or 0)
        return d

    @staticmethod
    def create_many(user_id: int, signals: list) -> list:
        """signals = list of dicts matching ai_signals columns."""
        import json
        created = []
        with get_db_cursor() as (cur, conn):
            for s in signals:
                cur.execute("""
                    INSERT INTO ai_signals (
                        user_id, portfolio_id, symbol, company_name, market,
                        action, quantity, price_at_signal, confidence,
                        rationale, rule_summary, expires_at, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                    RETURNING id, user_id, portfolio_id, symbol, company_name, market,
                              action, quantity, price_at_signal, confidence,
                              rationale, rule_summary, status, generated_at,
                              decided_at, decided_by, expires_at, executed_order_id
                """, (
                    user_id, s['portfolio_id'], s['symbol'], s.get('company_name'),
                    s.get('market', 'ASX'), s['action'], s['quantity'],
                    s['price_at_signal'], s.get('confidence', 0.5),
                    json.dumps(s.get('rationale', {})), s.get('rule_summary', ''),
                    s.get('expires_at'),
                ))
                created.append(AISignalService._row_to_dict(cur.fetchone()))
            conn.commit()
        return created

    @staticmethod
    def list_for_user(user_id: int, status: str = None, limit: int = 100) -> list:
        with get_db_cursor() as (cur, conn):
            if status:
                cur.execute("""
                    SELECT s.*, p.name AS portfolio_name
                    FROM ai_signals s
                    LEFT JOIN portfolios p ON p.id = s.portfolio_id
                    WHERE s.user_id = %s AND s.status = %s
                    ORDER BY s.generated_at DESC LIMIT %s
                """, (user_id, status, limit))
            else:
                cur.execute("""
                    SELECT s.*, p.name AS portfolio_name
                    FROM ai_signals s
                    LEFT JOIN portfolios p ON p.id = s.portfolio_id
                    WHERE s.user_id = %s
                    ORDER BY s.generated_at DESC LIMIT %s
                """, (user_id, limit))
            return [AISignalService._row_to_dict(r) for r in cur.fetchall()]

    @staticmethod
    def get(user_id: int, signal_id: int) -> dict:
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                SELECT s.*, p.name AS portfolio_name
                FROM ai_signals s
                LEFT JOIN portfolios p ON p.id = s.portfolio_id
                WHERE s.id = %s AND s.user_id = %s
            """, (signal_id, user_id))
            return AISignalService._row_to_dict(cur.fetchone())

    @staticmethod
    def update_status(user_id: int, signal_id: int, status: str,
                      decided_by: str = 'user', executed_order_id: int = None,
                      new_expires_at=None) -> dict:
        with get_db_cursor() as (cur, conn):
            sets = ["status = %s", "decided_at = CURRENT_TIMESTAMP", "decided_by = %s"]
            params: list = [status, decided_by]
            if executed_order_id is not None:
                sets.append("executed_order_id = %s")
                params.append(executed_order_id)
            if new_expires_at is not None:
                sets.append("expires_at = %s")
                params.append(new_expires_at)
            params.extend([signal_id, user_id])
            cur.execute(f"""
                UPDATE ai_signals SET {', '.join(sets)}
                WHERE id = %s AND user_id = %s
                RETURNING id
            """, params)
            row = cur.fetchone()
            conn.commit()
            if row is None:
                return None
        return AISignalService.get(user_id, signal_id)


class BrokerOrderService:
    """Persisted broker order ledger (links signals → broker fills)."""

    @staticmethod
    def _row_to_dict(row) -> dict:
        if row is None:
            return None
        d = dict(row)
        for k in ('quantity', 'limit_price', 'filled_qty', 'avg_fill_price', 'fees'):
            if d.get(k) is not None:
                d[k] = float(d[k])
        return d

    @staticmethod
    def insert(user_id: int, order, account_id: str = None,
               portfolio_id: int = None, signal_id: int = None) -> dict:
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                INSERT INTO broker_orders (
                    user_id, portfolio_id, signal_id, broker_order_id, broker,
                    account_id, symbol, side, quantity, order_type, limit_price,
                    status, filled_qty, avg_fill_price, fees, sim, submitted_at
                ) VALUES (%s, %s, %s, %s, 'IBKR', %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING *
            """, (
                user_id, portfolio_id, signal_id, order.order_id, account_id,
                order.symbol, order.side, order.quantity, order.order_type,
                order.limit_price, order.status, order.filled_qty,
                order.avg_fill_price, order.fees, getattr(order, 'sim', True),
            ))
            row = cur.fetchone()
            conn.commit()
            return BrokerOrderService._row_to_dict(row)

    @staticmethod
    def list_recent(user_id: int, limit: int = 50) -> list:
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                SELECT * FROM broker_orders WHERE user_id = %s
                ORDER BY submitted_at DESC LIMIT %s
            """, (user_id, limit))
            return [BrokerOrderService._row_to_dict(r) for r in cur.fetchall()]


class AIAuditService:
    """Append-only audit log for AI events (kill-switch, autonomous executions)."""

    @staticmethod
    def log(user_id: int, event_type: str, payload: dict = None,
            portfolio_id: int = None, signal_id: int = None,
            order_id: int = None) -> None:
        import json
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                INSERT INTO ai_audit_log (
                    user_id, event_type, portfolio_id, signal_id, order_id, payload
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, event_type, portfolio_id, signal_id, order_id,
                  json.dumps(payload or {})))
            conn.commit()

    @staticmethod
    def list_recent(user_id: int, limit: int = 100) -> list:
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                SELECT * FROM ai_audit_log WHERE user_id = %s
                ORDER BY created_at DESC LIMIT %s
            """, (user_id, limit))
            return [dict(r) for r in cur.fetchall()]
