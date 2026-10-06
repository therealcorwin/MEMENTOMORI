// Types partagés pour l'application dashboard

export type Sensitivity = 'public' | 'interne' | 'confidentiel' | 'secret'
export type DocumentStatus = 'recu' | 'a_verifier' | 'actif' | 'archive' | 'obsolete' | 'rejete' | 'supprime'
export type Role = 'admin' | 'owner' | 'cs' | 'coproprietaire' | 'reader' | 'contributor'

export interface Workspace {
  id: string
  slug: string
  name: string
  domain?: 'perso' | 'pro'
  description?: string
  settings?: Record<string, unknown>
  document_count?: number
  documents_count?: number
  collections_count?: number
  policies_count?: number
  created_at: string
}

export interface Document {
  id: string
  title: string
  status: DocumentStatus
  sensitivity: Sensitivity
  scope: string
  collection_id?: string
  collection_name?: string
  workspace_id?: string
  workspace_slug?: string
  source_url?: string
  version?: number
  is_active?: boolean
  created_at: string
  updated_at?: string
  fragment_count?: number
  metadata?: Record<string, unknown>
}

export interface DocumentDetail extends Document {
  content_preview?: string
  extracted_text?: string
  fragments_count?: number
  versions: DocumentVersion[]
  fragments?: Fragment[]
}

export interface DocumentVersion {
  id: string
  version?: number
  version_number?: number
  original_file_ref?: string
  created_at: string
  checksum?: string
}

export interface Fragment {
  id: string
  content?: string
  content_preview?: string
  chunk_index?: number
  context_prefix?: string
  page_number?: number
  sensitivity?: Sensitivity
  scope?: string
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
  id: string | number
  created_at: string
  principal_id?: string
  principal_name?: string
  principal_type?: string
  action: string
  workspace_id?: string
  workspace_name?: string
  workspace_slug?: string
  target_type?: string
  target_id?: string
  target_name?: string
  summary?: string
  detail?: Record<string, unknown>
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
