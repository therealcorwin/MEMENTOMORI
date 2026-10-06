import { apiClient } from './client'

export interface SearchRequest {
  query: string
  workspace_id: string
  top_k?: number
}

export interface AnswerRequest {
  question: string
  workspace_id: string
}

export const searchApi = {
  search: async (req: SearchRequest) => {
    const { data } = await apiClient.post('/search', req)
    return data
  },

  answer: async (req: AnswerRequest) => {
    const { data } = await apiClient.post('/answer', req)
    return data
  },
}
