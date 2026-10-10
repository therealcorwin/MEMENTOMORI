/**
 * Widget Web Chat Universel pour le Knowledge Dashboard (Sprint 14, Tâche 14.2).
 * Connecté au routeur universel /v1/orchestrate/query avec routage automatique multi-workspaces.
 */
import { useState, useRef, useEffect } from 'react'
import {
  MessageSquare,
  X,
  Send,
  Loader2,
  Trash2,
  FileText,
  ChevronDown,
  ChevronUp,
  Maximize2,
  Minimize2,
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
  'Quel est le solde de mon compte courant fin janvier ?',
  'Quels sont les modèles de contrats de prestation disponibles ?',
  'Quelle est la synthèse de conformité de la directive NIS2 ?',
  'Quel est le montant de la dernière facture espaces verts ?',
]

export function ChatWidget({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  const [isExpanded, setIsExpanded] = useState(false)
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
    if (isOpen) {
      scrollToBottom()
    }
  }, [messages, isOpen])

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
    <>
      {/* Bouton Flottant Déclencheur */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] px-4 py-3.5 shadow-xl hover:scale-105 active:scale-95 transition-all duration-200"
          title="Ouvrir le Chat Assistant Universel"
        >
          <Bot size={22} className="animate-pulse" />
          <span className="font-semibold text-sm">Assistant IA</span>
        </button>
      )}

      {/* Fenêtre du Widget */}
      {isOpen && (
        <div
          className={cn(
            'fixed z-50 flex flex-col border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-2xl rounded-2xl overflow-hidden transition-all duration-300',
            isExpanded
              ? 'bottom-4 right-4 left-4 sm:left-auto sm:right-6 sm:bottom-6 w-auto sm:w-[720px] h-[85vh]'
              : 'bottom-4 right-4 left-4 sm:left-auto sm:right-6 sm:bottom-6 w-auto sm:w-[460px] h-[620px]'
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]/50">
            <div className="flex items-center gap-2.5">
              <div className="flex items-center justify-center w-8 h-8 rounded-full bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))]">
                <Sparkles size={18} />
              </div>
              <div>
                <h3 className="font-semibold text-sm text-[hsl(var(--card-foreground))]">
                  Assistant Universel
                </h3>
                <p className="text-[11px] text-[hsl(var(--muted-foreground))]">
                  Orchestrateur Multi-Workspaces (§16.13)
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <button
                onClick={clearHistory}
                className="p-1.5 rounded-lg text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--destructive))] hover:bg-[hsl(var(--accent))] transition-colors"
                title="Effacer la conversation"
              >
                <Trash2 size={15} />
              </button>
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="hidden sm:inline-flex p-1.5 rounded-lg text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--accent))] transition-colors"
                title={isExpanded ? 'Réduire la fenêtre' : 'Agrandir la fenêtre'}
              >
                {isExpanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1.5 rounded-lg text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--accent))] transition-colors"
                title="Fermer"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {/* Zone des messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm bg-[hsl(var(--background))]/50">
            {messages.map((msg) => {
              const isUser = msg.sender === 'user'
              const meta = msg.responseMetadata
              const isSourceOpen = expandedSources[msg.id]

              return (
                <div
                  key={msg.id}
                  className={cn('flex flex-col', isUser ? 'items-end' : 'items-start')}
                >
                  <div className="flex items-start gap-2 max-w-[92%]">
                    {!isUser && (
                      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] flex items-center justify-center mt-0.5">
                        <Bot size={15} />
                      </div>
                    )}

                    <div
                      className={cn(
                        'rounded-2xl px-4 py-3 leading-relaxed shadow-sm',
                        isUser
                          ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] rounded-tr-none'
                          : 'bg-[hsl(var(--card))] text-[hsl(var(--card-foreground))] border border-[hsl(var(--border))] rounded-tl-none'
                      )}
                    >
                      {/* Badge du domaine identifié si réponse de l'assistant */}
                      {!isUser && meta && (
                        <div className="mb-2 flex flex-wrap items-center gap-1.5 pb-2 border-b border-[hsl(var(--border))]/60">
                          {meta.strategy === 'single' && meta.workspace && (
                            <span
                              className={cn(
                                'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium border',
                                WORKSPACE_TAGS[meta.workspace]?.color || 'bg-gray-100 text-gray-700'
                              )}
                            >
                              <span>{WORKSPACE_TAGS[meta.workspace]?.icon || '📂'}</span>
                              <span>{WORKSPACE_TAGS[meta.workspace]?.label || meta.workspace}</span>
                            </span>
                          )}

                          {meta.strategy === 'multi' && meta.workspaces && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium bg-purple-500/10 text-purple-600 border border-purple-500/20">
                              <span>🌐</span>
                              <span>Synthèse Multi-Espaces ({meta.workspaces.join(', ')})</span>
                            </span>
                          )}

                          {meta.confidence && (
                            <span className="text-[10px] text-[hsl(var(--muted-foreground))] ml-auto">
                              Confiance : {String(meta.confidence)}
                            </span>
                          )}
                        </div>
                      )}

                      {/* Contenu du message */}
                      <div className="whitespace-pre-wrap">{msg.content}</div>

                      {/* Accordéon des sources citées */}
                      {!isUser && meta?.sources && meta.sources.length > 0 && (
                        <div className="mt-3 pt-2 border-t border-[hsl(var(--border))]/60">
                          <button
                            onClick={() => toggleSource(msg.id)}
                            className="flex items-center gap-1.5 text-xs text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] transition-colors font-medium"
                          >
                            <FileText size={13} />
                            <span>
                              {meta.sources.length} source{meta.sources.length > 1 ? 's' : ''} vérifiée{meta.sources.length > 1 ? 's' : ''}
                            </span>
                            {isSourceOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                          </button>

                          {isSourceOpen && (
                            <div className="mt-2 space-y-1.5 pl-1">
                              {meta.sources.map((src: OrchestrateSource, sIdx: number) => (
                                <div
                                  key={sIdx}
                                  className="text-[11px] p-2 rounded-lg bg-[hsl(var(--muted))]/50 border border-[hsl(var(--border))]/50 flex items-center justify-between"
                                >
                                  <div className="truncate mr-2 font-medium">
                                    • {src.document_title}
                                  </div>
                                  {src.workspace && (
                                    <span className="flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-[hsl(var(--card))] border border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))]">
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
                      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-[hsl(var(--secondary))] text-[hsl(var(--secondary-foreground))] flex items-center justify-center mt-0.5">
                        <User size={15} />
                      </div>
                    )}
                  </div>
                </div>
              )
            })}

            {loading && (
              <div className="flex items-center gap-2.5 text-sm text-[hsl(var(--muted-foreground))] pl-1">
                <div className="w-7 h-7 rounded-full bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] flex items-center justify-center">
                  <Bot size={15} />
                </div>
                <div className="flex items-center gap-2 p-3 rounded-2xl bg-[hsl(var(--card))] border border-[hsl(var(--border))]">
                  <Loader2 size={16} className="animate-spin text-[hsl(var(--primary))]" />
                  <span>Recherche & analyse cross-workspaces...</span>
                </div>
              </div>
            )}

            {/* Suggestions si conversation courte */}
            {messages.length === 1 && (
              <div className="pt-2">
                <p className="text-xs text-[hsl(var(--muted-foreground))] mb-2 font-medium">
                  💡 Suggestions rapides :
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {SUGGESTIONS.map((sug, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(sug)}
                      className="text-left text-xs px-2.5 py-1.5 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] hover:bg-[hsl(var(--accent))] hover:text-[hsl(var(--accent-foreground))] transition-colors"
                    >
                      {sug}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Zone de saisie */}
          <div className="p-3 border-t border-[hsl(var(--border))] bg-[hsl(var(--card))]">
            <form
              onSubmit={(e) => {
                e.preventDefault()
                handleSend()
              }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Posez votre question multi-domaines..."
                disabled={loading}
                className="flex-1 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/50 transition-all disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!input.trim() || loading}
                className="flex items-center justify-center w-10 h-10 rounded-xl bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 active:scale-95 transition-all disabled:opacity-40 disabled:hover:opacity-40 disabled:active:scale-100"
                title="Envoyer la question"
              >
                {loading ? <Loader2 size={17} className="animate-spin" /> : <Send size={16} />}
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  )
}

