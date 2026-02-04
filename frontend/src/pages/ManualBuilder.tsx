import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { stocksApi, portfolioApi } from '../lib/api'
import { OptimizationResult } from '../types'
import { toast } from 'sonner'
import { Search, X, TrendingUp, Save, AlertTriangle, CheckCircle, Info, Loader2 } from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'
import { useTheme } from '../lib/theme'

const COLORS = ['#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']

const getCorrelationColor = (value: number): string => {
  if (value >= 0.7) return 'bg-red-500/80 text-white'
  if (value >= 0.4) return 'bg-amber-500/80 text-white'
  if (value >= 0) return 'bg-emerald-500/80 text-white'
  if (value >= -0.4) return 'bg-sky-500/80 text-white'
  return 'bg-blue-600/80 text-white'
}

const CorrelationMatrix = ({ matrix, symbols, isDark }: { matrix: number[][], symbols: string[], isDark: boolean }) => {
  const avgCorr = matrix.reduce((sum, row, i) => 
    sum + row.reduce((rowSum, val, j) => i !== j ? rowSum + val : rowSum, 0), 0
  ) / (matrix.length * (matrix.length - 1))
  
  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="p-2"></th>
              {symbols.map(s => (
                <th key={s} className={`p-2 font-semibold text-center ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{s}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={symbols[i]}>
                <td className={`p-2 font-semibold ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{symbols[i]}</td>
                {row.map((val, j) => (
                  <td key={j} className={`p-2 text-center rounded transition-all duration-300 ${i === j ? (isDark ? 'bg-slate-700' : 'bg-slate-200') : getCorrelationColor(val)}`}>
                    {val.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      <div className={`flex items-center gap-2 p-3 rounded-lg border backdrop-blur-sm ${
        avgCorr < 0.3 ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' :
        avgCorr < 0.5 ? 'bg-sky-500/20 text-sky-300 border-sky-500/30' :
        'bg-amber-500/20 text-amber-300 border-amber-500/30'
      }`}>
        {avgCorr < 0.3 ? <CheckCircle className="w-5 h-5" /> :
         avgCorr < 0.5 ? <Info className="w-5 h-5" /> :
         <AlertTriangle className="w-5 h-5" />}
        <span className="text-sm font-medium">
          Avg. correlation: {avgCorr.toFixed(2)} - {
            avgCorr < 0.3 ? 'Excellent diversification!' :
            avgCorr < 0.5 ? 'Good diversification' :
            'Consider adding less correlated assets'
          }
        </span>
      </div>
    </div>
  )
}

const formSchema = z.object({
  investment_amount: z.number().min(1000, 'Minimum $1,000').max(10000000, 'Maximum $10,000,000'),
  risk_tolerance: z.enum(['conservative', 'moderate', 'aggressive']),
})

type FormData = z.infer<typeof formSchema>

export default function ManualBuilder() {
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  
  const [selectedStocks, setSelectedStocks] = useState<string[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<{ symbol: string; name: string }[]>([])
  const [optimizing, setOptimizing] = useState(false)
  const [result, setResult] = useState<OptimizationResult | null>(null)
  const [saving, setSaving] = useState(false)
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [portfolioName, setPortfolioName] = useState('')

  const { register, handleSubmit, formState: { errors }, watch } = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      investment_amount: 10000,
      risk_tolerance: 'moderate',
    },
  })

  const investmentAmount = watch('investment_amount')
  const riskTolerance = watch('risk_tolerance')

  const searchStocks = async (query: string) => {
    if (query.length < 1) {
      setSearchResults([])
      return
    }
    try {
      const response = await stocksApi.search(query)
      setSearchResults(response.data.filter((s: { symbol: string }) => !selectedStocks.includes(s.symbol)))
    } catch (error) {
      console.error('Search failed:', error)
    }
  }

  const addStock = (symbol: string) => {
    if (!selectedStocks.includes(symbol)) {
      setSelectedStocks([...selectedStocks, symbol])
    }
    setSearchQuery('')
    setSearchResults([])
  }

  const removeStock = (symbol: string) => {
    setSelectedStocks(selectedStocks.filter((s) => s !== symbol))
    setResult(null)
  }

  const onSubmit = async (data: FormData) => {
    if (selectedStocks.length < 2) {
      toast.error('Please select at least 2 stocks')
      return
    }

    setOptimizing(true)
    try {
      const response = await portfolioApi.optimize(
        selectedStocks,
        data.investment_amount,
        data.risk_tolerance
      )
      setResult(response.data)
      toast.success('Portfolio optimized successfully!')
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Optimization failed')
    } finally {
      setOptimizing(false)
    }
  }

  const openSaveModal = () => {
    if (!result) return
    setPortfolioName('')
    setShowSaveModal(true)
  }

  const savePortfolio = async () => {
    if (!result || !portfolioName.trim()) return

    setSaving(true)
    try {
      await portfolioApi.save(portfolioName.trim(), result, investmentAmount, 'manual', riskTolerance)
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

  const chartData = result ? Object.entries(result.weights).map(([symbol, weight]) => ({
    name: symbol.replace('.AX', ''),
    value: (weight as number) * 100,
  })) : []

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className={`text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Manual Portfolio Builder</h1>
        <p className={`mt-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Select ASX stocks and optimize your portfolio allocation</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="card">
            <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Select Stocks</h2>
            
            <div className="relative">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${isDark ? 'text-slate-400' : 'text-slate-600'}`} />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                  searchStocks(e.target.value)
                }}
                placeholder="Search ASX stocks (e.g., BHP, CBA, CSL)"
                className="input pl-10"
              />
            </div>

            {searchResults.length > 0 && (
              <div className={`mt-2 border rounded-lg overflow-hidden backdrop-blur-sm ${isDark ? 'border-slate-600/50 bg-slate-800/80' : 'border-slate-300 bg-white'}`}>
                {searchResults.map((stock) => (
                  <button
                    key={stock.symbol}
                    onClick={() => addStock(stock.symbol)}
                    className={`w-full px-4 py-2 text-left flex justify-between items-center border-b last:border-b-0 transition-all duration-300 ${isDark ? 'hover:bg-slate-700/50 border-slate-600/50' : 'hover:bg-slate-100 border-slate-200'}`}
                  >
                    <span className={`font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{stock.symbol}</span>
                    <span className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>{stock.name}</span>
                  </button>
                ))}
              </div>
            )}

            <div className="flex flex-wrap gap-2 mt-4">
              {selectedStocks.map((symbol) => (
                <span
                  key={symbol}
                  className="inline-flex items-center gap-1 px-3 py-1 bg-sky-500/20 text-sky-300 border border-sky-500/30 rounded-full text-sm backdrop-blur-sm transition-all duration-300 hover:bg-sky-500/30"
                >
                  {symbol}
                  <button onClick={() => removeStock(symbol)} className="hover:text-sky-100 transition-colors">
                    <X className="w-4 h-4" />
                  </button>
                </span>
              ))}
              {selectedStocks.length === 0 && (
                <p className="text-slate-500 text-sm">No stocks selected. Search and add stocks above.</p>
              )}
            </div>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="card">
            <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Optimization Settings</h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="label">Investment Amount (AUD)</label>
                <input
                  type="number"
                  {...register('investment_amount', { valueAsNumber: true })}
                  className="input"
                />
                {errors.investment_amount && (
                  <p className="error-text">{errors.investment_amount.message}</p>
                )}
              </div>

              <div>
                <label className="label">Risk Tolerance</label>
                <select {...register('risk_tolerance')} className="input">
                  <option value="conservative">Conservative</option>
                  <option value="moderate">Moderate</option>
                  <option value="aggressive">Aggressive</option>
                </select>
              </div>
            </div>

            <button
              type="submit"
              disabled={optimizing || selectedStocks.length < 2}
              className="btn-primary mt-4 flex items-center gap-2"
            >
              {optimizing ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <TrendingUp className="w-5 h-5" />
              )}
              {optimizing ? 'Fetching market data & optimizing...' : 'Optimize Portfolio'}
            </button>
          </form>
        </div>

        <div className="space-y-6">
          {optimizing && (
            <div className="card">
              <div className="flex flex-col items-center justify-center py-12">
                <Loader2 className="w-12 h-12 animate-spin text-sky-400 mb-4" />
                <p className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Fetching market data from Yahoo Finance...</p>
                <p className={`mt-2 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Running portfolio optimization algorithm</p>
              </div>
            </div>
          )}
          
          {!optimizing && result && (
            <>
              <div className="card">
                <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Portfolio Metrics</h2>
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-emerald-500/20 border border-emerald-500/30 p-4 rounded-xl backdrop-blur-sm transition-all duration-300 hover:bg-emerald-500/30">
                    <p className="text-sm text-emerald-300">Expected Return</p>
                    <p className="text-2xl font-bold text-emerald-400">
                      {(result.expected_return * 100).toFixed(2)}%
                    </p>
                  </div>
                  <div className="bg-sky-500/20 border border-sky-500/30 p-4 rounded-xl backdrop-blur-sm transition-all duration-300 hover:bg-sky-500/30">
                    <p className="text-sm text-sky-300">Sharpe Ratio</p>
                    <p className="text-2xl font-bold text-sky-400">{result.sharpe_ratio.toFixed(3)}</p>
                  </div>
                  <div className="bg-amber-500/20 border border-amber-500/30 p-4 rounded-xl backdrop-blur-sm transition-all duration-300 hover:bg-amber-500/30">
                    <p className="text-sm text-amber-300">Volatility</p>
                    <p className="text-2xl font-bold text-amber-400">{(result.volatility * 100).toFixed(2)}%</p>
                  </div>
                  <div className="bg-red-500/20 border border-red-500/30 p-4 rounded-xl backdrop-blur-sm transition-all duration-300 hover:bg-red-500/30">
                    <p className="text-sm text-red-300">Max Drawdown</p>
                    <p className="text-2xl font-bold text-red-400">{(result.max_drawdown * 100).toFixed(2)}%</p>
                  </div>
                </div>
                
                <div className={`mt-4 p-4 border rounded-xl backdrop-blur-sm ${isDark ? 'bg-slate-800/50 border-slate-600/50' : 'bg-slate-100 border-slate-300'}`}>
                  <div className="flex justify-between items-center">
                    <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>Dividend Yield</span>
                    <span className="font-semibold text-purple-400">
                      {(result.portfolio_dividend_yield * 100).toFixed(2)}%
                    </span>
                  </div>
                  <div className="flex justify-between items-center mt-2">
                    <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>Value at Risk (95%)</span>
                    <span className={`font-semibold ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                      {(result.var_95 * 100).toFixed(2)}%
                    </span>
                  </div>
                </div>

                <button
                  onClick={openSaveModal}
                  disabled={saving}
                  className="btn-success w-full mt-4 flex items-center justify-center gap-2"
                >
                  <Save className="w-5 h-5" />
                  Save Portfolio
                </button>
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
                      labelStyle={{ color: isDark ? '#f1f5f9' : '#0f172a' }}
                      itemStyle={{ color: isDark ? '#94a3b8' : '#64748b' }}
                    />
                    <Legend wrapperStyle={{ color: isDark ? '#94a3b8' : '#64748b' }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {result.correlation_matrix && result.correlation_symbols && (
                <div className="card">
                  <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Correlation Matrix</h2>
                  <CorrelationMatrix 
                    matrix={result.correlation_matrix} 
                    symbols={result.correlation_symbols}
                    isDark={isDark}
                  />
                </div>
              )}

              <div className="card">
                <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Allocation Breakdown</h2>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={chartData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke={isDark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(148, 163, 184, 0.3)'} />
                    <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} stroke={isDark ? '#94a3b8' : '#64748b'} />
                    <YAxis type="category" dataKey="name" width={60} stroke={isDark ? '#94a3b8' : '#64748b'} />
                    <Tooltip 
                      formatter={(value: number) => `${value.toFixed(2)}%`}
                      contentStyle={{ backgroundColor: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.95)', border: isDark ? '1px solid rgba(148, 163, 184, 0.2)' : '1px solid rgba(148, 163, 184, 0.3)', borderRadius: '8px' }}
                      labelStyle={{ color: isDark ? '#f1f5f9' : '#0f172a' }}
                      itemStyle={{ color: isDark ? '#94a3b8' : '#64748b' }}
                    />
                    <Bar dataKey="value" fill="#0ea5e9" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </div>
      </div>

      {showSaveModal && result && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="rounded-2xl p-6 w-full max-w-md border transition-all duration-300" style={{ background: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.95)', borderColor: isDark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(148, 163, 184, 0.3)', boxShadow: isDark ? '0 8px 32px rgba(0, 0, 0, 0.5), 0 0 20px rgba(56, 189, 248, 0.1)' : '0 8px 32px rgba(0, 0, 0, 0.15)' }}>
            <h3 className={`text-xl font-bold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Save Portfolio</h3>
            <p className={`mb-4 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Enter a name for your optimized portfolio:</p>
            <input
              type="text"
              value={portfolioName}
              onChange={(e) => setPortfolioName(e.target.value)}
              placeholder="e.g., My ASX Portfolio"
              className="input mb-4"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && portfolioName.trim() && savePortfolio()}
            />
            <div className="flex gap-3">
              <button
                onClick={() => setShowSaveModal(false)}
                className="btn-secondary flex-1"
                disabled={saving}
              >
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
