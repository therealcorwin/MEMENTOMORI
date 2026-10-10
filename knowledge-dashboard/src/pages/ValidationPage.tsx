/**
 * File de validation — Documents à vérifier (§14.4 Priorité haute)
 * Permet de consulter l'intégralité du document en cliquant dessus,
 * d'examiner le texte complet et les fragments, et de valider ou rejeter.
 */
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { documentsApi } from '@/api/documents'
import { workspacesApi } from '@/api/workspaces'
import { formatDate, sensitivityColor, statusColor, extractSourceUrl } from '@/lib/utils'
import type { Document, DocumentDetail, Workspace, Sensitivity } from '@/types'
import {
  Eye,
  Check,
  X,
  FileText,
  Layers,
  Info,
  Copy,
  CheckCircle2,
  ExternalLink,
  ChevronRight,
  Shield,
} from 'lucide-react'

const SENSITIVITY_OPTIONS: Sensitivity[] = ['public', 'interne', 'confidentiel', 'secret']

const SCOPE_OPTIONS: string[] = [
  'veille',
  'public',
  'pro',
  'dev',
  'consulting',
  'finances',
  'formation',
  'copro',
  'collectif',
  'conseil_syndical',
  'cs',
  'syndic',
  'owner',
  'admin',
]

export function ValidationPage() {
  const [docs, setDocs] = useState<Document[]>([])
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [selectedWs, setSelectedWs] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  // Consultation complète du document
  const [selectedDoc, setSelectedDoc] = useState<DocumentDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'text' | 'fragments' | 'meta'>('text')
  const [editSensitivity, setEditSensitivity] = useState<Sensitivity>('interne')
  const [editScope, setEditScope] = useState<string>('cs')
  const [isCustomScope, setIsCustomScope] = useState(false)
  const [copied, setCopied] = useState(false)
  const [feedbackMsg, setFeedbackMsg] = useState<{ text: string; type: 'success' | 'info' } | null>(null)

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

  // Ouvrir la consultation intégrale d'un document
  const handleOpenDetail = async (docId: string) => {
    setDetailLoading(true)
    setDetailError(null)
    setActiveTab('text')
    setCopied(false)
    try {
      const detail = await documentsApi.get(docId)
      setSelectedDoc(detail)
      setEditSensitivity((detail.sensitivity as Sensitivity) || 'interne')
      const docScope = detail.scope || 'public'
      setEditScope(docScope)
      setIsCustomScope(!SCOPE_OPTIONS.includes(docScope))
    } catch (err) {
      console.error('Erreur chargement détail document:', err)
      setDetailError('Impossible de charger le contenu intégral du document.')
    } finally {
      setDetailLoading(false)
    }
  }

  // Valider (Approuver) ou Rejeter le document
  const handleAction = async (
    docId: string,
    status: 'actif' | 'rejete',
    customSensitivity?: Sensitivity,
    customScope?: string
  ) => {
    setActionLoading(docId)
    try {
      const payload: { status: 'actif' | 'rejete'; sensitivity?: Sensitivity; scope?: string } = { status }
      if (customSensitivity) payload.sensitivity = customSensitivity
      if (customScope) payload.scope = customScope

      await documentsApi.patch(docId, payload)
      setDocs((prev) => prev.filter((d) => d.id !== docId))
      if (selectedDoc?.id === docId) {
        setSelectedDoc(null)
      }
      setFeedbackMsg({
        text: status === 'actif' ? '✅ Document validé et indexé avec succès.' : '❌ Document rejeté.',
        type: status === 'actif' ? 'success' : 'info',
      })
      setTimeout(() => setFeedbackMsg(null), 4000)
    } catch (err) {
      console.error(`Erreur lors de l'action ${status} sur le document:`, err)
      setError(`Échec de l'action sur le document.`)
    } finally {
      setActionLoading(null)
    }
  }

  const handleCopyText = () => {
    if (!selectedDoc?.extracted_text) return
    navigator.clipboard.writeText(selectedDoc.extracted_text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2500)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">File de validation</h1>
          <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
            Cliquez sur un document pour consulter son contenu intégral et le valider ou le rejeter.
          </p>
        </div>
        <div className="flex items-center gap-2">
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
          <Button variant="outline" size="sm" onClick={fetchDocs} disabled={loading}>
            Rafraîchir
          </Button>
        </div>
      </div>

      {feedbackMsg && (
        <div
          className={`px-4 py-2.5 rounded-lg border text-sm transition-all ${
            feedbackMsg.type === 'success'
              ? 'bg-green-950/40 border-green-800 text-green-200'
              : 'bg-zinc-900 border-zinc-700 text-zinc-200'
          }`}
        >
          {feedbackMsg.text}
        </div>
      )}

      {loading && <p className="text-[hsl(var(--muted-foreground))]">Chargement des documents à valider…</p>}
      {error && <p className="text-red-400 text-sm">{error}</p>}
      {!loading && !error && docs.length === 0 && (
        <Card>
          <CardContent className="pt-6 text-center text-[hsl(var(--muted-foreground))]">
            ✅ Aucun document en attente de validation.
          </CardContent>
        </Card>
      )}

      {/* Liste des documents en attente — cartes cliquables pour consultation intégrale */}
      <div className="space-y-3">
        {(docs || []).map((doc) => (
          <Card
            key={doc.id}
            onClick={() => handleOpenDetail(doc.id)}
            className="cursor-pointer hover:border-[hsl(var(--primary))] hover:shadow-md transition-all group"
            title="Cliquez pour consulter l'intégralité du document"
          >
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-base text-[hsl(var(--foreground))] group-hover:text-[hsl(var(--primary))] group-hover:underline truncate">
                      {doc.title}
                    </h3>
                    <ChevronRight size={16} className="text-[hsl(var(--muted-foreground))] group-hover:translate-x-1 transition-transform shrink-0" />
                  </div>
                  <div className="flex flex-wrap items-center gap-2 mt-1.5 text-xs text-[hsl(var(--muted-foreground))]">
                    <span className="font-medium text-[hsl(var(--foreground))]">
                      {doc.collection_name ?? doc.workspace_slug ?? (doc.workspace_id ? doc.workspace_id.slice(0, 8) : '—')}
                    </span>
                    <span>·</span>
                    <span>{formatDate(doc.created_at)}</span>
                    {doc.scope && (
                      <>
                        <span>·</span>
                        <Badge variant="outline" className="text-[10px] py-0 px-1.5">
                          scope: {doc.scope}
                        </Badge>
                      </>
                    )}
                  </div>
                  {(() => {
                    const cardUrl = extractSourceUrl(doc)
                    if (cardUrl) {
                      return (
                        <div
                          className="mt-2 flex items-center gap-1.5"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <span className="text-[11px] text-[hsl(var(--muted-foreground))] shrink-0 font-medium">Source originelle :</span>
                          <a
                            href={cardUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-blue-400 hover:text-blue-300 hover:underline inline-flex items-center gap-1 font-mono text-xs truncate max-w-full font-medium transition-colors"
                            title={`Ouvrir la source originelle : ${cardUrl}`}
                          >
                            <ExternalLink size={12} className="shrink-0 text-blue-400" />
                            <span className="truncate">{cardUrl}</span>
                          </a>
                        </div>
                      )
                    }
                    return null
                  })()}
                </div>
                <Badge className={sensitivityColor(doc.sensitivity)}>{doc.sensitivity}</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <span className="text-xs text-[hsl(var(--muted-foreground))] flex items-center gap-1.5 group-hover:text-[hsl(var(--foreground))] transition-colors">
                  <Eye size={14} />
                  Consulter l'intégralité du document →
                </span>

                <div
                  className="flex items-center gap-2"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Button
                    size="sm"
                    onClick={() => handleAction(doc.id, 'actif')}
                    disabled={actionLoading === doc.id}
                    className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white"
                  >
                    <Check size={14} />
                    Valider
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => handleAction(doc.id, 'rejete')}
                    disabled={actionLoading === doc.id}
                    className="flex items-center gap-1.5"
                  >
                    <X size={14} />
                    Rejeter
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Lecteur / Modale de consultation intégrale du document */}
      {(selectedDoc || detailLoading || detailError) && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl max-w-5xl w-full max-h-[92vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in-50">
            {/* Header du lecteur avec actions rapides */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 sm:p-5 border-b border-[hsl(var(--border))] gap-3 bg-[hsl(var(--card))]">
              <div className="flex-1 min-w-0 pr-2">
                <h2 className="text-lg font-bold truncate">
                  {selectedDoc ? selectedDoc.title : 'Chargement du document…'}
                </h2>
                {selectedDoc && (
                  <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-[hsl(var(--muted-foreground))]">
                    <span>Collection : {selectedDoc.collection_name ?? 'N/A'}</span>
                    <span>·</span>
                    <span>ID : {selectedDoc.id}</span>
                    <span>·</span>
                    <span>{formatDate(selectedDoc.created_at)}</span>
                  </div>
                )}
              </div>

              {selectedDoc && (
                <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => handleAction(selectedDoc.id, 'rejete')}
                    disabled={actionLoading === selectedDoc.id}
                    className="flex items-center gap-1.5"
                  >
                    <X size={14} />
                    Rejeter
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => handleAction(selectedDoc.id, 'actif', editSensitivity, editScope)}
                    disabled={actionLoading === selectedDoc.id}
                    className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white"
                  >
                    <Check size={14} />
                    Valider ce document
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => { setSelectedDoc(null); setDetailError(null) }}
                    className="h-8 w-8 p-0 ml-1"
                  >
                    ✕
                  </Button>
                </div>
              )}
            </div>

            {/* Contenu principal */}
            {detailLoading ? (
              <div className="p-16 text-center text-[hsl(var(--muted-foreground))]">
                Chargement du contenu intégral du document…
              </div>
            ) : detailError ? (
              <div className="p-8 text-center text-red-400 space-y-3">
                <p>{detailError}</p>
                <Button variant="outline" size="sm" onClick={() => setSelectedDoc(null)}>Fermer</Button>
              </div>
            ) : selectedDoc ? (
              <>
                {/* Barre de contrôle : Sensibilité, Scope, Fichier d'origine */}
                <div className="px-5 py-2.5 bg-[hsl(var(--accent)/0.15)] border-b border-[hsl(var(--border))] flex flex-wrap items-center justify-between gap-3 text-xs">
                  <div className="flex flex-wrap items-center gap-4">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[hsl(var(--muted-foreground))] font-medium">Statut :</span>
                      <Badge className={statusColor(selectedDoc.status)}>{selectedDoc.status}</Badge>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <label htmlFor="reader-sensitivity" className="text-[hsl(var(--muted-foreground))] font-medium">
                        Sensibilité :
                      </label>
                      <select
                        id="reader-sensitivity"
                        className="rounded border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-2 py-1 text-xs"
                        value={editSensitivity}
                        onChange={(e) => setEditSensitivity(e.target.value as Sensitivity)}
                      >
                        {SENSITIVITY_OPTIONS.map((opt) => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <label htmlFor="reader-scope" className="text-[hsl(var(--muted-foreground))] font-medium">
                        Scope :
                      </label>
                      {isCustomScope ? (
                        <div className="flex items-center gap-1">
                          <input
                            id="reader-scope"
                            type="text"
                            className="rounded border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-2 py-1 text-xs w-28"
                            value={editScope}
                            onChange={(e) => setEditScope(e.target.value)}
                            placeholder="ex: lot:42"
                          />
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-6 px-1.5 text-[10px]"
                            onClick={() => {
                              setIsCustomScope(false)
                              if (!SCOPE_OPTIONS.includes(editScope)) setEditScope(SCOPE_OPTIONS[0])
                            }}
                            title="Revenir à la liste déroulante"
                          >
                            Liste
                          </Button>
                        </div>
                      ) : (
                        <select
                          id="reader-scope"
                          className="rounded border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-2 py-1 text-xs"
                          value={SCOPE_OPTIONS.includes(editScope) ? editScope : '__custom__'}
                          onChange={(e) => {
                            if (e.target.value === '__custom__') {
                              setIsCustomScope(true)
                            } else {
                              setEditScope(e.target.value)
                            }
                          }}
                        >
                          {!SCOPE_OPTIONS.includes(editScope) && editScope && (
                            <option value={editScope}>{editScope} (actuel)</option>
                          )}
                          {SCOPE_OPTIONS.map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                          <option value="__custom__">✏️ Autre (personnalisé)...</option>
                        </select>
                      )}
                    </div>
                  </div>

                  {/* URL / Source originelle cliquable à droite de Scope */}
                  {(() => {
                    const targetUrl = extractSourceUrl(selectedDoc)
                    const rawRef = selectedDoc.versions?.[0]?.original_file_ref

                    if (targetUrl) {
                      return (
                        <a
                          href={targetUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 text-blue-400 hover:text-blue-300 hover:underline max-w-xs sm:max-w-md lg:max-w-lg truncate font-mono text-[11px] bg-[hsl(var(--accent)/0.3)] hover:bg-[hsl(var(--accent)/0.5)] px-2.5 py-1 rounded border border-[hsl(var(--border))] transition-colors"
                          title={`Consulter la source originelle : ${targetUrl}`}
                        >
                          <ExternalLink size={12} className="shrink-0 text-blue-400" />
                          <span className="truncate">{targetUrl}</span>
                        </a>
                      )
                    }

                    if (rawRef) {
                      return (
                        <div className="flex items-center gap-1.5 text-[hsl(var(--muted-foreground))] font-mono text-[11px] truncate max-w-sm">
                          <FileText size={12} className="shrink-0" />
                          <span className="truncate">{rawRef}</span>
                        </div>
                      )
                    }

                    return null
                  })()}
                </div>

                {/* Onglets de navigation */}
                <div className="flex border-b border-[hsl(var(--border))] px-5 bg-[hsl(var(--card))]">
                  <button
                    type="button"
                    className={`py-3 px-4 text-xs font-medium border-b-2 flex items-center gap-1.5 transition-colors ${
                      activeTab === 'text'
                        ? 'border-[hsl(var(--primary))] text-[hsl(var(--foreground))] font-semibold'
                        : 'border-transparent text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
                    }`}
                    onClick={() => setActiveTab('text')}
                  >
                    <FileText size={14} />
                    Document intégral ({selectedDoc.extracted_text ? selectedDoc.extracted_text.length : 0} caractères)
                  </button>
                  <button
                    type="button"
                    className={`py-3 px-4 text-xs font-medium border-b-2 flex items-center gap-1.5 transition-colors ${
                      activeTab === 'fragments'
                        ? 'border-[hsl(var(--primary))] text-[hsl(var(--foreground))] font-semibold'
                        : 'border-transparent text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
                    }`}
                    onClick={() => setActiveTab('fragments')}
                  >
                    <Layers size={14} />
                    Fragments & Découpage ({selectedDoc.fragments?.length ?? selectedDoc.fragments_count ?? 0})
                  </button>
                  <button
                    type="button"
                    className={`py-3 px-4 text-xs font-medium border-b-2 flex items-center gap-1.5 transition-colors ${
                      activeTab === 'meta'
                        ? 'border-[hsl(var(--primary))] text-[hsl(var(--foreground))] font-semibold'
                        : 'border-transparent text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
                    }`}
                    onClick={() => setActiveTab('meta')}
                  >
                    <Info size={14} />
                    Métadonnées & Versions
                  </button>
                </div>

                {/* Corps de consultation */}
                <div className="p-5 overflow-y-auto flex-1 space-y-4">
                  {/* Onglet 1 : Document intégral */}
                  {activeTab === 'text' && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-[hsl(var(--muted-foreground))] font-medium">
                          Texte intégral extrait du document original :
                        </span>
                        {selectedDoc.extracted_text && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={handleCopyText}
                            className="text-xs flex items-center gap-1 h-7"
                          >
                            {copied ? <CheckCircle2 size={13} className="text-green-400" /> : <Copy size={13} />}
                            {copied ? 'Copié !' : 'Copier tout le texte'}
                          </Button>
                        )}
                      </div>

                      {selectedDoc.extracted_text ? (
                        <div className="p-5 bg-[hsl(var(--accent)/0.2)] border border-[hsl(var(--border))] rounded-lg text-sm font-mono text-[hsl(var(--foreground))] whitespace-pre-wrap max-h-[58vh] overflow-y-auto leading-relaxed select-text shadow-inner">
                          {selectedDoc.extracted_text}
                        </div>
                      ) : (
                        <div className="p-12 text-center text-sm text-[hsl(var(--muted-foreground))] border border-dashed border-[hsl(var(--border))] rounded-lg">
                          Aucun texte brut extrait disponible pour ce document.
                        </div>
                      )}
                    </div>
                  )}

                  {/* Onglet 2 : Fragments */}
                  {activeTab === 'fragments' && (
                    <div className="space-y-3">
                      <p className="text-xs text-[hsl(var(--muted-foreground))]">
                        Découpage vectoriel en fragments (chunks) pour la recherche hybride :
                      </p>
                      {selectedDoc.fragments && selectedDoc.fragments.length > 0 ? (
                        <div className="space-y-3 max-h-[58vh] overflow-y-auto pr-1">
                          {selectedDoc.fragments.map((frag, idx) => (
                            <div
                              key={frag.id ?? idx}
                              className="p-3.5 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] text-xs space-y-2 shadow-sm"
                            >
                              <div className="flex items-center justify-between text-[hsl(var(--muted-foreground))]">
                                <span className="font-semibold text-[hsl(var(--foreground))]">
                                  Fragment #{frag.chunk_index ?? idx + 1}
                                  {frag.page_number ? ` · Page ${frag.page_number}` : ''}
                                </span>
                                {frag.sensitivity && (
                                  <Badge className={sensitivityColor(frag.sensitivity)}>
                                    {frag.sensitivity}
                                  </Badge>
                                )}
                              </div>
                              {frag.context_prefix && (
                                <div className="p-2 rounded bg-[hsl(var(--accent)/0.2)] text-[11px] font-mono text-[hsl(var(--muted-foreground))]">
                                  <span className="font-semibold text-[hsl(var(--foreground))]">Contexte injecté : </span>
                                  {frag.context_prefix}
                                </div>
                              )}
                              <p className="text-[hsl(var(--foreground))] whitespace-pre-wrap leading-relaxed select-text">
                                {frag.content_preview ?? frag.content}
                              </p>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="p-12 text-center text-sm text-[hsl(var(--muted-foreground))] border border-dashed border-[hsl(var(--border))] rounded-lg">
                          Aucun fragment vectorisé disponible.
                        </div>
                      )}
                    </div>
                  )}

                  {/* Onglet 3 : Métadonnées */}
                  {activeTab === 'meta' && (
                    <div className="space-y-4 text-xs">
                      <div>
                        <h4 className="font-semibold mb-2">Historique des versions ({selectedDoc.versions?.length || 0})</h4>
                        <div className="space-y-1.5">
                          {(selectedDoc.versions || []).map((v) => (
                            <div key={v.id} className="p-2.5 rounded border border-[hsl(var(--border))] flex justify-between">
                              <div>
                                <span className="font-medium">Version #{v.version_number ?? v.version ?? 1}</span>
                                {v.original_file_ref && (
                                  <span className="text-[hsl(var(--muted-foreground))] ml-2">({v.original_file_ref})</span>
                                )}
                              </div>
                              <span className="text-[hsl(var(--muted-foreground))]">{formatDate(v.created_at)}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div>
                        <h4 className="font-semibold mb-2">Métadonnées brutes (JSON)</h4>
                        <pre className="p-3 bg-[hsl(var(--accent)/0.2)] rounded-lg font-mono text-[11px] overflow-x-auto">
                          {JSON.stringify(selectedDoc.metadata || {}, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>

                {/* Footer du lecteur avec boutons de validation */}
                <div className="p-4 border-t border-[hsl(var(--border))] bg-[hsl(var(--card))] flex items-center justify-between gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setSelectedDoc(null)}
                  >
                    Fermer la consultation
                  </Button>

                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => handleAction(selectedDoc.id, 'rejete')}
                      disabled={actionLoading === selectedDoc.id}
                      className="flex items-center gap-1.5"
                    >
                      <X size={14} />
                      Rejeter
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => handleAction(selectedDoc.id, 'actif', editSensitivity, editScope)}
                      disabled={actionLoading === selectedDoc.id}
                      className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white"
                    >
                      <Check size={14} />
                      Valider ce document
                    </Button>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}
