/**
 * Explorateur de documents — Tableau paginé avec filtres (§14.4 Priorité haute)
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { documentsApi } from '@/api/documents'
import { workspacesApi } from '@/api/workspaces'
import { formatDate, statusColor, sensitivityColor } from '@/lib/utils'
import type { Document, Workspace } from '@/types'

const STATUS_OPTIONS = ['', 'recu', 'a_verifier', 'actif', 'archive', 'obsolete', 'rejete']
const SENSITIVITY_OPTIONS = ['', 'public', 'interne', 'confidentiel', 'secret']
const PAGE_SIZE = 20

export function DocumentsPage() {
  const navigate = useNavigate()
  const [docs, setDocs] = useState<Document[]>([])
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)

  // Filters
  const [wsFilter, setWsFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [sensitivityFilter, setSensitivityFilter] = useState('')

  const fetchDocs = async () => {
    setLoading(true)
    try {
      const res = await documentsApi.list({
        workspace_id: wsFilter || undefined,
        status: statusFilter || undefined,
        sensitivity: sensitivityFilter || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      if (Array.isArray(res)) {
        setDocs(res)
        setTotal(res.length)
      } else {
        setDocs(res.items)
        setTotal(res.total)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { workspacesApi.list().then(setWorkspaces) }, [])
  useEffect(() => { fetchDocs() }, [wsFilter, statusFilter, sensitivityFilter, offset])

  const resetFilters = () => {
    setWsFilter(''); setStatusFilter(''); setSensitivityFilter(''); setOffset(0)
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
              <select className="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm min-w-[160px]" value={wsFilter} onChange={(e) => { setWsFilter(e.target.value); setOffset(0) }}>
                <option value="">Tous</option>
                {workspaces.map((ws) => <option key={ws.id} value={ws.id}>{ws.name}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-[hsl(var(--muted-foreground))]">Statut</label>
              <select className="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setOffset(0) }}>
                {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s || 'Tous'}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-[hsl(var(--muted-foreground))]">Sensibilité</label>
              <select className="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm" value={sensitivityFilter} onChange={(e) => { setSensitivityFilter(e.target.value); setOffset(0) }}>
                {SENSITIVITY_OPTIONS.map((s) => <option key={s} value={s}>{s || 'Toutes'}</option>)}
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
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] text-left">
                  <th className="px-4 py-3">Titre</th>
                  <th className="px-4 py-3">Workspace</th>
                  <th className="px-4 py-3">Statut</th>
                  <th className="px-4 py-3">Sensibilité</th>
                  <th className="px-4 py-3">Mise à jour</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr key={doc.id} className="border-b border-[hsl(var(--border))] hover:bg-[hsl(var(--accent)/0.3)] transition-colors">
                    <td className="px-4 py-3 font-medium max-w-xs truncate">{doc.title}</td>
                    <td className="px-4 py-3 text-[hsl(var(--muted-foreground))]">{doc.workspace_slug ?? doc.workspace_id.slice(0, 8)}</td>
                    <td className="px-4 py-3"><Badge className={statusColor(doc.status)}>{doc.status}</Badge></td>
                    <td className="px-4 py-3"><Badge className={sensitivityColor(doc.sensitivity)}>{doc.sensitivity}</Badge></td>
                    <td className="px-4 py-3 text-[hsl(var(--muted-foreground))] whitespace-nowrap">{formatDate(doc.updated_at)}</td>
                    <td className="px-4 py-3">
                      <Button size="sm" variant="ghost" onClick={() => navigate(`/documents/${doc.id}`)}>
                        Détail →
                      </Button>
                    </td>
                  </tr>
                ))}
                {!loading && docs.length === 0 && (
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
    </div>
  )
}
