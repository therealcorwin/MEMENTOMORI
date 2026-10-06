import { apiClient } from './client'
import type { Workspace } from '../types'

export const workspacesApi = {
  list: async (): Promise<Workspace[]> => {
    const { data } = await apiClient.get('/admin/workspaces')
    return data
  },

  create: async (payload: { slug: string; name: string; description?: string }) => {
    const { data } = await apiClient.post('/admin/workspaces', payload)
    return data
  },

  patch: async (id: string, changes: Partial<Pick<Workspace, 'name' | 'description'>>) => {
    const { data } = await apiClient.patch(`/admin/workspaces/${id}`, changes)
    return data
  },
}
