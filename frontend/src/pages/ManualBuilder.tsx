import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { stocksApi, portfolioApi } from '../lib/api'
import { OptimizationResult } from '../types'
import { toast } from 'sonner'
import { Search, X, TrendingUp, Save } from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts'

const COLORS = ['#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']

const formSchema = z.object({
  investment_amount: z.number().min(1000, 'Minimum $1,000').max(10000000, 'Maximum $10,000,000'),
  risk_tolerance: z.enum(['conservative', 'moderate', 'aggressive']),
})

type FormData = z.infer<typeof formSchema>

export default function ManualBuilder() {
  const [selectedStocks, setSelectedStocks] = useState<string[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<{ symbol: string; name: string }[]>([])
  const [optimizing, setOptimizing] = useState(false)
  const [result, setResult] = useState<OptimizationResult | null>(null)
  const [saving, setSaving] = useState(false)

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

  const savePortfolio = async () => {
    if (!result) return

    const name = prompt('Enter a name for this portfolio:')
    if (!name) return

    setSaving(true)
    try {
      await portfolioApi.save(name, result, investmentAmount, 'manual', riskTolerance)
      toast.success('Portfolio saved successfully!')
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
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Manual Portfolio Builder</h1>
        <p className="text-slate-600 mt-1">Select ASX stocks and optimize your portfolio allocation</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="card">
            <h2 className="text-lg font-semibold text-slate-900 mb-4">Select Stocks</h2>
            
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
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
              <div className="mt-2 border border-slate-200 rounded-lg overflow-hidden">
                {searchResults.map((stock) => (
                  <button
                    key={stock.symbol}
                    onClick={() => addStock(stock.symbol)}
                    className="w-full px-4 py-2 text-left hover:bg-slate-50 flex justify-between items-center border-b last:border-b-0"
                  >
                    <span className="font-medium">{stock.symbol}</span>
                    <span className="text-sm text-slate-500">{stock.name}</span>
                  </button>
                ))}
              </div>
            )}

            <div className="flex flex-wrap gap-2 mt-4">
              {selectedStocks.map((symbol) => (
                <span
                  key={symbol}
                  className="inline-flex items-center gap-1 px-3 py-1 bg-sky-100 text-sky-700 rounded-full text-sm"
                >
                  {symbol}
                  <button onClick={() => removeStock(symbol)} className="hover:text-sky-900">
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
            <h2 className="text-lg font-semibold text-slate-900 mb-4">Optimization Settings</h2>
            
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
              <TrendingUp className="w-5 h-5" />
              {optimizing ? 'Optimizing...' : 'Optimize Portfolio'}
            </button>
          </form>
        </div>

        <div className="space-y-6">
          {result && (
            <>
              <div className="card">
                <h2 className="text-lg font-semibold text-slate-900 mb-4">Portfolio Metrics</h2>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-slate-600">Expected Return</span>
                    <span className="font-medium text-emerald-600">
                      {(result.expected_return * 100).toFixed(2)}%
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-600">Volatility</span>
                    <span className="font-medium">{(result.volatility * 100).toFixed(2)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-600">Sharpe Ratio</span>
                    <span className="font-medium">{result.sharpe_ratio.toFixed(3)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-600">Max Drawdown</span>
                    <span className="font-medium text-red-600">
                      {(result.max_drawdown * 100).toFixed(2)}%
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-600">Dividend Yield</span>
                    <span className="font-medium">
                      {(result.portfolio_dividend_yield * 100).toFixed(2)}%
                    </span>
                  </div>
                </div>

                <button
                  onClick={savePortfolio}
                  disabled={saving}
                  className="btn-success w-full mt-4 flex items-center justify-center gap-2"
                >
                  <Save className="w-5 h-5" />
                  {saving ? 'Saving...' : 'Save Portfolio'}
                </button>
              </div>

              <div className="card">
                <h2 className="text-lg font-semibold text-slate-900 mb-4">Allocation</h2>
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
                    >
                      {chartData.map((_, index) => (
                        <Cell key={index} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value: number) => `${value.toFixed(2)}%`} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
