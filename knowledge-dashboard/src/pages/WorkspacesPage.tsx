/**
 * Gestion des Workspaces (§14.4 Priorité moyenne)
 */
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { workspacesApi } from '@/api/workspaces'
import type { Workspace } from '@/types'

export function WorkspacesPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    workspacesApi.list().then(setWorkspaces).finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Workspaces</h1>
      </div>

      {loading && <p className="text-[hsl(var(--muted-foreground))]">Chargement…</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {workspaces.map((ws) => (
          <Card key={ws.id}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <span className="text-lg">🌍</span>
                {ws.name}
              </CardTitle>
              <code className="text-xs text-[hsl(var(--muted-foreground))]">{ws.slug}</code>
            </CardHeader>
            <CardContent>
              {ws.description && (
                <p className="text-sm text-[hsl(var(--muted-foreground))] mb-3">{ws.description}</p>
              )}
              <div className="text-sm">
                <span className="font-medium">{ws.document_count ?? '—'}</span>
                <span className="text-[hsl(var(--muted-foreground))] ml-1">documents</span>
              </div>
            </CardContent>
          </Card>
        ))}
        {!loading && workspaces.length === 0 && (
          <p className="text-[hsl(var(--muted-foreground))] col-span-3">Aucun workspace configuré.</p>
        )}
      </div>
    </div>
  )
}
