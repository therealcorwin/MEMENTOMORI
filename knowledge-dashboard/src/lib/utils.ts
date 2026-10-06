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
