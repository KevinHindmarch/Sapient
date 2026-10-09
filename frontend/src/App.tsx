import { Routes, Route, Navigate } from 'react-router-dom'
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
import Layout from './components/Layout'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="manual-builder" element={<ManualBuilder />} />
        <Route path="auto-builder" element={<AutoBuilder />} />
        <Route path="fundamentals-builder" element={<Navigate to="/auto-builder" replace />} />
        <Route path="capm-builder" element={<CAPMBuilder />} />
        <Route path="portfolios" element={<Portfolios />} />
        <Route path="portfolios/:id" element={<PortfolioDetail />} />
        <Route path="analysis" element={<StockAnalysis />} />
        <Route path="ai-inbox" element={<AITradingInbox />} />
        <Route path="ai-trading" element={<AITradingSettings />} />
        <Route path="brokerage" element={<BrokerageSettings />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default App
