export interface User {
  id: number
  email: string
  display_name: string | null
  created_at: string
}

export interface StockInfo {
  symbol: string
  name: string
  sector: string
  industry: string
  current_price: number
  market_cap: number
}

export interface OptimizationResult {
  weights: Record<string, number>
  expected_return: number
  volatility: number
  sharpe_ratio: number
  var_95: number
  max_drawdown: number
  beta: number
  portfolio_dividend_yield: number
  risk_tolerance: string
  optimization_success: boolean
  correlation_matrix?: number[][]
  correlation_symbols?: string[]
}

export interface BacktestResult {
  total_return: number
  annual_return: number
  annual_volatility: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  best_day: number
  worst_day: number
  portfolio_values: number[]
  dates: string[]
}

export interface Portfolio {
  id: number
  name: string
  mode: string
  initial_investment: number
  expected_return: number | null
  expected_volatility: number | null
  expected_sharpe: number | null
  expected_dividend_yield: number | null
  risk_tolerance: string
  created_at: string
  status: string
  position_count?: number
}

export interface Position {
  id: number
  symbol: string
  quantity: number
  avg_cost: number
  weight_at_creation: number | null
  allocation_amount: number | null
  status: string
}

export interface Transaction {
  id: number
  txn_type: string
  symbol: string
  quantity: number
  price: number
  total_amount: number
  txn_time: string
  notes: string | null
}

export interface TechnicalAnalysis {
  symbol: string
  current_price: number
  trend: string
  indicators: {
    rsi: {
      value: number
      signal: IndicatorSignal
    }
    macd: {
      macd_line: number
      signal_line: number
      histogram: number
      signal: IndicatorSignal
    }
    moving_averages: {
      sma_20: number
      sma_50: number
      price_vs_sma20: string
      price_vs_sma50: string
    }
    bollinger: {
      upper: number
      middle: number
      lower: number
      position: string
    }
  }
  overall_signal: string
  active_signals: [string, string, string][]
  analysis_date: string
}

export interface IndicatorSignal {
  signal: string
  strength: string
  value: number
  explanation: string
}
