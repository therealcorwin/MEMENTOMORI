/**
 * Explorateur de documents — Tableau paginé avec filtres & Modal de Détail (§14.4 Priorité haute)
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { documentsApi } from '@/api/documents'
import { workspacesApi } from '@/api/workspaces'
import { formatDate, statusColor, sensitivityColor } from '@/lib/utils'
import type { Document, DocumentDetail, Workspace } from '@/types'

const STATUS_OPTIONS = ['', 'recu', 'a_verifier', 'actif', 'archive', 'obsolete', 'rejete']
const SENSITIVITY_OPTIONS = ['', 'public', 'interne', 'confidentiel', 'secret']
const PAGE_SIZE = 20

export function DocumentsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [docs, setDocs] = useState<Document[]>([])
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [wsFilter, setWsFilter] = useState(searchParams.get('workspace_id') || '')
  const [statusFilter, setStatusFilter] = useState('')
  const [sensitivityFilter, setSensitivityFilter] = useState('')

  // Detail Modal State
  const [selectedDoc, setSelectedDoc] = useState<DocumentDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const fetchDocs = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await documentsApi.list({
        workspace_id: wsFilter || undefined,
        status: statusFilter || undefined,
        sensitivity: sensitivityFilter || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      setDocs(Array.isArray(res?.items) ? res.items : Array.isArray(res) ? res : [])
      setTotal(res?.total ?? (Array.isArray(res) ? res.length : 0))
    } catch (err) {
      console.error('Erreur chargement documents:', err)
      setError('Impossible de charger les documents.')
      setDocs([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    workspacesApi.list()
      .then((data) => {
        const list = Array.isArray(data) ? data : []
        setWorkspaces(list)
        const param = searchParams.get('workspace_id')
        if (param) {
          const match = list.find((w) => w.id === param || w.slug === param)
          if (match && match.id !== wsFilter) {
            setWsFilter(match.id)
          }
        }
      })
      .catch((err) => {
        console.error('Erreur chargement workspaces:', err)
        setWorkspaces([])
      })
  }, [searchParams])

  useEffect(() => {
    fetchDocs()
  }, [wsFilter, statusFilter, sensitivityFilter, offset])

  const handleWsChange = (val: string) => {
    setWsFilter(val)
    setOffset(0)
    if (val) {
      setSearchParams({ workspace_id: val })
    } else {
      setSearchParams({})
    }
  }

  const resetFilters = () => {
    setWsFilter('')
    setStatusFilter('')
    setSensitivityFilter('')
    setOffset(0)
    setSearchParams({})
  }

  const handleOpenDetail = async (docId: string) => {
    setDetailLoading(true)
    try {
      const detail = await documentsApi.get(docId)
      setSelectedDoc(detail)
    } catch (err) {
      console.error('Erreur chargement détail document:', err)
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Explorateur de documents</h1>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4 pb-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-[hsl(var(--muted-foreground))]">Workspace</label>
              <select
                className="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm min-w-[160px]"
                value={wsFilter}
                onChange={(e) => handleWsChange(e.target.value)}
              >
                <option value="">Tous</option>
                {(workspaces || []).map((ws) => (
                  <option key={ws.id} value={ws.id}>{ws.name}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-[hsl(var(--muted-foreground))]">Statut</label>
              <select
                className="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm"
                value={statusFilter}
                onChange={(e) => { setStatusFilter(e.target.value); setOffset(0) }}
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s || 'Tous'}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-[hsl(var(--muted-foreground))]">Sensibilité</label>
              <select
                className="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm"
                value={sensitivityFilter}
                onChange={(e) => { setSensitivityFilter(e.target.value); setOffset(0) }}
              >
                {SENSITIVITY_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s || 'Toutes'}</option>
                ))}
              </select>
            </div>
            <Button variant="outline" size="sm" onClick={resetFilters}>Réinitialiser</Button>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle>
            {loading ? 'Chargement…' : `${total} document${total > 1 ? 's' : ''}`}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {error && <p className="text-red-400 text-sm p-4">{error}</p>}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] text-left">
                  <th className="px-4 py-3">Titre</th>
                  <th className="px-4 py-3">Collection / Workspace</th>
                  <th className="px-4 py-3">Statut</th>
                  <th className="px-4 py-3">Sensibilité</th>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {(docs || []).map((doc) => (
                  <tr key={doc.id} className="border-b border-[hsl(var(--border))] hover:bg-[hsl(var(--accent)/0.3)] transition-colors">
                    <td className="px-4 py-3 font-medium max-w-xs truncate">{doc.title}</td>
                    <td className="px-4 py-3 text-[hsl(var(--muted-foreground))]">
                      {doc.collection_name ?? doc.workspace_slug ?? (doc.workspace_id ? doc.workspace_id.slice(0, 8) : '—')}
                    </td>
                    <td className="px-4 py-3"><Badge className={statusColor(doc.status)}>{doc.status}</Badge></td>
                    <td className="px-4 py-3"><Badge className={sensitivityColor(doc.sensitivity)}>{doc.sensitivity}</Badge></td>
                    <td className="px-4 py-3 text-[hsl(var(--muted-foreground))] whitespace-nowrap">
                      {formatDate(doc.updated_at || doc.created_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleOpenDetail(doc.id)}
                        disabled={detailLoading}
                      >
                        Détail →
                      </Button>
                    </td>
                  </tr>
                ))}
                {!loading && docs.length === 0 && !error && (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-[hsl(var(--muted-foreground))]">Aucun document trouvé.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-[hsl(var(--border))]">
              <span className="text-sm text-[hsl(var(--muted-foreground))]">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} sur {total}
              </span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>← Préc.</Button>
                <Button size="sm" variant="outline" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Suiv. →</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Modal Détail du document */}
      {selectedDoc && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl">
            <div className="flex items-start justify-between p-6 border-b border-[hsl(var(--border))]">
              <div>
                <h2 className="text-lg font-bold">{selectedDoc.title}</h2>
                <div className="flex items-center gap-2 mt-1 text-xs text-[hsl(var(--muted-foreground))]">
                  <span>Collection: {selectedDoc.collection_name ?? 'N/A'}</span>
                  <span>·</span>
                  <span>ID: {selectedDoc.id.slice(0, 8)}…</span>
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setSelectedDoc(null)}>✕</Button>
            </div>

            <div className="p-6 overflow-y-auto space-y-4 flex-1">
              <div className="flex items-center gap-2">
                <Badge className={statusColor(selectedDoc.status)}>{selectedDoc.status}</Badge>
                <Badge className={sensitivityColor(selectedDoc.sensitivity)}>{selectedDoc.sensitivity}</Badge>
                <Badge variant="outline">Scope: {selectedDoc.scope}</Badge>
                {selectedDoc.version !== undefined && (
                  <Badge variant="outline">v{selectedDoc.version}</Badge>
                )}
              </div>

              {selectedDoc.extracted_text && (
                <div>
                  <h3 className="text-sm font-semibold mb-1">Extrait du texte indexé</h3>
                  <div className="p-3 bg-[hsl(var(--accent)/0.3)] rounded-lg text-xs font-mono text-[hsl(var(--muted-foreground))] whitespace-pre-wrap max-h-48 overflow-y-auto">
                    {selectedDoc.extracted_text}
                  </div>
                </div>
              )}

              {selectedDoc.fragments && selectedDoc.fragments.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-2">
                    Fragments ({selectedDoc.fragments.length})
                  </h3>
                  <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                    {selectedDoc.fragments.map((frag, idx) => (
                      <div key={frag.id ?? idx} className="p-2.5 rounded border border-[hsl(var(--border))] text-xs space-y-1">
                        <div className="flex items-center justify-between text-[hsl(var(--muted-foreground))]">
                          <span>Chunk #{frag.chunk_index ?? idx + 1} {frag.page_number ? `· Page ${frag.page_number}` : ''}</span>
                          {frag.sensitivity && <Badge className={sensitivityColor(frag.sensitivity)}>{frag.sensitivity}</Badge>}
                        </div>
                        {frag.context_prefix && (
                          <div className="font-semibold text-xs text-[hsl(var(--foreground))]">{frag.context_prefix}</div>
                        )}
                        <p className="text-[hsl(var(--muted-foreground))] whitespace-pre-wrap">
                          {frag.content_preview ?? frag.content}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="p-4 border-t border-[hsl(var(--border))] flex justify-end">
              <Button variant="outline" size="sm" onClick={() => setSelectedDoc(null)}>Fermer</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
