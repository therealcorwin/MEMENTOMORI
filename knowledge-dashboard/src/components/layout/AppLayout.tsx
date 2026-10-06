/**
 * Layout principal : sidebar fixe + contenu scrollable
 */
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'

export function AppLayout() {
  return (
    <div className="min-h-screen flex">
      <Sidebar />
      <div
        className="flex-1 flex flex-col min-w-0"
        style={{ marginLeft: 'var(--sidebar-width)' }}
      >
        <Header />
        <main className="flex-1 overflow-y-auto p-6 max-w-screen-2xl mx-auto w-full">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}
