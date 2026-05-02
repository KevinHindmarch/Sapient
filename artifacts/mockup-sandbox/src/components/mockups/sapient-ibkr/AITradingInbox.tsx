import React, { useState } from "react";
import { 
  ChevronRight, Send, X, Clock, CheckCircle2, 
  ChevronDown, Activity, TrendingUp, Target, 
  BrainCircuit, LineChart, ShieldAlert, BarChart2,
  PieChart, DollarSign
} from "lucide-react";
import "./_group.css";

export function AITradingInbox() {
  const [activeTab, setActiveTab] = useState("Pending");

  return (
    <div className="sapient-dark sapient-bg" style={{ minHeight: '100vh', fontFamily: "system-ui, -apple-system, sans-serif" }}>
      {/* Background Mesh */}
      <div className="fixed inset-0 pointer-events-none opacity-20" 
           style={{ 
             background: 'radial-gradient(circle at 15% 50%, rgba(168, 85, 247, 0.4), transparent 50%), radial-gradient(circle at 85% 30%, rgba(56, 189, 248, 0.4), transparent 50%)' 
           }}>
      </div>

      <div className="relative max-w-[1600px] mx-auto p-4 md:p-8 flex flex-col lg:flex-row gap-8 items-start">
        
        {/* Main Content Area */}
        <div className="flex-1 w-full space-y-6">
          
          {/* Header */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
            <div>
              <div className="flex items-center gap-2 text-sm text-slate-400 font-medium mb-3">
                <span>AI Trading</span>
                <ChevronRight className="w-4 h-4" />
                <span className="text-slate-200">Inbox</span>
              </div>
              <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-white mb-2">
                <span className="sapient-gradient-text">Pending Signals</span>
              </h1>
              <p className="text-slate-400 text-sm md:text-base">
                Sapient AI has proposed 3 trades based on your portfolio rules. Review and approve.
              </p>
            </div>

            {/* Tab Bar */}
            <div className="flex items-center gap-1 p-1 rounded-xl bg-slate-800/50 backdrop-blur-md border border-slate-700/50">
              {["Pending", "Approved", "Rejected", "All"].map(tab => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                    activeTab === tab 
                      ? "bg-slate-700/80 text-white shadow-sm" 
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                  }`}
                >
                  {tab === "Pending" ? "Pending (3 active)" : tab}
                </button>
              ))}
            </div>
          </div>

          {/* Filter / Status Row */}
          <div className="flex flex-wrap items-center gap-3 pt-2 pb-4 border-b border-slate-800/50">
            <button className="sapient-badge bg-slate-800/80 text-slate-200 border-slate-700/50 hover:border-slate-600 transition-colors">
              All Portfolios
            </button>
            <button className="sapient-badge bg-slate-800/40 text-slate-400 border-slate-800 hover:text-slate-300 transition-colors">
              ASX Growth Sharpe-Max
            </button>
            <button className="sapient-badge bg-slate-800/40 text-slate-400 border-slate-800 hover:text-slate-300 transition-colors">
              US Tech Momentum
            </button>
            
            <div className="ml-auto flex items-center gap-4 text-xs font-medium text-slate-400">
              <span className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> Avg approval time 14s</span>
              <span className="flex items-center gap-1.5"><Activity className="w-3.5 h-3.5" /> Auto-execute deadline: 16:00 AEST today</span>
            </div>
          </div>

          {/* Signal Cards */}
          <div className="space-y-4">
            
            {/* Card 1: BUY BHP */}
            <div className="sapient-card relative overflow-hidden group">
              <div className="absolute top-0 bottom-0 left-0 w-1.5 bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]"></div>
              
              {/* Top Row */}
              <div className="flex flex-wrap md:flex-nowrap justify-between items-start gap-4 mb-5">
                <div className="flex items-center gap-3">
                  <span className="sapient-badge bg-emerald-500/10 text-emerald-400 border-emerald-500/20 px-3 py-1 font-bold tracking-wide">
                    BUY
                  </span>
                  <div className="flex items-baseline gap-2">
                    <h3 className="text-xl font-bold text-white tracking-tight">BHP.AX</h3>
                    <span className="text-slate-400 font-medium">· BHP Group</span>
                  </div>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">ASX</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 font-medium flex items-center gap-1">
                    <Clock className="w-3 h-3" /> Generated 8 min ago
                  </span>
                  <div className="flex items-center gap-2 sapient-badge bg-sky-500/10 text-sky-400 border-sky-500/20">
                    <BrainCircuit className="w-3.5 h-3.5" />
                    <span>Confidence 82%</span>
                  </div>
                </div>
              </div>

              {/* Middle */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-12 mb-6">
                {/* Trade Plan */}
                <div className="space-y-3">
                  <h4 className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2">Trade plan</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <span className="block text-xs text-slate-500 mb-0.5">Quantity</span>
                      <span className="text-sm font-semibold text-slate-200">12 shares</span>
                    </div>
                    <div>
                      <span className="block text-xs text-slate-500 mb-0.5">Order Type</span>
                      <span className="text-sm font-semibold text-slate-200">Market</span>
                    </div>
                    <div>
                      <span className="block text-xs text-slate-500 mb-0.5">Estimated Cost</span>
                      <span className="text-sm font-semibold text-slate-200">~A$542.40</span>
                    </div>
                    <div>
                      <span className="block text-xs text-slate-500 mb-0.5">Estimated Fees</span>
                      <span className="text-sm font-semibold text-slate-200">A$5.00</span>
                    </div>
                  </div>
                  <div className="mt-4 pt-3 border-t border-slate-800/50 flex items-center justify-between">
                    <span className="text-xs text-slate-500 flex items-center gap-1.5">
                      <PieChart className="w-3.5 h-3.5" /> Target portfolio weight
                    </span>
                    <span className="text-sm font-medium text-slate-300">
                      8.2% <ArrowRightInline /> <span className="text-emerald-400">11.5%</span>
                    </span>
                  </div>
                </div>

                {/* Reasons */}
                <div>
                  <h4 className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-3">Why Sapient is proposing this</h4>
                  <ul className="space-y-3">
                    <li className="flex items-start gap-2.5 text-sm text-slate-300">
                      <BarChart2 className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
                      <span>
                        <span className="font-semibold text-white">RSI 28.4</span> (oversold, threshold 30)
                        <span className="ml-2 inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-sky-500/10 text-sky-400 border border-sky-500/20">TECHNICAL</span>
                      </span>
                    </li>
                    <li className="flex items-start gap-2.5 text-sm text-slate-300">
                      <TrendingUp className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
                      <span>
                        <span className="font-semibold text-white">MACD</span> bullish crossover on 4-hour chart
                      </span>
                    </li>
                    <li className="flex items-start gap-2.5 text-sm text-slate-300">
                      <Target className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
                      <span>
                        <span className="font-semibold text-white">Underweight</span> vs target by 3.3%
                        <span className="ml-2 inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">REBALANCING</span>
                      </span>
                    </li>
                  </ul>
                </div>
              </div>

              {/* Bottom Row */}
              <div className="flex flex-col sm:flex-row justify-between items-center gap-4 pt-4 border-t border-slate-800/50">
                <button className="text-xs text-sky-400 font-medium hover:text-sky-300 flex items-center gap-1 transition-colors">
                  Show technical chart <ChevronDown className="w-3.5 h-3.5" />
                </button>
                <div className="flex items-center gap-3 w-full sm:w-auto">
                  <button className="sapient-btn-secondary text-xs py-2 px-3">
                    Snooze 1h
                  </button>
                  <button className="border border-red-500/30 text-red-400 hover:bg-red-500/10 rounded-xl px-4 py-2 text-sm font-medium transition-colors">
                    Reject
                  </button>
                  <button className="sapient-btn-success flex items-center gap-2 py-2 text-sm flex-1 sm:flex-none justify-center">
                    Approve & send to IBKR <Send className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            {/* Card 2: SELL CSL */}
            <div className="sapient-card relative overflow-hidden group">
              <div className="absolute top-0 bottom-0 left-0 w-1.5 bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]"></div>
              
              <div className="flex flex-wrap md:flex-nowrap justify-between items-start gap-4 mb-5">
                <div className="flex items-center gap-3">
                  <span className="sapient-badge bg-red-500/10 text-red-400 border-red-500/20 px-3 py-1 font-bold tracking-wide">
                    SELL
                  </span>
                  <div className="flex items-baseline gap-2">
                    <h3 className="text-xl font-bold text-white tracking-tight">CSL.AX</h3>
                    <span className="text-slate-400 font-medium">· CSL Limited</span>
                  </div>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">ASX</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 font-medium flex items-center gap-1">
                    <Clock className="w-3 h-3" /> Generated 22 min ago
                  </span>
                  <div className="flex items-center gap-2 sapient-badge bg-sky-500/10 text-sky-400 border-sky-500/20">
                    <BrainCircuit className="w-3.5 h-3.5" />
                    <span>Confidence 76%</span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-12 mb-6">
                <div className="space-y-3">
                  <h4 className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2">Trade plan</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <span className="block text-xs text-slate-500 mb-0.5">Quantity</span>
                      <span className="text-sm font-semibold text-slate-200">4 shares</span>
                    </div>
                    <div>
                      <span className="block text-xs text-slate-500 mb-0.5">Order Type</span>
                      <span className="text-sm font-semibold text-slate-200">Market</span>
                    </div>
                    <div>
                      <span className="block text-xs text-slate-500 mb-0.5">Estimated Value</span>
                      <span className="text-sm font-semibold text-slate-200">~A$1,148.20</span>
                    </div>
                    <div>
                      <span className="block text-xs text-slate-500 mb-0.5">Estimated Fees</span>
                      <span className="text-sm font-semibold text-slate-200">A$5.00</span>
                    </div>
                  </div>
                  <div className="mt-4 pt-3 border-t border-slate-800/50 flex items-center justify-between">
                    <span className="text-xs text-slate-500 flex items-center gap-1.5">
                      <PieChart className="w-3.5 h-3.5" /> Target portfolio weight
                    </span>
                    <span className="text-sm font-medium text-slate-300">
                      12.8% <ArrowRightInline /> <span className="text-red-400">10.5%</span>
                    </span>
                  </div>
                </div>

                <div>
                  <h4 className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-3">Why Sapient is proposing this</h4>
                  <ul className="space-y-3">
                    <li className="flex items-start gap-2.5 text-sm text-slate-300">
                      <LineChart className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
                      <span>
                        <span className="font-semibold text-white">RSI 71.2</span> (overbought)
                      </span>
                    </li>
                    <li className="flex items-start gap-2.5 text-sm text-slate-300">
                      <Target className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
                      <span>
                        <span className="font-semibold text-white">Target weight</span> reached
                      </span>
                    </li>
                    <li className="flex items-start gap-2.5 text-sm text-slate-300">
                      <DollarSign className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                      <span>
                        Locking in <span className="font-semibold text-emerald-400">+12.4% gain</span>
                        <span className="ml-2 inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">PROFIT TAKER</span>
                      </span>
                    </li>
                  </ul>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row justify-between items-center gap-4 pt-4 border-t border-slate-800/50">
                <button className="text-xs text-sky-400 font-medium hover:text-sky-300 flex items-center gap-1 transition-colors">
                  Show technical chart <ChevronDown className="w-3.5 h-3.5" />
                </button>
                <div className="flex items-center gap-3 w-full sm:w-auto">
                  <button className="sapient-btn-secondary text-xs py-2 px-3">
                    Snooze 1h
                  </button>
                  <button className="border border-red-500/30 text-red-400 hover:bg-red-500/10 rounded-xl px-4 py-2 text-sm font-medium transition-colors">
                    Reject
                  </button>
                  <button className="sapient-btn-success flex items-center gap-2 py-2 text-sm flex-1 sm:flex-none justify-center">
                    Approve & send to IBKR <Send className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            {/* Card 3: BUY NVDA */}
            <div className="sapient-card relative overflow-hidden group">
              <div className="absolute top-0 bottom-0 left-0 w-1.5 bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]"></div>
              
              <div className="flex flex-wrap md:flex-nowrap justify-between items-start gap-4 mb-5">
                <div className="flex items-center gap-3">
                  <span className="sapient-badge bg-emerald-500/10 text-emerald-400 border-emerald-500/20 px-3 py-1 font-bold tracking-wide">
                    BUY
                  </span>
                  <div className="flex items-baseline gap-2">
                    <h3 className="text-xl font-bold text-white tracking-tight">NVDA</h3>
                    <span className="text-slate-400 font-medium">· NVIDIA Corp</span>
                  </div>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">NASDAQ</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 font-medium flex items-center gap-1">
                    <Clock className="w-3 h-3" /> Generated 45 min ago
                  </span>
                  <div className="flex items-center gap-2 sapient-badge bg-sky-500/10 text-sky-400 border-sky-500/20">
                    <BrainCircuit className="w-3.5 h-3.5" />
                    <span>Confidence 89%</span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-12 mb-6">
                <div className="space-y-3">
                  <h4 className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2">Trade plan</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <span className="block text-xs text-slate-500 mb-0.5">Quantity</span>
                      <span className="text-sm font-semibold text-slate-200">25 shares</span>
                    </div>
                    <div>
                      <span className="block text-xs text-slate-500 mb-0.5">Order Type</span>
                      <span className="text-sm font-semibold text-slate-200">Limit @ US$118.50</span>
                    </div>
                    <div>
                      <span className="block text-xs text-slate-500 mb-0.5">Estimated Cost</span>
                      <span className="text-sm font-semibold text-slate-200">~US$2,962.50</span>
                    </div>
                    <div>
                      <span className="block text-xs text-slate-500 mb-0.5">Estimated Fees</span>
                      <span className="text-sm font-semibold text-slate-200">US$0.35</span>
                    </div>
                  </div>
                  <div className="mt-4 pt-3 border-t border-slate-800/50 flex items-center justify-between">
                    <span className="text-xs text-slate-500 flex items-center gap-1.5">
                      <PieChart className="w-3.5 h-3.5" /> Target portfolio weight
                    </span>
                    <span className="text-sm font-medium text-slate-300">
                      0.0% <ArrowRightInline /> <span className="text-emerald-400">4.5%</span>
                    </span>
                  </div>
                </div>

                <div>
                  <h4 className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-3">Why Sapient is proposing this</h4>
                  <ul className="space-y-3">
                    <li className="flex items-start gap-2.5 text-sm text-slate-300">
                      <TrendingUp className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
                      <span>
                        <span className="font-semibold text-white">MACD crossover</span> on daily
                        <span className="ml-2 inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-sky-500/10 text-sky-400 border border-sky-500/20">TECHNICAL</span>
                      </span>
                    </li>
                    <li className="flex items-start gap-2.5 text-sm text-slate-300">
                      <Activity className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
                      <span>
                        <span className="font-semibold text-white">Sector rotation</span> signal detected for Semiconductors
                      </span>
                    </li>
                    <li className="flex items-start gap-2.5 text-sm text-slate-300">
                      <Target className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
                      <span>
                        <span className="font-semibold text-white">Allocation room</span> +A$3,400 available in US Tech Momentum
                      </span>
                    </li>
                  </ul>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row justify-between items-center gap-4 pt-4 border-t border-slate-800/50">
                <button className="text-xs text-sky-400 font-medium hover:text-sky-300 flex items-center gap-1 transition-colors">
                  Show technical chart <ChevronDown className="w-3.5 h-3.5" />
                </button>
                <div className="flex items-center gap-3 w-full sm:w-auto">
                  <button className="sapient-btn-secondary text-xs py-2 px-3">
                    Snooze 1h
                  </button>
                  <button className="border border-red-500/30 text-red-400 hover:bg-red-500/10 rounded-xl px-4 py-2 text-sm font-medium transition-colors">
                    Reject
                  </button>
                  <button className="sapient-btn-success flex items-center gap-2 py-2 text-sm flex-1 sm:flex-none justify-center">
                    Approve & send to IBKR <Send className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

          </div>
        </div>

        {/* Right Rail - Recent Activity */}
        <div className="w-full lg:w-72 shrink-0 space-y-4">
          <div className="sapient-card p-5">
            <h3 className="text-sm font-semibold text-white uppercase tracking-wider mb-5">Recent activity</h3>
            
            <div className="relative border-l border-slate-800 ml-3 space-y-6">
              
              <div className="relative pl-6">
                <div className="absolute -left-[11px] top-1 bg-slate-900 border border-emerald-500/50 rounded-full p-1">
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                </div>
                <p className="text-sm text-slate-300 leading-snug">
                  Approved <span className="font-medium text-emerald-400">BUY 50 WBC.AX</span>
                </p>
                <span className="text-xs text-slate-500 mt-1 block">09:42</span>
              </div>

              <div className="relative pl-6">
                <div className="absolute -left-[11px] top-1 bg-slate-900 border border-red-500/50 rounded-full p-1">
                  <X className="w-3 h-3 text-red-400" />
                </div>
                <p className="text-sm text-slate-300 leading-snug">
                  Rejected <span className="font-medium text-red-400">SELL 10 CBA.AX</span>
                </p>
                <span className="text-xs text-slate-500 mt-1 block">09:11</span>
              </div>

              <div className="relative pl-6">
                <div className="absolute -left-[11px] top-1 bg-slate-900 border border-sky-500/50 rounded-full p-1">
                  <BrainCircuit className="w-3 h-3 text-sky-400" />
                </div>
                <p className="text-sm text-slate-300 leading-snug">
                  Auto-executed <span className="font-medium text-emerald-400">BUY 8 WES.AX</span>
                </p>
                <span className="text-xs text-slate-500 mt-1 block">08:30</span>
              </div>

              <div className="relative pl-6">
                <div className="absolute -left-[11px] top-1 bg-slate-900 border border-slate-600 rounded-full p-1">
                  <Clock className="w-3 h-3 text-slate-400" />
                </div>
                <p className="text-sm text-slate-400 leading-snug">
                  Signal expired <span className="font-medium text-emerald-400/50">BUY MQG.AX</span>
                </p>
                <span className="text-xs text-slate-600 mt-1 block">Yesterday</span>
              </div>

              <div className="relative pl-6">
                <div className="absolute -left-[11px] top-1 bg-slate-900 border border-emerald-500/50 rounded-full p-1">
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                </div>
                <p className="text-sm text-slate-300 leading-snug">
                  Approved <span className="font-medium text-red-400">SELL 15 RIO.AX</span>
                </p>
                <span className="text-xs text-slate-500 mt-1 block">Yesterday</span>
              </div>

              <div className="relative pl-6">
                <div className="absolute -left-[11px] top-1 bg-slate-900 border border-sky-500/50 rounded-full p-1">
                  <BrainCircuit className="w-3 h-3 text-sky-400" />
                </div>
                <p className="text-sm text-slate-300 leading-snug">
                  Auto-executed <span className="font-medium text-emerald-400">BUY 100 TLS.AX</span>
                </p>
                <span className="text-xs text-slate-500 mt-1 block">Yesterday</span>
              </div>
            </div>
            
            <button className="w-full mt-5 py-2 text-xs font-medium text-sky-400 hover:text-sky-300 hover:bg-sky-500/10 rounded-lg transition-colors border border-transparent hover:border-sky-500/20">
              View all history
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ArrowRightInline() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="inline mx-1 text-slate-600">
      <path d="M5 12h14"></path>
      <path d="m12 5 7 7-7 7"></path>
    </svg>
  );
}
