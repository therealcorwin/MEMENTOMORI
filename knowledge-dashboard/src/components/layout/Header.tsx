/**
 * Barre d'en-tête supérieure avec état d'authentification et gestion de session (§14.5)
 */
import React from 'react'
import { useAuth } from '@/auth/AuthProvider'
import { ShieldCheck, User as UserIcon, LogOut, LogIn, ChevronDown } from 'lucide-react'

export function Header() {
  const { user, isDevMode, devPrincipal, setDevPrincipal, logout, login } = useAuth()

  const devIdentities = [
    { id: 'admin_user', label: 'admin_user (Super Administrateur)' },
    { id: 'cs_user', label: 'cs_user (Conseil Syndical)' },
    { id: 'copro_user', label: 'copro_user (Copropriétaire général)' },
    { id: 'copro_user_lot42', label: 'copro_user_lot42 (Résident Lot 42)' },
    { id: 'sante_user', label: 'sante_user (Espace Santé)' },
  ]

  const displayName = user
    ? user.profile.preferred_username || user.profile.name || user.profile.email || 'Utilisateur SSO'
    : devPrincipal

  return (
    <header className="h-16 border-b border-[hsl(var(--border))] bg-[hsl(var(--card))]/60 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-40">
      {/* Côté gauche : Titre & Fil d'Ariane */}
      <div className="flex items-center gap-2">
        <span className="text-xs uppercase tracking-wider text-[hsl(var(--muted-foreground))]">
          Espace de Travail
        </span>
        <span className="text-xs text-[hsl(var(--muted-foreground))]">/</span>
        <span className="text-sm font-semibold text-[hsl(var(--card-foreground))]">
          Plateforme Unifiée
        </span>
      </div>

      {/* Côté droit : Profil Utilisateur & Sécurité */}
      <div className="flex items-center gap-4">
        {isDevMode ? (
          /* Sélecteur de rôle en Mode DEV */
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/30">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
              Mode DEV
            </span>

            <div className="relative flex items-center">
              <select
                value={devPrincipal}
                onChange={(e) => setDevPrincipal(e.target.value)}
                className="appearance-none bg-[hsl(var(--accent))] border border-[hsl(var(--border))] text-[hsl(var(--card-foreground))] text-xs rounded-lg px-3 py-1.5 pr-8 focus:outline-none focus:ring-1 focus:ring-[hsl(var(--ring))] cursor-pointer font-medium"
                title="Changer de rôle pour tester le cloisonnement RBAC"
              >
                {devIdentities.map((id) => (
                  <option key={id.id} value={id.id}>
                    {id.label}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-2.5 text-[hsl(var(--muted-foreground))] pointer-events-none" />
            </div>

            <button
              onClick={() => login()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-opacity cursor-pointer shadow-sm"
              title="Basculer vers l'authentification officielle Authentik"
            >
              <LogIn size={13} />
              <span>Connexion SSO</span>
            </button>
          </div>
        ) : (
          /* Profil utilisateur authentifié via OIDC */
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
              <ShieldCheck size={12} className="text-emerald-400" />
              Authentik SSO
            </span>

            <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-[hsl(var(--accent))] border border-[hsl(var(--border))]">
              <UserIcon size={14} className="text-[hsl(var(--muted-foreground))]" />
              <span className="text-xs font-medium text-[hsl(var(--card-foreground))]">
                {displayName}
              </span>
            </div>

            <button
              onClick={() => logout()}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--accent))] transition-colors cursor-pointer border border-[hsl(var(--border))]"
              title="Déconnexion"
            >
              <LogOut size={13} />
              <span>Quitter</span>
            </button>
          </div>
        )}
      </div>
    </header>
  )
}

