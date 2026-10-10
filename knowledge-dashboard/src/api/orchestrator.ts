/**
 * Client API pour l'Orchestrateur Universel Multi-Agents (§8, §16.13, Sprint 14).
 */
import { apiClient } from './client'

export interface OrchestrateSource {
  document_title: string
  workspace?: string
  score?: number
  sensitivity?: string
}

export interface OrchestrateResponse {
  strategy: 'single' | 'multi' | 'unknown'
  workspace?: string
  workspaces?: string[]
  agent?: string
  answer: string
  confidence?: string | number
  sources?: OrchestrateSource[]
  results_count?: number
}

export interface ClassifyResponse {
  query: string
  strategy: string
  workspaces: Array<{
    slug: string
    confidence: number
    role: string
    description?: string
  }>
  raw_output?: string
}

export async function orchestrateQuery(
  query: string,
  topK: number = 5,
): Promise<OrchestrateResponse> {
  const resp = await apiClient.post<OrchestrateResponse>('/orchestrate/query', {
    query,
    top_k: topK,
  })
  return resp.data
}

export async function classifyQuery(query: string): Promise<ClassifyResponse> {
  const resp = await apiClient.post<ClassifyResponse>('/orchestrate/classify', {
    query,
  })
  return resp.data
}

