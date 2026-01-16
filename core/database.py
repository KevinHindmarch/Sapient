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
            risk_tolerance VARCHAR(20) DEFAULT 'moderate'
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
                       risk_tolerance: str = 'moderate') -> dict:
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
                        expected_dividend_yield, risk_tolerance
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    user_id, name, mode, float(investment_amount),
                    expected_return, volatility, sharpe_ratio, dividend_yield,
                    risk_tolerance
                ))
                
                portfolio_id = cur.fetchone()['id']
                
                weights = optimization_results.get('weights', {})
                
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
                    
                    quantity = allocation_amount / current_price if current_price > 0 else 0.0
                    
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
                
                conn.commit()
                return {'success': True, 'portfolio_id': portfolio_id}
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
