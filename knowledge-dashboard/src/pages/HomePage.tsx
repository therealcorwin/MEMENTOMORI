/**
 * Page d'accueil — KPIs et dernières ingestions (§14.4 Priorité haute)
 */
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { adminApi } from '@/api/admin'
import { formatDate, statusColor } from '@/lib/utils'
import type { Stats } from '@/types'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#84cc16']

export function HomePage() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    adminApi.stats()
      .then(setStats)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-[hsl(var(--muted-foreground))] py-12 text-center">Chargement…</div>
  if (error) return <div className="text-red-400 py-12 text-center">Erreur : {error}</div>
  if (!stats) return null

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Tableau de bord</h1>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-3xl font-bold">{stats.documents}</div>
            <div className="text-sm text-[hsl(var(--muted-foreground))] mt-1">Documents indexés</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-3xl font-bold text-amber-400">{stats.pending_validation}</div>
            <div className="text-sm text-[hsl(var(--muted-foreground))] mt-1">En attente de validation</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-3xl font-bold">{stats.fragments}</div>
            <div className="text-sm text-[hsl(var(--muted-foreground))] mt-1">Fragments vectorisés</div>
          </CardContent>
        </Card>
      </div>

      {/* Bar chart : documents par workspace */}
      <Card>
        <CardHeader>
          <CardTitle>Documents par workspace</CardTitle>
        </CardHeader>
        <CardContent>
          {(!stats.documents_by_workspace || stats.documents_by_workspace.length === 0) ? (
            <p className="text-sm text-[hsl(var(--muted-foreground))] py-4">Aucun document rattaché à un workspace.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={stats.documents_by_workspace} layout="vertical">
                <XAxis type="number" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }} />
                <YAxis
                  dataKey="slug"
                  type="category"
                  width={120}
                  tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }}
                />
                <Tooltip
                  contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 6 }}
                  labelStyle={{ color: 'hsl(var(--foreground))' }}
                />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {(stats.documents_by_workspace || []).map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Dernières ingestions */}
      <Card>
        <CardHeader>
          <CardTitle>Dernières ingestions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {(!stats.recent_ingestions || stats.recent_ingestions.length === 0) && (
              <p className="text-[hsl(var(--muted-foreground))] text-sm">Aucune ingestion récente.</p>
            )}
            {(stats.recent_ingestions || []).map((ing) => (
              <div key={ing.id} className="flex items-center justify-between py-2 border-b border-[hsl(var(--border))] last:border-0">
                <div>
                  <span className="text-sm font-medium">{ing.title}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className={statusColor(ing.status)}>{ing.status}</Badge>
                  <span className="text-xs text-[hsl(var(--muted-foreground))]">{ing.created_at ? formatDate(ing.created_at) : '—'}</span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
