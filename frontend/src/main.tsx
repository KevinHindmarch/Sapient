import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import './index.css'
import App from './App'
import { ThemeProvider } from './lib/theme'
import { Toaster } from 'sonner'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <ThemeProvider>
        <App />
        <Toaster position="top-right" richColors />
      </ThemeProvider>
    </HashRouter>
  </StrictMode>,
)
