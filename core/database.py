"""
Core database module
"""

from datetime import datetime, timezone
from decimal import Decimal

from core import db


def get_db_connection():
    """Open a connection to the local SQLite database."""
    return db.connect()


def get_db_cursor(dict_cursor=True):
    """Context manager yielding ``(cursor, connection)`` in one write transaction."""
    return db.transaction()


def init_database():
    """Create or upgrade the schema (backs up an existing database first)."""
    from core.migrations import migrate
    return migrate()


LOCAL_USER_ID = 1


class UserService:
    """The single local profile of the desktop app (no passwords, no login)."""

    @staticmethod
    def ensure_local_user() -> dict:
        """Create the local profile row on first run; all data hangs off it."""
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                INSERT INTO users (id, email, password_hash, display_name)
                VALUES (%s, 'local@sapient.invalid', '!', 'Investor')
                ON CONFLICT(id) DO NOTHING
            """, (LOCAL_USER_ID,))
        return UserService.get_local_user()

    @staticmethod
    def get_local_user() -> dict:
        return UserService.get_user_by_id(LOCAL_USER_ID)

    @staticmethod
    def update_profile(display_name: str | None = None, theme: str | None = None,
                       complete_onboarding: bool = False) -> dict:
        """Change the local profile; completing onboarding stops the first-run wizard."""
        from datetime import datetime, timezone
        sets, params = [], []
        if display_name is not None:
            sets.append("display_name = %s")
            params.append(display_name)
        if theme is not None:
            sets.append("theme = %s")
            params.append(theme)
        if complete_onboarding:
            sets.append("onboarded_at = COALESCE(onboarded_at, %s)")
            params.append(datetime.now(timezone.utc))
        if sets:
            with get_db_cursor() as (cur, conn):
                cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s", (*params, LOCAL_USER_ID))
        return UserService.get_local_user()

    @staticmethod
    def get_user_by_id(user_id: int) -> dict:
        """Get user by ID."""
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                SELECT id, email, display_name, theme, onboarded_at, created_at FROM users WHERE id = %s
            """, (user_id,))
            user = cur.fetchone()
            return dict(user) if user else None


