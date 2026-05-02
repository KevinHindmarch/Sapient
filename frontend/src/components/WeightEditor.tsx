import { useState, useEffect, useCallback } from 'react'
import { RefreshCw, AlertTriangle, CheckCircle } from 'lucide-react'
import { useTheme } from '../lib/theme'

interface WeightEditorProps {
  weights: Record<string, number>
  investmentAmount: number
  currency: string
  onWeightsChange: (weights: Record<string, number>) => void
}

const COLORS = ['#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']

function displaySymbol(sym: string) {
  return sym.replace('.AX', '')
}

export default function WeightEditor({ weights, investmentAmount, currency, onWeightsChange }: WeightEditorProps) {
  const { theme } = useTheme()
  const isDark = theme === 'dark'

  const [editedWeights, setEditedWeights] = useState<Record<string, number>>({})
  const [originalWeights] = useState<Record<string, number>>(weights)

  useEffect(() => {
    setEditedWeights({ ...weights })
  }, [weights])

  const symbols = Object.keys(editedWeights).sort((a, b) => (editedWeights[b] || 0) - (editedWeights[a] || 0))
  const total = symbols.reduce((sum, s) => sum + (editedWeights[s] || 0), 0)
  const totalPct = total * 100
  const isBalanced = Math.abs(totalPct - 100) < 0.1

  const updateWeight = useCallback((symbol: string, pct: number) => {
    const val = Math.max(0, Math.min(100, pct))
    const newWeights = { ...editedWeights, [symbol]: val / 100 }
    setEditedWeights(newWeights)
    onWeightsChange(newWeights)
  }, [editedWeights, onWeightsChange])

  const updateAmount = useCallback((symbol: string, amount: number) => {
    if (investmentAmount <= 0) return
    const pct = (Math.max(0, amount) / investmentAmount) * 100
    updateWeight(symbol, pct)
  }, [investmentAmount, updateWeight])

  const normalize = useCallback(() => {
    if (total <= 0) return
    const normalized: Record<string, number> = {}
    for (const s of symbols) {
      normalized[s] = (editedWeights[s] || 0) / total
    }
    setEditedWeights(normalized)
    onWeightsChange(normalized)
  }, [editedWeights, symbols, total, onWeightsChange])

  const reset = useCallback(() => {
    setEditedWeights({ ...originalWeights })
    onWeightsChange({ ...originalWeights })
  }, [originalWeights, onWeightsChange])

  const evenDistribute = useCallback(() => {
    const evenWeight = 1 / symbols.length
    const even: Record<string, number> = {}
    for (const s of symbols) even[s] = evenWeight
    setEditedWeights(even)
    onWeightsChange(even)
  }, [symbols, onWeightsChange])

  return (
    <div className="space-y-4">
      {/* Total indicator */}
      <div className={`flex items-center justify-between p-3 rounded-lg border ${
        isBalanced
          ? isDark ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-emerald-50 border-emerald-200'
          : isDark ? 'bg-amber-500/10 border-amber-500/30' : 'bg-amber-50 border-amber-200'
      }`}>
        <div className="flex items-center gap-2">
          {isBalanced
            ? <CheckCircle className="w-4 h-4 text-emerald-400" />
            : <AlertTriangle className="w-4 h-4 text-amber-400" />}
          <span className={`text-sm font-medium ${
            isBalanced
              ? isDark ? 'text-emerald-300' : 'text-emerald-700'
              : isDark ? 'text-amber-300' : 'text-amber-700'
          }`}>
            Total: {totalPct.toFixed(1)}%{!isBalanced && ` — ${totalPct > 100 ? 'over' : 'under'} by ${Math.abs(totalPct - 100).toFixed(1)}%`}
          </span>
        </div>
        <div className="flex gap-2">
          {!isBalanced && (
            <button
              onClick={normalize}
              className={`text-xs px-2 py-1 rounded-md border flex items-center gap-1 transition-colors ${
                isDark ? 'border-amber-500/30 text-amber-300 hover:bg-amber-500/20' : 'border-amber-300 text-amber-700 hover:bg-amber-100'
              }`}
            >
              <RefreshCw className="w-3 h-3" /> Normalize
            </button>
          )}
          <button
            onClick={evenDistribute}
            className={`text-xs px-2 py-1 rounded-md border flex items-center gap-1 transition-colors ${
              isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-slate-300 text-slate-600 hover:bg-slate-100'
            }`}
          >
            Even split
          </button>
          <button
            onClick={reset}
            className={`text-xs px-2 py-1 rounded-md border flex items-center gap-1 transition-colors ${
              isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-slate-300 text-slate-600 hover:bg-slate-100'
            }`}
          >
            Reset
          </button>
        </div>
      </div>

      {/* Weight rows */}
      <div className="space-y-3">
        {symbols.map((symbol, index) => {
          const pct = (editedWeights[symbol] || 0) * 100
          const amount = (editedWeights[symbol] || 0) * investmentAmount
          return (
            <div key={symbol} className={`p-3 rounded-lg border ${isDark ? 'bg-slate-800/50 border-slate-700/50' : 'bg-slate-50 border-slate-200'}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                  <span className={`font-semibold text-sm ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{displaySymbol(symbol)}</span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={`text-xs mb-1 block ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Weight (%)</label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.1}
                    value={pct.toFixed(1)}
                    onChange={(e) => updateWeight(symbol, parseFloat(e.target.value) || 0)}
                    className={`w-full text-sm px-2 py-1.5 rounded-lg border transition-colors ${
                      isDark
                        ? 'bg-slate-700/50 border-slate-600/50 text-slate-100 focus:border-sky-500/50 focus:bg-slate-700'
                        : 'bg-white border-slate-300 text-slate-900 focus:border-sky-400'
                    } focus:outline-none focus:ring-1 focus:ring-sky-500/30`}
                  />
                </div>
                <div>
                  <label className={`text-xs mb-1 block ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>{currency} Amount</label>
                  <input
                    type="number"
                    min={0}
                    step={100}
                    value={Math.round(amount)}
                    onChange={(e) => updateAmount(symbol, parseFloat(e.target.value) || 0)}
                    className={`w-full text-sm px-2 py-1.5 rounded-lg border transition-colors ${
                      isDark
                        ? 'bg-slate-700/50 border-slate-600/50 text-slate-100 focus:border-sky-500/50 focus:bg-slate-700'
                        : 'bg-white border-slate-300 text-slate-900 focus:border-sky-400'
                    } focus:outline-none focus:ring-1 focus:ring-sky-500/30`}
                  />
                </div>
              </div>
              {/* Progress bar */}
              <div className={`mt-2 h-1.5 rounded-full ${isDark ? 'bg-slate-700' : 'bg-slate-200'}`}>
                <div
                  className="h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${Math.min(100, pct)}%`, backgroundColor: COLORS[index % COLORS.length] }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
