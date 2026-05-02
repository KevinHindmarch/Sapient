import { useEffect, useState, ReactNode } from 'react'
import { aiApi, AISettingsUpdate } from '../lib/api'
import { useTheme } from '../lib/theme'
import { toast } from 'sonner'
import {
  Bot,
  Lightbulb,
  Power,
  Shield,
  AlertOctagon,
  Loader2,
  Sparkles,
  X,
} from 'lucide-react'

type Mode = 'off' | 'suggestions' | 'autonomous'

interface Settings {
  mode: Mode
  rsi_buy_threshold: number
  rsi_sell_threshold: number
  max_trade_pct: number
  max_daily_trades: number
  max_daily_turnover_pct: number
  sector_cap_pct: number
  paper_only: boolean
  breaker_on_loss_pct: number
  breaker_on_volatility_spike: boolean
  breaker_on_news_event: boolean
  last_kill_switch_at: string | null
}

const DEFAULTS: Settings = {
  mode: 'off',
  rsi_buy_threshold: 30,
  rsi_sell_threshold: 70,
  max_trade_pct: 5,
  max_daily_trades: 8,
  max_daily_turnover_pct: 20,
  sector_cap_pct: 35,
  paper_only: true,
  breaker_on_loss_pct: 3,
  breaker_on_volatility_spike: true,
  breaker_on_news_event: true,
  last_kill_switch_at: null,
}