class PortfolioService:
    """Handle portfolio CRUD operations."""

    BROKER_MANAGED = ("This portfolio trades at Interactive Brokers, so its holdings follow your actual fills. "
                      "Change it with orders (Orders page or the AI Inbox) instead.")

    @staticmethod
    def _own(cur, portfolio_id: int, user_id: int) -> dict | None:
        cur.execute("SELECT * FROM portfolios WHERE id = %s AND user_id = %s", (portfolio_id, user_id))
        row = cur.fetchone()
        return dict(row) if row else None
    
    @staticmethod
    def save_portfolio(user_id: int, name: str, optimization_results: dict, 
                       investment_amount: float, mode: str = 'auto',
                       risk_tolerance: str = 'moderate', market: str = 'ASX') -> dict:
        """Save a generated portfolio to the database."""
        from core import yahoo as yf
        
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
        """Record a buy or sell you made yourself (bookkeeping only, nothing is sent to a broker)."""
        from core import ledger
        if txn_type not in ('buy', 'sell'):
            return {'success': False, 'error': 'Trade type must be buy or sell'}
        if not quantity or quantity <= 0 or not price or price <= 0:
            return {'success': False, 'error': 'Quantity and price must be positive'}
        with get_db_cursor() as (cur, conn):
            try:
                portfolio = PortfolioService._own(cur, portfolio_id, user_id)
                if portfolio is None:
                    return {'success': False, 'error': 'Portfolio not found'}
                if portfolio.get('trading_environment'):
                    return {'success': False, 'error': PortfolioService.BROKER_MANAGED}
                
                total_amount = quantity * price
                realised = None
                
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
                    cur.execute("SELECT avg_cost FROM portfolio_positions WHERE id = %s", (position['id'],))
                    realised = (price - float(cur.fetchone()['avg_cost'])) * quantity
                    
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
                    ledger.add_money_if_needed(cur, portfolio_id, Decimal(str(total_amount)))
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
                        quantity, price, total_amount, notes, realised_pnl
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (portfolio_id, position_id, txn_type, symbol, quantity, price, total_amount, notes, realised))
                
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
                if PortfolioService._own(cur, portfolio_id, user_id).get('trading_environment'):
                    return {'success': False, 'error': PortfolioService.BROKER_MANAGED}
                
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
                    if txn_type == 'buy':
                        from core import ledger
                        ledger.cover_negative_cash(cur, portfolio_id)  # the position was already updated
                    cur.execute("""
                        INSERT INTO transactions (
                            portfolio_id, portfolio_position_id, txn_type, symbol, 
                            quantity, price, total_amount, notes, realised_pnl
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (portfolio_id, position_id, txn_type, position['symbol'], 
                          txn_qty, new_avg_cost, txn_qty * new_avg_cost,
                          'Position adjustment (recorded at average cost)', 0 if txn_type == 'sell' else None))
                
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
                if PortfolioService._own(cur, portfolio_id, user_id).get('trading_environment') \
                        and float(position['quantity']) > 0:
                    return {'success': False, 'error': PortfolioService.BROKER_MANAGED}
                
                cur.execute("""
                    UPDATE portfolio_positions 
                    SET status = 'sold', quantity = 0, closed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (position_id,))
                
                qty = float(position['quantity'])
                price = float(position['avg_cost'])
                if qty > 0:
                    cur.execute("""
                        INSERT INTO transactions (
                            portfolio_id, portfolio_position_id, txn_type, symbol, 
                            quantity, price, total_amount, notes, realised_pnl
                        )
                        VALUES (%s, %s, 'sell', %s, %s, %s, %s, %s, 0)
                    """, (portfolio_id, position_id, position['symbol'], 
                          qty, price, qty * price, 'Position removed (recorded at average cost)'))
                
                conn.commit()
                return {'success': True, 'message': 'Position removed'}
            except Exception as e:
                return {'success': False, 'error': str(e)}

    @staticmethod
    def delete_portfolio(portfolio_id: int, user_id: int) -> dict:
        """Delete a portfolio and all its associated data."""
        with get_db_cursor() as (cur, conn):
            try:
                portfolio = PortfolioService._own(cur, portfolio_id, user_id)
                if portfolio is None:
                    return {'success': False, 'error': 'Portfolio not found'}
                if db.table_exists(cur, 'paper_orders'):
                    from core.tws.paper import WORKING
                    working = "','".join(WORKING)
                    cur.execute(f"""SELECT count(*) AS n FROM paper_orders
                                    WHERE portfolio_id = %s AND state IN ('{working}')""", (portfolio_id,))
                    if cur.fetchone()['n']:
                        return {'success': False, 'error': 'This portfolio has orders working at IBKR. Cancel them '
                                                           '(Orders page) and wait until TWS confirms, then delete it.'}
                cur.execute("""SELECT coalesce(sum(CAST(quantity AS REAL)), 0) AS q FROM portfolio_positions
                               WHERE portfolio_id = %s AND status = 'active'""", (portfolio_id,))
                held = float(cur.fetchone()['q'])
                if db.table_exists(cur, 'safety_intents'):  # retired simulation records keep no link
                    cur.execute("UPDATE safety_intents SET portfolio_id = NULL WHERE portfolio_id = %s", (portfolio_id,))
                
                cur.execute("DELETE FROM portfolios WHERE id = %s AND user_id = %s", 
                            (portfolio_id, user_id))
                conn.commit()
                message = 'Portfolio deleted'
                if portfolio.get('trading_environment') and held > 0:
                    message += ('. Its shares are still in your IBKR account; Sapient no longer manages them '
                                '(sell them in TWS if you want to).')
                return {'success': True, 'message': message}
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
                portfolio = PortfolioService._own(cur, portfolio_id, user_id)
                if portfolio is None:
                    return {'success': False, 'error': 'Portfolio not found'}
                if portfolio.get('trading_environment'):
                    return {'success': False, 'error': PortfolioService.BROKER_MANAGED}
                
                cur.execute("""
                    SELECT id FROM portfolio_positions 
                    WHERE portfolio_id = %s AND symbol = %s AND status = 'active'
                """, (portfolio_id, symbol))
                
                if cur.fetchone():
                    return {'success': False, 'error': f'{symbol} already exists in portfolio. Use edit to modify.'}
                from core import ledger
                ledger.add_money_if_needed(cur, portfolio_id, Decimal(str(quantity * avg_cost)))
                
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
        'stop_loss_pct': None,
        'take_profit_pct': None,
        'approval_timeout_minutes': 15,
        'scheduler_enabled': False,
        'check_after_open_minutes': 15,
        'check_before_close_minutes': 30,
    }
    # Changing these alters order admission policy, so it halts the safety account.
    POLICY_KEYS = {
        'mode', 'rsi_buy_threshold', 'rsi_sell_threshold', 'max_trade_pct',
        'max_daily_trades', 'max_daily_turnover_pct', 'sector_cap_pct',
        'paper_only', 'breaker_on_loss_pct', 'breaker_on_volatility_spike',
        'breaker_on_news_event',
    }
    # Scan schedule and exit rules only change what gets proposed.
    STRATEGY_KEYS = {
        'stop_loss_pct', 'take_profit_pct', 'approval_timeout_minutes',
        'scheduler_enabled', 'check_after_open_minutes', 'check_before_close_minutes',
    }
    COLUMNS = '''mode, rsi_buy_threshold, rsi_sell_threshold, max_trade_pct,
                 max_daily_trades, max_daily_turnover_pct, sector_cap_pct,
                 paper_only, breaker_on_loss_pct, breaker_on_volatility_spike,
                 breaker_on_news_event, last_kill_switch_at, stop_loss_pct,
                 take_profit_pct, approval_timeout_minutes, scheduler_enabled,
                 check_after_open_minutes, check_before_close_minutes'''

    @staticmethod
    def _row_to_dict(row) -> dict:
        if row is None:
            return None
        d = dict(row)
        for k in ('rsi_buy_threshold', 'rsi_sell_threshold', 'max_trade_pct',
                  'max_daily_turnover_pct', 'sector_cap_pct', 'breaker_on_loss_pct',
                  'stop_loss_pct', 'take_profit_pct'):
            if d.get(k) is not None:
                d[k] = float(d[k])
        return d

    @staticmethod
    def get(user_id: int) -> dict:
        with get_db_cursor() as (cur, conn):
            cols = AITradingSettingsService.COLUMNS
            cur.execute(f"SELECT {cols} FROM ai_trading_settings WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row is None:
                cur.execute(f"INSERT INTO ai_trading_settings (user_id) VALUES (%s) RETURNING {cols}",
                            (user_id,))
                row = cur.fetchone()
                conn.commit()
            return AITradingSettingsService._row_to_dict(row)

    @staticmethod
    def update(user_id: int, updates: dict) -> dict:
        AITradingSettingsService.get(user_id)  # ensure row exists
        allowed = AITradingSettingsService.POLICY_KEYS | AITradingSettingsService.STRATEGY_KEYS
        nullable = {'stop_loss_pct', 'take_profit_pct'}  # None/0 = rule off
        sets = []
        params = []
        changed = set()
        for k, v in updates.items():
            if k in nullable:
                sets.append(f"{k} = %s")
                params.append(v if v else None)
                changed.add(k)
            elif k in allowed and v is not None:
                sets.append(f"{k} = %s")
                params.append(v)
                changed.add(k)
        if not sets:
            return AITradingSettingsService.get(user_id)
        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.append(user_id)
        with get_db_cursor() as (cur, conn):
            # Same write transaction as admission (BEGIN IMMEDIATE). Policy changes
            # never leave old queued authority or reservations usable.
            if changed & AITradingSettingsService.POLICY_KEYS and db.table_exists(cur, "safety_accounts"):
                cur.execute("SELECT user_id FROM safety_accounts WHERE user_id=%s", (user_id,))
                if cur.fetchone():
                    from core.execution_safety import IntentService
                    IntentService()._invalidate(cur, user_id)
                    cur.execute("""UPDATE safety_accounts SET halted=TRUE,recovery_required=TRUE,
                        policy_revision=policy_revision+1 WHERE user_id=%s""", (user_id,))
            cur.execute(f"""
                UPDATE ai_trading_settings SET {', '.join(sets)}
                WHERE user_id = %s
            """, params)
            conn.commit()
        return AITradingSettingsService.get(user_id)

    @staticmethod
    def kill_switch(user_id: int) -> dict:
        """Persist a halt; never fabricate broker cancellation evidence."""
        from core.execution_safety import IntentService
        return IntentService().halt(user_id)


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
                WHERE id = %s AND user_id = %s AND status IN ('pending','snoozed')
                RETURNING id
            """, params)
            row = cur.fetchone()
            conn.commit()
            if row is None:
                return None
        return AISignalService.get(user_id, signal_id)

    @staticmethod
    def expire_stale(now=None) -> list:
        """Unanswered proposals past their deadline expire; they are never acted on."""
        now = now or datetime.now(timezone.utc)
        with get_db_cursor() as (cur, conn):
            cur.execute("""
                UPDATE ai_signals SET status = 'expired', decided_by = 'system', decided_at = %s
                WHERE status IN ('pending', 'snoozed') AND expires_at IS NOT NULL AND expires_at <= %s
                RETURNING id, user_id, portfolio_id, symbol, action
            """, (now, now))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
        return rows


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
