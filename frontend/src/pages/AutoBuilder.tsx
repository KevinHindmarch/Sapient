import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { stocksApi, portfolioApi } from '../lib/api'
import { OptimizationResult } from '../types'
import { toast } from 'sonner'
import { Wand2, Save, TrendingUp, AlertCircle, Loader2, CheckCircle, Info, AlertTriangle } from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'

const COLORS = ['#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']

const formSchema = z.object({
  investment_amount: z.number().min(1000, 'Minimum $1,000').max(10000000, 'Maximum $10,000,000'),
  portfolio_size: z.enum(['small', 'medium', 'large']),
  risk_tolerance: z.enum(['conservative', 'moderate', 'aggressive']),
})

type FormData = z.infer<typeof formSchema>

const PORTFOLIO_SIZES = {
  small: { min: 5, max: 8, label: 'Small (5-8 stocks)' },
  medium: { min: 8, max: 12, label: 'Medium (8-12 stocks)' },
  large: { min: 12, max: 20, label: 'Large (12-20 stocks)' },
}

const getCorrelationColor = (value: number): string => {
  if (value >= 0.7) return 'bg-red-500 text-white'
  if (value >= 0.4) return 'bg-amber-400 text-slate-900'
  if (value >= 0) return 'bg-emerald-400 text-slate-900'
  if (value >= -0.4) return 'bg-sky-400 text-slate-900'
  return 'bg-blue-600 text-white'
}

