/**
 * Layout principal : sidebar fixe + contenu scrollable
 */
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function AppLayout() {
  return (
    <div className="min-h-screen flex">
      <Sidebar />
      <main
        className="flex-1 overflow-y-auto"
        style={{ marginLeft: 'var(--sidebar-width)' }}
      >
        <div className="p-6 max-w-screen-2xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
