/**
 * Console de recherche hybride & interrogations IA (§14.4, §16.6, §16.13)
 * Supporte la recherche ciblée par workspace ou transversale multi-workspaces via l'orchestrateur.
 */
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { searchApi } from '@/api/search'
import { workspacesApi } from '@/api/workspaces'
import { sensitivityColor } from '@/lib/utils'
import type { Workspace } from '@/types'

type Mode = 'search' | 'answer'

interface SearchFrag {
  content: string
  document_title: string
  score: number
  sensitivity: string
  page_number?: number
  workspace_name?: string
  workspace_slug?: string
}

interface SearchResultData {
  results: SearchFrag[]
  total?: number
}

interface SourceItem {
  document_title: string
  workspace?: string
  score?: number
  sensitivity?: string
}

interface AnswerResultData {
  answer: string
  confidence?: number | string
  strategy?: string
  workspace?: string
  workspaces?: string[]
  sources?: SourceItem[]
  cached?: boolean
  cache_type?: string
  warning?: string
  grounding_score?: number
  grounding_verified?: boolean
}

export function SearchPage() {
  const [query, setQuery] = useState('')
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>('all')
  const [mode, setMode] = useState<Mode>('search')
  const [result, setResult] = useState<SearchResultData | AnswerResultData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Charger la liste des workspaces disponibles
  useEffect(() => {
    workspacesApi.list()
      .then((data) => {
        const list = Array.isArray(data) ? data : []
        setWorkspaces(list)
      })
      .catch((err) => {
        console.error('Erreur chargement workspaces pour recherche:', err)
      })
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      if (selectedWorkspace === 'all') {
        // --- Recherche Multi-Workspaces (Cross-Workspaces) ---
        if (mode === 'answer') {
          // Utiliser l'orchestrateur central multi-agents (§16.13)
          const res = await searchApi.orchestrate({ query: query.trim(), top_k: 5 })
          setResult(res)
        } else {
          // Recherche hybride en parallèle sur tous les workspaces
          const settled = await Promise.allSettled(
            workspaces.map(async (ws) => {
              const res = await searchApi.search({ query: query.trim(), workspace_id: ws.id, top_k: 4 })
              const frags: SearchFrag[] = Array.isArray(res?.results) ? res.results : []
              return frags.map((f) => ({
                ...f,
                workspace_name: ws.name,
                workspace_slug: ws.slug,
              }))
            })
          )

          const combined: SearchFrag[] = []
          for (const item of settled) {
            if (item.status === 'fulfilled') {
              combined.push(...item.value)
            }
          }
          combined.sort((a, b) => (b.score || 0) - (a.score || 0))
          setResult({ results: combined, total: combined.length })
        }
      } else {
        // --- Recherche Ciblée sur un Workspace spécifique ---
        const wsObj = workspaces.find((w) => w.id === selectedWorkspace || w.slug === selectedWorkspace)
        const targetId = wsObj ? wsObj.id : selectedWorkspace

        if (mode === 'search') {
          const res = await searchApi.search({ query: query.trim(), workspace_id: targetId, top_k: 5 })
          const frags: SearchFrag[] = Array.isArray(res?.results) ? res.results : []
          const withWs = frags.map((f) => ({
            ...f,
            workspace_name: wsObj?.name,
            workspace_slug: wsObj?.slug,
          }))
          setResult({ results: withWs, total: res?.total ?? withWs.length })
        } else {
          const res = await searchApi.answer({ query: query.trim(), workspace_id: targetId, top_k: 5 })
          setResult(res)
        }
      }
    } catch (err: unknown) {
      console.error('Erreur recherche:', err)
      const msg = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
        : err instanceof Error ? err.message : 'Erreur inconnue'
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg) || 'Échec de la recherche.')
    } finally {
      setLoading(false)
    }
  }

  const selectedWsName = selectedWorkspace === 'all'
    ? 'Tous les workspaces'
    : workspaces.find((w) => w.id === selectedWorkspace || w.slug === selectedWorkspace)?.name || selectedWorkspace

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Console de recherche</h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
            Recherche sémantique vectorielle et questions / réponses IA étayées par vos documents.
          </p>
        </div>
      </div>

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Sélecteur de Mode */}
            <div className="flex items-center justify-between gap-4">
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => { setMode('search'); setResult(null); setError(null); }}
                  className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                    mode === 'search'
                      ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] shadow-sm'
                      : 'bg-[hsl(var(--accent))] hover:bg-[hsl(var(--accent))]/80 text-[hsl(var(--foreground))]'
                  }`}
                >
                  🔍 Extraits & Fragments
                </button>
                <button
                  type="button"
                  onClick={() => { setMode('answer'); setResult(null); setError(null); }}
                  className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                    mode === 'answer'
                      ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] shadow-sm'
                      : 'bg-[hsl(var(--accent))] hover:bg-[hsl(var(--accent))]/80 text-[hsl(var(--foreground))]'
                  }`}
                >
                  🤖 Réponse IA étayée
                </button>
              </div>

              {selectedWorkspace === 'all' && (
                <Badge variant="outline" className="text-xs text-[hsl(var(--primary))] border-[hsl(var(--primary))]/40">
                  ✨ Mode transversal actif
                </Badge>
              )}
            </div>

            {/* Sélecteur de Workspace */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[hsl(var(--muted-foreground))] flex items-center justify-between">
                <span>Périmètre de recherche (Workspace)</span>
                <span className="text-[10px] text-[hsl(var(--muted-foreground))]">
                  {workspaces.length} workspace(s) disponible(s)
                </span>
              </label>
              <select
                value={selectedWorkspace}
                onChange={(e) => {
                  setSelectedWorkspace(e.target.value)
                  setResult(null)
                  setError(null)
                }}
                className="w-full rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[hsl(var(--primary))]"
              >
                <option value="all">
                  🌐 Tous les workspaces (Recherche transversale / Orchestrateur multi-agents)
                </option>
                {workspaces.map((ws) => (
                  <option key={ws.id} value={ws.id}>
                    📁 {ws.name} ({ws.slug})
                  </option>
                ))}
              </select>
            </div>

            {/* Champ de Requête */}
            <div className="flex gap-2">
              <input
                type="text"
                placeholder={
                  mode === 'search'
                    ? selectedWorkspace === 'all'
                      ? 'Rechercher des extraits dans tous les workspaces (ex: appel de fonds, contrat, facture)...'
                      : `Rechercher des extraits dans ${selectedWsName}...`
                    : selectedWorkspace === 'all'
                      ? 'Posez votre question transversale (ex: Combien coûtent les charges par rapport à mon solde ?)...'
                      : `Posez votre question sur ${selectedWsName}...`
                }
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="flex-1 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[hsl(var(--primary))]"
              />
              <Button type="submit" disabled={loading || !query.trim()} className="gap-2">
                {loading ? (
                  <>
                    <span className="animate-spin text-sm">⏳</span>
                    <span>Recherche…</span>
                  </>
                ) : mode === 'search' ? (
                  '🔍 Chercher'
                ) : (
                  '🤖 Demander'
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {error && (
        <div className="p-3 bg-red-950/30 border border-red-500/30 text-red-400 text-sm rounded-lg">
          <strong>Erreur :</strong> {error}
        </div>
      )}

      {/* RÉSULTATS MODE RECHERCHE (Fragments) */}
      {result && mode === 'search' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-[hsl(var(--muted-foreground))]">
            <span>
              {(result as SearchResultData).results?.length ?? 0} extrait(s) trouvé(s)
            </span>
            <span>Trié par similarité sémantique (score décroissant)</span>
          </div>

          {(result as SearchResultData).results?.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-sm text-[hsl(var(--muted-foreground))]">
                Aucun fragment pertinent trouvé pour cette requête. Essayez de reformuler vos mots-clés.
              </CardContent>
            </Card>
          ) : (
            (result as SearchResultData).results?.map((frag, i) => (
              <Card key={i} className="hover:border-[hsl(var(--primary))]/50 transition-colors">
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="space-y-1">
                      <CardTitle className="text-sm font-semibold flex items-center gap-2">
                        <span>📄</span>
                        {frag.document_title}
                      </CardTitle>
                      {frag.workspace_name && (
                        <div className="text-xs text-[hsl(var(--muted-foreground))] flex items-center gap-1.5">
                          <span>📁 Workspace :</span>
                          <span className="font-medium text-[hsl(var(--foreground))]">{frag.workspace_name}</span>
                          <code>({frag.workspace_slug})</code>
                        </div>
                      )}
                    </div>
                    <div className="flex gap-2 items-center shrink-0">
                      <Badge className={sensitivityColor(frag.sensitivity)}>{frag.sensitivity}</Badge>
                      <span className="text-xs font-mono text-[hsl(var(--muted-foreground))] bg-[hsl(var(--muted))] px-2 py-0.5 rounded">
                        score: {typeof frag.score === 'number' ? frag.score.toFixed(3) : frag.score}
                      </span>
                    </div>
                  </div>
                  {frag.page_number && (
                    <span className="text-xs text-[hsl(var(--muted-foreground))]">Page {frag.page_number}</span>
                  )}
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-[hsl(var(--muted-foreground))] whitespace-pre-wrap font-sans leading-relaxed bg-[hsl(var(--muted))]/30 p-3 rounded-md border border-[hsl(var(--border))]/50">
                    {frag.content}
                  </p>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}

      {/* RÉSULTATS MODE RÉPONSE IA */}
      {result && mode === 'answer' && (
        <Card className="border-[hsl(var(--primary))]/40 shadow-lg">
          <CardHeader className="pb-3 border-b border-[hsl(var(--border))]">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <span>🤖</span> Synthèse et Réponse IA
              </CardTitle>
              <div className="flex items-center gap-2 flex-wrap justify-end">
                {(result as AnswerResultData).cached && (
                  (result as AnswerResultData).cache_type === 'semantic' ? (
                    <Badge className="bg-purple-500/10 text-purple-400 border border-purple-500/30 text-xs font-mono">
                      🧠 Cache Sémantique
                    </Badge>
                  ) : (
                    <Badge className="bg-blue-500/10 text-blue-400 border border-blue-500/30 text-xs font-mono">
                      ⚡ Cache Exact
                    </Badge>
                  )
                )}
                {(result as AnswerResultData).grounding_verified !== undefined && (
                  (result as AnswerResultData).grounding_verified ? (
                    <Badge className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 text-xs">
                      🛡️ Grounding certifié
                    </Badge>
                  ) : (
                    <Badge className="bg-amber-500/10 text-amber-400 border border-amber-500/30 text-xs">
                      ⚠️ Grounding partiel ({typeof (result as AnswerResultData).grounding_score === 'number' ? Math.round((result as AnswerResultData).grounding_score! * 100) : 0}%)
                    </Badge>
                  )
                )}
                {(result as AnswerResultData).strategy && (
                  <Badge variant="outline" className="text-xs capitalize font-mono">
                    stratégie : {(result as AnswerResultData).strategy}
                  </Badge>
                )}
                {(result as AnswerResultData).confidence !== undefined && (
                  <span className="text-xs text-[hsl(var(--muted-foreground))]">
                    confiance: {String((result as AnswerResultData).confidence)}
                  </span>
                )}
              </div>
            </div>
            {((result as AnswerResultData).workspace || (result as AnswerResultData).workspaces) && (
              <div className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                Espace(s) interrogé(s) :{' '}
                <strong className="text-[hsl(var(--foreground))]">
                  {Array.isArray((result as AnswerResultData).workspaces)
                    ? (result as AnswerResultData).workspaces!.join(', ')
                    : (result as AnswerResultData).workspace}
                </strong>
              </div>
            )}
          </CardHeader>
          <CardContent className="pt-4 space-y-4">
            {(result as AnswerResultData).warning && (
              <div className="p-3 bg-amber-950/20 border border-amber-500/30 text-amber-300 text-xs rounded-md">
                <strong>Avertissement :</strong> {(result as AnswerResultData).warning}
              </div>
            )}
            <div className="text-sm leading-relaxed whitespace-pre-wrap">
              {(result as AnswerResultData).answer}
            </div>

            {(result as AnswerResultData).sources && (result as AnswerResultData).sources!.length > 0 && (
              <div className="pt-4 border-t border-[hsl(var(--border))] text-xs text-[hsl(var(--muted-foreground))] space-y-2">
                <strong className="text-[hsl(var(--foreground))] block">
                  Sources et documents cités ({(result as AnswerResultData).sources!.length}) :
                </strong>
                <ul className="space-y-1 list-disc list-inside">
                  {(result as AnswerResultData).sources!.map((s, idx) => (
                    <li key={idx}>
                      <span className="font-medium text-[hsl(var(--foreground))]">{s.document_title}</span>
                      {s.workspace && <span className="ml-1 text-[hsl(var(--muted-foreground))]">[{s.workspace}]</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
