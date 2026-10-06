import React, { Component, type ErrorInfo, type ReactNode } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from './Card'
import { Button } from './Button'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary a capturé une exception React:', error, errorInfo)
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null })
    window.location.reload()
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="p-8 max-w-xl mx-auto">
          <Card className="border-red-500/50 bg-red-950/20">
            <CardHeader>
              <CardTitle className="text-red-400 flex items-center gap-2">
                <span>⚠️</span> Une erreur inattendue est survenue
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-[hsl(var(--muted-foreground))]">
                L'affichage de ce composant a rencontré un problème. Vous pouvez recharger la page ou revenir à l'accueil.
              </p>
              {this.state.error && (
                <pre className="p-3 bg-black/40 rounded text-xs text-red-300 font-mono overflow-x-auto whitespace-pre-wrap">
                  {this.state.error.message}
                </pre>
              )}
              <div className="flex gap-3">
                <Button onClick={this.handleReset} variant="outline" size="sm">
                  Recharger la page
                </Button>
                <Button onClick={() => { window.location.href = '/' }} size="sm">
                  Retour à l'accueil
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )
    }

    return this.props.children
  }
}
