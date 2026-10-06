/**
 * Sidebar de navigation (§14.5 — Architecture dashboard)
 */
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import {
  Home,
  CheckSquare,
  FileText,
  Globe,
  Search,
  ClipboardList,
  Activity,
} from 'lucide-react'

const navItems = [
  { to: '/',            icon: Home,          label: 'Accueil' },
  { to: '/validation',  icon: CheckSquare,   label: 'Validation' },
  { to: '/documents',   icon: FileText,      label: 'Documents' },
  { to: '/workspaces',  icon: Globe,         label: 'Workspaces' },
  { to: '/search',      icon: Search,        label: 'Recherche' },
  { to: '/audit',       icon: ClipboardList, label: 'Audit' },
  { to: '/monitoring',  icon: Activity,      label: 'Monitoring' },
]

export function Sidebar() {
  return (
    <aside
      className="fixed top-0 left-0 h-screen flex flex-col border-r border-[hsl(var(--border))] bg-[hsl(var(--card))]"
      style={{ width: 'var(--sidebar-width)' }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-5 border-b border-[hsl(var(--border))]">
        <span className="text-xl">🧠</span>
        <span className="font-semibold text-sm">Knowledge Platform</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 space-y-1 px-2">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))]'
                  : 'text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--accent))] hover:text-[hsl(var(--accent-foreground))]',
              )
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-[hsl(var(--border))] text-xs text-[hsl(var(--muted-foreground))]">
        MEMENTOMORI v0.8
      </div>
    </aside>
  )
}
