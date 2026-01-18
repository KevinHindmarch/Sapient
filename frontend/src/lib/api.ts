import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }),
  register: (email: string, password: string, display_name?: string) =>
    api.post('/auth/register', { email, password, display_name }),
  me: () => api.get('/auth/me'),
}

export const stocksApi = {
  search: (q: string) => api.get(`/stocks/search?q=${q}`),
  info: (symbol: string) => api.get(`/stocks/info/${symbol}`),
  historical: (symbols: string[], period: string = '2y') =>
    api.post('/stocks/historical', { symbols, period }),
  dividends: (symbols: string[]) =>
    api.get(`/stocks/dividends?symbols=${symbols.join(',')}`),
  asx200: () => api.get('/stocks/asx200'),
  validate: (symbol: string) => api.get(`/stocks/validate/${symbol}`),
  rankByPerformance: () => api.get('/stocks/rank'),
}

export const portfolioApi = {
  optimize: (symbols: string[], investment_amount: number, risk_tolerance: string, period: string = '2y') =>
    api.post('/portfolio/optimize', { symbols, investment_amount, risk_tolerance, period }),
  backtest: (symbols: string[], weights: Record<string, number>, initial_investment: number, period: string = '2y') =>
    api.post('/portfolio/backtest', { symbols, weights, initial_investment, period }),
  compareStrategies: (symbols: string[], investment_amount: number, period: string = '2y') =>
    api.post('/portfolio/compare-strategies', { symbols, investment_amount, period }),
  save: (name: string, optimization_results: Record<string, unknown>, investment_amount: number, mode: string, risk_tolerance: string) =>
    api.post('/portfolio/save', { name, optimization_results, investment_amount, mode, risk_tolerance }),
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
  scanFundamentals: (top_n: number = 20) =>
    api.get(`/portfolio/fundamentals/scan?top_n=${top_n}`),
  optimizeFundamentals: (symbols: string[], investment_amount: number, risk_tolerance: string, period: string = '1y') =>
    api.post('/portfolio/fundamentals/optimize', { symbols, investment_amount, risk_tolerance, period }),
  analyzeCAPM: (symbols: string[], period: string = '2y') =>
    api.get(`/portfolio/capm/analyze?symbols=${symbols.join(',')}&period=${period}`),
  optimizeCAPM: (symbols: string[], investment_amount: number, risk_tolerance: string, period: string = '2y') =>
    api.post('/portfolio/capm/optimize', { symbols, investment_amount, risk_tolerance, period }),
  scanCAPM: (top_n: number = 30) =>
    api.get(`/portfolio/capm/scan?top_n=${top_n}`),
}

export const indicatorsApi = {
  analyze: (symbol: string, period: string = '1y') =>
    api.get(`/indicators/analyze/${symbol}?period=${period}`),
  chartData: (symbol: string, indicator: string = 'all', period: string = '1y') =>
    api.get(`/indicators/chart-data/${symbol}?indicator=${indicator}&period=${period}`),
}

export default api
