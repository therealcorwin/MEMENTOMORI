import { apiClient } from './client'
import type { Stats, LlmMetrics, HealthStatus } from '../types'

export const adminApi = {
  stats: async (): Promise<Stats> => {
    const { data } = await apiClient.get('/admin/stats')
    return data
  },

  health: async (): Promise<HealthStatus> => {
    const { data } = await apiClient.get('/admin/health/all')
    return data
  },

  llmMetrics: async (): Promise<LlmMetrics> => {
    const { data } = await apiClient.get('/admin/llm/metrics')
    return data
  },

  llmCosts: async () => {
    const { data } = await apiClient.get('/admin/llm/costs')
    return data
  },

  cache: async () => {
    const { data } = await apiClient.get('/admin/cache')
    return data
  },
}
