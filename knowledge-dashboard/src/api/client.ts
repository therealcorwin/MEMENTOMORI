/**
 * Client HTTP Axios pour knowledge-api.
 * Injecte automatiquement le JWT Bearer depuis sessionStorage.
 * Redirige vers /login en cas de 401.
 */
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/v1'

export const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// Injecte le token JWT à chaque requête (ou le principal sélectionné en mode dev)
apiClient.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  } else if (import.meta.env.DEV || sessionStorage.getItem('dev_bypass') === 'true') {
    const activePrincipal = sessionStorage.getItem('dev_principal') || 'admin_user'
    config.headers['X-Dev-Principal'] = activePrincipal
  }
  return config
})

// En cas d'erreur 401
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !import.meta.env.DEV && sessionStorage.getItem('dev_bypass') !== 'true') {
      sessionStorage.removeItem('access_token')
      window.location.href = '/'
    }
    return Promise.reject(error)
  },
)
