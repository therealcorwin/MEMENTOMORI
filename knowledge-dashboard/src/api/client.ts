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

// Injecte le token JWT à chaque requête
apiClient.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Redirige vers /login si le token est expiré (401)
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      sessionStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)
