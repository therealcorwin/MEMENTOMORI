/**
 * Page de réception du rappel OIDC Authentik (Sprint 8, Tâche 8.2)
 * Valide le code d'autorisation et le token PKCE puis redirige l'utilisateur.
 */
import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { userManager } from '@/auth/oidcConfig'
import { Loader2, AlertCircle } from 'lucide-react'

export function CallbackPage() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    const processCallback = async () => {
      try {
        const user = await userManager.signinRedirectCallback()
        if (user && active) {
          sessionStorage.setItem('access_token', user.access_token)
          sessionStorage.removeItem('dev_bypass')
          navigate('/', { replace: true })
        }
      } catch (err: unknown) {
        if (active) {
          const message = err instanceof Error ? err.message : String(err)
          setError(`Échec de la validation de connexion OIDC : ${message}`)
        }
      }
    }

    processCallback()

    return () => {
      active = false
    }
  }, [navigate])

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))] p-4">
        <div className="w-full max-w-md border border-[hsl(var(--destructive))] rounded-xl bg-[hsl(var(--card))] p-6 text-center">
          <AlertCircle className="mx-auto text-[hsl(var(--destructive-foreground))] mb-3" size={36} />
          <h2 className="text-lg font-bold mb-2">Erreur d'authentification</h2>
          <p className="text-sm text-[hsl(var(--muted-foreground))] mb-6">{error}</p>
          <button
            onClick={() => navigate('/', { replace: true })}
            className="px-4 py-2 rounded-lg bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] text-sm font-medium hover:opacity-90 cursor-pointer"
          >
            Retourner à l'accueil
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[hsl(var(--background))] text-[hsl(var(--foreground))]">
      <div className="flex items-center gap-3 mb-4">
        <span className="text-3xl">🧠</span>
        <h1 className="text-xl font-bold">Connexion en cours</h1>
      </div>
      <div className="flex items-center gap-2 text-sm text-[hsl(var(--muted-foreground))]">
        <Loader2 className="animate-spin" size={20} />
        <span>Validation des jetons Authentik OIDC...</span>
      </div>
    </div>
  )
}

