/**
 * Composant Guard pour sécuriser l'accès aux routes du Dashboard (Sprint 8, Tâche 8.2)
 */
import React, { type ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { useAuth } from './AuthProvider'
import { LogIn, Shield, Code, Loader2 } from 'lucide-react'

interface ProtectedRouteProps {
  children?: ReactNode
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, error, login, enableDevBypass } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[hsl(var(--background))] text-[hsl(var(--foreground))]">
        <div className="flex items-center gap-3 mb-4">
          <span className="text-4xl animate-pulse">🧠</span>
          <h1 className="text-xl font-bold">Knowledge Platform</h1>
        </div>
        <div className="flex items-center gap-2 text-sm text-[hsl(var(--muted-foreground))]">
          <Loader2 className="animate-spin" size={18} />
          <span>Vérification de la session en cours...</span>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))] p-4">
        <div className="w-full max-w-md border border-[hsl(var(--border))] rounded-xl bg-[hsl(var(--card))] p-8 shadow-2xl">
          {/* Logo & En-tête */}
          <div className="text-center mb-8">
            <span className="text-5xl inline-block mb-3">🧠</span>
            <h1 className="text-2xl font-bold text-[hsl(var(--card-foreground))]">
              Knowledge Platform
            </h1>
            <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
              Base de connaissances unifiée & RAG multi-agents
            </p>
          </div>

          {/* Erreur éventuelle */}
          {error && (
            <div className="mb-6 p-3 rounded-lg bg-[hsl(var(--destructive))]/20 border border-[hsl(var(--destructive))] text-xs text-[hsl(var(--destructive-foreground))]">
              {error}
            </div>
          )}

          {/* Actions de connexion */}
          <div className="space-y-4">
            <button
              onClick={() => login()}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-medium bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-opacity cursor-pointer shadow"
            >
              <LogIn size={18} />
              <span>Se connecter via Authentik SSO</span>
            </button>

            <div className="relative flex items-center justify-center my-6">
              <div className="border-t border-[hsl(var(--border))] w-full" />
              <span className="bg-[hsl(var(--card))] px-3 text-xs text-[hsl(var(--muted-foreground))] uppercase tracking-wider absolute">
                ou
              </span>
            </div>

            <button
              onClick={() => enableDevBypass('admin_user')}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm border border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--accent))] transition-colors cursor-pointer"
            >
              <Code size={16} />
              <span>Accès direct Mode DEV (admin_user)</span>
            </button>
          </div>

          {/* Badge de sécurité */}
          <div className="mt-8 pt-6 border-t border-[hsl(var(--border))] flex items-center justify-center gap-2 text-xs text-[hsl(var(--muted-foreground))]">
            <Shield size={14} className="text-emerald-500" />
            <span>Sécurisé par Authentik OIDC (RS256 PKCE)</span>
          </div>
        </div>
      </div>
    )
  }

  return children ? <>{children}</> : <Outlet />
}

