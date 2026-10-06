/**
 * Monitoring — Santé de la stack (§14.4 Priorité basse / §14.9)
 */
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { adminApi } from '@/api/admin'
import { formatTokens } from '@/lib/utils'
import type { HealthStatus, LlmMetrics, LlmCosts } from '@/types'

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    ok: 'bg-green-500',
    up: 'bg-green-500',
    healthy: 'bg-green-500',
    warning: 'bg-amber-500',
    slow: 'bg-amber-500',
    degraded: 'bg-amber-500',
    error: 'bg-red-500',
    down: 'bg-red-500',
  }
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${colors[status] ?? 'bg-gray-500'}`} />
}

export function MonitoringPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [llm, setLlm] = useState<LlmMetrics | null>(null)
  const [costs, setCosts] = useState<LlmCosts | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.allSettled([adminApi.health(), adminApi.llmMetrics(), adminApi.llmCosts()])
      .then(([h, l, c]) => {
        if (h.status === 'fulfilled') setHealth(h.value)
        if (l.status === 'fulfilled') setLlm(l.value)
        if (c.status === 'fulfilled') setCosts(c.value)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-[hsl(var(--muted-foreground))] py-12 text-center">Chargement…</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Monitoring & Santé</h1>
        {health && (
          <div className="flex items-center gap-2 text-sm">
            <StatusDot status={health.status} />
            <span className="capitalize text-[hsl(var(--muted-foreground))]">
              État global : <strong className="text-[hsl(var(--foreground))]">{health.status}</strong>
            </span>
          </div>
        )}
      </div>

      {/* Health Services */}
      <Card>
        <CardHeader>
          <CardTitle>Services de l'infrastructure</CardTitle>
        </CardHeader>
        <CardContent>
          {!health?.services && (
            <p className="text-[hsl(var(--muted-foreground))] text-sm">Impossible de récupérer l'état des services.</p>
          )}
          {health?.services && (
            <div className="space-y-3">
              {Object.entries(health.services).map(([name, svc]) => (
                <div
                  key={name}
                  className="flex flex-col sm:flex-row sm:items-center justify-between py-2.5 border-b border-[hsl(var(--border))] last:border-0 gap-2"
                >
                  <div className="flex items-center gap-2.5">
                    <StatusDot status={svc.status} />
                    <span className="text-sm font-semibold capitalize">{name}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-[hsl(var(--muted-foreground))]">
                    {svc.latency_ms !== undefined && (
                      <span className="font-mono">{svc.latency_ms} ms</span>
                    )}
                    {svc.error && (
                      <span className="text-red-400 truncate max-w-xs" title={svc.error}>
                        {svc.error}
                      </span>
                    )}
                    <Badge
                      className={
                        svc.status === 'ok'
                          ? 'bg-green-500/10 text-green-400 border-green-500/20'
                          : svc.status === 'warning'
                          ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                          : 'bg-red-500/10 text-red-400 border-red-500/20'
                      }
                    >
                      {svc.status.toUpperCase()}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* LLM Metrics */}
      {llm && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Métriques LLM & RAG</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">{llm.total_calls}</div>
                <div className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Appels LLM</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">
                  ${(costs?.total_estimated_cost_usd ?? 0).toFixed(4)}
                </div>
                <div className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Coût estimé (USD)</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">
                  {formatTokens(llm.total_tokens_input + llm.total_tokens_output)}
                </div>
                <div className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Tokens consommés</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">{llm.average_latency_ms} ms</div>
                <div className="text-xs text-[hsl(var(--muted-foreground))] mt-1">Latence moyenne</div>
              </CardContent>
            </Card>
          </div>

          {/* Répartition par modèle */}
          {llm.calls_by_model && Object.keys(llm.calls_by_model).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Répartition par modèle</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-3">
                  {Object.entries(llm.calls_by_model).map(([model, count]) => (
                    <div
                      key={model}
                      className="px-3 py-1.5 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] text-xs flex items-center gap-2"
                    >
                      <span className="font-mono text-[hsl(var(--foreground))]">{model}</span>
                      <Badge className="bg-[hsl(var(--accent))] text-[hsl(var(--foreground))]">
                        {count} appel{count > 1 ? 's' : ''}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
