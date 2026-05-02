import React, { useState } from 'react';
import { 
  ChevronRight, 
  RefreshCw, 
  Zap, 
  MoreVertical, 
  TrendingUp, 
  Sparkles, 
  ArrowRight,
  ShieldAlert,
  AlertCircle
} from 'lucide-react';
import "./_group.css";

export function PortfolioExecute() {
  const [aiMode, setAiMode] = useState<'off' | 'suggestions' | 'autonomous'>('suggestions');

  const positions = [
    { ticker: 'CBA.AX', name: 'Commonwealth Bank', shares: 140, avgCost: 102.50, price: 115.20, value: 16128.00, pl: 1778.00, plPct: 12.39, targetPct: 25, currentPct: 27.6, drift: 2.6 },
    { ticker: 'BHP.AX', name: 'BHP Group', shares: 250, avgCost: 42.80, price: 46.10, value: 11525.00, pl: 825.00, plPct: 7.71, targetPct: 22, currentPct: 19.8, drift: -2.2, pendingBuy: true },
    { ticker: 'CSL.AX', name: 'CSL Limited', shares: 35, avgCost: 270.20, price: 295.40, value: 10339.00, pl: 882.00, plPct: 9.32, targetPct: 14, currentPct: 17.7, drift: 3.7, pendingSell: true },
    { ticker: 'NAB.AX', name: 'National Australia Bank', shares: 210, avgCost: 29.10, price: 34.20, value: 7182.00, pl: 1071.00, plPct: 17.52, targetPct: 12, currentPct: 12.3, drift: 0.3 },
    { ticker: 'WBC.AX', name: 'Westpac Banking', shares: 180, avgCost: 22.40, price: 26.50, value: 4780.00, pl: 738.00, plPct: 18.30, targetPct: 10, currentPct: 8.2, drift: -1.8, pendingBuy: true },
    { ticker: 'MQG.AX', name: 'Macquarie Group', shares: 20, avgCost: 175.50, price: 192.30, value: 3846.00, pl: 336.00, plPct: 9.57, targetPct: 8, currentPct: 6.6, drift: -1.4 },
    { ticker: 'WES.AX', name: 'Wesfarmers Limited', shares: 55, avgCost: 50.10, price: 58.20, value: 3201.00, pl: 445.50, plPct: 16.16, targetPct: 5, currentPct: 5.5, drift: 0.5 },
    { ticker: 'TLS.AX', name: 'Telstra Group', shares: 310, avgCost: 3.90, price: 4.02, value: 1246.20, pl: 37.20, plPct: 3.07, targetPct: 4, currentPct: 2.1, drift: -1.9 },
  ];

  return (
    <div className="sapient-dark sapient-bg font-sans p-6 sm:p-8 md:p-10 space-y-8">
      {/* Header */}
      <header className="space-y-4">
        <div className="flex items-center text-sm font-medium text-slate-400 space-x-2">
          <span className="hover:text-slate-200 cursor-pointer transition-colors">Portfolios</span>
          <ChevronRight className="w-4 h-4" />
          <span className="text-slate-200">ASX Growth Sharpe-Max</span>
        </div>
        
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white mb-1">
              <span className="sapient-gradient-text">ASX Growth Sharpe-Max</span>
            </h1>
            <p className="text-slate-400 text-sm">Created Jan 14, 2026 · Moderate risk · 8 holdings</p>
          </div>
          
          <div className="flex items-center space-x-3">
            <button className="sapient-btn-secondary flex items-center space-x-2 text-sm">
              <RefreshCw className="w-4 h-4" />
              <span>Sync with IBKR</span>
            </button>
            <button className="sapient-btn-primary flex items-center space-x-2 text-sm">
              <Zap className="w-4 h-4 fill-white" />
              <span>Execute via Broker</span>
            </button>
            <button className="sapient-btn-secondary px-2">
              <MoreVertical className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      {/* AI Trading Mode Switcher */}
      <section>
        <div className="sapient-card p-5 border border-indigo-500/20 bg-gradient-to-r from-slate-900/80 to-indigo-950/40 relative overflow-hidden">
          <div className="absolute top-0 right-0 -mr-20 -mt-20 w-64 h-64 bg-sky-500/10 rounded-full blur-3xl pointer-events-none"></div>
          
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 relative z-10">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-indigo-500/20 rounded-lg border border-indigo-500/30">
                <Sparkles className="w-5 h-5 text-indigo-400" />
              </div>
              <div>
                <h3 className="font-semibold text-white">AI Trading Mode</h3>
                <div className="flex items-center text-sm text-slate-400 mt-0.5 space-x-2">
                  <span>Sapient will propose buy/sell signals; you approve each one.</span>
                  <span className="sapient-badge border-amber-500/30 bg-amber-500/10 text-amber-400 cursor-pointer hover:bg-amber-500/20 transition-colors flex items-center space-x-1 py-0.5">
                    <span>3 pending in your inbox</span>
                    <ArrowRight className="w-3 h-3" />
                  </span>
                </div>
              </div>
            </div>
            
            <div className="flex bg-slate-950/60 p-1 rounded-xl border border-slate-800/60">
              <button 
                onClick={() => setAiMode('off')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  aiMode === 'off' 
                    ? 'bg-slate-800 text-white shadow-sm' 
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                Off
              </button>
              <button 
                onClick={() => setAiMode('suggestions')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  aiMode === 'suggestions' 
                    ? 'bg-gradient-to-r from-sky-500 to-indigo-500 text-white shadow-[0_0_15px_rgba(56,189,248,0.3)]' 
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                Suggestions
              </button>
              <button 
                onClick={() => setAiMode('autonomous')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  aiMode === 'autonomous' 
                    ? 'bg-gradient-to-r from-purple-500 to-fuchsia-500 text-white shadow-[0_0_15px_rgba(168,85,247,0.3)]' 
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                Autonomous
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Row */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="sapient-card sapient-card-hover p-5">
          <p className="text-sm text-slate-400 font-medium mb-1">Initial Investment</p>
          <p className="text-2xl font-bold text-white">A$50,000</p>
        </div>
        <div className="sapient-card sapient-card-hover p-5">
          <p className="text-sm text-slate-400 font-medium mb-1">Current Value</p>
          <p className="text-2xl font-bold text-white">A$58,247</p>
        </div>
        <div className="sapient-card sapient-card-hover p-5 border-emerald-500/20 bg-emerald-500/5 relative overflow-hidden">
          <div className="absolute right-0 top-0 w-24 h-24 bg-emerald-500/10 blur-2xl rounded-full"></div>
          <p className="text-sm text-slate-400 font-medium mb-1">Total Return</p>
          <div className="flex items-baseline space-x-2">
            <p className="text-2xl font-bold text-emerald-400">+A$8,247</p>
            <span className="text-sm font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full flex items-center">
              <TrendingUp className="w-3 h-3 mr-1" />
              16.49%
            </span>
          </div>
        </div>
        <div className="sapient-card sapient-card-hover p-5 border-sky-500/20 bg-sky-500/5 relative overflow-hidden">
          <div className="absolute right-0 top-0 w-24 h-24 bg-sky-500/10 blur-2xl rounded-full"></div>
          <p className="text-sm text-slate-400 font-medium mb-1 flex items-center">
            Sharpe Ratio
          </p>
          <p className="text-2xl font-bold text-sky-400">1.84</p>
        </div>
      </section>

      {/* Allocation & Broker Sync */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Col: Target vs Current Allocation */}
        <div className="lg:col-span-2 sapient-card p-6">
          <h2 className="text-lg font-semibold text-white mb-6">Target vs Current Allocation</h2>
          
          <div className="space-y-5">
            {positions.map((pos) => (
              <div key={pos.ticker} className="flex flex-col sm:flex-row sm:items-center gap-3">
                <div className="w-40 shrink-0">
                  <div className="font-medium text-slate-200">{pos.ticker}</div>
                  <div className="text-xs text-slate-500 truncate">{pos.name}</div>
                </div>
                
                <div className="flex-1 relative h-6 bg-slate-800/50 rounded-full overflow-hidden border border-slate-700/50">
                  {/* Target Bar */}
                  <div 
                    className="absolute top-0 left-0 h-1.5 bg-sky-500 rounded-full mt-1.5 opacity-40" 
                    style={{ width: `${pos.targetPct}%` }}
                  ></div>
                  {/* Current Bar */}
                  <div 
                    className="absolute top-0 left-0 h-1.5 bg-indigo-400 rounded-full mt-3" 
                    style={{ width: `${pos.currentPct}%` }}
                  ></div>
                </div>
                
                <div className="w-24 shrink-0 text-right flex flex-col items-end">
                  <span className="text-sm font-medium text-slate-300">{pos.targetPct}% target</span>
                  {Math.abs(pos.drift) > 2 ? (
                    <span className="text-xs text-amber-400 flex items-center mt-0.5">
                      <ShieldAlert className="w-3 h-3 mr-1" />
                      Drift {Math.abs(pos.drift).toFixed(1)}%
                    </span>
                  ) : (
                    <span className="text-xs text-slate-500 mt-0.5">
                      Current {pos.currentPct.toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Col: Pending Broker Sync */}
        <div className="sapient-card p-6 flex flex-col relative border-indigo-500/20">
          <div className="absolute top-0 right-0 -mr-16 -mt-16 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>
          
          <div className="flex items-center justify-between mb-6 relative z-10">
            <h2 className="text-lg font-semibold text-white">Pending Broker Sync</h2>
            <span className="sapient-badge border-indigo-500/30 bg-indigo-500/10 text-indigo-300 text-xs">
              AI Suggested
            </span>
          </div>

          <div className="flex-1 space-y-3 relative z-10">
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-3 flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <span className="sapient-badge border-emerald-500/30 bg-emerald-500/10 text-emerald-400 font-bold px-2 py-0.5">BUY</span>
                <div>
                  <div className="font-bold text-slate-200 text-sm">12 BHP.AX</div>
                  <div className="text-xs text-slate-400">@ market</div>
                </div>
              </div>
              <div className="text-right">
                <div className="font-medium text-slate-300 text-sm">est A$615.24</div>
              </div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-3 flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <span className="sapient-badge border-red-500/30 bg-red-500/10 text-red-400 font-bold px-2 py-0.5">SELL</span>
                <div>
                  <div className="font-bold text-slate-200 text-sm">4 CSL.AX</div>
                  <div className="text-xs text-slate-400">@ market</div>
                </div>
              </div>
              <div className="text-right">
                <div className="font-medium text-slate-300 text-sm">est A$1,124.80</div>
              </div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-3 flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <span className="sapient-badge border-emerald-500/30 bg-emerald-500/10 text-emerald-400 font-bold px-2 py-0.5">BUY</span>
                <div>
                  <div className="font-bold text-slate-200 text-sm">8 WBC.AX</div>
                  <div className="text-xs text-slate-400">@ limit A$30.10</div>
                </div>
              </div>
              <div className="text-right">
                <div className="font-medium text-slate-300 text-sm">est A$240.80</div>
              </div>
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-slate-800/80 relative z-10">
            <div className="flex justify-between items-end mb-4">
              <div>
                <p className="text-sm font-medium text-slate-300">Total est cost A$1,981</p>
                <p className="text-xs text-slate-500">Estimated fees A$8.85</p>
              </div>
            </div>
            <button className="sapient-btn-primary w-full justify-center">
              Execute 3 orders via IBKR
            </button>
          </div>
        </div>

      </section>

      {/* Positions Table */}
      <section className="sapient-card p-6 overflow-x-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Holdings</h2>
          <span className="text-xs font-medium text-slate-400 flex items-center">
            <RefreshCw className="w-3 h-3 mr-1.5 text-indigo-400" />
            Last broker sync 2m ago
          </span>
        </div>
        
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-slate-400 border-b border-slate-800/80">
            <tr>
              <th className="px-4 py-3 font-medium">Ticker</th>
              <th className="px-4 py-3 font-medium hidden sm:table-cell">Name</th>
              <th className="px-4 py-3 font-medium text-right">Shares</th>
              <th className="px-4 py-3 font-medium text-right">Avg Cost</th>
              <th className="px-4 py-3 font-medium text-right">Current Price</th>
              <th className="px-4 py-3 font-medium text-right">Market Value</th>
              <th className="px-4 py-3 font-medium text-right">Unrealized P/L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => (
              <tr key={pos.ticker} className="border-b border-slate-800/40 hover:bg-slate-800/20 transition-colors">
                <td className="px-4 py-3 font-medium text-slate-200">
                  <div className="flex items-center space-x-2">
                    {pos.ticker}
                    {pos.pendingBuy && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 ml-2" title="Pending Buy Order"></span>}
                    {pos.pendingSell && <span className="w-1.5 h-1.5 rounded-full bg-red-400 ml-2" title="Pending Sell Order"></span>}
                  </div>
                </td>
                <td className="px-4 py-3 text-slate-400 hidden sm:table-cell">{pos.name}</td>
                <td className="px-4 py-3 text-right text-slate-300">{pos.shares}</td>
                <td className="px-4 py-3 text-right text-slate-300">A${pos.avgCost.toFixed(2)}</td>
                <td className="px-4 py-3 text-right text-slate-300">A${pos.price.toFixed(2)}</td>
                <td className="px-4 py-3 text-right font-medium text-slate-200">A${pos.value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td className={`px-4 py-3 text-right font-medium ${pos.pl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {pos.pl >= 0 ? '+' : '-'}A${Math.abs(pos.pl).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} 
                  <span className="text-xs ml-1 opacity-80">({pos.plPct.toFixed(2)}%)</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

    </div>
  );
}
