import { apiClient } from './client'
import type { AuditLog, PaginatedResponse } from '../types'

export interface AuditFilters {
  workspace_id?: string
  principal_id?: string
  action?: string
  limit?: number
  offset?: number
}

export const auditApi = {
  list: async (filters: AuditFilters = {}): Promise<PaginatedResponse<AuditLog>> => {
    const { data } = await apiClient.get('/admin/audit', { params: filters })
    return data
  },
}
