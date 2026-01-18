import { useState } from 'react'
import { portfolioApi, stocksApi } from '../lib/api'
import { toast } from 'sonner'
import { Search, TrendingUp, Save, Loader2, Activity, Target, Shield, Zap, X, Plus } from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'
import { useTheme } from '../lib/theme'

const COLORS = ['#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']

interface StockCAPMData {
  symbol: string
  beta: number
  expected_return: number
  volatility: number
  alpha: number
  risk_category: string
  current_price: number | null
}

interface OptimizationResult {
  weights: Record<string, number>
  expected_return: number
  volatility: number
  sharpe_ratio: number
  var_95: number
  max_drawdown: number
  portfolio_dividend_yield: number
  market_premium: number
  risk_free_rate: number
  stock_capm_data: {
    symbol: string
    weight: number
    beta: number
    expected_return: number
    volatility: number
    alpha: number
    risk_category: string
  }[]
}

export default function CAPMBuilder() {
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<{symbol: string, name: string}[]>([])
  const [searching, setSearching] = useState(false)
  const [selectedStocks, setSelectedStocks] = useState<string[]>([])
  const [analyzing, setAnalyzing] = useState(false)
  const [stockData, setStockData] = useState<Record<string, StockCAPMData>>({})
  const [optimizing, setOptimizing] = useState(false)
  const [result, setResult] = useState<OptimizationResult | null>(null)
  const [saving, setSaving] = useState(false)
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [portfolioName, setPortfolioName] = useState('')
  const [investmentAmount, setInvestmentAmount] = useState(50000)
  const [riskTolerance, setRiskTolerance] = useState<'conservative' | 'moderate' | 'aggressive'>('moderate')

  const searchStocks = async (query: string) => {
    if (query.length < 1) {
      setSearchResults([])
      return
    }
    setSearching(true)
    try {
      const response = await stocksApi.search(query)
      setSearchResults(response.data.slice(0, 10))
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  const addStock = (symbol: string) => {
    if (!selectedStocks.includes(symbol)) {
      setSelectedStocks([...selectedStocks, symbol])
      setResult(null)
    }
    setSearchQuery('')
    setSearchResults([])
  }

  const removeStock = (symbol: string) => {
    setSelectedStocks(selectedStocks.filter(s => s !== symbol))
    const newData = { ...stockData }
    delete newData[symbol]
    setStockData(newData)
    setResult(null)
  }

  const analyzeStocks = async () => {
    if (selectedStocks.length < 2) {
      toast.error('Select at least 2 stocks')
      return
    }
    
    setAnalyzing(true)
    try {
      const response = await portfolioApi.analyzeCAPM(selectedStocks)
      const data: Record<string, StockCAPMData> = {}
      for (const symbol of selectedStocks) {
        if (response.data.stocks[symbol + '.AX']) {
          data[symbol] = response.data.stocks[symbol + '.AX']
        }
      }
      setStockData(data)
      toast.success('CAPM analysis complete')
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Failed to analyze stocks')
    } finally {
      setAnalyzing(false)
    }
  }

  const optimizePortfolio = async () => {
    if (selectedStocks.length < 2) {
      toast.error('Select at least 2 stocks')
      return
    }

    setOptimizing(true)
    try {
      const response = await portfolioApi.optimizeCAPM(
        selectedStocks,
        investmentAmount,
        riskTolerance
      )
      setResult(response.data)
      toast.success('Portfolio optimized using CAPM!')
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Failed to optimize portfolio')
    } finally {
      setOptimizing(false)
    }
  }

  const savePortfolio = async () => {
    if (!result || !portfolioName.trim()) return
    
    setSaving(true)
    try {
      await portfolioApi.save(portfolioName.trim(), result, investmentAmount, 'capm', riskTolerance)
      toast.success('Portfolio saved!')
      setShowSaveModal(false)
      setPortfolioName('')
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Failed to save portfolio')
    } finally {
      setSaving(false)
    }
  }

  const chartData = result 
    ? Object.entries(result.weights)
        .sort(([,a], [,b]) => (b as number) - (a as number))
        .map(([symbol, weight]) => ({
          name: symbol.replace('.AX', ''),
          value: (weight as number) * 100
        }))
    : []

  const getRiskBadge = (category: string) => {
    switch (category) {
      case 'Defensive':
        return <span className="px-2 py-0.5 text-xs rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30">Defensive</span>
      case 'Neutral':
        return <span className="px-2 py-0.5 text-xs rounded-full bg-slate-500/20 text-slate-400 border border-slate-500/30">Neutral</span>
      case 'Aggressive':
        return <span className="px-2 py-0.5 text-xs rounded-full bg-orange-500/20 text-orange-400 border border-orange-500/30">Aggressive</span>
      default:
        return null
    }
  }

  const getValuationBadge = (alpha: number) => {
    if (alpha > 0.02) {
      return <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">Undervalued</span>
    } else if (alpha < -0.02) {
      return <span className="px-2 py-0.5 text-xs rounded-full bg-red-500/20 text-red-400 border border-red-500/30">Overvalued</span>
    } else {
      return <span className="px-2 py-0.5 text-xs rounded-full bg-slate-500/20 text-slate-400 border border-slate-500/30">Fair Value</span>
    }
  }

  return (
    <div className={`min-h-screen p-6 ${isDark ? '' : 'bg-slate-50'}`}>
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <h1 className={`text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>CAPM Portfolio Builder</h1>
          <p className={`mt-2 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
            Build a portfolio using the Capital Asset Pricing Model (CAPM) to estimate expected returns based on market risk.
          </p>
        </div>

        <div className={`card mb-6 p-4 rounded-xl border ${isDark ? 'bg-indigo-500/10 border-indigo-500/30' : 'bg-indigo-50 border-indigo-200'}`}>
          <h3 className={`font-semibold mb-2 ${isDark ? 'text-indigo-300' : 'text-indigo-700'}`}>
            <Activity className="w-5 h-5 inline mr-2" />
            CAPM Formula & Valuation
          </h3>
          <p className={`text-sm ${isDark ? 'text-indigo-200' : 'text-indigo-800'}`}>
            <strong>Expected Return = Risk-Free Rate + Beta × (Market Return - Risk-Free Rate)</strong>
          </p>
          <p className={`text-sm mt-1 ${isDark ? 'text-indigo-200' : 'text-indigo-800'}`}>
            <strong>Alpha = Actual Return - Expected Return</strong> (measures over/underperformance)
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
            <div>
              <p className={`text-xs font-medium ${isDark ? 'text-indigo-300' : 'text-indigo-700'}`}>Risk Categories (Beta):</p>
              <ul className={`text-xs mt-1 space-y-0.5 ${isDark ? 'text-indigo-300' : 'text-indigo-600'}`}>
                <li><strong>β &lt; 0.8:</strong> Defensive (less volatile)</li>
                <li><strong>β ≈ 1:</strong> Neutral (moves with market)</li>
                <li><strong>β &gt; 1.2:</strong> Aggressive (more volatile)</li>
              </ul>
            </div>
            <div>
              <p className={`text-xs font-medium ${isDark ? 'text-indigo-300' : 'text-indigo-700'}`}>Valuation (Alpha):</p>
              <ul className={`text-xs mt-1 space-y-0.5 ${isDark ? 'text-indigo-300' : 'text-indigo-600'}`}>
                <li><span className="text-emerald-400">●</span> <strong>α &gt; 2%:</strong> Undervalued (outperformed)</li>
                <li><span className="text-slate-400">●</span> <strong>α ≈ 0:</strong> Fair Value</li>
                <li><span className="text-red-400">●</span> <strong>α &lt; -2%:</strong> Overvalued (underperformed)</li>
              </ul>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1 space-y-4">
            <div className="card">
              <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Add Stocks</h2>
              
              <div className="relative mb-4">
                <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`} />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value)
                    searchStocks(e.target.value)
                  }}
                  placeholder="Search ASX stocks..."
                  className="input pl-10"
                />
                {searching && (
                  <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 animate-spin text-sky-500" />
                )}
              </div>

              {searchResults.length > 0 && (
                <div className={`border rounded-lg mb-4 max-h-48 overflow-y-auto ${isDark ? 'border-slate-700 bg-slate-800/50' : 'border-slate-200 bg-white'}`}>
                  {searchResults.map((stock) => (
                    <button
                      key={stock.symbol}
                      onClick={() => addStock(stock.symbol.replace('.AX', ''))}
                      className={`w-full text-left p-2 flex items-center justify-between hover:bg-sky-500/10 ${isDark ? 'border-slate-700' : 'border-slate-200'} border-b last:border-b-0`}
                    >
                      <span>
                        <span className={`font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{stock.symbol.replace('.AX', '')}</span>
                        <span className={`text-sm ml-2 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>{stock.name}</span>
                      </span>
                      <Plus className="w-4 h-4 text-sky-500" />
                    </button>
                  ))}
                </div>
              )}

              <div className="space-y-2">
                {selectedStocks.map((symbol) => (
                  <div key={symbol} className={`flex items-center justify-between p-2 rounded-lg ${isDark ? 'bg-slate-700/50' : 'bg-slate-100'}`}>
                    <span className={`font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{symbol}</span>
                    <div className="flex items-center gap-2">
                      {stockData[symbol] && (
                        <span className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                          β={stockData[symbol].beta.toFixed(2)}
                        </span>
                      )}
                      <button onClick={() => removeStock(symbol)} className="text-red-400 hover:text-red-500">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {selectedStocks.length > 0 && (
                <button
                  onClick={analyzeStocks}
                  disabled={analyzing || selectedStocks.length < 2}
                  className="btn-secondary w-full mt-4 flex items-center justify-center gap-2"
                >
                  {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
                  {analyzing ? 'Analyzing...' : 'Analyze Betas'}
                </button>
              )}
            </div>

            <div className="card">
              <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Settings</h2>
              
              <label className={`block text-sm mb-2 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Investment Amount</label>
              <input
                type="number"
                value={investmentAmount}
                onChange={(e) => setInvestmentAmount(Number(e.target.value))}
                className="input mb-4"
                min={1000}
                step={1000}
              />

              <label className={`block text-sm mb-2 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Risk Tolerance</label>
              <div className="grid grid-cols-3 gap-2 mb-4">
                {(['conservative', 'moderate', 'aggressive'] as const).map((risk) => (
                  <button
                    key={risk}
                    onClick={() => { setRiskTolerance(risk); setResult(null) }}
                    className={`p-2 rounded-lg text-sm capitalize transition-all ${
                      riskTolerance === risk
                        ? 'bg-sky-500 text-white'
                        : isDark ? 'bg-slate-700/50 text-slate-300 hover:bg-slate-700' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                    }`}
                  >
                    {risk === 'conservative' && <Shield className="w-4 h-4 inline mr-1" />}
                    {risk === 'moderate' && <Target className="w-4 h-4 inline mr-1" />}
                    {risk === 'aggressive' && <Zap className="w-4 h-4 inline mr-1" />}
                    {risk}
                  </button>
                ))}
              </div>

              <button
                onClick={optimizePortfolio}
                disabled={optimizing || selectedStocks.length < 2}
                className="btn-primary w-full flex items-center justify-center gap-2"
              >
                {optimizing ? <Loader2 className="w-5 h-5 animate-spin" /> : <TrendingUp className="w-5 h-5" />}
                {optimizing ? 'Optimizing...' : 'Optimize Portfolio'}
              </button>
            </div>
          </div>

          <div className="lg:col-span-2 space-y-4">
            {Object.keys(stockData).length > 0 && !result && (
              <div className="card">
                <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>CAPM Analysis</h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className={isDark ? 'text-slate-400' : 'text-slate-600'}>
                        <th className="text-left p-2">Stock</th>
                        <th className="text-right p-2">Beta</th>
                        <th className="text-right p-2">Expected Return</th>
                        <th className="text-right p-2">Volatility</th>
                        <th className="text-right p-2">Alpha</th>
                        <th className="text-center p-2">Valuation</th>
                        <th className="text-center p-2">Risk</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(stockData).map(([symbol, data]: [string, StockCAPMData]) => (
                        <tr key={symbol} className={`border-t ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
                          <td className={`p-2 font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{symbol}</td>
                          <td className="p-2 text-right font-mono">{data.beta.toFixed(2)}</td>
                          <td className="p-2 text-right text-emerald-400">{(data.expected_return * 100).toFixed(1)}%</td>
                          <td className="p-2 text-right text-amber-400">{(data.volatility * 100).toFixed(1)}%</td>
                          <td className={`p-2 text-right ${data.alpha >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {(data.alpha * 100).toFixed(2)}%
                          </td>
                          <td className="p-2 text-center">{getValuationBadge(data.alpha)}</td>
                          <td className="p-2 text-center">{getRiskBadge(data.risk_category)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {result && (
              <>
                <div className="card">
                  <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Portfolio Metrics</h2>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="bg-emerald-500/20 border border-emerald-500/30 p-4 rounded-xl">
                      <p className="text-sm text-emerald-300">Expected Return</p>
                      <p className="text-2xl font-bold text-emerald-400">{(result.expected_return * 100).toFixed(2)}%</p>
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
                      Market Premium: {(result.market_premium * 100).toFixed(1)}% | Risk-Free Rate: {(result.risk_free_rate * 100).toFixed(1)}%
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
                          <th className="text-right p-2">Beta</th>
                          <th className="text-right p-2">Weight</th>
                          <th className="text-right p-2">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.stock_capm_data
                          .sort((a, b) => b.weight - a.weight)
                          .map((stock) => (
                          <tr key={stock.symbol} className={`border-t ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
                            <td className={`p-2 font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                              {stock.symbol.replace('.AX', '')}
                            </td>
                            <td className="p-2 text-right font-mono">
                              {stock.beta.toFixed(2)}
                            </td>
                            <td className={`p-2 text-right ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                              {(stock.weight * 100).toFixed(1)}%
                            </td>
                            <td className="p-2 text-right font-bold text-emerald-400">
                              ${(stock.weight * investmentAmount).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                            </td>
                          </tr>
                        ))}
                        <tr className={`border-t-2 ${isDark ? 'border-slate-600' : 'border-slate-300'}`}>
                          <td className={`p-2 font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Total</td>
                          <td className="p-2"></td>
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
      </div>

      {showSaveModal && result && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="rounded-2xl p-6 w-full max-w-md border" style={{ background: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.95)', borderColor: isDark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(148, 163, 184, 0.3)' }}>
            <h3 className={`text-xl font-bold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Save CAPM Portfolio</h3>
            <p className={`mb-4 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Enter a name for your CAPM-optimized portfolio:</p>
            <input
              type="text"
              value={portfolioName}
              onChange={(e) => setPortfolioName(e.target.value)}
              placeholder="e.g., Beta-Balanced Portfolio"
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
