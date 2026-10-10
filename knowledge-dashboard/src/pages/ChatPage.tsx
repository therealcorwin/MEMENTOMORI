/**
 * Page Dédiée Chat Assistant Universel (§8, §16.13, Sprint 14, Tâche 14.2).
 */
import { useState, useRef, useEffect } from 'react'
import {
  Send,
  Loader2,
  Trash2,
  FileText,
  ChevronDown,
  ChevronUp,
  Bot,
  User,
  Sparkles,
} from 'lucide-react'
import { orchestrateQuery, type OrchestrateResponse, type OrchestrateSource } from '@/api/orchestrator'
import { cn } from '@/lib/utils'

export interface ChatMessage {
  id: string
  sender: 'user' | 'assistant'
  content: string
  timestamp: Date
  responseMetadata?: OrchestrateResponse
}

const WORKSPACE_TAGS: Record<string, { label: string; color: string; icon: string }> = {
  copro: { label: 'Copropriété', color: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20', icon: '🏢' },
  'finances-perso': { label: 'Finances Perso', color: 'bg-amber-500/10 text-amber-600 border-amber-500/20', icon: '💰' },
  'admin-perso': { label: 'Admin Perso', color: 'bg-blue-500/10 text-blue-600 border-blue-500/20', icon: '📑' },
  'sante-perso': { label: 'Santé Perso', color: 'bg-rose-500/10 text-rose-600 border-rose-500/20', icon: '🩺' },
  entreprise: { label: 'Entreprise & Pro', color: 'bg-purple-500/10 text-purple-600 border-purple-500/20', icon: '💼' },
  dev: { label: 'Développement & Tech', color: 'bg-indigo-500/10 text-indigo-600 border-indigo-500/20', icon: '💻' },
  formation: { label: 'Formation', color: 'bg-teal-500/10 text-teal-600 border-teal-500/20', icon: '🎓' },
  consulting: { label: 'Consulting', color: 'bg-orange-500/10 text-orange-600 border-orange-500/20', icon: '🤝' },
  veille: { label: 'Veille & IA', color: 'bg-cyan-500/10 text-cyan-600 border-cyan-500/20', icon: '📡' },
}

const SUGGESTIONS = [
  'Quels sont les horaires autorisés pour les travaux bruyants ?',
  'Quel est le solde de mon compte courant fin janvier 2026 ?',
  'Quels sont les modèles de contrats de prestation disponibles ?',
  'Quelle est la synthèse de conformité de la directive NIS2 ?',
  'Quel est le montant de la dernière facture espaces verts ?',
  'Comment sont déclarées les cotisations URSSAF trimestrielles ?',
]

export function ChatPage() {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      content:
        'Bonjour ! Je suis l’Assistant Universel MEMENTOMORI. Posez-moi n’importe quelle question, je consulte automatiquement le ou les espaces de travail pertinents (Copropriété, Finances, Administratif, Santé, Entreprise, Dev, Formation, Consulting, Veille).',
      timestamp: new Date(),
    },
  ])
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({})
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const toggleSource = (msgId: string) => {
    setExpandedSources((prev) => ({ ...prev, [msgId]: !prev[msgId] }))
  }

  const handleSend = async (queryText?: string) => {
    const text = (queryText || input).trim()
    if (!text || loading) return

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      sender: 'user',
      content: text,
      timestamp: new Date(),
    }

    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const resp = await orchestrateQuery(text, 5)

      const assistantMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        sender: 'assistant',
        content: resp.answer || 'Aucune information trouvée.',
        timestamp: new Date(),
        responseMetadata: resp,
      }

      setMessages((prev) => [...prev, assistantMsg])
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        sender: 'assistant',
        content: `Désolé, une erreur est survenue lors de l'interrogation de l'orchestrateur (${err?.message || 'Erreur réseau'}).`,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, errorMsg])
    } finally {
      setLoading(false)
    }
  }

  const clearHistory = () => {
    setMessages([
      {
        id: 'welcome',
        sender: 'assistant',
        content:
          'Historique réinitialisé. Posez une nouvelle question pour interroger vos bases de connaissances.',
        timestamp: new Date(),
      },
    ])
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-5xl mx-auto border border-[hsl(var(--border))] rounded-2xl bg-[hsl(var(--card))] overflow-hidden shadow-lg">
      {/* En-tête */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]/40">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))]">
            <Sparkles size={22} />
          </div>
          <div>
            <h1 className="font-semibold text-base text-[hsl(var(--card-foreground))]">
              Assistant Universel Multi-Workspaces
            </h1>
            <p className="text-xs text-[hsl(var(--muted-foreground))]">
              Routage sémantique autonome & RAG fédéré sur 9 espaces de vie et de travail
            </p>
          </div>
        </div>

        <button
          onClick={clearHistory}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--destructive))] hover:bg-[hsl(var(--accent))] transition-colors"
          title="Effacer la conversation"
        >
          <Trash2 size={15} />
          <span>Effacer l'historique</span>
        </button>
      </div>

      {/* Zone des messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-5 bg-[hsl(var(--background))]/30">
        {messages.map((msg) => {
          const isUser = msg.sender === 'user'
          const meta = msg.responseMetadata
          const isSourceOpen = expandedSources[msg.id]

          return (
            <div
              key={msg.id}
              className={cn('flex flex-col', isUser ? 'items-end' : 'items-start')}
            >
              <div className="flex items-start gap-3 max-w-[85%]">
                {!isUser && (
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] flex items-center justify-center mt-0.5">
                    <Bot size={18} />
                  </div>
                )}

                <div
                  className={cn(
                    'rounded-2xl px-5 py-3.5 leading-relaxed shadow-sm text-sm',
                    isUser
                      ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] rounded-tr-none'
                      : 'bg-[hsl(var(--card))] text-[hsl(var(--card-foreground))] border border-[hsl(var(--border))] rounded-tl-none'
                  )}
                >
                  {/* Badges de domaine identifié */}
                  {!isUser && meta && (
                    <div className="mb-2.5 flex flex-wrap items-center gap-2 pb-2 border-b border-[hsl(var(--border))]/60">
                      {meta.strategy === 'single' && meta.workspace && (
                        <span
                          className={cn(
                            'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-medium border',
                            WORKSPACE_TAGS[meta.workspace]?.color || 'bg-gray-100 text-gray-700'
                          )}
                        >
                          <span>{WORKSPACE_TAGS[meta.workspace]?.icon || '📂'}</span>
                          <span>{WORKSPACE_TAGS[meta.workspace]?.label || meta.workspace}</span>
                        </span>
                      )}

                      {meta.strategy === 'multi' && meta.workspaces && (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-medium bg-purple-500/10 text-purple-600 border border-purple-500/20">
                          <span>🌐</span>
                          <span>Synthèse Multi-Espaces ({meta.workspaces.join(', ')})</span>
                        </span>
                      )}

                      {meta.confidence && (
                        <span className="text-[11px] text-[hsl(var(--muted-foreground))] ml-auto">
                          Confiance : {String(meta.confidence)}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Corps du message */}
                  <div className="whitespace-pre-wrap">{msg.content}</div>

                  {/* Accordéon des sources vérifiées */}
                  {!isUser && meta?.sources && meta.sources.length > 0 && (
                    <div className="mt-3.5 pt-2.5 border-t border-[hsl(var(--border))]/60">
                      <button
                        onClick={() => toggleSource(msg.id)}
                        className="flex items-center gap-1.5 text-xs text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] transition-colors font-medium"
                      >
                        <FileText size={14} />
                        <span>
                          {meta.sources.length} source{meta.sources.length > 1 ? 's' : ''} vérifiée{meta.sources.length > 1 ? 's' : ''}
                        </span>
                        {isSourceOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>

                      {isSourceOpen && (
                        <div className="mt-2.5 space-y-2 pl-1">
                          {meta.sources.map((src: OrchestrateSource, sIdx: number) => (
                            <div
                              key={sIdx}
                              className="text-xs p-2.5 rounded-xl bg-[hsl(var(--muted))]/50 border border-[hsl(var(--border))]/50 flex items-center justify-between"
                            >
                              <div className="truncate mr-3 font-medium">
                                • {src.document_title}
                              </div>
                              {src.workspace && (
                                <span className="flex-shrink-0 text-[11px] px-2 py-0.5 rounded-md bg-[hsl(var(--card))] border border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] font-medium">
                                  {src.workspace}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {isUser && (
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[hsl(var(--secondary))] text-[hsl(var(--secondary-foreground))] flex items-center justify-center mt-0.5">
                    <User size={18} />
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {loading && (
          <div className="flex items-center gap-3 text-sm text-[hsl(var(--muted-foreground))] pl-1">
            <div className="w-8 h-8 rounded-full bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] flex items-center justify-center">
              <Bot size={18} />
            </div>
            <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-[hsl(var(--card))] border border-[hsl(var(--border))]">
              <Loader2 size={18} className="animate-spin text-[hsl(var(--primary))]" />
              <span>Orchestration, recherche sémantique & synthèse LLM en cours...</span>
            </div>
          </div>
        )}

        {/* Suggestions initiales */}
        {messages.length === 1 && (
          <div className="pt-4 max-w-2xl">
            <p className="text-xs text-[hsl(var(--muted-foreground))] mb-3 font-semibold uppercase tracking-wider">
              Exemples de questions transversales :
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {SUGGESTIONS.map((sug, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSend(sug)}
                  className="text-left text-xs p-3 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] hover:bg-[hsl(var(--accent))] hover:text-[hsl(var(--accent-foreground))] transition-all shadow-xs"
                >
                  {sug}
                </button>
              ))}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Barre de saisie */}
      <div className="p-4 border-t border-[hsl(var(--border))] bg-[hsl(var(--card))]">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            handleSend()
          }}
          className="flex items-center gap-3"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Posez votre question multi-domaines (ex: 'Quel est mon solde ?', 'Horaires travaux ?', 'Contrat type ?')..."
            disabled={loading}
            className="flex-1 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/50 transition-all disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="flex items-center justify-center px-5 py-3 rounded-xl bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] font-medium text-sm hover:opacity-90 active:scale-95 transition-all disabled:opacity-40 disabled:hover:opacity-40"
          >
            {loading ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <div className="flex items-center gap-2">
                <span>Envoyer</span>
                <Send size={15} />
              </div>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}

