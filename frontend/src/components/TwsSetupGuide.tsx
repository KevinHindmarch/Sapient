import { ExternalLink, Copy } from 'lucide-react'
import { toast } from 'sonner'

// Step-by-step instructions for installing TWS and enabling its API.

const TWS_DOWNLOAD_URL = 'https://www.interactivebrokers.com/en/trading/tws.php'
const TWS_API_DOWNLOAD_URL = 'https://interactivebrokers.github.io/'

export function openExternal(url: string) {
  if (window.sapient?.openExternal) window.sapient.openExternal(url)
  else window.open(url, '_blank', 'noopener,noreferrer')
}

function copy(value: string) {
  navigator.clipboard?.writeText(value).then(() => toast.success(`Copied ${value}`)).catch(() => undefined)
}

interface Step {
  title: string
  body: React.ReactNode
}

export const TWS_SETUP_STEPS: Step[] = [
  {
    title: 'Install Trader Workstation (TWS)',
    body: (
      <>
        <p>Download <strong>TWS Latest</strong> or <strong>TWS Stable</strong> for Windows from Interactive Brokers,
          run the installer with the default options, then start TWS from the Start menu.</p>
        <button className="btn-secondary mt-3 inline-flex items-center gap-2" onClick={() => openExternal(TWS_DOWNLOAD_URL)}>
          <ExternalLink className="w-4 h-4" /> Open IBKR download page
        </button>
      </>
    ),
  },
  {
    title: 'Log in to Paper Trading',
    body: <p>On the TWS login screen choose <strong>Paper Trading</strong>. Sapient starts with paper (simulated money) only.
      Real-money trading needs a separate sign-off later.</p>,
  },
  {
    title: 'Turn on the API in TWS',
    body: (
      <ol className="list-decimal ml-5 space-y-1">
        <li>Open <strong>File → Global Configuration</strong> (on some layouts <strong>Edit → Global Configuration</strong>).</li>
        <li>In the left panel choose <strong>API → Settings</strong>.</li>
        <li>Tick <strong>Enable ActiveX and Socket Clients</strong>.</li>
        <li>Keep <strong>Read-Only API</strong> ticked — Sapient only reads at this stage.</li>
        <li>Set <strong>Socket port</strong> to{' '}
          <button className="font-mono underline" onClick={() => copy('7497')}>7497 <Copy className="w-3 h-3 inline" /></button>{' '}
          (paper default; live is normally 7496).</li>
        <li>Tick <strong>Allow connections from localhost only</strong>.</li>
        <li>Leave <strong>Master API client ID</strong> empty.</li>
        <li>Click <strong>Apply</strong>, then <strong>OK</strong>.</li>
        <li>Recommended: under <strong>Lock and Exit</strong> set the daily auto-restart to a time you are not trading.</li>
        <li>If TWS asks “Accept incoming connection?” when Sapient connects, click <strong>Yes</strong>.</li>
      </ol>
    ),
  },
  {
    title: 'Install the IBKR API software',
    body: (
      <>
        <p>Download the <strong>Windows</strong> installer of the TWS API that matches your TWS version and run it with
          the defaults (it installs to <span className="font-mono">C:\TWS API</span>). Sapient can’t include this itself
          because of IBKR’s licence terms.</p>
        <button className="btn-secondary mt-3 inline-flex items-center gap-2" onClick={() => openExternal(TWS_API_DOWNLOAD_URL)}>
          <ExternalLink className="w-4 h-4" /> Open TWS API download page
        </button>
      </>
    ),
  },
]

export default function TwsSetupGuide() {
  return (
    <ol className="space-y-5">
      {TWS_SETUP_STEPS.map((step, index) => (
        <li key={step.title} className="flex gap-4">
          <div className="w-7 h-7 shrink-0 rounded-full border border-sky-500/40 bg-sky-500/10 text-sky-600 text-sm font-semibold flex items-center justify-center">
            {index + 1}
          </div>
          <div className="flex-1 text-sm theme-text-secondary">
            <h3 className="text-base font-semibold theme-text mb-1">{step.title}</h3>
            {step.body}
          </div>
        </li>
      ))}
    </ol>
  )
}
