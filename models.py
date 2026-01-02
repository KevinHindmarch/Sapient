"""
Database models and schema for the Australian Stock Portfolio Optimizer.
Handles user authentication, portfolio tracking, and performance analysis.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import hashlib
import secrets
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


class UserManager:
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
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            password_hash = UserManager.hash_password(password)
            cur.execute("""
                INSERT INTO users (email, password_hash, display_name)
                VALUES (%s, %s, %s)
                RETURNING id, email, display_name, created_at
            """, (email.lower(), password_hash, display_name or email.split('@')[0]))
            
            user = dict(cur.fetchone())
            conn.commit()
            return {'success': True, 'user': user}
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return {'success': False, 'error': 'Email already registered'}
        except Exception as e:
            conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            cur.close()
            conn.close()
    
    @staticmethod
    def authenticate(email: str, password: str) -> dict:
        """Authenticate a user and return their info."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cur.execute("""
                SELECT id, email, password_hash, display_name, created_at
                FROM users WHERE email = %s
            """, (email.lower(),))
            
            user = cur.fetchone()
            if not user:
                return {'success': False, 'error': 'Invalid email or password'}
            
            if not UserManager.verify_password(password, user['password_hash']):
                return {'success': False, 'error': 'Invalid email or password'}
            
            cur.execute("""
                UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s
            """, (user['id'],))
            conn.commit()
            
            del user['password_hash']
            return {'success': True, 'user': dict(user)}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            cur.close()
            conn.close()


class PortfolioManager:
    """Handle portfolio CRUD operations."""
    
    @staticmethod
    def save_portfolio(user_id: int, name: str, optimization_results: dict, 
                       investment_amount: float, mode: str = 'auto',
                       risk_tolerance: str = 'moderate') -> dict:
        """Save a generated portfolio to the database."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cur.execute("""
                INSERT INTO portfolios (
                    user_id, name, mode, initial_investment, 
                    expected_return, expected_volatility, expected_sharpe,
                    expected_dividend_yield, risk_tolerance
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                user_id, name, mode, investment_amount,
                optimization_results.get('expected_return', 0),
                optimization_results.get('volatility', 0),
                optimization_results.get('sharpe_ratio', 0),
                optimization_results.get('portfolio_dividend_yield', 0),
                risk_tolerance
            ))
            
            portfolio_id = cur.fetchone()['id']
            
            # Build allocations from optimizer output - handle 'weights' dict format
            weights = optimization_results.get('weights', {})
            
            # Fetch current prices for each stock
            import yfinance as yf
            for symbol, weight in weights.items():
                if weight < 0.001:  # Skip negligible weights
                    continue
                    
                allocation_amount = weight * investment_amount
                
                # Get current price for the stock
                try:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period='1d')
                    current_price = hist['Close'].iloc[-1] if not hist.empty else 0
                except:
                    current_price = 0
                
                quantity = allocation_amount / current_price if current_price > 0 else 0
                
                cur.execute("""
                    INSERT INTO portfolio_positions (
                        portfolio_id, symbol, quantity, avg_cost,
                        weight_at_creation, allocation_amount, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'active')
                """, (
                    portfolio_id,
                    symbol,
                    quantity,
                    current_price,
                    weight,
                    allocation_amount
                ))
            
            cur.execute("""
                INSERT INTO transactions (
                    portfolio_id, txn_type, symbol, quantity, price, total_amount, notes
                )
                VALUES (%s, 'buy', 'PORTFOLIO_INIT', 1, %s, %s, 'Initial portfolio creation')
            """, (portfolio_id, investment_amount, investment_amount))
            
            conn.commit()
            return {'success': True, 'portfolio_id': portfolio_id}
        except Exception as e:
            conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            cur.close()
            conn.close()
    
    @staticmethod
    def get_user_portfolios(user_id: int) -> list:
        """Get all portfolios for a user."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cur.execute("""
                SELECT p.*, 
                       (SELECT COUNT(*) FROM portfolio_positions pp WHERE pp.portfolio_id = p.id AND pp.status = 'active') as position_count,
                       (SELECT MAX(snapshot_date) FROM portfolio_snapshots ps WHERE ps.portfolio_id = p.id) as last_snapshot
                FROM portfolios p
                WHERE p.user_id = %s
                ORDER BY p.created_at DESC
            """, (user_id,))
            
            return [dict(row) for row in cur.fetchall()]
        finally:
            cur.close()
            conn.close()
    
    @staticmethod
    def get_portfolio_details(portfolio_id: int, user_id: int) -> dict:
        """Get detailed portfolio information including positions."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
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
        finally:
            cur.close()
            conn.close()
    
    @staticmethod
    def update_portfolio_snapshot(portfolio_id: int, current_prices: dict) -> dict:
        """Update portfolio with current market prices."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cur.execute("""
                SELECT pp.*, p.initial_investment
                FROM portfolio_positions pp
                JOIN portfolios p ON p.id = pp.portfolio_id
                WHERE pp.portfolio_id = %s AND pp.status = 'active'
            """, (portfolio_id,))
            
            positions = cur.fetchall()
            if not positions:
                return {'success': False, 'error': 'No active positions'}
            
            total_value = 0
            initial_investment = float(positions[0]['initial_investment'])
            today = datetime.now().date()
            
            for pos in positions:
                symbol = pos['symbol']
                current_price = current_prices.get(symbol, float(pos['avg_cost']))
                quantity = float(pos['quantity'])
                market_value = current_price * quantity
                total_value += market_value
                
                return_pct = ((current_price - float(pos['avg_cost'])) / float(pos['avg_cost'])) * 100 if float(pos['avg_cost']) > 0 else 0
                
                cur.execute("""
                    INSERT INTO position_snapshots (portfolio_position_id, snapshot_date, price, market_value, return_pct)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (portfolio_position_id, snapshot_date) 
                    DO UPDATE SET price = EXCLUDED.price, market_value = EXCLUDED.market_value, return_pct = EXCLUDED.return_pct
                """, (pos['id'], today, current_price, market_value, return_pct))
            
            cumulative_return = ((total_value - initial_investment) / initial_investment) * 100 if initial_investment > 0 else 0
            
            cur.execute("""
                SELECT cumulative_return FROM portfolio_snapshots 
                WHERE portfolio_id = %s AND snapshot_date < %s
                ORDER BY snapshot_date DESC LIMIT 1
            """, (portfolio_id, today))
            
            prev = cur.fetchone()
            prev_cum_return = float(prev['cumulative_return']) if prev else 0
            daily_return = cumulative_return - prev_cum_return
            
            cur.execute("""
                INSERT INTO portfolio_snapshots (portfolio_id, snapshot_date, total_value, daily_return, cumulative_return)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (portfolio_id, snapshot_date)
                DO UPDATE SET total_value = EXCLUDED.total_value, daily_return = EXCLUDED.daily_return, cumulative_return = EXCLUDED.cumulative_return
            """, (portfolio_id, today, total_value, daily_return, cumulative_return))
            
            conn.commit()
            return {'success': True, 'total_value': total_value, 'cumulative_return': cumulative_return}
        except Exception as e:
            conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            cur.close()
            conn.close()
    
    @staticmethod
    def execute_trade(portfolio_id: int, user_id: int, symbol: str, 
                      txn_type: str, quantity: float, price: float, notes: str = None) -> dict:
        """Execute a buy or sell trade."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
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
                    return {'success': False, 'error': f'Insufficient shares. You have {position["quantity"]} shares.'}
                
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
            return {'success': True, 'message': f'{txn_type.upper()} order executed: {quantity} shares of {symbol} at ${price:.2f}'}
        except Exception as e:
            conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            cur.close()
            conn.close()
    
    @staticmethod
    def save_signal(portfolio_id: int, symbol: str, indicator: str, 
                    signal: str, value: float, price: float, notes: str = None) -> dict:
        """Save a trading signal."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cur.execute("""
                INSERT INTO strategy_signals (
                    portfolio_id, symbol, indicator, signal, 
                    indicator_value, price_at_signal, notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (portfolio_id, symbol, indicator, signal, value, price, notes))
            
            signal_id = cur.fetchone()['id']
            conn.commit()
            return {'success': True, 'signal_id': signal_id}
        except Exception as e:
            conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            cur.close()
            conn.close()
    
    @staticmethod
    def get_portfolio_signals(portfolio_id: int, limit: int = 20) -> list:
        """Get recent trading signals for a portfolio."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cur.execute("""
                SELECT * FROM strategy_signals 
                WHERE portfolio_id = %s
                ORDER BY generated_at DESC
                LIMIT %s
            """, (portfolio_id, limit))
            
            return [dict(row) for row in cur.fetchall()]
        finally:
            cur.close()
            conn.close()
