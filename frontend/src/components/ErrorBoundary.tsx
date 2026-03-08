import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
          <h1 className="text-2xl font-semibold">發生了一個錯誤</h1>
          <p className="text-muted-foreground max-w-md text-sm">
            頁面無法載入，請重新整理。如果問題持續發生，請聯絡開發者。
          </p>
          <pre className="bg-muted max-w-lg overflow-auto rounded p-3 text-left text-xs">
            {this.state.error.message}
          </pre>
          <button
            className="bg-primary text-primary-foreground rounded px-4 py-2 text-sm"
            onClick={() => window.location.reload()}
          >
            重新整理
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
