import { apiClient } from './client'
import type { AuditLog, PaginatedResponse } from '../types'

export interface AuditFilters {
  workspace_id?: string
  principal_id?: string
  action?: string
  search?: string
  limit?: number
  offset?: number
}

export const auditApi = {
  list: async (filters: AuditFilters = {}): Promise<PaginatedResponse<AuditLog>> => {
    const { data } = await apiClient.get('/admin/audit', { params: filters })
    if (Array.isArray(data)) {
      return {
        items: data,
        total: data.length,
        limit: filters.limit ?? 25,
        offset: filters.offset ?? 0,
      }
    }
    return {
      items: Array.isArray(data?.items) ? data.items : [],
      total: data?.total ?? (data?.items?.length || 0),
      limit: data?.limit ?? filters.limit ?? 25,
      offset: data?.offset ?? filters.offset ?? 0,
    }
  },
}
