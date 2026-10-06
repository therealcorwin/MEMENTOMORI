/**
 * Console de recherche hybride (§14.4 Priorité moyenne)
 */
import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { searchApi } from '@/api/search'
import { sensitivityColor } from '@/lib/utils'

type Mode = 'search' | 'answer'

interface SearchFrag {
  content: string
  document_title: string
  score: number
  sensitivity: string
  page_number?: number
}

interface SearchResultData { results: SearchFrag[] }
interface AnswerResultData { answer: string; sources?: { document_title: string }[] }

export function SearchPage() {
  const [query, setQuery] = useState('')
  const [workspaceId, setWorkspaceId] = useState('')
  const [mode, setMode] = useState<Mode>('search')
  const [result, setResult] = useState<SearchResultData | AnswerResultData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim() || !workspaceId.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = mode === 'search'
        ? await searchApi.search({ query, workspace_id: workspaceId, top_k: 5 })
        : await searchApi.answer({ question: query, workspace_id: workspaceId })
      setResult(res)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Erreur inconnue')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Console de recherche</h1>

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex gap-2">
              <button type="button" onClick={() => setMode('search')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${mode === 'search' ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]' : 'bg-[hsl(var(--accent))]'}`}>
                Recherche
              </button>
              <button type="button" onClick={() => setMode('answer')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${mode === 'answer' ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]' : 'bg-[hsl(var(--accent))]'}`}>
                Réponse IA
              </button>
            </div>

            <input
              type="text"
              placeholder="Workspace ID (ex: copro-jardins)"
              value={workspaceId}
              onChange={(e) => setWorkspaceId(e.target.value)}
              className="w-full rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-sm"
            />
            <div className="flex gap-2">
              <input
                type="text"
                placeholder={mode === 'search' ? 'Requête de recherche…' : 'Posez votre question…'}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="flex-1 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-sm"
              />
              <Button type="submit" disabled={loading || !query.trim() || !workspaceId.trim()}>
                {loading ? '…' : mode === 'search' ? 'Chercher' : 'Demander'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {error && <div className="text-red-400 text-sm">{error}</div>}

      {result && mode === 'search' && (
        <div className="space-y-3">
          {(result as SearchResultData).results?.map((frag, i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">{frag.document_title}</CardTitle>
                  <div className="flex gap-2 items-center">
                    <Badge className={sensitivityColor(frag.sensitivity)}>{frag.sensitivity}</Badge>
                    <span className="text-xs text-[hsl(var(--muted-foreground))]">score: {frag.score.toFixed(3)}</span>
                  </div>
                </div>
                {frag.page_number && <span className="text-xs text-[hsl(var(--muted-foreground))]">Page {frag.page_number}</span>}
              </CardHeader>
              <CardContent>
                <p className="text-sm text-[hsl(var(--muted-foreground))] whitespace-pre-wrap">{frag.content}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {result && mode === 'answer' && (
        <Card>
          <CardHeader>
            <CardTitle>Réponse</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap">{(result as AnswerResultData).answer}</p>
            {(result as AnswerResultData).sources && (
              <div className="mt-4 text-xs text-[hsl(var(--muted-foreground))]">
                <strong>Sources :</strong>{' '}
                {(result as AnswerResultData).sources!.map((s) => s.document_title).join(', ')}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

