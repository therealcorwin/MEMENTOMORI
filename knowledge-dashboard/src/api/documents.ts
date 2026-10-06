import { apiClient } from './client'
import type { Document, DocumentDetail, PaginatedResponse } from '../types'

export interface DocumentFilters {
  workspace_id?: string
  status?: string
  sensitivity?: string
  limit?: number
  offset?: number
}

export const documentsApi = {
  list: async (filters: DocumentFilters = {}): Promise<PaginatedResponse<Document>> => {
    const { data } = await apiClient.get('/admin/documents', { params: filters })
    if (Array.isArray(data)) {
      return {
        items: data,
        total: data.length,
        limit: filters.limit ?? 50,
        offset: filters.offset ?? 0,
      }
    }
    return {
      items: Array.isArray(data?.items) ? data.items : [],
      total: data?.total ?? (data?.items?.length || 0),
      limit: data?.limit ?? filters.limit ?? 50,
      offset: data?.offset ?? filters.offset ?? 0,
    }
  },

  get: async (id: string): Promise<DocumentDetail> => {
    const { data } = await apiClient.get(`/admin/documents/${id}`)
    return data
  },

  patch: async (id: string, changes: Partial<Pick<Document, 'status' | 'sensitivity' | 'scope'>>) => {
    const { data } = await apiClient.patch(`/admin/documents/${id}`, changes)
    return data
  },

  delete: async (id: string) => {
    const { data } = await apiClient.delete(`/admin/documents/${id}`)
    return data
  },
}
