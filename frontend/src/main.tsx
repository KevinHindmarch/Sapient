import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-sans/700.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/ibm-plex-mono/600.css'
import './index.css'
import App from './App'
import { ThemeProvider } from './lib/theme'
import { ProfileProvider } from './lib/profile'
import { Toaster } from 'sonner'
import ErrorBoundary from './components/ErrorBoundary'
import { CompanyProvider } from './components/CompanyPanel'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <ThemeProvider>
        <ErrorBoundary>
          <ProfileProvider>
            <CompanyProvider>
              <App />
            </CompanyProvider>
          </ProfileProvider>
        </ErrorBoundary>
        <Toaster position="top-right" richColors />
      </ThemeProvider>
    </HashRouter>
  </StrictMode>,
)
