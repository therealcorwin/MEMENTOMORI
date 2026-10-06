// Types partagés pour l'application dashboard

export type Sensitivity = 'public' | 'interne' | 'confidentiel' | 'secret'
export type DocumentStatus = 'recu' | 'a_verifier' | 'actif' | 'archive' | 'obsolete' | 'rejete' | 'supprime'
export type Role = 'admin' | 'owner' | 'cs' | 'coproprietaire' | 'reader' | 'contributor'

export interface Workspace {
  id: string
  slug: string
  name: string
  description?: string
  document_count?: number
  created_at: string
}

export interface Document {
  id: string
  title: string
  status: DocumentStatus
  sensitivity: Sensitivity
  scope: string
  workspace_id: string
  workspace_slug?: string
  source_url?: string
  created_at: string
  updated_at: string
  fragment_count?: number
}

export interface DocumentDetail extends Document {
  content_preview?: string
  versions: DocumentVersion[]
  fragments?: Fragment[]
}

export interface DocumentVersion {
  id: string
  version: number
  created_at: string
  checksum?: string
}

export interface Fragment {
  id: string
  content: string
  page_number?: number
  sensitivity: Sensitivity
  scope: string
}

export interface SearchResult {
  fragment_id: string
  document_id: string
  document_title: string
  content: string
  score: number
  page_number?: number
  sensitivity: Sensitivity
  scope: string
}

export interface Stats {
  workspaces: number
  documents: number
  fragments: number
  pending_validation: number
  total_cache_hits: number
  total_estimated_llm_cost_usd: number
  status_distribution: Record<string, number>
  documents_by_workspace: WorkspaceDocStat[]
  recent_ingestions: RecentIngestion[]
}

export interface WorkspaceDocStat {
  slug: string
  name: string
  count: number
}

export interface RecentIngestion {
  id: string
  title: string
  status: DocumentStatus
  created_at: string
}

export interface AuditLog {
  id: string
  created_at: string
  principal_id: string
  action: string
  workspace_id?: string
  target_id?: string
  details?: Record<string, unknown>
}

export interface LlmMetrics {
  total_calls: number
  total_tokens_input: number
  total_tokens_output: number
  average_latency_ms: number
  calls_by_model: Record<string, number>
  calls_by_request_type: Record<string, number>
}

export interface LlmCosts {
  total_estimated_cost_usd: number
  cost_by_workspace: Record<string, number>
}

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'down'
  timestamp: string
  services: Record<string, ServiceHealthItem>
}

export interface ServiceHealthItem {
  status: 'ok' | 'error' | 'warning'
  latency_ms: number
  error: string | null
}

export interface ApiError {
  detail: string
  status_code?: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}
