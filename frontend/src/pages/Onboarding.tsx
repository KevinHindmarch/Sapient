import { useState } from 'react'
import { ArrowLeft, ArrowRight, Check, Moon, ShieldCheck, Sun, User } from 'lucide-react'
import { toast } from 'sonner'
import logo from '../assets/logo.png'
import { useTheme } from '../lib/theme'
import { useProfile } from '../lib/profile'

// First-run welcome wizard: name → theme → Interactive Brokers (now or later).
// Shown until the user finishes it; everything can be changed later in Settings.

const STEPS = ['Welcome', 'Your name', 'Look and feel', 'Interactive Brokers', 'All set'] as const

export default function Onboarding({ onDone }: { onDone: (goTo: string) => void }) {
  const { theme, setTheme } = useTheme()
  const { update } = useProfile()
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [connectNow, setConnectNow] = useState<boolean | null>(null)
  const [saving, setSaving] = useState(false)
  const isDark = theme === 'dark'
  const nameOk = name.trim().length > 0 && name.trim().length <= 60

  const finish = async () => {
    setSaving(true)
    try {
      await update({ display_name: name.trim(), theme, complete_onboarding: true })
      onDone(connectNow ? '/brokerage' : '/')
    } catch {
      toast.error('Could not save your profile. Please try again.')
      setSaving(false)
    }
  }

  const canContinue = step === 1 ? nameOk : step === 3 ? connectNow !== null : true

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="card w-full max-w-2xl p-0 overflow-hidden" data-testid="onboarding">
        <div className="flex items-center gap-3 px-8 pt-8">
          <img src={logo} alt="" className="w-12 h-12 rounded-lg" />
          <div>
            <h1 className="text-xl font-bold gradient-text">Welcome to Sapient</h1>
            <p className="text-sm theme-text-secondary">Step {step + 1} of {STEPS.length}: {STEPS[step]}</p>
          </div>
        </div>
        <div className="flex gap-1.5 px-8 mt-5">
          {STEPS.map((label, index) => (
            <div key={label} className={`h-1.5 flex-1 rounded-full ${index <= step ? 'bg-sky-500' : 'bg-slate-500/20'}`} />
          ))}
        </div>

        <div className="px-8 py-8 min-h-[18rem]">
          {step === 0 && (
            <div className="space-y-3 theme-text-secondary">
              <h2 className="text-2xl font-semibold theme-text">Let's set Sapient up for you</h2>
              <p>This takes about a minute. Sapient runs entirely on this PC: your portfolios and settings are
                stored here and never uploaded anywhere.</p>
              <p>You'll choose your name and how Sapient looks, and whether to connect Interactive Brokers now or
                later. You can change everything afterwards in <strong>Settings</strong>.</p>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <h2 className="text-2xl font-semibold theme-text flex items-center gap-2"><User className="w-6 h-6 text-sky-500" /> What should we call you?</h2>
              <p className="theme-text-secondary">Your name is shown on the dashboard. It stays on this PC.</p>
              <input
                autoFocus
                className="input w-full text-lg"
                placeholder="Your first name"
                maxLength={60}
                value={name}
                onChange={(event) => setName(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter' && nameOk) setStep(2) }}
                aria-label="Your name"
              />
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <h2 className="text-2xl font-semibold theme-text">Light or dark?</h2>
              <p className="theme-text-secondary">Pick what's easiest on your eyes. Sapient switches straight away so you can see it.</p>
              <div className="grid grid-cols-2 gap-4">
                {([
                  { value: 'light', label: 'Light', icon: Sun, hint: 'Bright and clean' },
                  { value: 'dark', label: 'Dark', icon: Moon, hint: 'Easier at night' },
                ] as const).map(({ value, label, icon: Icon, hint }) => (
                  <button
                    key={value}
                    onClick={() => setTheme(value)}
                    className={`p-5 rounded-xl border-2 text-left transition-all ${theme === value ? 'border-sky-500 bg-sky-500/10' : 'theme-border hover:border-sky-400/60'}`}
                    aria-pressed={theme === value}
                  >
                    <Icon className={`w-7 h-7 mb-3 ${value === 'dark' ? 'text-indigo-400' : 'text-amber-500'}`} />
                    <p className="font-semibold theme-text">{label}</p>
                    <p className="text-sm theme-text-secondary">{hint}</p>
                    {theme === value && <p className="mt-2 text-xs text-sky-600 flex items-center gap-1"><Check className="w-3 h-3" /> Selected</p>}
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <h2 className="text-2xl font-semibold theme-text flex items-center gap-2"><ShieldCheck className="w-6 h-6 text-sky-500" /> Interactive Brokers</h2>
              <p className="theme-text-secondary">Sapient can connect to Trader Workstation (TWS) on this PC to read your
                account. It starts read-only and with paper (practice) money; real trading needs your separate approval later.</p>
              <div className="grid gap-3">
                {[
                  { value: true, title: 'Set it up now', text: 'Go to the step-by-step TWS setup after this (about 10–15 minutes).' },
                  { value: false, title: 'Later', text: 'Start with research and portfolio building. Set up TWS any time from Brokerage.' },
                ].map((option) => (
                  <button
                    key={option.title}
                    onClick={() => setConnectNow(option.value)}
                    className={`p-4 rounded-xl border-2 text-left ${connectNow === option.value ? 'border-sky-500 bg-sky-500/10' : 'theme-border hover:border-sky-400/60'}`}
                    aria-pressed={connectNow === option.value}
                  >
                    <p className="font-semibold theme-text">{option.title}</p>
                    <p className="text-sm theme-text-secondary">{option.text}</p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-3 theme-text-secondary">
              <h2 className="text-2xl font-semibold theme-text">You're all set, {name.trim()}!</h2>
              <p>Theme: <strong>{isDark ? 'Dark' : 'Light'}</strong>. {connectNow ? 'Next: the TWS setup steps.' : 'You can connect Interactive Brokers later from Brokerage.'}</p>
              <p>Tip: the <strong>Help &amp; Glossary</strong> button in the sidebar explains terms like Sharpe ratio and RSI.</p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between px-8 pb-8">
          <button className="btn-secondary inline-flex items-center gap-2" disabled={step === 0 || saving}
            onClick={() => setStep(step - 1)} style={{ visibility: step === 0 ? 'hidden' : 'visible' }}>
            <ArrowLeft className="w-4 h-4" /> Back
          </button>
          {step < STEPS.length - 1 ? (
            <button className="btn-primary inline-flex items-center gap-2" disabled={!canContinue} onClick={() => setStep(step + 1)}>
              {step === 0 ? 'Get started' : 'Continue'} <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button className="btn-primary inline-flex items-center gap-2" disabled={saving} onClick={finish}>
              {connectNow ? 'Set up TWS' : 'Open Sapient'} <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
