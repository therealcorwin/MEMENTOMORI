/**
 * Monitoring — Santé de la stack (§14.4 Priorité basse / §14.9)
 */
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { adminApi } from '@/api/admin'
import { formatCost, formatTokens } from '@/lib/utils'
import type { HealthStatus, LlmMetrics } from '@/types'

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = { up: 'bg-green-500', slow: 'bg-amber-500', down: 'bg-red-500' }
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${colors[status] ?? 'bg-gray-500'}`} />
}

export function MonitoringPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [llm, setLlm] = useState<LlmMetrics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.allSettled([adminApi.health(), adminApi.llmMetrics()])
      .then(([h, l]) => {
        if (h.status === 'fulfilled') setHealth(h.value)
        if (l.status === 'fulfilled') setLlm(l.value)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-[hsl(var(--muted-foreground))] py-12 text-center">Chargement…</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Monitoring</h1>

      {/* Health */}
      <Card>
        <CardHeader>
          <CardTitle>Santé de la stack</CardTitle>
        </CardHeader>
        <CardContent>
          {!health && <p className="text-[hsl(var(--muted-foreground))] text-sm">Impossible de récupérer l'état de santé.</p>}
          {health && (
            <div className="space-y-2">
              {health.services.map((svc) => (
                <div key={svc.name} className="flex items-center justify-between py-2 border-b border-[hsl(var(--border))] last:border-0">
                  <div className="flex items-center gap-2">
                    <StatusDot status={svc.status} />
                    <span className="text-sm font-medium">{svc.name}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-[hsl(var(--muted-foreground))]">
                    {svc.latency_ms !== undefined && <span>{svc.latency_ms} ms</span>}
                    {svc.details && <span>{svc.details}</span>}
                    <span className={svc.status === 'up' ? 'text-green-400' : svc.status === 'slow' ? 'text-amber-400' : 'text-red-400'}>
                      {svc.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* LLM Metrics */}
      {llm && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Card><CardContent className="pt-6"><div className="text-2xl font-bold">{llm.total_requests}</div><div className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Requêtes LLM</div></CardContent></Card>
          <Card><CardContent className="pt-6"><div className="text-2xl font-bold">{formatCost(llm.estimated_cost_eur)}</div><div className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Coût estimé</div></CardContent></Card>
          <Card><CardContent className="pt-6"><div className="text-2xl font-bold">{formatTokens(llm.total_tokens_input + llm.total_tokens_output)}</div><div className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Tokens totaux</div></CardContent></Card>
          <Card><CardContent className="pt-6"><div className="text-2xl font-bold">{llm.avg_latency_ms} ms</div><div className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Latence moyenne</div></CardContent></Card>
        </div>
      )}
    </div>
  )
}
