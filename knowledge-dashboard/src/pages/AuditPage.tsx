/**
 * Piste d'audit — Journal complet des événements et opérations (§14.4, §14.7)
 * Affiche les identités réelles, résumés contextuels, filtres conviviaux et panneau d'inspection.
 */
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { auditApi, type AuditFilters } from '@/api/audit'
import { workspacesApi } from '@/api/workspaces'
import { formatDate } from '@/lib/utils'
import type { AuditLog, Workspace } from '@/types'

const PAGE_SIZE = 25

export function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)

  // Filtres
  const [filterAction, setFilterAction] = useState<string>('')
  const [filterWorkspace, setFilterWorkspace] = useState<string>('')
  const [filterPrincipal, setFilterPrincipal] = useState<string>('')
  const [searchQuery, setSearchQuery] = useState<string>('')

  // Détail inspecté dans la modale
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null)
  const [copied, setCopied] = useState(false)

  // Charger les workspaces pour le filtre déroulant
  useEffect(() => {
    workspacesApi.list()
      .then((data) => setWorkspaces(Array.isArray(data) ? data : []))
      .catch((err) => console.error('Erreur chargement workspaces:', err))
  }, [])

  const fetchLogs = async () => {
    setLoading(true)
    try {
      const filters: AuditFilters = {
        limit: PAGE_SIZE,
        offset,
      }
      if (filterAction) filters.action = filterAction
      if (filterWorkspace) filters.workspace_id = filterWorkspace
      if (filterPrincipal) filters.principal_id = filterPrincipal
      if (searchQuery.trim()) filters.search = searchQuery.trim()

      const res = await auditApi.list(filters)
      setLogs(Array.isArray(res?.items) ? res.items : Array.isArray(res) ? res : [])
      setTotal(res?.total ?? (Array.isArray(res) ? res.length : 0))
    } catch (err) {
      console.error('Erreur chargement logs audit:', err)
      setLogs([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLogs()
  }, [filterAction, filterWorkspace, filterPrincipal, offset])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setOffset(0)
    fetchLogs()
  }

  const handleResetFilters = () => {
    setFilterAction('')
    setFilterWorkspace('')
    setFilterPrincipal('')
    setSearchQuery('')
    setOffset(0)
  }

  const handleCopyJson = (data: unknown) => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Formatage visuel des actions
  const getActionBadge = (action: string) => {
    if (action === 'search') {
      return { label: 'Recherche', color: 'bg-blue-950/70 text-blue-300 border-blue-500/40', icon: '🔍' }
    }
    if (action === 'answer') {
      return { label: 'Réponse IA', color: 'bg-purple-950/70 text-purple-300 border-purple-500/40', icon: '🤖' }
    }
    if (action.startsWith('delete')) {
      return { label: action, color: 'bg-red-950/70 text-red-300 border-red-500/40', icon: '🗑️' }
    }
    if (action.startsWith('create')) {
      return { label: action, color: 'bg-emerald-950/70 text-emerald-300 border-emerald-500/40', icon: '➕' }
    }
    if (action.startsWith('validate')) {
      return { label: 'Validation', color: 'bg-green-950/70 text-green-300 border-green-500/40', icon: '✅' }
    }
    if (action.startsWith('reject')) {
      return { label: 'Rejet', color: 'bg-rose-950/70 text-rose-300 border-rose-500/40', icon: '❌' }
    }
    if (action.startsWith('update') || action.startsWith('patch')) {
      return { label: action, color: 'bg-amber-950/70 text-amber-300 border-amber-500/40', icon: '✏️' }
    }
    return { label: action, color: 'bg-slate-800 text-slate-300 border-slate-600/40', icon: '⚙️' }
  }

  // KPI compteurs sur le lot affiché
  const countSearch = logs.filter((l) => l.action === 'search').length
  const countAnswer = logs.filter((l) => l.action === 'answer').length
  const countAdmin = logs.filter((l) => !['search', 'answer'].includes(l.action)).length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Piste d'audit</h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
            Traçabilité intégrale des requêtes, générations IA et opérations administratives (§14.7).
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchLogs} disabled={loading} className="gap-2">
          <span>🔄</span> Rafraîchir
        </Button>
      </div>

      {/* Cartes KPIs de synthèse */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="text-xs text-[hsl(var(--muted-foreground))] uppercase font-medium">Total Événements</div>
          <div className="text-2xl font-bold mt-1">{total}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-blue-400 uppercase font-medium">🔍 Recherches</div>
          <div className="text-2xl font-bold mt-1 text-blue-300">{countSearch}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-purple-400 uppercase font-medium">🤖 Réponses RAG</div>
          <div className="text-2xl font-bold mt-1 text-purple-300">{countAnswer}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-amber-400 uppercase font-medium">🛡️ Opérations Admin</div>
          <div className="text-2xl font-bold mt-1 text-amber-300">{countAdmin}</div>
        </Card>
      </div>

      {/* Barre de filtres conviviaux */}
      <Card>
        <CardContent className="pt-4 pb-4">
          <form onSubmit={handleSearchSubmit} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {/* Filtre Action */}
              <div className="space-y-1">
                <label className="text-xs text-[hsl(var(--muted-foreground))]">Type d'action</label>
                <select
                  value={filterAction}
                  onChange={(e) => { setFilterAction(e.target.value); setOffset(0); }}
                  className="w-full rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm"
                >
                  <option value="">Toutes les actions</option>
                  <option value="search">🔍 Recherches (search)</option>
                  <option value="answer">🤖 Réponses IA (answer)</option>
                  <option value="delete_workspace">🗑️ Suppressions workspace</option>
                  <option value="create_workspace">➕ Créations workspace</option>
                  <option value="update_workspace">✏️ Modifications workspace</option>
                  <option value="delete_document">🗑️ Suppressions document</option>
                  <option value="validate_document">✅ Validations document</option>
                </select>
              </div>

              {/* Filtre Workspace */}
              <div className="space-y-1">
                <label className="text-xs text-[hsl(var(--muted-foreground))]">Workspace</label>
                <select
                  value={filterWorkspace}
                  onChange={(e) => { setFilterWorkspace(e.target.value); setOffset(0); }}
                  className="w-full rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm"
                >
                  <option value="">Tous les workspaces</option>
                  {workspaces.map((ws) => (
                    <option key={ws.id} value={ws.id}>
                      📁 {ws.name} ({ws.slug})
                    </option>
                  ))}
                </select>
              </div>

              {/* Filtre Utilisateur / Agent */}
              <div className="space-y-1">
                <label className="text-xs text-[hsl(var(--muted-foreground))]">Auteur (Principal)</label>
                <select
                  value={filterPrincipal}
                  onChange={(e) => { setFilterPrincipal(e.target.value); setOffset(0); }}
                  className="w-full rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm"
                >
                  <option value="">Tous les auteurs</option>
                  <option value="admin_user">👤 admin_user</option>
                  <option value="dev_admin">👤 dev_admin</option>
                  <option value="copro_user">👤 copro_user</option>
                  <option value="sante_user">👤 sante_user</option>
                  <option value="csbot">🤖 csbot (Agent Copro)</option>
                  <option value="agent-finances">🤖 agent-finances</option>
                  <option value="agent-sante">🤖 agent-sante</option>
                  <option value="agent-dev">🤖 agent-dev</option>
                </select>
              </div>

              {/* Recherche libre par mot-clé */}
              <div className="space-y-1">
                <label className="text-xs text-[hsl(var(--muted-foreground))]">Recherche textuelle</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder="Requête, document, nom…"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm"
                  />
                  <Button type="submit" size="sm" variant="default">
                    Filtrer
                  </Button>
                </div>
              </div>
            </div>

            {/* Bouton de réinitialisation */}
            {(filterAction || filterWorkspace || filterPrincipal || searchQuery) && (
              <div className="flex items-center justify-end pt-1">
                <Button size="sm" variant="ghost" onClick={handleResetFilters} className="text-xs h-7">
                  ✕ Réinitialiser tous les filtres
                </Button>
              </div>
            )}
          </form>
        </CardContent>
      </Card>

      {/* Tableau d'Audit Principal */}
      <Card>
        <CardHeader className="py-3 px-4 border-b border-[hsl(var(--border))] flex flex-row items-center justify-between">
          <CardTitle className="text-base font-semibold">
            {loading ? 'Chargement des entrées…' : `${total} événement${total > 1 ? 's' : ''} enregistré${total > 1 ? 's' : ''}`}
          </CardTitle>
          <span className="text-xs text-[hsl(var(--muted-foreground))]">
            Cliquez sur une ligne pour inspecter son détail
          </span>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]/40 text-[hsl(var(--muted-foreground))] text-xs font-semibold">
                  <th className="px-4 py-3 whitespace-nowrap">Date & Heure</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Auteur</th>
                  <th className="px-4 py-3">Workspace</th>
                  <th className="px-4 py-3">Résumé de l'opération</th>
                  <th className="px-4 py-3 text-right">Détails</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[hsl(var(--border))]">
                {(logs || []).map((log) => {
                  const badge = getActionBadge(log.action)
                  const isBot = log.principal_type === 'app' || (log.principal_name && log.principal_name.toLowerCase().includes('bot'))
                  const pName = log.principal_name || (log.principal_id ? `${String(log.principal_id).slice(0, 8)}…` : 'Système')
                  const wsName = log.workspace_name || (log.workspace_slug ? log.workspace_slug : (log.workspace_id ? `${String(log.workspace_id).slice(0, 8)}…` : '—'))

                  return (
                    <tr
                      key={String(log.id)}
                      onClick={() => setSelectedLog(log)}
                      className="cursor-pointer hover:bg-[hsl(var(--accent))]/40 transition-colors group"
                    >
                      {/* Date */}
                      <td className="px-4 py-3 text-xs text-[hsl(var(--muted-foreground))] whitespace-nowrap font-mono">
                        {formatDate(log.created_at)}
                      </td>

                      {/* Action */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${badge.color}`}>
                          <span>{badge.icon}</span>
                          <span>{log.action}</span>
                        </span>
                      </td>

                      {/* Auteur (Principal) */}
                      <td className="px-4 py-3 whitespace-nowrap text-xs">
                        <span className="inline-flex items-center gap-1.5 font-medium">
                          <span>{isBot ? '🤖' : '👤'}</span>
                          <span className={isBot ? 'text-indigo-300 font-mono' : 'text-[hsl(var(--foreground))] font-mono'}>
                            {pName}
                          </span>
                        </span>
                      </td>

                      {/* Workspace */}
                      <td className="px-4 py-3 whitespace-nowrap text-xs">
                        {wsName !== '—' ? (
                          <Badge variant="outline" className="text-xs bg-[hsl(var(--card))]">
                            📁 {wsName}
                          </Badge>
                        ) : (
                          <span className="text-[hsl(var(--muted-foreground))]">—</span>
                        )}
                      </td>

                      {/* Résumé de l'opération */}
                      <td className="px-4 py-3 text-xs">
                        <div className="font-medium text-[hsl(var(--foreground))] line-clamp-1 max-w-xl">
                          {log.summary || (log.detail?.query ? String(log.detail.query) : `${log.action} sur ${log.target_type || 'ressource'}`)}
                        </div>
                      </td>

                      {/* Bouton Voir */}
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={(e) => {
                            e.stopPropagation()
                            setSelectedLog(log)
                          }}
                          className="text-xs h-7 px-2 opacity-70 group-hover:opacity-100"
                        >
                          🔍 Voir
                        </Button>
                      </td>
                    </tr>
                  )
                })}
                {!loading && logs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-sm text-[hsl(var(--muted-foreground))]">
                      Aucune entrée d'audit ne correspond aux filtres appliqués.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-[hsl(var(--border))] text-xs text-[hsl(var(--muted-foreground))]">
              <span>
                Affichage de {offset + 1} à {Math.min(offset + PAGE_SIZE, total)} sur {total} événements
              </span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                  disabled={offset === 0}
                  className="h-8 text-xs"
                >
                  ← Précédent
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setOffset((o) => o + PAGE_SIZE)}
                  disabled={offset + PAGE_SIZE >= total}
                  className="h-8 text-xs"
                >
                  Suivant →
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Modale d'Inspection Détaillée */}
      {selectedLog && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            {/* Header Modal */}
            <div className="flex items-start justify-between p-5 border-b border-[hsl(var(--border))]">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-semibold border ${getActionBadge(selectedLog.action).color}`}>
                    <span>{getActionBadge(selectedLog.action).icon}</span>
                    <span>{selectedLog.action}</span>
                  </span>
                  <span className="text-xs text-[hsl(var(--muted-foreground))] font-mono">
                    ID #{String(selectedLog.id)}
                  </span>
                </div>
                <h2 className="text-base font-bold text-[hsl(var(--foreground))]">
                  {selectedLog.summary || `Action ${selectedLog.action}`}
                </h2>
                <div className="text-xs text-[hsl(var(--muted-foreground))]">
                  Enregistré le {formatDate(selectedLog.created_at)}
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setSelectedLog(null)} className="h-8 w-8 p-0">
                ✕
              </Button>
            </div>

            {/* Corps Modal */}
            <div className="p-5 overflow-y-auto space-y-4 text-xs">
              {/* Grille des acteurs & ressources */}
              <div className="grid grid-cols-2 gap-3 p-3 rounded-lg bg-[hsl(var(--muted))]/30 border border-[hsl(var(--border))]/50">
                <div>
                  <span className="text-[hsl(var(--muted-foreground))] block">Auteur / Principal :</span>
                  <strong className="text-[hsl(var(--foreground))] font-mono text-sm">
                    {selectedLog.principal_name || 'Non spécifié'}
                  </strong>
                  {selectedLog.principal_id && (
                    <span className="text-[10px] text-[hsl(var(--muted-foreground))] font-mono block">
                      UUID: {String(selectedLog.principal_id)}
                    </span>
                  )}
                </div>

                <div>
                  <span className="text-[hsl(var(--muted-foreground))] block">Workspace :</span>
                  <strong className="text-[hsl(var(--foreground))] text-sm">
                    {selectedLog.workspace_name || selectedLog.workspace_slug || 'Global / Aucun'}
                  </strong>
                  {selectedLog.workspace_id && (
                    <span className="text-[10px] text-[hsl(var(--muted-foreground))] font-mono block">
                      UUID: {String(selectedLog.workspace_id)}
                    </span>
                  )}
                </div>

                <div>
                  <span className="text-[hsl(var(--muted-foreground))] block">Type de cible :</span>
                  <strong className="text-[hsl(var(--foreground))] capitalize">
                    {selectedLog.target_type || '—'}
                  </strong>
                </div>

                <div>
                  <span className="text-[hsl(var(--muted-foreground))] block">Identifiant cible :</span>
                  <span className="text-[hsl(var(--foreground))] font-mono">
                    {selectedLog.target_id ? String(selectedLog.target_id) : '—'}
                  </span>
                </div>
              </div>

              {/* Détails spécifiques selon type d'opération */}
              {selectedLog.detail && Object.keys(selectedLog.detail).length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-[hsl(var(--foreground))]">
                      Données détaillées de l'événement (Payload) :
                    </span>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleCopyJson(selectedLog)}
                      className="text-xs h-6 px-2 gap-1"
                    >
                      {copied ? '✅ Copié !' : '📋 Copier JSON'}
                    </Button>
                  </div>
                  <pre className="bg-black/60 p-3.5 rounded-lg border border-[hsl(var(--border))] text-[11px] font-mono text-emerald-400 overflow-x-auto whitespace-pre-wrap leading-relaxed">
                    {JSON.stringify(selectedLog.detail, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Footer Modal */}
            <div className="p-3 border-t border-[hsl(var(--border))] flex justify-end">
              <Button size="sm" variant="outline" onClick={() => setSelectedLog(null)}>
                Fermer
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
