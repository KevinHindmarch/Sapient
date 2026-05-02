import React, { useState } from "react";
import { 
  Shield, 
  Power, 
  Lightbulb, 
  Bot, 
  AlertOctagon, 
  ChevronRight, 
  Settings, 
  Info 
} from "lucide-react";
import "./_group.css";

export function AITradingSettings() {
  const [tradingMode, setTradingMode] = useState<"off" | "suggestions" | "autonomous">("suggestions");
  const [rsiBuy, setRsiBuy] = useState(30);
  const [rsiSell, setRsiSell] = useState(70);
  const [requireMacd, setRequireMacd] = useState(true);
  const [requireVolume, setRequireVolume] = useState(false);

  const [haltDrawdown, setHaltDrawdown] = useState(true);
  const [pauseVolatility, setPauseVolatility] = useState(true);
  const [pauseLosing, setPauseLosing] = useState(false);

  return (
    <div className="sapient-dark sapient-bg font-sans" style={{ minHeight: '100vh' }}>
      <div className="max-w-5xl mx-auto p-6 md:p-10 space-y-8">
        
        {/* Page Header */}
        <div className="space-y-4">
          <div className="flex items-center text-sm text-slate-400 font-medium space-x-2">
            <Settings className="w-4 h-4" />
            <span>Settings</span>
            <ChevronRight className="w-4 h-4 opacity-50" />
            <span className="sapient-gradient-text">AI Trading</span>
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-slate-100">AI Trading</h1>
            <p className="text-slate-400 mt-2">
              Configure how Sapient's AI engine proposes and executes trades on your behalf.
            </p>
          </div>
        </div>

        {/* Warning Banner */}
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 flex items-start gap-4 backdrop-blur-md">
          <div className="bg-amber-500/20 p-2 rounded-full shrink-0">
            <Shield className="w-5 h-5 text-amber-400" />
          </div>
          <div className="flex-1">
            <p className="text-amber-200 font-medium">
              Paper-trading required for the first 7 days <span className="opacity-50 mx-1">·</span> 4 days remaining before live trading unlocks.
            </p>
            <a href="#" className="text-amber-400 text-sm hover:underline mt-1 inline-block">Why?</a>
          </div>
        </div>

        {/* Section 1 — Trading Mode */}
        <section className="sapient-card space-y-6">
          <div>
            <h2 className="text-xl font-semibold text-slate-100">Trading Mode</h2>
            <p className="text-sm text-slate-400 mt-1">Select the level of autonomy for the AI engine.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Off */}
            <button 
              onClick={() => setTradingMode("off")}
              className={`relative p-5 rounded-xl border text-left transition-all ${
                tradingMode === "off" 
                  ? "bg-slate-800/80 border-slate-500 shadow-[0_0_15px_rgba(100,116,139,0.2)]" 
                  : "bg-slate-900/50 border-slate-700/50 hover:bg-slate-800/50"
              }`}
            >
              <div className={`p-2.5 rounded-lg inline-block mb-4 ${tradingMode === "off" ? "bg-slate-700" : "bg-slate-800"}`}>
                <Power className={`w-6 h-6 ${tradingMode === "off" ? "text-slate-200" : "text-slate-400"}`} />
              </div>
              <h3 className={`font-semibold text-lg ${tradingMode === "off" ? "text-slate-100" : "text-slate-300"}`}>Off</h3>
              <p className="text-sm text-slate-400 mt-2">AI signals are disabled. You build portfolios manually.</p>
            </button>

            {/* Suggestions */}
            <button 
              onClick={() => setTradingMode("suggestions")}
              className={`relative p-5 rounded-xl border text-left transition-all ${
                tradingMode === "suggestions" 
                  ? "bg-slate-800/80 border-sky-400 shadow-[0_0_20px_rgba(56,189,248,0.2)] ring-1 ring-sky-400/50" 
                  : "bg-slate-900/50 border-slate-700/50 hover:bg-slate-800/50 hover:border-sky-500/30"
              }`}
            >
              <div className={`p-2.5 rounded-lg inline-block mb-4 ${tradingMode === "suggestions" ? "bg-sky-500/20" : "bg-slate-800"}`}>
                <Lightbulb className={`w-6 h-6 ${tradingMode === "suggestions" ? "text-sky-400" : "text-slate-400"}`} />
              </div>
              <h3 className={`font-semibold text-lg ${tradingMode === "suggestions" ? "text-sky-100" : "text-slate-300"}`}>Suggestions</h3>
              <p className="text-sm text-slate-400 mt-2">AI proposes trades. You approve each one in the inbox before execution.</p>
            </button>

            {/* Autonomous */}
            <button 
              onClick={() => setTradingMode("autonomous")}
              className={`relative p-5 rounded-xl border text-left transition-all ${
                tradingMode === "autonomous" 
                  ? "bg-slate-800/80 border-purple-500 shadow-[0_0_20px_rgba(168,85,247,0.2)] ring-1 ring-purple-500/50" 
                  : "bg-slate-900/50 border-slate-700/50 hover:bg-slate-800/50 hover:border-purple-500/30"
              }`}
            >
              <div className="absolute top-4 right-4 sapient-badge bg-purple-500/20 text-purple-300 border-purple-500/30">
                Live only
              </div>
              <div className={`p-2.5 rounded-lg inline-block mb-4 ${tradingMode === "autonomous" ? "bg-purple-500/20" : "bg-slate-800"}`}>
                <Bot className={`w-6 h-6 ${tradingMode === "autonomous" ? "text-purple-400" : "text-slate-400"}`} />
              </div>
              <h3 className={`font-semibold text-lg ${tradingMode === "autonomous" ? "text-purple-100" : "text-slate-300"}`}>Autonomous</h3>
              <p className="text-sm text-slate-400 mt-2">AI executes approved-rule trades automatically through IBKR. Use with caution.</p>
            </button>
          </div>
        </section>

        {/* Section 2 — Signal Thresholds */}
        <section className="sapient-card space-y-8">
          <div>
            <h2 className="text-xl font-semibold text-slate-100">Signal Thresholds</h2>
            <p className="text-sm text-slate-400 mt-1">Adjust the technical indicator sensitivities used by the AI.</p>
          </div>
          
          <div className="space-y-6">
            {/* RSI Buy Slider */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="text-sm font-medium text-slate-300">RSI buy threshold</label>
                <span className="text-sm font-bold text-sky-400">{rsiBuy}</span>
              </div>
              <input 
                type="range" 
                min="0" max="50" 
                value={rsiBuy} 
                onChange={(e) => setRsiBuy(Number(e.target.value))}
                className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-sky-400 focus:outline-none"
                style={{ accentColor: '#38bdf8' }}
              />
              <p className="text-xs text-slate-500 mt-2">Trigger BUY when RSI drops below this value.</p>
            </div>

            {/* RSI Sell Slider */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="text-sm font-medium text-slate-300">RSI sell threshold</label>
                <span className="text-sm font-bold text-red-400">{rsiSell}</span>
              </div>
              <input 
                type="range" 
                min="50" max="100" 
                value={rsiSell} 
                onChange={(e) => setRsiSell(Number(e.target.value))}
                className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-red-400 focus:outline-none"
                style={{ accentColor: '#f87171' }}
              />
              <p className="text-xs text-slate-500 mt-2">Trigger SELL when RSI rises above this value.</p>
            </div>
          </div>

          <div className="flex flex-col md:flex-row gap-6 pt-4 border-t border-slate-700/50">
            <label className="flex items-center gap-3 cursor-pointer group">
              <div className={`w-10 h-5 flex items-center rounded-full p-1 transition-colors ${requireMacd ? 'bg-sky-500' : 'bg-slate-700'}`}>
                <div className={`bg-white w-3.5 h-3.5 rounded-full shadow-md transform transition-transform ${requireMacd ? 'translate-x-5' : ''}`} />
              </div>
              <input type="checkbox" className="hidden" checked={requireMacd} onChange={() => setRequireMacd(!requireMacd)} />
              <span className="text-sm font-medium text-slate-300 group-hover:text-slate-200">Require MACD confirmation</span>
            </label>

            <label className="flex items-center gap-3 cursor-pointer group">
              <div className={`w-10 h-5 flex items-center rounded-full p-1 transition-colors ${requireVolume ? 'bg-sky-500' : 'bg-slate-700'}`}>
                <div className={`bg-white w-3.5 h-3.5 rounded-full shadow-md transform transition-transform ${requireVolume ? 'translate-x-5' : ''}`} />
              </div>
              <input type="checkbox" className="hidden" checked={requireVolume} onChange={() => setRequireVolume(!requireVolume)} />
              <span className="text-sm font-medium text-slate-300 group-hover:text-slate-200">Require volume confirmation</span>
            </label>
          </div>
        </section>

        {/* Section 3 — Risk Guardrails */}
        <section className="sapient-card space-y-6">
          <div>
            <h2 className="text-xl font-semibold text-slate-100">Risk Guardrails</h2>
            <p className="text-sm text-slate-400 mt-1">Hard limits on portfolio exposure and trade frequency.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Max trade size</label>
              <input type="text" defaultValue="5%" className="sapient-input" />
              <p className="text-xs text-slate-500 mt-1.5">of portfolio value per single trade</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Max daily trades</label>
              <input type="text" defaultValue="8" className="sapient-input" />
              <p className="text-xs text-slate-500 mt-1.5">across all portfolios</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Max daily turnover</label>
              <input type="text" defaultValue="20%" className="sapient-input" />
              <p className="text-xs text-slate-500 mt-1.5">of portfolio NAV per day</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Sector cap</label>
              <input type="text" defaultValue="35%" className="sapient-input" />
              <p className="text-xs text-slate-500 mt-1.5">max single GICS sector weight</p>
            </div>
          </div>
        </section>

        {/* Section 4 — Circuit Breakers */}
        <section className="sapient-card space-y-6">
          <div>
            <h2 className="text-xl font-semibold text-slate-100">Circuit Breakers</h2>
            <p className="text-sm text-slate-400 mt-1">Automatic pause conditions based on market and portfolio events.</p>
          </div>

          <div className="space-y-4">
            {/* Breaker 1 */}
            <div className="flex items-center justify-between p-4 rounded-xl bg-slate-800/30 border border-slate-700/50">
              <div>
                <h4 className="text-slate-200 font-medium text-sm">Halt trading on -3% daily portfolio drawdown</h4>
                <p className="text-slate-500 text-xs mt-1">Pauses all AI trading for the remainder of the trading day.</p>
              </div>
              <label className="flex items-center cursor-pointer">
                <div className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors ${haltDrawdown ? 'bg-sky-500' : 'bg-slate-700'}`}>
                  <div className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${haltDrawdown ? 'translate-x-5' : ''}`} />
                </div>
                <input type="checkbox" className="hidden" checked={haltDrawdown} onChange={() => setHaltDrawdown(!haltDrawdown)} />
              </label>
            </div>

            {/* Breaker 2 */}
            <div className="flex items-center justify-between p-4 rounded-xl bg-slate-800/30 border border-slate-700/50">
              <div>
                <h4 className="text-slate-200 font-medium text-sm">Pause new signals during ASX market open volatility</h4>
                <p className="text-slate-500 text-xs mt-1">Ignores signals generated in the first 15 minutes of trading.</p>
              </div>
              <label className="flex items-center cursor-pointer">
                <div className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors ${pauseVolatility ? 'bg-sky-500' : 'bg-slate-700'}`}>
                  <div className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${pauseVolatility ? 'translate-x-5' : ''}`} />
                </div>
                <input type="checkbox" className="hidden" checked={pauseVolatility} onChange={() => setPauseVolatility(!pauseVolatility)} />
              </label>
            </div>

            {/* Breaker 3 */}
            <div className="flex items-center justify-between p-4 rounded-xl bg-slate-800/30 border border-slate-700/50">
              <div>
                <h4 className="text-slate-200 font-medium text-sm">Auto-pause after 3 consecutive losing trades</h4>
                <p className="text-slate-500 text-xs mt-1">Requires manual re-activation if a losing streak occurs.</p>
              </div>
              <label className="flex items-center cursor-pointer">
                <div className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors ${pauseLosing ? 'bg-sky-500' : 'bg-slate-700'}`}>
                  <div className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${pauseLosing ? 'translate-x-5' : ''}`} />
                </div>
                <input type="checkbox" className="hidden" checked={pauseLosing} onChange={() => setPauseLosing(!pauseLosing)} />
              </label>
            </div>
          </div>
        </section>

        {/* Section 5 — Kill Switch */}
        <section className="bg-slate-900/80 border border-red-500/30 rounded-2xl p-8 backdrop-blur-xl relative overflow-hidden">
          {/* Subtle red glow effect behind */}
          <div className="absolute top-0 right-0 w-64 h-64 bg-red-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/4 pointer-events-none" />
          
          <div className="relative z-10 flex flex-col md:flex-row md:items-center gap-8">
            <div className="bg-red-500/10 p-5 rounded-2xl border border-red-500/20 shrink-0">
              <AlertOctagon className="w-12 h-12 text-red-500" />
            </div>
            
            <div className="flex-1">
              <h2 className="text-2xl font-bold text-slate-100">Emergency Kill Switch</h2>
              <p className="text-slate-400 mt-2 max-w-xl text-sm leading-relaxed">
                Immediately cancel all open AI orders and disable AI trading across every portfolio. Manual trading remains available.
              </p>
            </div>

            <div className="shrink-0 flex flex-col items-start md:items-end">
              <div className="flex items-center gap-3">
                <span className="text-xs text-slate-500 font-medium">Last triggered: never</span>
                <button className="sapient-btn-danger whitespace-nowrap text-sm px-6 py-3 font-semibold uppercase tracking-wide">
                  Pause AI trading now
                </button>
              </div>
              <p className="text-xs text-slate-500 mt-3 max-w-[250px] md:text-right">
                Requires re-enabling from this page after you pause. Existing positions will not be liquidated.
              </p>
            </div>
          </div>
        </section>

        {/* Footer Actions */}
        <div className="flex justify-between items-center pt-6 pb-12">
          <button className="text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors">
            Reset to defaults
          </button>
          <button className="sapient-btn-primary">
            Save changes
          </button>
        </div>

      </div>
    </div>
  );
}
