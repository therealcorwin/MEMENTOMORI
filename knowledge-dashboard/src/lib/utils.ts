import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Fusionne les classes Tailwind sans conflits (utilitaire shadcn/ui) */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Formate une date ISO en français */
export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))
}

/** Formate un nombre de tokens avec séparateur de milliers */
export function formatTokens(n: number): string {
  return new Intl.NumberFormat('fr-FR').format(n)
}

/** Formate un coût en euros */
export function formatCost(eur: number): string {
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  }).format(eur)
}

/** Couleur de badge selon la sensibilité */
export function sensitivityColor(s: string): string {
  switch (s) {
    case 'public':      return 'bg-green-900 text-green-200'
    case 'interne':     return 'bg-blue-900 text-blue-200'
    case 'confidentiel':return 'bg-amber-900 text-amber-200'
    case 'secret':      return 'bg-red-900 text-red-200'
    default:            return 'bg-gray-800 text-gray-300'
  }
}

/** Couleur de badge selon le statut document */
export function statusColor(s: string): string {
  switch (s) {
    case 'actif':       return 'bg-green-900 text-green-200'
    case 'a_verifier':  return 'bg-amber-900 text-amber-200'
    case 'recu':        return 'bg-blue-900 text-blue-200'
    case 'archive':     return 'bg-gray-800 text-gray-300'
    case 'rejete':      return 'bg-red-900 text-red-200'
    case 'supprime':    return 'bg-red-950 text-red-300'
    case 'obsolete':    return 'bg-gray-700 text-gray-400'
    default:            return 'bg-gray-800 text-gray-300'
  }
}

/**
 * Extrait l'URL source originelle d'un document à partir de ses métadonnées,
 * versions ou champs directs (supporte link, url, source_url, feed_url, etc.)
 */
export function extractSourceUrl(doc?: {
  metadata?: Record<string, unknown>
  source_url?: string
  versions?: { original_file_ref?: string }[]
  original_file_ref?: string
} | null): string | null {
  if (!doc) return null
  const meta = doc.metadata || {}

  // 1. Clés d'URL dans les métadonnées (link pour RSS, url pour Web, feed_url, etc.)
  for (const key of ['link', 'url', 'source_url', 'original_url', 'feed_url']) {
    const val = meta[key]
    if (typeof val === 'string' && (val.startsWith('http://') || val.startsWith('https://'))) {
      return val
    }
  }

  // 2. original_file_ref direct
  if (
    typeof doc.original_file_ref === 'string' &&
    (doc.original_file_ref.startsWith('http://') || doc.original_file_ref.startsWith('https://'))
  ) {
    return doc.original_file_ref
  }

  // 3. versions[0].original_file_ref
  const vRef = doc.versions?.[0]?.original_file_ref
  if (typeof vRef === 'string' && (vRef.startsWith('http://') || vRef.startsWith('https://'))) {
    return vRef
  }

  // 4. source_url direct
  if (
    typeof doc.source_url === 'string' &&
    (doc.source_url.startsWith('http://') || doc.source_url.startsWith('https://'))
  ) {
    return doc.source_url
  }

  return null
}

