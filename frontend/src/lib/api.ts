import axios from 'axios'
import { toast } from 'sonner'
import { apiBase, apiToken } from './runtime'

const api = axios.create({
  baseURL: apiBase,
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
    api.post<{ success: boolean; portfolio_id?: number }>('/portfolio/save', { name, optimization_results, investment_amount, mode, risk_tolerance, market }),
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
  executeRebalance: (portfolioId: number, request: IntentBatchRequest) =>
    api.post<IntentQueueResponse>(`/portfolio/${portfolioId}/execute-rebalance`, request),
}

export const indicatorsApi = {
  analyze: (symbol: string, period: string = '1y', market: string = 'asx') =>
    api.get(`/indicators/analyze/${symbol}?period=${period}&market=${market}`),
  chartData: (symbol: string, indicator: string = 'all', period: string = '1y', market: string = 'asx') =>
    api.get(`/indicators/chart-data/${symbol}?indicator=${indicator}&period=${period}&market=${market}`),
  rsiScreener: (market: string = 'asx', signal: string = 'buy') =>
    api.get(`/indicators/rsi-screener?market=${market}&signal=${signal}`),
}

export interface BrokerOrderPayload {
  symbol: string
  side: 'BUY' | 'SELL'
  quantity: number
  order_type: 'LMT'
  limit_price: number
  idempotency_key: string
  expires_at: string
  portfolio_id?: number | null
  signal_id?: number | null
}

export interface IntentBatchRequest {
  orders: BrokerOrderPayload[]
  idempotency_key: string
  environment: 'simulation'
}

export interface QueuedIntent {
  id: string
  state: string
  symbol: string
  side: 'BUY' | 'SELL'
  quantity: string | number
  limit_price: string | number
}

export interface IntentQueueResponse {
  intents: QueuedIntent[]
  execution_enabled: false
  message: string
  failed?: { symbol: string; error: string }[]
}

export interface BrokerStatus {
  mode: 'simulation' | 'tws_paper' | 'tws_live'
  tws_configured: boolean
  worker: string
  execution_enabled: boolean
  message: string
}

export const brokerApi = {
  getStatus: () => api.get<BrokerStatus>('/broker/status'),
  placeOrders: (orders: BrokerOrderPayload[], idempotency_key: string) =>
    api.post<IntentQueueResponse>('/broker/orders', { orders, idempotency_key, environment: 'simulation' }),
  recentOrders: (limit: number = 25) =>
    api.get(`/broker/orders/recent?limit=${limit}`),
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

export interface BrokerCompare {
  state: string
  account: string | null
  positions_taken_at: string | null
  available: boolean
  paper_started_at: string | null
  live_started_at: string | null
  trading_environment: TradingEnv | null
  ai_mode: 'off' | 'suggestions' | 'autonomous'
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
  approveSignal: (id: number) => api.post<{ intent?: QueuedIntent; paper_order?: PaperOrder; environment?: 'tws_paper' | 'tws_live';
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
  startPortfolio: (id: number, mode?: 'suggestions' | 'autonomous') => api.post<{ started: boolean;
    results: { symbol: string; ok: boolean; quantity?: number; message?: string }[] }>(`${base}/portfolios/${id}/start`,
    mode ? { mode } : {}),
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