const CorrelationMatrix = ({ matrix, symbols }: { matrix: number[][], symbols: string[] }) => {
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
                <th key={s} className="p-2 font-semibold text-slate-700 text-center">{s}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={symbols[i]}>
                <td className="p-2 font-semibold text-slate-700">{symbols[i]}</td>
                {row.map((val, j) => (
                  <td key={j} className={`p-2 text-center rounded ${i === j ? 'bg-slate-200' : getCorrelationColor(val)}`}>
                    {val.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      <div className={`flex items-center gap-2 p-3 rounded-lg ${
        avgCorr < 0.3 ? 'bg-emerald-50 text-emerald-700' :
        avgCorr < 0.5 ? 'bg-sky-50 text-sky-700' :
        'bg-amber-50 text-amber-700'
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

export default function AutoBuilder() {
  const [building, setBuilding] = useState(false)
  const [result, setResult] = useState<OptimizationResult | null>(null)
  const [selectedStocks, setSelectedStocks] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [progress, setProgress] = useState('')
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [portfolioName, setPortfolioName] = useState('')

  const { register, handleSubmit, formState: { errors }, watch } = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      investment_amount: 50000,
      portfolio_size: 'medium',
      risk_tolerance: 'moderate',
    },
  })

  const investmentAmount = watch('investment_amount')
  const riskTolerance = watch('risk_tolerance')

  const onSubmit = async (data: FormData) => {
    setBuilding(true)
    setProgress('Analyzing all ASX200 stocks by Sharpe ratio...')
    
    try {
      const rankResponse = await stocksApi.rankByPerformance()
      const rankings = rankResponse.data.rankings as Array<{symbol: string, sharpe_ratio: number, annual_return: number}>
      
      if (!rankings || rankings.length === 0) {
        throw new Error('No stock data available')
      }
      
      setProgress(`Ranked ${rankings.length} stocks - selecting top performers...`)
      
      const sizeConfig = PORTFOLIO_SIZES[data.portfolio_size]
      const targetSize = Math.floor((sizeConfig.min + sizeConfig.max) / 2)
      
      const topStocks = rankings
        .filter(s => s.sharpe_ratio > 0)
        .slice(0, targetSize)
        .map(s => s.symbol)
      
      if (topStocks.length < 3) {
        throw new Error('Not enough stocks with positive Sharpe ratio')
      }
      
      setSelectedStocks(topStocks)
      setProgress(`Optimizing top ${topStocks.length} performers for maximum Sharpe ratio...`)
      
      const response = await portfolioApi.optimize(
        topStocks,
        data.investment_amount,
        data.risk_tolerance
      )
      
      setResult(response.data)
      toast.success(`Selected top ${topStocks.length} stocks from ${rankings.length} analyzed!`)
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Failed to build portfolio')
    } finally {
      setBuilding(false)
      setProgress('')
    }
  }

  const openSaveModal = () => {
    setPortfolioName('')
    setShowSaveModal(true)
  }

  const savePortfolio = async () => {
    if (!result || !portfolioName.trim()) return

    setSaving(true)
    try {
      await portfolioApi.save(portfolioName.trim(), result, investmentAmount, 'auto', riskTolerance)
      toast.success('Portfolio saved successfully!')
      setShowSaveModal(false)
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Failed to save portfolio')
    } finally {
      setSaving(false)
    }
  }

  const chartData = result ? Object.entries(result.weights)
    .sort(([, a], [, b]) => (b as number) - (a as number))
    .slice(0, 8)
    .map(([symbol, weight]) => ({
      name: symbol.replace('.AX', ''),
      value: (weight as number) * 100,
    })) : []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Auto Portfolio Builder</h1>
        <p className="text-slate-600 mt-1">
          Automatically generate an optimized portfolio from ASX200 stocks
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <form onSubmit={handleSubmit(onSubmit)} className="card">
            <h2 className="text-lg font-semibold text-slate-900 mb-4">Build Settings</h2>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
                <label className="label">Portfolio Size</label>
                <select {...register('portfolio_size')} className="input">
                  {Object.entries(PORTFOLIO_SIZES).map(([key, config]) => (
                    <option key={key} value={key}>{config.label}</option>
                  ))}
                </select>
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

            <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-amber-600 mt-0.5" />
              <div>
                <p className="text-sm text-amber-800 font-medium">How it works</p>
                <p className="text-sm text-amber-700 mt-1">
                  Sapient fetches the full ASX200 index, selects diversified stocks based on your portfolio size,
                  and optimizes allocations using real Yahoo Finance data and Modern Portfolio Theory (Sharpe ratio maximization).
                </p>
              </div>
            </div>

            <button
              type="submit"
              disabled={building}
              className="btn-primary mt-4 flex items-center gap-2"
            >
              {building ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Wand2 className="w-5 h-5" />
              )}
              {building ? progress || 'Building...' : 'Build Portfolio'}
            </button>
          </form>

          {building && (
            <div className="card mt-6">
              <div className="flex flex-col items-center justify-center py-12">
                <Loader2 className="w-12 h-12 animate-spin text-sky-600 mb-4" />
                <p className="text-lg font-semibold text-slate-700">{progress || 'Processing...'}</p>
                <p className="text-slate-500 mt-2">This may take a moment as we fetch real market data</p>
              </div>
            </div>
          )}

          {!building && result && (
            <>
              <div className="card mt-6">
                <h2 className="text-lg font-semibold text-slate-900 mb-4">Recommended Allocation</h2>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-sm text-slate-500 border-b">
                        <th className="pb-3 font-medium">Stock</th>
                        <th className="pb-3 font-medium text-right">Weight</th>
                        <th className="pb-3 font-medium text-right">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(result.weights)
                        .sort(([, a], [, b]) => (b as number) - (a as number))
                        .map(([symbol, weight], index) => {
                          const weightNum = weight as number
                          const amount = weightNum * investmentAmount
                          return (
                            <tr key={symbol} className="border-b border-slate-100 last:border-0">
                              <td className="py-3">
                                <div className="flex items-center gap-2">
                                  <div 
                                    className="w-3 h-3 rounded-full" 
                                    style={{ backgroundColor: COLORS[index % COLORS.length] }}
                                  />
                                  <span className="font-medium text-slate-900">{symbol.replace('.AX', '')}</span>
                                </div>
                              </td>
                              <td className="py-3 text-right">
                                <span className="font-medium text-sky-600">{(weightNum * 100).toFixed(1)}%</span>
                              </td>
                              <td className="py-3 text-right">
                                <span className="text-slate-700">${amount.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                              </td>
                            </tr>
                          )
                        })}
                    </tbody>
                    <tfoot>
                      <tr className="border-t-2 border-slate-200">
                        <td className="py-3 font-semibold text-slate-900">Total</td>
                        <td className="py-3 text-right font-semibold text-sky-600">100%</td>
                        <td className="py-3 text-right font-semibold text-slate-900">${investmentAmount.toLocaleString()}</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            </>
          )}
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
                    <span className="font-medium text-sky-600">{result.sharpe_ratio.toFixed(3)}</span>
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
                  <div className="flex justify-between">
                    <span className="text-slate-600">Stocks in Portfolio</span>
                    <span className="font-medium">{Object.keys(result.weights).length}</span>
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
                <h2 className="text-lg font-semibold text-slate-900 mb-4">Top Holdings</h2>
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

              {result.correlation_matrix && result.correlation_symbols && (
                <div className="card">
                  <h2 className="text-lg font-semibold text-slate-900 mb-4">Correlation Matrix</h2>
                  <CorrelationMatrix 
                    matrix={result.correlation_matrix} 
                    symbols={result.correlation_symbols} 
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {showSaveModal && result && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl">
            <h3 className="text-xl font-bold text-slate-900 mb-4">Save Portfolio</h3>
            <p className="text-slate-600 mb-4">Enter a name for your auto-generated portfolio:</p>
            <input
              type="text"
              value={portfolioName}
              onChange={(e) => setPortfolioName(e.target.value)}
              placeholder="e.g., ASX200 Optimized"
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
