import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { useProfile } from './lib/profile'
import Onboarding from './pages/Onboarding'
import Dashboard from './pages/Dashboard'
import ManualBuilder from './pages/ManualBuilder'
import AutoBuilder from './pages/AutoBuilder'
import CAPMBuilder from './pages/CAPMBuilder'
import Portfolios from './pages/Portfolios'
import PortfolioDetail from './pages/PortfolioDetail'
import StockAnalysis from './pages/StockAnalysis'
import Settings from './pages/Settings'
import BrokerageSettings from './pages/BrokerageSettings'
import AITradingSettings from './pages/AITradingSettings'
import AITradingInbox from './pages/AITradingInbox'
import PaperOrders from './pages/PaperOrders'
import Layout from './components/Layout'

function App() {
  const { profile, error, reload } = useProfile()
  const navigate = useNavigate()

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 theme-text-secondary">
        <p>Sapient's engine isn't answering yet.</p>
        <button className="btn-primary" onClick={reload}>Try again</button>
      </div>
    )
  }
  if (!profile) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-500" />
      </div>
    )
  }
  if (!profile.onboarded) {
    return <Onboarding onDone={(goTo) => navigate(goTo, { replace: true })} />
  }

  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="manual-builder" element={<ManualBuilder />} />
        <Route path="auto-builder" element={<AutoBuilder />} />
        <Route path="factor-builder" element={<Navigate to="/auto-builder" replace />} />
        <Route path="fundamentals-builder" element={<Navigate to="/auto-builder" replace />} />
        <Route path="capm-builder" element={<CAPMBuilder />} />
        <Route path="portfolios" element={<Portfolios />} />
        <Route path="portfolios/:id" element={<PortfolioDetail />} />
        <Route path="analysis" element={<StockAnalysis />} />
        <Route path="ai-inbox" element={<AITradingInbox />} />
        <Route path="ai-trading" element={<AITradingSettings />} />
        <Route path="brokerage" element={<BrokerageSettings />} />
        <Route path="paper-orders" element={<PaperOrders />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default App
