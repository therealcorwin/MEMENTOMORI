import { apiClient } from './client'
import type { Workspace } from '../types'

export const workspacesApi = {
  list: async (): Promise<Workspace[]> => {
    const { data } = await apiClient.get('/admin/workspaces')
    if (Array.isArray(data)) return data
    if (data && Array.isArray(data.workspaces)) return data.workspaces
    return []
  },

  create: async (payload: { slug: string; name: string; domain?: 'perso' | 'pro'; settings?: Record<string, unknown> }) => {
    const { data } = await apiClient.post('/admin/workspaces', payload)
    return data
  },

  patch: async (id: string, changes: Partial<Pick<Workspace, 'name' | 'domain' | 'settings'>>) => {
    const { data } = await apiClient.patch(`/admin/workspaces/${id}`, changes)
    return data
  },

  delete: async (id: string, deleteDocuments: boolean = false) => {
    const { data } = await apiClient.delete(`/admin/workspaces/${id}`, {
      params: { delete_documents: deleteDocuments }
    })
    return data
  },
}
