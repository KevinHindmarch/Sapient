import axios from 'axios'
import type { OptimizationResult } from '../types'
import { toast } from 'sonner'
import { apiBase, apiToken } from './runtime'

const api = axios.create({
  baseURL: apiBase,
  timeout: 300_000,  // a full market scan can take a few minutes; nothing should wait forever
  headers: {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${apiToken}`,
  },
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 || error.response?.status === 403) {
      // The per-launch key didn't match: the engine was restarted separately.
      toast.error('Lost connection to the Sapient engine. Please restart Sapient.', { id: 'engine-auth' })
    }
    return Promise.reject(error)
  }
)

export function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') {
    return detail.message
  }
  if (Array.isArray(detail) && detail.length) {  // FastAPI input check: say which field and why
    const first = detail[0] as { loc?: unknown[]; msg?: string }
    const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : ''
    if (first.msg) return `${fallback}: ${field ? `${field} – ` : ''}${first.msg}`
  }
  return fallback
}

export interface Profile {
  display_name: string
  theme: 'light' | 'dark' | null
  onboarded: boolean
  data_dir: string
}

export const profileApi = {
  get: () => api.get<Profile>('/profile'),
  update: (changes: { display_name?: string; theme?: 'light' | 'dark'; complete_onboarding?: boolean }) =>
    api.put<Profile>('/profile', changes),
}

export const stocksApi = {
  search: (q: string, market: string = 'ASX') => api.get(`/stocks/search?q=${encodeURIComponent(q)}&market=${market}`),
  info: (symbol: string) => api.get(`/stocks/info/${symbol}`),
  quickInfo: (symbol: string) => api.get(`/stocks/info/${symbol}`),
  historical: (symbols: string[], period: string = '2y') =>
    api.post('/stocks/historical', { symbols, period }),
  dividends: (symbols: string[]) =>
    api.get(`/stocks/dividends?symbols=${symbols.join(',')}`),
  asx200: () => api.get('/stocks/asx200'),
  validate: (symbol: string) => api.get(`/stocks/validate/${symbol}`),
  rankByPerformance: () => api.get('/stocks/rank'),
}

export const portfolioApi = {
  optimize: (symbols: string[], investment_amount: number, risk_tolerance: string, period: string = '2y', market: string = 'ASX') =>
    api.post('/portfolio/optimize', { symbols, investment_amount, risk_tolerance, period, market }),
  backtest: (symbols: string[], weights: Record<string, number>, initial_investment: number, period: string = '2y') =>
    api.post('/portfolio/backtest', { symbols, weights, initial_investment, period }),
  compareStrategies: (symbols: string[], investment_amount: number, period: string = '2y') =>
    api.post('/portfolio/compare-strategies', { symbols, investment_amount, period }),
  save: (name: string, optimization_results: object, investment_amount: number, mode: string, risk_tolerance: string, market: string = 'ASX') =>
    api.post<{ success: boolean; portfolio_id?: number; warning?: string }>('/portfolio/save', { name, optimization_results, investment_amount, mode, risk_tolerance, market }),
  list: () => api.get('/portfolio/list'),
  detail: (id: number) => api.get(`/portfolio/${id}`),
  trade: (portfolioId: number, symbol: string, txn_type: string, quantity: number, price: number, notes?: string) =>
    api.post(`/portfolio/${portfolioId}/trade`, { symbol, txn_type, quantity, price, notes }),
  updatePosition: (portfolioId: number, positionId: number, quantity: number, avg_cost?: number) =>
    api.put(`/portfolio/${portfolioId}/positions/${positionId}`, { quantity, avg_cost }),
  removePosition: (portfolioId: number, positionId: number) =>
    api.delete(`/portfolio/${portfolioId}/positions/${positionId}`),
  addStock: (portfolioId: number, symbol: string, quantity: number, avg_cost: number) =>
    api.post(`/portfolio/${portfolioId}/stocks`, { symbol, quantity, avg_cost }),
  deletePortfolio: (portfolioId: number) =>
    api.delete(`/portfolio/${portfolioId}`),
  scanFundamentals: (top_n: number = 20, market: string = 'ASX') =>
    api.get(`/portfolio/fundamentals/scan?top_n=${top_n}&market=${market}`),
  optimizeFundamentals: (symbols: string[], investment_amount: number, risk_tolerance: string, period: string = '1y', market: string = 'ASX') =>
    api.post('/portfolio/fundamentals/optimize', { symbols, investment_amount, risk_tolerance, period, market }),
  sp500: () => api.get('/stocks/sp500'),
  analyzeCAPM: (symbols: string[], period: string = '2y') =>
    api.get(`/portfolio/capm/analyze?symbols=${symbols.join(',')}&period=${period}`),
  optimizeCAPM: (symbols: string[], investment_amount: number, risk_tolerance: string, period: string = '2y') =>
    api.post('/portfolio/capm/optimize', { symbols, investment_amount, risk_tolerance, period }),
  scanCAPM: (top_n: number = 30) =>
    api.get(`/portfolio/capm/scan?top_n=${top_n}`),
  getRebalancePlan: (portfolioId: number) =>
    api.get(`/portfolio/${portfolioId}/rebalance-plan`),
  executeRebalance: (portfolioId: number, legs: RebalanceLeg[], idempotency_key: string) =>
    api.post<RebalanceResult>(`/portfolio/${portfolioId}/execute-rebalance`, { legs, idempotency_key }),
  summary: (portfolioId: number) => api.get<PortfolioSummary>(`/portfolio/${portfolioId}/summary`),
  summaries: () => api.get<PortfolioSummary[]>('/portfolio/summaries'),
}

export interface HoldingSummary {
  position_id: number | null
  symbol: string
  quantity: number
  planned_quantity: number | null
  avg_cost: number
  price: number | null
  price_missing: boolean
  cost: number
  value: number
  unrealised_pnl: number | null
  target_weight: number | null
  weight: number
}

/** Money for one portfolio, worked out by the engine (core/ledger.py). */
export interface PortfolioSummary {
  portfolio_id: number
  name: string
  market: string
  currency: 'AUD' | 'USD'
  trading_environment: TradingEnv | null
  money_put_in: number
  market_value: number
  cash: number
  total_value: number
  cost_of_holdings: number
  unrealised_pnl: number
  realised_pnl: number
  fees: number
  total_return: number
  total_return_pct: number
  prices_missing: string[]
  holdings: HoldingSummary[]
}

export const money = (value: number, currency: 'AUD' | 'USD' = 'AUD', digits = 2) =>
  `${currency === 'USD' ? 'US$' : 'A$'}${value.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`

export interface RebalanceLeg {
  symbol: string
  side: 'BUY' | 'SELL'
  quantity: number
  price: number
  estimated_value: number
  current_weight: number
  target_weight: number
  drift_pct: number
}

export interface RebalancePlan {
  portfolio_id: number
  portfolio_value: number
  cash: number
  total_drift_value: number
  legs: RebalanceLeg[]
  notes: string
  environment: TradingEnv | null
  can_execute: boolean
}

export interface RebalanceResult {
  environment: TradingEnv
  queued: number
  message: string
  results: { symbol: string; side: string; ok: boolean; order_id?: string; code?: string; message?: string }[]
}

export const indicatorsApi = {
  analyze: (symbol: string, period: string = '1y', market: string = 'asx') =>
    api.get(`/indicators/analyze/${symbol}?period=${period}&market=${market}`),
  chartData: (symbol: string, indicator: string = 'all', period: string = '1y', market: string = 'asx') =>
    api.get(`/indicators/chart-data/${symbol}?indicator=${indicator}&period=${period}&market=${market}`),
  rsiScreener: (market: string = 'asx', signal: string = 'buy') =>
    api.get(`/indicators/rsi-screener?market=${market}&signal=${signal}`),
}

export interface BrokerStatus {
  mode: 'none' | 'tws_paper' | 'tws_live'
  tws_configured: boolean
  worker: string
  paper_trading_enabled: boolean
  live_trading_enabled: boolean
  message: string
}

export const brokerApi = {
  getStatus: () => api.get<BrokerStatus>('/broker/status'),
}

export interface TwsSettings {
  enabled: boolean
  port: number
  client_id: number
  expected_account: string | null
  paper_confirmed?: boolean      // paper profile column
  live_confirmed?: boolean       // live profile column
  account_confirmed: boolean     // either: the user confirmed which kind of account this login is
  sdk_folder: string | null
  profile?: TradingEnv
}

export type TradingEnv = 'paper' | 'live'

export interface TwsStatus {
  state: string
  detail: string | null
  account: string | null
  server_version: number | null
  sdk_version: string | null
  ib_connected: boolean | null
  connected_since: string | null
  last_sync_at: string | null
  worker_running: boolean
}

export interface TwsTestStep {
  key: string
  title: string
  status: 'ok' | 'warn' | 'fail' | 'skipped'
  detail: string | null
  fix: string | null
}

export interface TwsCommand {
  id: number
  status: 'pending' | 'running' | 'done' | 'failed'
  result: { ok?: boolean; steps?: TwsTestStep[]; message?: string; facts?: Record<string, unknown> } | null
}

export interface TwsAccount {
  state: string
  account: string | null
  snapshots: Record<string, { data: unknown; taken_at: string }>
}

// One TWS login: '/tws' is the paper login, '/tws-live' the live (real-money) login.
const makeTwsApi = (base: string) => ({
  settings: () => api.get<TwsSettings>(`${base}/settings`),
  saveSettings: (changes: Partial<TwsSettings>) => api.put<TwsSettings>(`${base}/settings`, changes),
  sdk: () => api.get<{ found: boolean; folder: string | null; version: string | null }>(`${base}/sdk`),
  status: () => api.get<TwsStatus>(`${base}/status`),
  startTest: () => api.post<{ id: number }>(`${base}/test`),
  testResult: (id: number) => api.get<TwsCommand>(`${base}/test/${id}`),
  reconnect: () => api.post(`${base}/reconnect`),
  account: () => api.get<TwsAccount>(`${base}/account`),
  compare: (portfolioId: number) => api.get<BrokerCompare>(`/tws/compare/${portfolioId}`),
})
export const twsApi = makeTwsApi('/tws')
export const twsLiveApi = makeTwsApi('/tws-live')
export const twsApiFor = (env: TradingEnv) => (env === 'live' ? twsLiveApi : twsApi)

/** RSI-dip entry: buy each stock only when its RSI is below `rsi_below`; skip it after `deadline_days`. */
export interface EntryChoice { entry: 'now' | 'rsi_dip'; rsi_below?: number; deadline_days?: number }

export interface BrokerCompare {
  state: string
  account: string | null
  positions_taken_at: string | null
  available: boolean
  paper_started_at: string | null
  live_started_at: string | null
  trading_environment: TradingEnv | null
  ai_mode: 'off' | 'suggestions' | 'autonomous'
  entry_mode: 'now' | 'rsi_dip' | null
  entry_rsi_below: number | null
  entry_deadline: string | null
  waiting: string[]
  skipped: string[]
  rows: { symbol: string; model_quantity: number | null; broker_quantity: number | null; difference: number;
    status: 'match' | 'differs' | 'model_only' | 'broker_only' }[]
}

export interface AISettingsUpdate {
  mode?: 'off' | 'suggestions' | 'autonomous'
  rsi_buy_threshold?: number
  rsi_sell_threshold?: number
  max_trade_pct?: number
  max_daily_trades?: number
  max_daily_turnover_pct?: number
  sector_cap_pct?: number
  paper_only?: boolean
  breaker_on_loss_pct?: number
  breaker_on_volatility_spike?: boolean
  breaker_on_news_event?: boolean
  stop_loss_pct?: number
  take_profit_pct?: number
  approval_timeout_minutes?: number
  scheduler_enabled?: boolean
  check_after_open_minutes?: number
  check_before_close_minutes?: number
}

export interface SchedulerStatus {
  running: boolean
  detail: string | null
  heartbeat_at: string | null
  next_check_at: string | null
  markets: { code: string; name: string; open_now: boolean; next_open: string | null; calendar_up_to_date: boolean;
    today: { open: string; close: string } | null }[]
  recent_runs: { portfolio_id: number; portfolio_name: string; window_key: string; outcome: string;
    result: { new_signals?: number; error?: string } | null; started_at: string; finished_at: string | null }[]
}

export const aiApi = {
  getSettings: () => api.get('/ai/settings'),
  updateSettings: (payload: AISettingsUpdate) => api.put('/ai/settings', payload),
  killSwitch: () => api.post('/ai/kill-switch'),
  scheduler: () => api.get<SchedulerStatus>('/ai/scheduler'),
  listSignals: (status: string = 'pending') =>
    api.get(`/ai/signals?status=${status}`),
  approveSignal: (id: number) => api.post<{ paper_order?: PaperOrder; environment?: 'tws_paper' | 'tws_live';
    execution_enabled: boolean; message: string }>(`/ai/signals/${id}/approve`),
  rejectSignal: (id: number) => api.post(`/ai/signals/${id}/reject`),
  snoozeSignal: (id: number, snooze_minutes: number = 60) =>
    api.post(`/ai/signals/${id}/snooze`, { snooze_minutes }),
  scan: (portfolioId: number) => api.post(`/ai/scan/${portfolioId}`),
  audit: () => api.get('/ai/audit'),
  setPortfolioMode: (portfolioId: number, mode: 'off' | 'suggestions' | 'autonomous') =>
    api.put(`/portfolio/${portfolioId}/ai-mode`, { ai_mode: mode }),
}

export default api

// ---- Paper trading through TWS ------------------------------------------------
export interface PaperBinding {
  account_id: string | null
  enabled: boolean
  authorised_at: string | null
  halted: boolean
  halted_at: string | null
  max_order_value: number
  max_orders_per_day: number
  max_value_per_day: number
  max_price_gap_pct: number
  autonomous_allowed: boolean
}

export interface PaperStatus {
  environment: TradingEnv
  realtime_required: boolean
  binding: PaperBinding
  ready: boolean
  blockers: { code: string; message: string }[]
  authorisation_text: string
}

export type PaperOrderState = 'QUEUED' | 'SUBMITTING' | 'SUBMITTED' | 'PARTIALLY_FILLED' | 'FILLED'
  | 'CANCEL_REQUESTED' | 'CANCELLED' | 'REJECTED' | 'EXPIRED' | 'BLOCKED' | 'UNKNOWN'

export interface PaperFill {
  exec_id: string
  shares: string
  price: string
  exec_time: string
  commission: string | null
  commission_currency: string | null
}

export interface PaperOrder {
  id: string
  environment: TradingEnv
  origin: 'manual' | 'ai_approval' | 'ai_autonomous' | 'entry'
  account_id: string
  portfolio_id: number | null
  portfolio_name?: string | null
  symbol: string
  currency?: string | null   // AUD (ASX) or USD (US)
  side: 'BUY' | 'SELL'
  quantity: string
  reference_price: string
  limit_price: string | null
  quote: { delayed?: boolean; market_data_type?: number } | null
  state: PaperOrderState
  detail: string | null
  api_order_id: number | null
  filled_quantity: string
  avg_fill_price: string | null
  broker_status: string | null
  created_at: string
  submitted_at: string | null
  updated_at: string
  fills: PaperFill[]
}

export type PaperLimits = Partial<Pick<PaperBinding, 'max_order_value' | 'max_orders_per_day' | 'max_value_per_day'
  | 'max_price_gap_pct' | 'autonomous_allowed'>>

export const UNKNOWN_CHECK_TEXT = 'I checked TWS: this order is not there and did not fill.'

// Orders in one environment: '/paper' (practice) or '/live' (REAL MONEY).
const makeTradingApi = (base: string) => ({
  status: () => api.get<PaperStatus>(`${base}/status`),
  authorise: (account_id: string, confirmation: string, limits: PaperLimits) =>
    api.post<PaperBinding>(`${base}/authorise`, { account_id, confirmation, limits }),
  updateLimits: (limits: PaperLimits) => api.put<PaperBinding>(`${base}/limits`, limits),
  disable: () => api.post<PaperBinding>(`${base}/disable`),
  orders: () => api.get<PaperOrder[]>(`${base}/orders`),
  place: (ticket: { symbol: string; side: 'BUY' | 'SELL'; quantity: number; portfolio_id?: number; idempotency_key: string }) =>
    api.post<PaperOrder>(`${base}/orders`, ticket),
  cancel: (id: string) => api.post<PaperOrder>(`${base}/orders/${id}/cancel`),
  resolveUnknown: (id: string) => api.post<PaperOrder>(`${base}/orders/${id}/resolve`, { confirmation: UNKNOWN_CHECK_TEXT }),
  startPortfolio: (id: number, mode?: 'suggestions' | 'autonomous', entry?: EntryChoice) => api.post<{ started: boolean;
    entry?: 'rsi_dip'; deadline?: string
    results: { symbol: string; ok: boolean; waiting?: boolean; quantity?: number; message?: string }[] }>(
    `${base}/portfolios/${id}/start`, { ...(mode ? { mode } : {}), ...(entry ?? {}) }),
  autonomy: () => api.get<AutonomyChecklist>(`${base}/autonomy`),
})
export const paperApi = makeTradingApi('/paper')
export const liveApi = makeTradingApi('/live')
export const tradingApiFor = (env: TradingEnv) => (env === 'live' ? liveApi : paperApi)

export interface ChecklistItem { key: string; ok: boolean; text: string }
export interface AutonomyChecklist {
  shared: ChecklistItem[]
  portfolios: { portfolio_id: number; name: string; environment: TradingEnv; items: ChecklistItem[]; autonomous: boolean }[]
}

/** Fewest stocks each risk profile needs (matches core/optimizer.py RISK_PARAMS). */
export const MIN_STOCKS: Record<string, number> = { conservative: 4, moderate: 3, aggressive: 2 }

/** Hand-edited weights scaled to add up to exactly 100% (what gets saved). */
export function normaliseWeights(weights: Record<string, number>): Record<string, number> {
  const total = Object.values(weights).reduce((sum, w) => sum + (w > 0 ? w : 0), 0)
  if (total <= 0) return weights
  return Object.fromEntries(Object.entries(weights).filter(([, w]) => w > 0).map(([s, w]) => [s, w / total]))
}

export interface BackupFile { name: string; kind: string; size: number; modified_at: string }
export interface BackupsInfo {
  backups: BackupFile[]
  status: { last_backup_at?: string; last_check_ok?: boolean; last_check_detail?: string }
  pending_restore: { backup: string } | null
  folder: string
}

export const backupsApi = {
  list: () => api.get<BackupsInfo>('/backups'),
  now: () => api.post('/backups/now'),
  restore: (name: string) => api.post('/backups/restore', { name }),
  cancelRestore: () => api.delete('/backups/restore'),
}

// ---- Model B (Fama-French five factors + momentum): Factor Builder and monthly management ----
export type FactorKey = 'MOM' | 'QUAL' | 'VAL' | 'GROW' | 'SIZE'
export interface FactorRow {
  rank: number; symbol: string; name: string | null; sector: string | null; price: number | null
  score: number; z: Partial<Record<FactorKey, number>>
}
export interface FactorBuild {
  market: 'ASX' | 'US'; model: 'B'; weights: Partial<Record<FactorKey, number>>; labels: Record<FactorKey, string>
  ranking: FactorRow[]; optimization: OptimizationResult
  ranked: number; undervalued: number; undervalued_only: boolean
}
export interface FactorPlan {
  month: string; model: 'B'; target: Record<string, number>; weights?: Record<string, number>
  ranks?: Record<string, number>; reasons?: Record<string, string>; adopted?: boolean; value?: number
}
export const factorsApi = {
  build: (market: 'ASX' | 'US', investment_amount: number, risk_tolerance: string, top_n = 20, undervalued_only = true) =>
    api.post<FactorBuild>('/factors/build', { market, investment_amount, risk_tolerance, top_n, undervalued_only }),
  plan: (portfolioId: number) =>
    api.get<{ strategy: 'rules' | 'factor'; plan: FactorPlan | null; hold: number; keep_within: number }>(`/factors/portfolio/${portfolioId}`),
  setStrategy: (portfolioId: number, strategy: 'rules' | 'factor') =>
    api.put<{ strategy: 'rules' | 'factor' }>(`/factors/portfolio/${portfolioId}/strategy`, { strategy }),
}
