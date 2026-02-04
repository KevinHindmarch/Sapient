import { useState } from 'react'
import { portfolioApi } from '../lib/api'
import { toast } from 'sonner'
import { Search, TrendingUp, Save, Loader2, Star, BarChart3, Target, Zap, Globe } from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'
import { useTheme } from '../lib/theme'

const COLORS = ['#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']

type Market = 'ASX' | 'US'

interface StockFundamentals {
  symbol: string
  name: string
  sector: string
  current_price: number
  market_cap: number
  earnings_yield: number | null
  roe: number | null
  earnings_growth: number | null
  dividend_yield: number | null
  value_score: number
  quality_score: number
  growth_score: number
  composite_score: number
  expected_return: number
}

interface OptimizationResult {
  weights: Record<string, number>
  expected_return: number
  volatility: number
  sharpe_ratio: number
  var_95: number
  max_drawdown: number
  portfolio_dividend_yield: number
  stock_fundamentals: {
    symbol: string
    name: string
    weight: number
    expected_return: number
    value_score: number
    quality_score: number
    composite_score: number
  }[]
}

export default function FundamentalsBuilder() {
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  
  const [market, setMarket] = useState<Market>('ASX')
  const [scanning, setScanning] = useState(false)
  const [stocks, setStocks] = useState<StockFundamentals[]>([])
  const [selectedStocks, setSelectedStocks] = useState<string[]>([])
  const [optimizing, setOptimizing] = useState(false)
  const [result, setResult] = useState<OptimizationResult | null>(null)
  const [saving, setSaving] = useState(false)
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [portfolioName, setPortfolioName] = useState('')
  const [investmentAmount, setInvestmentAmount] = useState(50000)
  const [riskTolerance, setRiskTolerance] = useState<'conservative' | 'moderate' | 'aggressive'>('moderate')

  const currency = market === 'US' ? 'USD' : 'AUD'
  const currencySymbol = market === 'US' ? '$' : 'A$'

  const handleMarketChange = (newMarket: Market) => {
    setMarket(newMarket)
    setStocks([])
    setSelectedStocks([])
    setResult(null)
  }

  const scanStocks = async () => {
    setScanning(true)
    setStocks([])
    setSelectedStocks([])
    setResult(null)
    
    try {
      const response = await portfolioApi.scanFundamentals(30, market)
      setStocks(response.data.stocks)
      setSelectedStocks(response.data.stocks.slice(0, 15).map((s: StockFundamentals) => s.symbol))
      toast.success(`Scanned ${response.data.total_scanned} ${market === 'US' ? 'S&P 500' : 'ASX200'} stocks, found ${response.data.returned} opportunities`)
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Failed to scan stocks')
    } finally {
      setScanning(false)
    }
  }

  const toggleStock = (symbol: string) => {
    if (selectedStocks.includes(symbol)) {
      setSelectedStocks(selectedStocks.filter(s => s !== symbol))
    } else {
      setSelectedStocks([...selectedStocks, symbol])
    }
    setResult(null)
  }

  const optimizePortfolio = async () => {
    if (selectedStocks.length < 2) {
      toast.error('Select at least 2 stocks')
      return
    }

    setOptimizing(true)
    try {
      const response = await portfolioApi.optimizeFundamentals(
        selectedStocks,
        investmentAmount,
        riskTolerance,
        '1y',
        market
      )
      setResult(response.data)
      toast.success(`Portfolio optimized using ${market === 'US' ? 'S&P 500' : 'ASX'} fundamentals!`)
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Optimization failed')
    } finally {
      setOptimizing(false)
    }
  }

  const savePortfolio = async () => {
    if (!result || !portfolioName.trim()) return

    setSaving(true)
    try {
      await portfolioApi.save(portfolioName.trim(), result, investmentAmount, 'fundamentals', riskTolerance, market)
      toast.success('Portfolio saved successfully!')
      setShowSaveModal(false)
      setPortfolioName('')
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Failed to save portfolio')
    } finally {
      setSaving(false)
    }
  }

  const formatPercent = (val: number | null | undefined) => {
    if (val === null || val === undefined) return 'N/A'
    return `${(val * 100).toFixed(1)}%`
  }

  const formatMarketCap = (val: number) => {
    if (val >= 1e12) return `$${(val / 1e12).toFixed(1)}T`
    if (val >= 1e9) return `$${(val / 1e9).toFixed(1)}B`
    if (val >= 1e6) return `$${(val / 1e6).toFixed(0)}M`
    return `$${val.toLocaleString()}`
  }

  const getScoreColor = (score: number) => {
    if (score >= 70) return 'text-emerald-400'
    if (score >= 50) return 'text-sky-400'
    if (score >= 30) return 'text-amber-400'
    return 'text-red-400'
  }

  const chartData = result ? Object.entries(result.weights).map(([symbol, weight]) => ({
    name: symbol.replace('.AX', ''),
    value: (weight as number) * 100,
  })) : []

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className={`text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Fundamentals Builder</h1>
        <p className={`mt-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
          Build portfolios using fundamental analysis - earnings yield, quality, and growth metrics
        </p>
      </div>

      <div className={`card p-6 ${isDark ? 'bg-gradient-to-r from-indigo-500/20 to-purple-500/20 border-indigo-500/30' : 'bg-gradient-to-r from-indigo-50 to-purple-50 border-indigo-200'}`}>
        <div className="flex items-start gap-4">
          <div className={`p-3 rounded-xl ${isDark ? 'bg-indigo-500/30' : 'bg-indigo-100'}`}>
            <Target className="w-8 h-8 text-indigo-400" />
          </div>
          <div>
            <h3 className={`font-semibold text-lg ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>How it works</h3>
            <p className={`mt-1 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
              Uses <strong>Fama-French multi-factor model</strong> backed by Nobel Prize-winning research:
            </p>
            <ul className={`mt-2 space-y-1 text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
              <li><strong>Value</strong> = Earnings Yield, Price-to-Book (high = undervalued)</li>
              <li><strong>Quality</strong> = ROE, Profit Margins, Low Debt (profitability factor)</li>
              <li><strong>Size</strong> = Small-cap premium (smaller companies outperform)</li>
              <li><strong>Momentum</strong> = 12-month price trend (strongest 2024 factor)</li>
              <li><strong>Growth</strong> = Sustainable Growth Rate (ROE × Retention + Historical CAGR)</li>
            </ul>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-4 items-end">
        <div>
          <label className="label flex items-center gap-2">
            <Globe className="w-4 h-4" />
            Market
          </label>
          <div className="flex rounded-lg overflow-hidden border border-slate-300 dark:border-slate-600">
            <button
              onClick={() => handleMarketChange('ASX')}
              className={`px-4 py-2 text-sm font-medium transition-all ${
                market === 'ASX'
                  ? 'bg-sky-500 text-white'
                  : isDark ? 'bg-slate-700 text-slate-300 hover:bg-slate-600' : 'bg-white text-slate-700 hover:bg-slate-100'
              }`}
            >
              🇦🇺 ASX
            </button>
            <button
              onClick={() => handleMarketChange('US')}
              className={`px-4 py-2 text-sm font-medium transition-all ${
                market === 'US'
                  ? 'bg-sky-500 text-white'
                  : isDark ? 'bg-slate-700 text-slate-300 hover:bg-slate-600' : 'bg-white text-slate-700 hover:bg-slate-100'
              }`}
            >
              🇺🇸 S&P 500
            </button>
          </div>
        </div>
        <div>
          <label className="label">Investment Amount ({currency})</label>
          <input
            type="number"
            value={investmentAmount}
            onChange={(e) => setInvestmentAmount(Number(e.target.value))}
            className="input w-40"
            min={1000}
          />
        </div>
        <div>
          <label className="label">Risk Tolerance</label>
          <select
            value={riskTolerance}
            onChange={(e) => setRiskTolerance(e.target.value as 'conservative' | 'moderate' | 'aggressive')}
            className="input"
          >
            <option value="conservative">Conservative</option>
            <option value="moderate">Moderate</option>
            <option value="aggressive">Aggressive</option>
          </select>
        </div>
        <button
          onClick={scanStocks}
          disabled={scanning}
          className="btn-primary flex items-center gap-2"
        >
          {scanning ? <Loader2 className="w-5 h-5 animate-spin" /> : <Search className="w-5 h-5" />}
          {scanning ? `Scanning ${market === 'US' ? 'S&P 500' : 'ASX200'}...` : 'Scan for Opportunities'}
        </button>
      </div>

      {scanning && (
        <div className="card">
          <div className="flex flex-col items-center justify-center py-16">
            <Loader2 className="w-16 h-16 animate-spin text-indigo-400 mb-4" />
            <p className={`text-xl font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
              Analyzing {market === 'US' ? 'S&P 500' : 'ASX200'} Fundamentals...
            </p>
            <p className={`mt-2 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Fetching earnings, valuations, and quality metrics</p>
            <p className={`mt-1 text-sm ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>This may take 30-60 seconds</p>
          </div>
        </div>
      )}

      {stocks.length > 0 && !scanning && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <div className="card">
              <div className="flex justify-between items-center mb-4">
                <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                  Top Opportunities ({stocks.length} stocks)
                </h2>
                <span className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                  {selectedStocks.length} selected
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className={isDark ? 'text-slate-400' : 'text-slate-600'}>
                      <th className="text-left p-2">Select</th>
                      <th className="text-left p-2">Stock</th>
                      <th className="text-right p-2">Score</th>
                      <th className="text-right p-2">Exp. Return</th>
                      <th className="text-right p-2">Value</th>
                      <th className="text-right p-2">Quality</th>
                      <th className="text-right p-2">Growth</th>
                      <th className="text-right p-2">Size</th>
                      <th className="text-right p-2">Momentum</th>
                      <th className="text-right p-2">Market Cap</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stocks.map((stock, idx) => (
                      <tr 
                        key={stock.symbol}
                        className={`border-t transition-all duration-200 cursor-pointer ${
                          selectedStocks.includes(stock.symbol) 
                            ? (isDark ? 'bg-indigo-500/20 border-indigo-500/30' : 'bg-indigo-50 border-indigo-200')
                            : (isDark ? 'border-slate-700/50 hover:bg-slate-800/50' : 'border-slate-200 hover:bg-slate-50')
                        }`}
                        onClick={() => toggleStock(stock.symbol)}
                      >
                        <td className="p-2">
                          <input
                            type="checkbox"
                            checked={selectedStocks.includes(stock.symbol)}
                            onChange={() => toggleStock(stock.symbol)}
                            className="rounded"
                          />
                        </td>
                        <td className="p-2">
                          <div>
                            <span className={`font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                              {idx + 1}. {stock.symbol.replace('.AX', '')}
                            </span>
                            <p className={`text-xs truncate max-w-[150px] ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>
                              {stock.name}
                            </p>
                          </div>
                        </td>
                        <td className={`p-2 text-right font-bold ${getScoreColor(stock.composite_score)}`}>
                          {stock.composite_score.toFixed(0)}
                        </td>
                        <td className="p-2 text-right text-emerald-400 font-medium">
                          {formatPercent(stock.expected_return)}
                        </td>
                        <td className={`p-2 text-right ${getScoreColor(stock.value_score)}`}>
                          {stock.value_score.toFixed(0)}
                        </td>
                        <td className={`p-2 text-right ${getScoreColor(stock.quality_score)}`}>
                          {stock.quality_score.toFixed(0)}
                        </td>
                        <td className={`p-2 text-right ${getScoreColor(stock.growth_score)}`}>
                          {stock.growth_score.toFixed(0)}
                        </td>
                        <td className={`p-2 text-right ${getScoreColor(stock.size_score || 50)}`}>
                          {(stock.size_score || 50).toFixed(0)}
                        </td>
                        <td className={`p-2 text-right ${getScoreColor(stock.momentum_score || 50)}`}>
                          {(stock.momentum_score || 50).toFixed(0)}
                        </td>
                        <td className={`p-2 text-right ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                          {formatMarketCap(stock.market_cap)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <button
                onClick={optimizePortfolio}
                disabled={optimizing || selectedStocks.length < 2}
                className="btn-primary mt-4 flex items-center gap-2"
              >
                {optimizing ? <Loader2 className="w-5 h-5 animate-spin" /> : <TrendingUp className="w-5 h-5" />}
                {optimizing ? 'Optimizing...' : `Optimize ${selectedStocks.length} Stocks`}
              </button>
            </div>

            <div className={`card ${isDark ? 'bg-slate-800/50' : 'bg-slate-50'}`}>
              <h3 className={`font-semibold mb-3 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Score Legend</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-emerald-400"></div>
                  <span className={isDark ? 'text-slate-300' : 'text-slate-700'}>70+ Excellent</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-sky-400"></div>
                  <span className={isDark ? 'text-slate-300' : 'text-slate-700'}>50-69 Good</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-amber-400"></div>
                  <span className={isDark ? 'text-slate-300' : 'text-slate-700'}>30-49 Average</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-red-400"></div>
                  <span className={isDark ? 'text-slate-300' : 'text-slate-700'}>Below 30 Poor</span>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {result && (
              <>
                <div className="card">
                  <div className="flex items-center gap-2 mb-4">
                    <Zap className="w-5 h-5 text-indigo-400" />
                    <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                      Fundamentals-Based Results
                    </h2>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-emerald-500/20 border border-emerald-500/30 p-4 rounded-xl">
                      <p className="text-sm text-emerald-300">Expected Return</p>
                      <p className="text-2xl font-bold text-emerald-400">
                        {(result.expected_return * 100).toFixed(2)}%
                      </p>
                    </div>
                    <div className="bg-sky-500/20 border border-sky-500/30 p-4 rounded-xl">
                      <p className="text-sm text-sky-300">Sharpe Ratio</p>
                      <p className="text-2xl font-bold text-sky-400">{result.sharpe_ratio.toFixed(3)}</p>
                    </div>
                    <div className="bg-amber-500/20 border border-amber-500/30 p-4 rounded-xl">
                      <p className="text-sm text-amber-300">Volatility</p>
                      <p className="text-2xl font-bold text-amber-400">{(result.volatility * 100).toFixed(2)}%</p>
                    </div>
                    <div className="bg-red-500/20 border border-red-500/30 p-4 rounded-xl">
                      <p className="text-sm text-red-300">Max Drawdown</p>
                      <p className="text-2xl font-bold text-red-400">{(result.max_drawdown * 100).toFixed(2)}%</p>
                    </div>
                  </div>

                  <div className={`mt-4 p-3 rounded-lg border ${isDark ? 'bg-indigo-500/10 border-indigo-500/30' : 'bg-indigo-50 border-indigo-200'}`}>
                    <p className={`text-xs ${isDark ? 'text-indigo-300' : 'text-indigo-700'}`}>
                      Using Fama-French multi-factor model: Value, Quality, Size, Momentum + Sustainable Growth Rate
                    </p>
                  </div>

                  <button
                    onClick={() => setShowSaveModal(true)}
                    className="btn-success w-full mt-4 flex items-center justify-center gap-2"
                  >
                    <Save className="w-5 h-5" />
                    Save Portfolio
                  </button>
                </div>

                <div className="card">
                  <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>How Much to Invest</h2>
                  <div className="overflow-x-auto mb-4">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className={isDark ? 'text-slate-400' : 'text-slate-600'}>
                          <th className="text-left p-2">Stock</th>
                          <th className="text-right p-2">Weight</th>
                          <th className="text-right p-2">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(result.weights)
                          .sort(([,a], [,b]) => (b as number) - (a as number))
                          .map(([symbol, weight]) => (
                          <tr key={symbol} className={`border-t ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
                            <td className={`p-2 font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                              {symbol.replace('.AX', '')}
                            </td>
                            <td className={`p-2 text-right ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                              {((weight as number) * 100).toFixed(1)}%
                            </td>
                            <td className="p-2 text-right font-bold text-emerald-400">
                              ${((weight as number) * investmentAmount).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                            </td>
                          </tr>
                        ))}
                        <tr className={`border-t-2 ${isDark ? 'border-slate-600' : 'border-slate-300'}`}>
                          <td className={`p-2 font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Total</td>
                          <td className={`p-2 text-right font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>100%</td>
                          <td className="p-2 text-right font-bold text-emerald-400">
                            ${investmentAmount.toLocaleString()}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="card">
                  <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Allocation</h2>
                  <ResponsiveContainer width="100%" height={250}>
                    <PieChart>
                      <Pie
                        data={chartData}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={80}
                        label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                        labelLine={{ stroke: isDark ? '#94a3b8' : '#64748b' }}
                      >
                        {chartData.map((_, index) => (
                          <Cell key={index} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip 
                        formatter={(value: number) => `${value.toFixed(2)}%`}
                        contentStyle={{ backgroundColor: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.95)', border: isDark ? '1px solid rgba(148, 163, 184, 0.2)' : '1px solid rgba(148, 163, 184, 0.3)', borderRadius: '8px' }}
                      />
                      <Legend wrapperStyle={{ color: isDark ? '#94a3b8' : '#64748b' }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>

                <div className="card">
                  <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Holdings by Weight</h2>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={chartData} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke={isDark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(148, 163, 184, 0.3)'} />
                      <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} stroke={isDark ? '#94a3b8' : '#64748b'} />
                      <YAxis type="category" dataKey="name" width={60} stroke={isDark ? '#94a3b8' : '#64748b'} />
                      <Tooltip 
                        formatter={(value: number) => `${value.toFixed(2)}%`}
                        contentStyle={{ backgroundColor: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.95)', border: isDark ? '1px solid rgba(148, 163, 184, 0.2)' : '1px solid rgba(148, 163, 184, 0.3)', borderRadius: '8px' }}
                      />
                      <Bar dataKey="value" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {showSaveModal && result && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="rounded-2xl p-6 w-full max-w-md border" style={{ background: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.95)', borderColor: isDark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(148, 163, 184, 0.3)' }}>
            <h3 className={`text-xl font-bold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Save Fundamentals Portfolio</h3>
            <p className={`mb-4 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Enter a name for your fundamentals-based portfolio:</p>
            <input
              type="text"
              value={portfolioName}
              onChange={(e) => setPortfolioName(e.target.value)}
              placeholder="e.g., Value & Quality Portfolio"
              className="input mb-4"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && portfolioName.trim() && savePortfolio()}
            />
            <div className="flex gap-3">
              <button onClick={() => setShowSaveModal(false)} className="btn-secondary flex-1" disabled={saving}>
                Cancel
              </button>
              <button
                onClick={savePortfolio}
                disabled={saving || !portfolioName.trim()}
                className="btn-success flex-1 flex items-center justify-center gap-2"
              >
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
