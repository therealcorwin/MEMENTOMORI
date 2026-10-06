/**
 * File de validation — Documents à vérifier (§14.4 Priorité haute)
 */
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { documentsApi } from '@/api/documents'
import { workspacesApi } from '@/api/workspaces'
import { formatDate, sensitivityColor } from '@/lib/utils'
import type { Document, Workspace } from '@/types'

export function ValidationPage() {
  const [docs, setDocs] = useState<Document[]>([])
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [selectedWs, setSelectedWs] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const fetchDocs = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await documentsApi.list({ status: 'a_verifier', workspace_id: selectedWs || undefined, limit: 50 })
      setDocs(Array.isArray(res?.items) ? res.items : Array.isArray(res) ? res : [])
    } catch (err) {
      console.error('Erreur chargement documents validation:', err)
      setError('Impossible de charger les documents à vérifier.')
      setDocs([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    workspacesApi.list()
      .then((data) => setWorkspaces(Array.isArray(data) ? data : []))
      .catch((err) => {
        console.error('Erreur chargement workspaces:', err)
        setWorkspaces([])
      })
  }, [])

  useEffect(() => { fetchDocs() }, [selectedWs])

  const handleAction = async (docId: string, status: 'actif' | 'rejete') => {
    setActionLoading(docId)
    try {
      await documentsApi.patch(docId, { status })
      setDocs((prev) => prev.filter((d) => d.id !== docId))
    } finally {
      setActionLoading(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">File de validation</h1>
        <select
          className="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm"
          value={selectedWs}
          onChange={(e) => setSelectedWs(e.target.value)}
        >
          <option value="">Tous les workspaces</option>
          {(workspaces || []).map((ws) => (
            <option key={ws.id} value={ws.id}>{ws.name}</option>
          ))}
        </select>
      </div>

      {loading && <p className="text-[hsl(var(--muted-foreground))]">Chargement…</p>}
      {error && <p className="text-red-400 text-sm">{error}</p>}
      {!loading && !error && docs.length === 0 && (
        <Card>
          <CardContent className="pt-6 text-center text-[hsl(var(--muted-foreground))]">
            ✅ Aucun document en attente de validation.
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {(docs || []).map((doc) => (
          <Card key={doc.id}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <CardTitle className="text-base">{doc.title}</CardTitle>
                  <div className="flex items-center gap-2 mt-1 text-xs text-[hsl(var(--muted-foreground))]">
                    <span>{doc.collection_name ?? doc.workspace_slug ?? doc.workspace_id ?? '—'}</span>
                    <span>·</span>
                    <span>{formatDate(doc.created_at)}</span>
                  </div>
                </div>
                <Badge className={sensitivityColor(doc.sensitivity)}>{doc.sensitivity}</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  onClick={() => handleAction(doc.id, 'actif')}
                  disabled={actionLoading === doc.id}
                >
                  ✅ Approuver
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => handleAction(doc.id, 'rejete')}
                  disabled={actionLoading === doc.id}
                >
                  ❌ Rejeter
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