export default function AITradingSettings() {
  const { theme } = useTheme()
  const isDark = theme === 'dark'

  const [settings, setSettings] = useState<Settings>(DEFAULTS)
  const [original, setOriginal] = useState<Settings>(DEFAULTS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showKillModal, setShowKillModal] = useState(false)
  const [killing, setKilling] = useState(false)

  useEffect(() => {
    load()
  }, [])

  const load = async () => {
    setLoading(true)
    try {
      const res = await aiApi.getSettings()
      const data = { ...DEFAULTS, ...res.data }
      setSettings(data)
      setOriginal(data)
    } catch (err) {
      console.error(err)
      toast.error('Failed to load AI settings')
    } finally {
      setLoading(false)
    }
  }

  const dirty = JSON.stringify(settings) !== JSON.stringify(original)

  const update = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload: AISettingsUpdate = {
        mode: settings.mode,
        rsi_buy_threshold: settings.rsi_buy_threshold,
        rsi_sell_threshold: settings.rsi_sell_threshold,
        max_trade_pct: settings.max_trade_pct,
        max_daily_trades: settings.max_daily_trades,
        max_daily_turnover_pct: settings.max_daily_turnover_pct,
        sector_cap_pct: settings.sector_cap_pct,
        paper_only: settings.paper_only,
        breaker_on_loss_pct: settings.breaker_on_loss_pct,
        breaker_on_volatility_spike: settings.breaker_on_volatility_spike,
        breaker_on_news_event: settings.breaker_on_news_event,
      }
      const res = await aiApi.updateSettings(payload)
      const data = { ...DEFAULTS, ...res.data }
      setSettings(data)
      setOriginal(data)
      toast.success('AI trading settings saved')
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e.response?.data?.detail || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => setSettings(DEFAULTS)

  const handleKillSwitch = async () => {
    setKilling(true)
    try {
      const res = await aiApi.killSwitch()
      toast.success(
        res.data?.message ||
          `Kill switch triggered. Cancelled ${res.data?.cancelled_signals || 0} signals.`
      )
      setShowKillModal(false)
      await load()
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e.response?.data?.detail || 'Kill switch failed')
    } finally {
      setKilling(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-500"></div>
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6 animate-fade-in">
      <div className="page-header">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-gradient-to-br from-sky-500/20 to-indigo-500/20 border border-sky-500/30">
            <Sparkles className="w-6 h-6 text-sky-500" />
          </div>
          <div>
            <h1 className="page-title">AI Trading</h1>
            <p className="page-subtitle">
              Configure how Sapient's AI engine proposes and executes trades on your behalf.
            </p>
          </div>
        </div>
      </div>

      {settings.paper_only && (
        <div className={`flex items-start gap-3 px-4 py-3 rounded-xl border ${
          isDark
            ? 'bg-amber-500/10 border-amber-500/30 text-amber-200'
            : 'bg-amber-50 border-amber-200 text-amber-700'
        }`}>
          <Shield className="w-5 h-5 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-medium">
              Paper-trading required. Toggle off below once you're ready for live trading.
            </p>
          </div>
        </div>
      )}

      {/* Trading Mode */}
      <section className="card space-y-4">
        <div>
          <h2 className={`text-xl font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
            Trading Mode
          </h2>
          <p className="text-sm theme-text-muted mt-1">
            Select the level of autonomy for the AI engine.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <ModeCard
            active={settings.mode === 'off'}
            onClick={() => update('mode', 'off')}
            icon={<Power className="w-5 h-5" />}
            title="Off"
            description="AI signals are disabled. You build portfolios manually."
            tone="slate"
            isDark={isDark}
          />
          <ModeCard
            active={settings.mode === 'suggestions'}
            onClick={() => update('mode', 'suggestions')}
            icon={<Lightbulb className="w-5 h-5" />}
            title="Suggestions"
            description="AI proposes trades. You approve each one in the inbox before execution."
            tone="sky"
            isDark={isDark}
          />
          <ModeCard
            active={settings.mode === 'autonomous'}
            onClick={() => update('mode', 'autonomous')}
            icon={<Bot className="w-5 h-5" />}
            title="Autonomous"
            description="AI executes approved-rule trades automatically through IBKR. Use with caution."
            tone="purple"
            badge="Live only"
            isDark={isDark}
          />
        </div>
      </section>

      {/* Signal Thresholds */}
      <section className="card space-y-6">
        <div>
          <h2 className={`text-xl font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
            Signal Thresholds
          </h2>
          <p className="text-sm theme-text-muted mt-1">
            Adjust the technical-indicator sensitivities used by the AI.
          </p>
        </div>

        <div className="space-y-6">
          <SliderRow
            label="RSI buy threshold"
            description="Trigger BUY when RSI drops below this value."
            min={5}
            max={50}
            value={settings.rsi_buy_threshold}
            color="sky"
            onChange={(v) => update('rsi_buy_threshold', v)}
          />
          <SliderRow
            label="RSI sell threshold"
            description="Trigger SELL when RSI rises above this value."
            min={50}
            max={95}
            value={settings.rsi_sell_threshold}
            color="red"
            onChange={(v) => update('rsi_sell_threshold', v)}
          />
        </div>

        <div className={`pt-4 border-t ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
          <ToggleRow
            label="Paper trading only"
            description="Block any orders from being routed to the live IBKR environment."
            checked={settings.paper_only}
            onChange={(v) => update('paper_only', v)}
          />
        </div>
      </section>

      {/* Risk Guardrails */}
      <section className="card space-y-5">
        <div>
          <h2 className={`text-xl font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
            Risk Guardrails
          </h2>
          <p className="text-sm theme-text-muted mt-1">
            Hard limits on portfolio exposure and trade frequency.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <NumberField
            label="Max trade size (%)"
            help="of portfolio value per single trade"
            value={settings.max_trade_pct}
            min={0.5}
            max={25}
            step={0.5}
            onChange={(v) => update('max_trade_pct', v)}
          />
          <NumberField
            label="Max daily trades"
            help="across all portfolios"
            value={settings.max_daily_trades}
            min={1}
            max={50}
            step={1}
            onChange={(v) => update('max_daily_trades', Math.round(v))}
          />
          <NumberField
            label="Max daily turnover (%)"
            help="of portfolio NAV per day"
            value={settings.max_daily_turnover_pct}
            min={1}
            max={100}
            step={1}
            onChange={(v) => update('max_daily_turnover_pct', v)}
          />
          <NumberField
            label="Sector cap (%)"
            help="max single GICS sector weight"
            value={settings.sector_cap_pct}
            min={10}
            max={100}
            step={1}
            onChange={(v) => update('sector_cap_pct', v)}
          />
        </div>
      </section>

      {/* Circuit Breakers */}
      <section className="card space-y-4">
        <div>
          <h2 className={`text-xl font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
            Circuit Breakers
          </h2>
          <p className="text-sm theme-text-muted mt-1">
            Automatic pause conditions based on market and portfolio events.
          </p>
        </div>

        <div className="space-y-3">
          <BreakerRow isDark={isDark}>
            <div className="flex-1">
              <h4 className={`font-medium text-sm ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                Halt trading on intraday portfolio drawdown
              </h4>
              <p className="text-xs theme-text-muted mt-1 flex items-center gap-2">
                Pauses all AI trading when daily drop exceeds
                <input
                  type="number"
                  step="0.5"
                  min={0.5}
                  max={20}
                  value={settings.breaker_on_loss_pct}
                  onChange={(e) => update('breaker_on_loss_pct', parseFloat(e.target.value) || 0)}
                  className="input !py-1 !px-2 !w-20 !text-xs"
                />
                %
              </p>
            </div>
          </BreakerRow>

          <BreakerRow isDark={isDark}>
            <div className="flex-1">
              <h4 className={`font-medium text-sm ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                Pause new signals during market open volatility
              </h4>
              <p className="text-xs theme-text-muted mt-1">
                Ignores signals generated in the first 15 minutes of trading.
              </p>
            </div>
            <Toggle
              checked={settings.breaker_on_volatility_spike}
              onChange={(v) => update('breaker_on_volatility_spike', v)}
            />
          </BreakerRow>

          <BreakerRow isDark={isDark}>
            <div className="flex-1">
              <h4 className={`font-medium text-sm ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                Pause on major news / earnings events
              </h4>
              <p className="text-xs theme-text-muted mt-1">
                Skips signals that overlap with high-impact news for the symbol.
              </p>
            </div>
            <Toggle
              checked={settings.breaker_on_news_event}
              onChange={(v) => update('breaker_on_news_event', v)}
            />
          </BreakerRow>
        </div>
      </section>

      {/* Kill Switch */}
      <section
        className={`rounded-2xl p-6 border relative overflow-hidden ${
          isDark ? 'bg-slate-900/80 border-red-500/30' : 'bg-white border-red-200'
        }`}
        style={{ boxShadow: '0 0 30px rgba(239, 68, 68, 0.1)' }}
      >
        <div className="absolute top-0 right-0 w-64 h-64 bg-red-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/4 pointer-events-none" />

        <div className="relative z-10 flex flex-col md:flex-row md:items-center gap-6">
          <div
            className={`p-4 rounded-2xl shrink-0 border ${
              isDark
                ? 'bg-red-500/10 border-red-500/20'
                : 'bg-red-50 border-red-200'
            }`}
          >
            <AlertOctagon className="w-10 h-10 text-red-500" />
          </div>

          <div className="flex-1">
            <h2 className={`text-xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
              Emergency Kill Switch
            </h2>
            <p className="text-sm theme-text-muted mt-1.5 max-w-xl">
              Immediately cancel all open AI orders and disable AI trading across every portfolio.
              Manual trading remains available.
            </p>
            <p className="text-xs theme-text-muted mt-2">
              Last triggered:{' '}
              {settings.last_kill_switch_at
                ? new Date(settings.last_kill_switch_at).toLocaleString()
                : 'never'}
            </p>
          </div>

          <button
            onClick={() => setShowKillModal(true)}
            className="btn-danger whitespace-nowrap text-sm px-5 py-3 font-semibold uppercase tracking-wide"
          >
            Pause AI trading now
          </button>
        </div>
      </section>

      {/* Footer Actions */}
      <div className={`flex justify-between items-center pt-4 pb-6 border-t ${
        isDark ? 'border-slate-700/50' : 'border-slate-200'
      }`}>
        <button
          onClick={handleReset}
          className="text-sm font-medium theme-text-secondary hover:theme-text transition-colors"
        >
          Reset to defaults
        </button>
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          className="btn-primary flex items-center gap-2"
        >
          {saving && <Loader2 className="w-4 h-4 animate-spin" />}
          Save changes
        </button>
      </div>

      {showKillModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div
            className="card max-w-md w-full"
            style={{
              background: isDark ? 'rgba(15, 23, 42, 0.95)' : 'rgba(255, 255, 255, 0.98)',
            }}
          >
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-red-500/10 border border-red-500/30">
                  <AlertOctagon className="w-5 h-5 text-red-500" />
                </div>
                <h3 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                  Trigger Kill Switch?
                </h3>
              </div>
              <button
                onClick={() => setShowKillModal(false)}
                className="theme-text-muted hover:theme-text"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-sm theme-text-secondary mb-6">
              All pending AI signals will be rejected and any open AI-placed orders will be cancelled.
              The AI engine will be set to <span className="font-semibold">Off</span>. This action is
              logged for your audit trail.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowKillModal(false)}
                className="btn-secondary"
                disabled={killing}
              >
                Cancel
              </button>
              <button
                onClick={handleKillSwitch}
                className="btn-danger flex items-center gap-2"
                disabled={killing}
              >
                {killing && <Loader2 className="w-4 h-4 animate-spin" />}
                Yes, pause everything
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ModeCard({
  active,
  onClick,
  icon,
  title,
  description,
  tone,
  badge,
  isDark,
}: {
  active: boolean
  onClick: () => void
  icon: ReactNode
  title: string
  description: string
  tone: 'slate' | 'sky' | 'purple'
  badge?: string
  isDark: boolean
}) {
  const toneClasses = {
    slate: active
      ? 'border-slate-400/60 bg-slate-500/10'
      : 'hover:border-slate-400/40',
    sky: active
      ? 'border-sky-500/60 bg-sky-500/10 shadow-[0_0_20px_rgba(56,189,248,0.18)]'
      : 'hover:border-sky-500/30',
    purple: active
      ? 'border-purple-500/60 bg-purple-500/10 shadow-[0_0_20px_rgba(168,85,247,0.18)]'
      : 'hover:border-purple-500/30',
  }

  const iconBg = {
    slate: active ? 'bg-slate-500/20 text-slate-300' : 'bg-slate-500/10 text-slate-400',
    sky: active ? 'bg-sky-500/20 text-sky-400' : 'bg-slate-500/10 text-slate-400',
    purple: active ? 'bg-purple-500/20 text-purple-400' : 'bg-slate-500/10 text-slate-400',
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative text-left p-5 rounded-xl border transition-all ${
        isDark ? 'bg-slate-800/30 border-slate-700/50' : 'bg-slate-50 border-slate-200'
      } ${toneClasses[tone]}`}
    >
      {badge && (
        <span className="absolute top-3 right-3 badge badge-purple">{badge}</span>
      )}
      <div className={`p-2.5 rounded-lg inline-block mb-3 ${iconBg[tone]}`}>{icon}</div>
      <h3 className={`font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
        {title}
      </h3>
      <p className="text-sm theme-text-muted mt-1.5">{description}</p>
    </button>
  )
}

function SliderRow({
  label,
  description,
  min,
  max,
  value,
  onChange,
  color,
}: {
  label: string
  description: string
  min: number
  max: number
  value: number
  onChange: (v: number) => void
  color: 'sky' | 'red'
}) {
  const valueColor = color === 'sky' ? 'text-sky-500' : 'text-red-500'
  const accent = color === 'sky' ? '#38bdf8' : '#f87171'
  return (
    <div>
      <div className="flex justify-between items-center mb-2">
        <label className="text-sm font-medium theme-text-secondary">{label}</label>
        <span className={`text-sm font-bold ${valueColor}`}>{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-2 rounded-lg appearance-none cursor-pointer focus:outline-none"
        style={{ accentColor: accent, background: 'rgba(148,163,184,0.25)' }}
      />
      <p className="text-xs theme-text-muted mt-2">{description}</p>
    </div>
  )
}

function NumberField({
  label,
  help,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string
  help: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        className="input"
      />
      <p className="text-xs theme-text-muted mt-1.5">{help}</p>
    </div>
  )
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors shrink-0 ${
        checked ? 'bg-sky-500' : 'bg-slate-500/40'
      }`}
    >
      <span
        className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
          checked ? 'translate-x-5' : ''
        }`}
      />
    </button>
  )
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string
  description: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <p className="text-sm font-medium theme-text">{label}</p>
        <p className="text-xs theme-text-muted mt-0.5">{description}</p>
      </div>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  )
}

function BreakerRow({
  isDark,
  children,
}: {
  isDark: boolean
  children: ReactNode
}) {
  return (
    <div
      className={`flex items-center justify-between gap-4 p-4 rounded-xl border ${
        isDark ? 'bg-slate-800/30 border-slate-700/50' : 'bg-slate-50 border-slate-200'
      }`}
    >
      {children}
    </div>
  )
}
