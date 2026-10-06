/**
 * Contexte et Provider d'authentification OIDC Authentik (Sprint 8, Tâche 8.2)
 * Supporte le flux OIDC officiel ainsi que le mode DEV local contrôlé.
 */
import React, { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { User } from 'oidc-client-ts'
import { userManager } from './oidcConfig'

export interface AuthContextType {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  isDevMode: boolean
  devPrincipal: string
  error: string | null
  login: () => Promise<void>
  logout: () => Promise<void>
  enableDevBypass: (principal?: string) => void
  setDevPrincipal: (principal: string) => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [isDevMode, setIsDevMode] = useState<boolean>(() => {
    return sessionStorage.getItem('dev_bypass') === 'true' || import.meta.env.DEV
  })
  const [devPrincipal, setDevPrincipalState] = useState<string>(() => {
    return sessionStorage.getItem('dev_principal') || 'admin_user'
  })

  // Initialisation au chargement de l'application
  useEffect(() => {
    let mounted = true

    const initAuth = async () => {
      try {
        const currentUser = await userManager.getUser()
        if (currentUser && !currentUser.expired) {
          if (mounted) {
            setUser(currentUser)
            sessionStorage.setItem('access_token', currentUser.access_token)
            sessionStorage.removeItem('dev_bypass')
            setIsDevMode(false)
          }
        } else {
          // Si en mode dev ou si dev_bypass est actif
          const bypassActive = sessionStorage.getItem('dev_bypass') === 'true' || import.meta.env.DEV
          if (bypassActive && mounted) {
            setIsDevMode(true)
            const activePrincipal = sessionStorage.getItem('dev_principal') || 'admin_user'
            setDevPrincipalState(activePrincipal)
            sessionStorage.setItem('dev_bypass', 'true')
            sessionStorage.setItem('dev_principal', activePrincipal)
          }
        }
      } catch (err: unknown) {
        if (mounted) {
          const message = err instanceof Error ? err.message : String(err)
          setError(`Erreur lors de la vérification de session : ${message}`)
        }
      } finally {
        if (mounted) {
          setIsLoading(false)
        }
      }
    }

    initAuth()

    // Écouteurs d'événements de l'état utilisateur OIDC
    const onUserLoaded = (loadedUser: User) => {
      setUser(loadedUser)
      sessionStorage.setItem('access_token', loadedUser.access_token)
      sessionStorage.removeItem('dev_bypass')
      setIsDevMode(false)
    }

    const onUserUnloaded = () => {
      setUser(null)
      sessionStorage.removeItem('access_token')
    }

    userManager.events.addUserLoaded(onUserLoaded)
    userManager.events.addUserUnloaded(onUserUnloaded)

    return () => {
      mounted = false
      userManager.events.removeUserLoaded(onUserLoaded)
      userManager.events.removeUserUnloaded(onUserUnloaded)
    }
  }, [])

  const login = async () => {
    setError(null)
    try {
      await userManager.signinRedirect()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      setError(`Impossible d'initier la connexion OIDC : ${message}`)
    }
  }

  const logout = async () => {
    sessionStorage.removeItem('access_token')
    sessionStorage.removeItem('dev_bypass')
    sessionStorage.removeItem('dev_principal')
    setUser(null)
    setIsDevMode(false)

    try {
      await userManager.signoutRedirect()
    } catch {
      window.location.href = '/'
    }
  }

  const enableDevBypass = (principal = 'admin_user') => {
    sessionStorage.setItem('dev_bypass', 'true')
    sessionStorage.setItem('dev_principal', principal)
    sessionStorage.removeItem('access_token')
    setDevPrincipalState(principal)
    setIsDevMode(true)
    setUser(null)
  }

  const setDevPrincipal = (principal: string) => {
    sessionStorage.setItem('dev_principal', principal)
    setDevPrincipalState(principal)
  }

  const isAuthenticated = Boolean(user && !user.expired) || isDevMode
  const token = user?.access_token || null

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated,
        isLoading,
        isDevMode,
        devPrincipal,
        error,
        login,
        logout,
        enableDevBypass,
        setDevPrincipal,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth doit être utilisé à l\'intérieur d\'un AuthProvider')
  }
  return context
}

