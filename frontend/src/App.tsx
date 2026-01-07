import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './lib/auth'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import ManualBuilder from './pages/ManualBuilder'
import AutoBuilder from './pages/AutoBuilder'
import Portfolios from './pages/Portfolios'
import PortfolioDetail from './pages/PortfolioDetail'
import StockAnalysis from './pages/StockAnalysis'
import Layout from './components/Layout'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-500"></div>
      </div>
    )
  }
  
  if (!user) {
    return <Navigate to="/login" replace />
  }
  
  return <>{children}</>
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="manual-builder" element={<ManualBuilder />} />
        <Route path="auto-builder" element={<AutoBuilder />} />
        <Route path="portfolios" element={<Portfolios />} />
        <Route path="portfolios/:id" element={<PortfolioDetail />} />
        <Route path="analysis" element={<StockAnalysis />} />
      </Route>
    </Routes>
  )
}

export default App
