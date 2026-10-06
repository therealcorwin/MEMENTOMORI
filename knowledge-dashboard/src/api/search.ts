import { apiClient } from './client'

export interface SearchRequest {
  query: string
  workspace_id: string
  top_k?: number
}

export interface AnswerRequest {
  query?: string
  question?: string
  workspace_id: string
  top_k?: number
}

export interface OrchestrateRequest {
  query: string
  top_k?: number
}

export const searchApi = {
  search: async (req: SearchRequest) => {
    const { data } = await apiClient.post('/search', req)
    return data
  },

  answer: async (req: AnswerRequest) => {
    const payload = {
      query: req.query || req.question || '',
      workspace_id: req.workspace_id,
      top_k: req.top_k ?? 5,
    }
    const { data } = await apiClient.post('/answer', payload)
    return data
  },

  orchestrate: async (req: OrchestrateRequest) => {
    const { data } = await apiClient.post('/orchestrate/query', req)
    return data
  },
}
