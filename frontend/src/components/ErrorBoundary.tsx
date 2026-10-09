import { Component, type ErrorInfo, type ReactNode } from 'react'

/** A crash in one page shows a way back instead of a blank window. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Sapient page crashed', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="card max-w-lg text-center space-y-3" data-testid="crash">
          <h1 className="text-lg font-semibold theme-text">Something went wrong on this page</h1>
          <p className="text-sm theme-text-secondary">Nothing was changed in your account. Reloading usually fixes it;
            if it keeps happening, tell us what you clicked.</p>
          <p className="text-xs theme-text-muted break-words">{this.state.error.message}</p>
          <div className="flex justify-center gap-2">
            <button className="btn-secondary" onClick={() => { window.location.hash = '#/'; window.location.reload() }}>
              Go to Dashboard</button>
            <button className="btn-primary" onClick={() => window.location.reload()}>Reload</button>
          </div>
        </div>
      </div>
    )
  }
}
