import React, { useState } from "react";
import {
  ExternalLink,
  Lock,
  RefreshCw,
  AlertTriangle,
  ChevronRight,
  Settings,
  Activity,
  Bell,
  ShieldCheck,
  CheckCircle2,
  Check
} from "lucide-react";
import "./_group.css";

export function BrokerageSettings() {
  const [selectedEnv, setSelectedEnv] = useState<"paper" | "live">("paper");

  return (
    <div className="sapient-dark sapient-bg font-sans" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header Chrome */}
      <header className="border-b border-white/10 bg-slate-900/50 backdrop-blur-md sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-sky-400 to-indigo-600 flex items-center justify-center shadow-lg shadow-sky-500/20">
              <span className="text-white font-bold text-lg leading-none tracking-tighter">S</span>
            </div>
            <nav className="flex items-center text-sm font-medium text-slate-400">
              <span className="hover:text-slate-200 cursor-pointer transition-colors">Settings</span>
              <ChevronRight className="w-4 h-4 mx-2 text-slate-600" />
              <span className="text-slate-200">Brokerage</span>
            </nav>
          </div>
        </div>
      </header>

      <div className="flex-1 max-w-6xl mx-auto w-full px-6 py-8 flex flex-col md:flex-row gap-10">
        {/* Left Mini-nav */}
        <aside className="w-full md:w-56 shrink-0 hidden md:block">
          <nav className="flex flex-col gap-1 sticky top-24">
            <a href="#" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 transition-all">
              <Settings className="w-4 h-4" />
              General
            </a>
            <a href="#" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-sky-400 bg-sky-500/10 border border-sky-500/20 shadow-[0_0_15px_rgba(56,189,248,0.1)]">
              <ShieldCheck className="w-4 h-4" />
              Brokerage
            </a>
            <a href="#" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 transition-all">
              <Activity className="w-4 h-4" />
              AI Trading
            </a>
            <a href="#" className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 transition-all">
              <Bell className="w-4 h-4" />
              Notifications
            </a>
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 max-w-3xl space-y-10">
          <div>
            <h1 className="text-3xl font-bold text-white tracking-tight">Brokerage</h1>
            <p className="text-slate-400 mt-2 text-base">Bring your own Interactive Brokers API keys to enable real-money execution.</p>
          </div>

          {/* STATE 1: NOT CONNECTED */}
          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-white/90">Setup Connection</h2>
            
            <div className="sapient-card space-y-8">
              {/* Step 1 */}
              <div className="flex gap-4">
                <div className="shrink-0 w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-sm font-semibold text-slate-300">1</div>
                <div className="flex-1 space-y-3">
                  <div>
                    <h3 className="text-base font-medium text-slate-200">Generate API credentials in IBKR Client Portal</h3>
                    <p className="text-sm text-slate-400 mt-1">
                      Log in to your Interactive Brokers account to create an OAuth Consumer Key and upload an RSA public key.
                    </p>
                  </div>
                  <button className="sapient-btn-secondary text-sm py-2 px-4 inline-flex items-center gap-2">
                    Open IBKR Client Portal
                    <ExternalLink className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Step 2 */}
              <div className="flex gap-4">
                <div className="shrink-0 w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-sm font-semibold text-slate-300">2</div>
                <div className="flex-1 space-y-3">
                  <div>
                    <h3 className="text-base font-medium text-slate-200">Paste your Consumer Key</h3>
                    <p className="text-sm text-slate-400 mt-1">This is the alphanumeric string generated in step 1.</p>
                  </div>
                  <input 
                    type="text" 
                    placeholder="e.g. YOUR_CONSUMER_KEY_12345" 
                    className="sapient-input font-mono text-sm"
                  />
                </div>
              </div>

              {/* Step 3 */}
              <div className="flex gap-4">
                <div className="shrink-0 w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-sm font-semibold text-slate-300">3</div>
                <div className="flex-1 space-y-3">
                  <div>
                    <h3 className="text-base font-medium text-slate-200">Paste your RSA private key (.pem)</h3>
                    <p className="text-sm text-slate-400 mt-1">Paste the exact contents of your generated .pem file.</p>
                  </div>
                  <textarea 
                    rows={6}
                    placeholder="-----BEGIN RSA PRIVATE KEY-----&#10;...&#10;-----END RSA PRIVATE KEY-----" 
                    className="sapient-input font-mono text-sm resize-y"
                  />
                  <div className="flex items-center gap-2 text-xs font-medium text-emerald-400/90">
                    <Lock className="w-3.5 h-3.5" />
                    <span>Encrypted at rest with AES-256. Never leaves your account.</span>
                  </div>
                </div>
              </div>

              {/* Step 4 */}
              <div className="flex gap-4">
                <div className="shrink-0 w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-sm font-semibold text-slate-300">4</div>
                <div className="flex-1 space-y-3">
                  <div>
                    <h3 className="text-base font-medium text-slate-200">Choose environment</h3>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <button 
                      onClick={() => setSelectedEnv("paper")}
                      className={`text-left p-4 rounded-xl border transition-all duration-200 ${
                        selectedEnv === "paper" 
                          ? 'bg-sky-500/10 border-sky-500/50 shadow-[0_0_15px_rgba(56,189,248,0.1)]' 
                          : 'bg-slate-800/40 border-slate-700/50 hover:bg-slate-800/80 hover:border-slate-600'
                      }`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <span className={`font-medium ${selectedEnv === "paper" ? 'text-sky-400' : 'text-slate-300'}`}>Paper trading</span>
                        <span className="sapient-badge bg-sky-500/20 text-sky-300 border-sky-500/30">Sandbox</span>
                      </div>
                      <p className="text-xs text-slate-400">Recommended for first 7 days to test optimization strategies.</p>
                    </button>

                    <button 
                      onClick={() => setSelectedEnv("live")}
                      className={`text-left p-4 rounded-xl border transition-all duration-200 ${
                        selectedEnv === "live" 
                          ? 'bg-amber-500/10 border-amber-500/50 shadow-[0_0_15px_rgba(245,158,11,0.1)]' 
                          : 'bg-slate-800/40 border-slate-700/50 hover:bg-slate-800/80 hover:border-slate-600'
                      }`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <span className={`font-medium ${selectedEnv === "live" ? 'text-amber-400' : 'text-slate-300'}`}>Live trading</span>
                        <span className="sapient-badge bg-amber-500/20 text-amber-300 border-amber-500/30 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" />
                          Real Money
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">Execute real trades with your own capital.</p>
                    </button>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="pt-6 mt-4 border-t border-white/5 flex flex-col sm:flex-row items-center gap-4">
                <button className="sapient-btn-primary w-full sm:w-auto px-8 py-3">
                  Connect to IBKR
                </button>
                <button className="sapient-btn-secondary w-full sm:w-auto px-6 py-3 border-transparent hover:border-slate-700 bg-transparent hover:bg-slate-800/50">
                  Test connection
                </button>
              </div>
            </div>
          </section>

          {/* Divider */}
          <div className="flex items-center gap-4 py-4">
            <div className="h-px bg-slate-800 flex-1"></div>
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-widest">Once connected you'll see:</span>
            <div className="h-px bg-slate-800 flex-1"></div>
          </div>

          {/* STATE 2: CONNECTED ACCOUNT SUMMARY */}
          <section className="sapient-card p-0 overflow-hidden">
            {/* Header row */}
            <div className="p-6 border-b border-white/5 bg-slate-800/30 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-white flex items-center justify-center shadow-md">
                  <span className="text-red-600 font-bold text-[10px] tracking-tight">IBKR</span>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-slate-200">U1234567 · Paper</h3>
                    <span className="sapient-badge bg-emerald-500/10 text-emerald-400 border-emerald-500/20 py-0.5 px-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 animate-pulse"></div>
                      Connected
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <p className="text-xs text-slate-400">Synced 2 min ago</p>
                    <button className="text-slate-500 hover:text-slate-300 transition-colors" title="Refresh data">
                      <RefreshCw className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Metrics grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/5">
              <div className="bg-[#0f172a]/95 p-5 flex flex-col justify-center">
                <span className="text-xs font-medium text-slate-400 mb-1">Cash Balance</span>
                <span className="text-lg font-bold text-slate-100">A$25,430.18</span>
              </div>
              <div className="bg-[#0f172a]/95 p-5 flex flex-col justify-center">
                <span className="text-xs font-medium text-slate-400 mb-1">Buying Power</span>
                <span className="text-lg font-bold text-slate-100">A$50,860.36</span>
              </div>
              <div className="bg-[#0f172a]/95 p-5 flex flex-col justify-center">
                <span className="text-xs font-medium text-slate-400 mb-1">Net Liquidation</span>
                <span className="text-lg font-bold text-slate-100">A$87,452.10</span>
              </div>
              <div className="bg-[#0f172a]/95 p-5 flex flex-col justify-center relative overflow-hidden group">
                <div className="absolute inset-0 bg-emerald-500/5 opacity-0 group-hover:opacity-100 transition-opacity"></div>
                <span className="text-xs font-medium text-slate-400 mb-1 relative z-10">Open P/L</span>
                <span className="text-lg font-bold text-emerald-400 relative z-10" style={{ textShadow: '0 0 10px rgba(52, 211, 153, 0.2)' }}>
                  +A$2,341.55
                </span>
              </div>
            </div>

            {/* Permissions row */}
            <div className="px-6 py-4 border-t border-white/5 bg-slate-800/10 flex flex-wrap items-center gap-3">
              <span className="text-xs font-medium text-slate-500">API Permissions:</span>
              <div className="flex flex-wrap gap-2">
                {["Read Positions", "Read Orders", "Place Orders", "Cancel Orders"].map((perm) => (
                  <span key={perm} className="sapient-badge bg-slate-800/60 text-slate-300 border-slate-700/50 py-0.5 px-2.5 flex items-center gap-1">
                    <Check className="w-3 h-3 text-sky-400" />
                    {perm}
                  </span>
                ))}
              </div>
            </div>

            {/* Footer */}
            <div className="p-6 border-t border-white/5 bg-slate-800/30 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <p className="text-xs text-amber-400/80 bg-amber-500/5 py-1.5 px-3 rounded-lg border border-amber-500/10">
                <AlertTriangle className="w-3.5 h-3.5 inline-block mr-1.5 relative -top-0.5" />
                Paper trading until April 28, 2026 — then live trading unlocks automatically.
              </p>
              <button className="text-xs font-medium text-red-400/70 hover:text-red-400 transition-colors">
                Disconnect IBKR
              </button>
            </div>
          </section>

        </main>
      </div>
    </div>
  );
}
