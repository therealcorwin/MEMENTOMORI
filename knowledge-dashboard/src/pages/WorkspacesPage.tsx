/**
 * Gestion des Workspaces — Listing, Création, Consultation & Suppression (§14.4)
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { workspacesApi } from '@/api/workspaces'
import { documentsApi } from '@/api/documents'
import { formatDate, statusColor, sensitivityColor } from '@/lib/utils'
import type { Workspace, Document, DocumentDetail } from '@/types'

export function WorkspacesPage() {
  const navigate = useNavigate()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // État du workspace sélectionné et de ses documents
  const [selectedWs, setSelectedWs] = useState<Workspace | null>(null)
  const [wsDocs, setWsDocs] = useState<Document[]>([])
  const [docsLoading, setDocsLoading] = useState(false)
  const [docsError, setDocsError] = useState<string | null>(null)

  // Aperçu rapide d'un document au sein de la modale
  const [previewDoc, setPreviewDoc] = useState<DocumentDetail | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  // Modale de Création de Workspace
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [createLoading, setCreateLoading] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [formName, setFormName] = useState('')
  const [formSlug, setFormSlug] = useState('')
  const [formDomain, setFormDomain] = useState<'pro' | 'perso'>('pro')
  const [formDesc, setFormDesc] = useState('')

  // Modale de Confirmation de Suppression
  const [deleteWsTarget, setDeleteWsTarget] = useState<Workspace | null>(null)
  const [deleteDocsChecked, setDeleteDocsChecked] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)

  const fetchWorkspaces = () => {
    setLoading(true)
    workspacesApi.list()
      .then((data) => {
        setWorkspaces(Array.isArray(data) ? data : [])
      })
      .catch((err) => {
        console.error('Erreur chargement workspaces:', err)
        setError('Impossible de charger les workspaces.')
        setWorkspaces([])
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchWorkspaces()
  }, [])

  // Auto-génération du slug depuis le nom
  const handleNameChange = (val: string) => {
    setFormName(val)
    if (!formSlug || formSlug === slugify(formName)) {
      setFormSlug(slugify(val))
    }
  }

  const slugify = (text: string) => {
    return text
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
  }

  // Création d'un workspace
  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formName.trim() || !formSlug.trim()) return

    setCreateLoading(true)
    setCreateError(null)
    try {
      await workspacesApi.create({
        name: formName.trim(),
        slug: formSlug.trim(),
        domain: formDomain,
        settings: formDesc.trim() ? { description: formDesc.trim() } : {}
      })
      setIsCreateOpen(false)
      setFormName('')
      setFormSlug('')
      setFormDesc('')
      fetchWorkspaces()
    } catch (err: unknown) {
      console.error('Erreur création workspace:', err)
      const msg = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : 'Échec de la création du workspace.'
      setCreateError(String(msg || 'Échec de la création du workspace.'))
    } finally {
      setCreateLoading(false)
    }
  }

  // Suppression d'un workspace
  const handleDeleteConfirm = async () => {
    if (!deleteWsTarget) return
    setDeleteLoading(true)
    try {
      await workspacesApi.delete(deleteWsTarget.id, deleteDocsChecked)
      setDeleteWsTarget(null)
      if (selectedWs?.id === deleteWsTarget.id) {
        setSelectedWs(null)
      }
      fetchWorkspaces()
    } catch (err) {
      console.error('Erreur suppression workspace:', err)
      alert('Impossible de supprimer ce workspace.')
    } finally {
      setDeleteLoading(false)
    }
  }

  // Quand un workspace est sélectionné, charger ses documents associés
  const handleSelectWorkspace = async (ws: Workspace) => {
    setSelectedWs(ws)
    setPreviewDoc(null)
    setDocsLoading(true)
    setDocsError(null)
    try {
      const res = await documentsApi.list({ workspace_id: ws.id, limit: 100 })
      setWsDocs(Array.isArray(res?.items) ? res.items : Array.isArray(res) ? res : [])
    } catch (err) {
      console.error('Erreur chargement documents workspace:', err)
      setDocsError('Impossible de charger les documents de ce workspace.')
      setWsDocs([])
    } finally {
      setDocsLoading(false)
    }
  }

  // Charger le détail d'un document
  const handlePreviewDoc = async (docId: string) => {
    setPreviewLoading(true)
    try {
      const detail = await documentsApi.get(docId)
      setPreviewDoc(detail)
    } catch (err) {
      console.error('Erreur aperçu document:', err)
    } finally {
      setPreviewLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header avec bouton Création */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Workspaces</h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
            Espaces de travail isolés. Cliquez sur une carte pour voir ses documents ou gérez leur cycle de vie.
          </p>
        </div>
        <Button onClick={() => { setIsCreateOpen(true); setCreateError(null); }} className="gap-2">
          <span>➕</span> Nouveau Workspace
        </Button>
      </div>

      {loading && <p className="text-[hsl(var(--muted-foreground))]">Chargement…</p>}
      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Grille des Workspaces */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {(workspaces || []).map((ws) => (
          <Card
            key={ws.id}
            onClick={() => handleSelectWorkspace(ws)}
            className="cursor-pointer transition-all duration-200 hover:border-[hsl(var(--primary))] hover:shadow-md flex flex-col justify-between group"
          >
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between gap-2">
                <CardTitle className="flex items-center gap-2 text-lg">
                  <span className="text-xl">🌍</span>
                  {ws.name}
                </CardTitle>
                {ws.domain && (
                  <Badge variant="outline" className="text-xs uppercase font-mono">
                    {ws.domain}
                  </Badge>
                )}
              </div>
              <code className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">{ws.slug}</code>
            </CardHeader>
            <CardContent className="space-y-4">
              {ws.description && (
                <p className="text-sm text-[hsl(var(--muted-foreground))] line-clamp-2">{ws.description}</p>
              )}

              <div className="flex items-center gap-4 text-sm pt-2 border-t border-[hsl(var(--border))]">
                <div>
                  <span className="font-semibold text-base">{ws.documents_count ?? ws.document_count ?? 0}</span>
                  <span className="text-[hsl(var(--muted-foreground))] ml-1 text-xs">documents</span>
                </div>
                {ws.collections_count !== undefined && (
                  <div>
                    <span className="font-semibold text-base">{ws.collections_count}</span>
                    <span className="text-[hsl(var(--muted-foreground))] ml-1 text-xs">collections</span>
                  </div>
                )}
                {ws.policies_count !== undefined && (
                  <div>
                    <span className="font-semibold text-base">{ws.policies_count}</span>
                    <span className="text-[hsl(var(--muted-foreground))] ml-1 text-xs">règles</span>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-between pt-1">
                <span className="text-xs text-[hsl(var(--primary))] font-medium group-hover:underline">
                  Voir documents ({ws.documents_count ?? ws.document_count ?? 0}) →
                </span>
                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => navigate(`/documents?workspace_id=${ws.id}`)}
                    className="text-xs h-7 px-2"
                  >
                    Explorateur ↗
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setDeleteWsTarget(ws)
                      setDeleteDocsChecked(false)
                    }}
                    className="text-xs h-7 px-2 text-red-400 hover:text-red-300 hover:bg-red-950/20"
                    title="Supprimer ce workspace"
                  >
                    🗑️
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {!loading && workspaces.length === 0 && !error && (
          <p className="text-[hsl(var(--muted-foreground))] col-span-3">Aucun workspace configuré.</p>
        )}
      </div>

      {/* Modale de Création d'un Workspace */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl max-w-md w-full shadow-2xl p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-[hsl(var(--border))] pb-3">
              <h2 className="text-lg font-bold flex items-center gap-2">
                <span>➕</span> Créer un Workspace
              </h2>
              <Button variant="ghost" size="sm" onClick={() => setIsCreateOpen(false)}>✕</Button>
            </div>

            {createError && (
              <p className="text-xs text-red-400 bg-red-950/30 p-2.5 rounded border border-red-500/30">
                {createError}
              </p>
            )}

            <form onSubmit={handleCreateSubmit} className="space-y-4 text-sm">
              <div className="space-y-1">
                <label className="text-xs font-medium text-[hsl(var(--muted-foreground))]">Nom du workspace *</label>
                <input
                  type="text"
                  required
                  placeholder="ex: Consulting & Conseil"
                  value={formName}
                  onChange={(e) => handleNameChange(e.target.value)}
                  className="w-full rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-sm"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[hsl(var(--muted-foreground))]">Slug unique * (a-z, 0-9, tirets)</label>
                <input
                  type="text"
                  required
                  pattern="^[a-z0-9-]+$"
                  placeholder="ex: consulting"
                  value={formSlug}
                  onChange={(e) => setFormSlug(e.target.value)}
                  className="w-full rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-sm font-mono"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[hsl(var(--muted-foreground))]">Domaine</label>
                <select
                  value={formDomain}
                  onChange={(e) => setFormDomain(e.target.value as 'pro' | 'perso')}
                  className="w-full rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-sm"
                >
                  <option value="pro">Professionnel (pro)</option>
                  <option value="perso">Personnel (perso)</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-[hsl(var(--muted-foreground))]">Description (optionnelle)</label>
                <textarea
                  placeholder="ex: Missions de conseil, livrables clients et factures..."
                  rows={2}
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  className="w-full rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-sm"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[hsl(var(--border))]">
                <Button type="button" variant="outline" size="sm" onClick={() => setIsCreateOpen(false)}>
                  Annuler
                </Button>
                <Button type="submit" size="sm" disabled={createLoading || !formName.trim() || !formSlug.trim()}>
                  {createLoading ? 'Création…' : 'Créer le workspace'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modale de Confirmation de Suppression */}
      {deleteWsTarget && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[hsl(var(--card))] border border-red-500/50 rounded-xl max-w-md w-full shadow-2xl p-6 space-y-4">
            <h2 className="text-lg font-bold text-red-400 flex items-center gap-2">
              <span>⚠️</span> Confirmer la suppression
            </h2>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              Êtes-vous sûr de vouloir supprimer définitivement le workspace{' '}
              <strong className="text-[hsl(var(--foreground))]">{deleteWsTarget.name}</strong> (<code>{deleteWsTarget.slug}</code>) ?
            </p>
            <div className="space-y-3 pt-1">
              {(deleteWsTarget.documents_count ?? deleteWsTarget.document_count ?? 0) > 0 && (
                <div className="text-xs bg-amber-950/30 text-amber-300 p-2.5 rounded border border-amber-500/30">
                  Ce workspace est actuellement associé à {deleteWsTarget.documents_count ?? deleteWsTarget.document_count} document(s).
                  Sans cocher l'option ci-dessous, la suppression du workspace conserve les documents et dissocie uniquement les liaisons.
                </div>
              )}

              <label className="flex items-start gap-2.5 p-3 rounded-lg border border-red-500/30 bg-red-950/20 cursor-pointer hover:bg-red-950/30 transition-colors">
                <input
                  type="checkbox"
                  checked={deleteDocsChecked}
                  onChange={(e) => setDeleteDocsChecked(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-red-400 text-red-600 focus:ring-red-500 cursor-pointer"
                />
                <div className="text-xs space-y-1">
                  <span className="font-semibold text-red-300 block">
                    Supprimer également tous les documents exclusifs rattachés à ce workspace
                  </span>
                  <span className="text-[hsl(var(--muted-foreground))] block leading-relaxed">
                    Cette action purgera définitivement de la base de connaissances les documents, versions et fragments vectoriels exclusifs à cet espace. (Les fichiers originaux dans Paperless-ngx resteront intacts).
                  </span>
                </div>
              </label>
            </div>
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-[hsl(var(--border))]">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDeleteWsTarget(null)}
                disabled={deleteLoading}
              >
                Annuler
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleDeleteConfirm}
                disabled={deleteLoading}
              >
                {deleteLoading ? 'Suppression…' : 'Supprimer définitivement'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Modal / Panel des documents associés au workspace sélectionné */}
      {selectedWs && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl max-w-4xl w-full max-h-[90vh] flex flex-col shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            {/* Header Modal */}
            <div className="flex items-start justify-between p-6 border-b border-[hsl(var(--border))]">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xl">🌍</span>
                  <h2 className="text-xl font-bold">{selectedWs.name}</h2>
                  {selectedWs.domain && (
                    <Badge variant="outline" className="text-xs uppercase font-mono">
                      {selectedWs.domain}
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-[hsl(var(--muted-foreground))]">
                  <code>{selectedWs.slug}</code>
                  <span>·</span>
                  <span>{docsLoading ? 'Chargement…' : `${wsDocs.length} document${wsDocs.length > 1 ? 's' : ''} associé${wsDocs.length > 1 ? 's' : ''}`}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setDeleteWsTarget(selectedWs)}
                  className="text-red-400 hover:text-red-300 hover:bg-red-950/20 text-xs"
                >
                  🗑️ Supprimer ce workspace
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setSelectedWs(null)}>✕</Button>
              </div>
            </div>

            {/* Contenu Modal */}
            <div className="p-6 overflow-y-auto space-y-4 flex-1">
              {docsLoading && (
                <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
                  Chargement des documents associés…
                </div>
              )}

              {docsError && (
                <div className="p-4 rounded-lg bg-red-950/20 border border-red-500/50 text-red-400 text-sm">
                  {docsError}
                </div>
              )}

              {!docsLoading && !docsError && wsDocs.length === 0 && (
                <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
                  Aucun document rattaché à ce workspace pour le moment.
                </div>
              )}

              {!docsLoading && wsDocs.length > 0 && (
                <div className="border border-[hsl(var(--border))] rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--accent)/0.3)] text-[hsl(var(--muted-foreground))] text-left text-xs">
                        <th className="px-4 py-3">Titre du document</th>
                        <th className="px-4 py-3">Collection</th>
                        <th className="px-4 py-3">Statut</th>
                        <th className="px-4 py-3">Sensibilité</th>
                        <th className="px-4 py-3">Date</th>
                        <th className="px-4 py-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {wsDocs.map((doc) => (
                        <tr
                          key={doc.id}
                          className="border-b border-[hsl(var(--border))] hover:bg-[hsl(var(--accent)/0.2)] transition-colors"
                        >
                          <td className="px-4 py-3 font-medium max-w-xs truncate">{doc.title}</td>
                          <td className="px-4 py-3 text-[hsl(var(--muted-foreground))] text-xs">
                            {doc.collection_name ?? 'Général'}
                          </td>
                          <td className="px-4 py-3">
                            <Badge className={statusColor(doc.status)}>{doc.status}</Badge>
                          </td>
                          <td className="px-4 py-3">
                            <Badge className={sensitivityColor(doc.sensitivity)}>{doc.sensitivity}</Badge>
                          </td>
                          <td className="px-4 py-3 text-[hsl(var(--muted-foreground))] text-xs whitespace-nowrap">
                            {formatDate(doc.updated_at || doc.created_at)}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handlePreviewDoc(doc.id)}
                              disabled={previewLoading}
                              className="text-xs h-7"
                            >
                              Détail →
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Aperçu du document sélectionné */}
              {previewDoc && (
                <div className="mt-4 p-4 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--accent)/0.15)] space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold text-sm flex items-center gap-2">
                      <span>📄</span> {previewDoc.title}
                    </h3>
                    <Button variant="ghost" size="sm" onClick={() => setPreviewDoc(null)} className="h-6 text-xs">✕ Masquer aperçu</Button>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <Badge className={statusColor(previewDoc.status)}>{previewDoc.status}</Badge>
                    <Badge className={sensitivityColor(previewDoc.sensitivity)}>{previewDoc.sensitivity}</Badge>
                    <Badge variant="outline">Scope: {previewDoc.scope}</Badge>
                  </div>
                  {previewDoc.extracted_text && (
                    <div className="p-3 bg-black/30 rounded text-xs font-mono text-[hsl(var(--muted-foreground))] whitespace-pre-wrap max-h-36 overflow-y-auto">
                      {previewDoc.extracted_text}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Footer Modal */}
            <div className="p-4 border-t border-[hsl(var(--border))] flex items-center justify-between">
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate(`/documents?workspace_id=${selectedWs.id}`)}
              >
                Ouvrir dans l'Explorateur de documents complet →
              </Button>
              <Button variant="default" size="sm" onClick={() => setSelectedWs(null)}>
                Fermer
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
