/**
 * Piste d'audit — Journal des actions (§14.4 Priorité moyenne)
 */
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { auditApi, type AuditFilters } from '@/api/audit'
import { formatDate } from '@/lib/utils'
import type { AuditLog } from '@/types'

const PAGE_SIZE = 25

export function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState<AuditFilters>({})

  const fetchLogs = async () => {
    setLoading(true)
    try {
      const res = await auditApi.list({ ...filters, limit: PAGE_SIZE, offset })
      if (Array.isArray(res)) { setLogs(res); setTotal(res.length) }
      else { setLogs(res.items); setTotal(res.total) }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchLogs() }, [filters, offset])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Piste d'audit</h1>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4 pb-4">
          <div className="flex flex-wrap gap-3">
            <input
              type="text"
              placeholder="Filtrer par action…"
              className="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm"
              onChange={(e) => setFilters((f) => ({ ...f, action: e.target.value || undefined }))}
            />
            <input
              type="text"
              placeholder="Filtrer par principal…"
              className="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-1.5 text-sm"
              onChange={(e) => setFilters((f) => ({ ...f, principal_id: e.target.value || undefined }))}
            />
            <Button size="sm" variant="outline" onClick={() => { setFilters({}); setOffset(0) }}>
              Réinitialiser
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle>{loading ? 'Chargement…' : `${total} entrée${total > 1 ? 's' : ''}`}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] text-left">
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Principal</th>
                  <th className="px-4 py-3">Workspace</th>
                  <th className="px-4 py-3">Cible</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} className="border-b border-[hsl(var(--border))] hover:bg-[hsl(var(--accent)/0.3)]">
                    <td className="px-4 py-2 text-[hsl(var(--muted-foreground))] whitespace-nowrap">{formatDate(log.created_at)}</td>
                    <td className="px-4 py-2 font-mono text-xs">{log.action}</td>
                    <td className="px-4 py-2 font-mono text-xs text-[hsl(var(--muted-foreground))]">{log.principal_id?.slice(0, 12)}…</td>
                    <td className="px-4 py-2 text-xs text-[hsl(var(--muted-foreground))]">{log.workspace_id?.slice(0, 12) ?? '—'}</td>
                    <td className="px-4 py-2 text-xs text-[hsl(var(--muted-foreground))]">{log.target_id?.slice(0, 12) ?? '—'}</td>
                  </tr>
                ))}
                {!loading && logs.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-[hsl(var(--muted-foreground))]">Aucune entrée d'audit.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-[hsl(var(--border))]">
              <span className="text-sm text-[hsl(var(--muted-foreground))]">{offset + 1}–{Math.min(offset + PAGE_SIZE, total)} sur {total}</span>
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
