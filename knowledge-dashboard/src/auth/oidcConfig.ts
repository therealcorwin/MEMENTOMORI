/**
 * Configuration OIDC Authentik pour knowledge-dashboard (Sprint 8, Tâche 8.2)
 * Utilise oidc-client-ts pour le flux Authorization Code avec PKCE.
 */
import { UserManager, type UserManagerSettings, WebStorageStateStore } from 'oidc-client-ts'

// Base Authority Authentik (détectée dynamiquement ou injectée via VITE_OIDC_AUTHORITY)
const getAuthority = (): string => {
  if (import.meta.env.VITE_OIDC_AUTHORITY) {
    return import.meta.env.VITE_OIDC_AUTHORITY
  }
  const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  if (isLocal) {
    return 'http://localhost:9000/application/o/knowledge-dashboard/'
  }
  return `https://auth.${window.location.host.replace(/^dashboard\./, '')}/application/o/knowledge-dashboard/`
}

export const oidcSettings: UserManagerSettings = {
  authority: getAuthority(),
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID || 'knowledge-dashboard',
  redirect_uri: `${window.location.origin}/callback`,
  post_logout_redirect_uri: `${window.location.origin}/`,
  response_type: 'code',
  scope: 'openid profile email',
  automaticSilentRenew: true,
  silent_redirect_uri: `${window.location.origin}/silent-renew.html`,
  loadUserInfo: true,
  monitorSession: false,
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
}

export const userManager = new UserManager(oidcSettings)

