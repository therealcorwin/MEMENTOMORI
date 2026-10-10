import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from '@/auth/AuthProvider'
import { ProtectedRoute } from '@/auth/ProtectedRoute'
import { AppLayout } from '@/components/layout/AppLayout'
import { HomePage } from '@/pages/HomePage'
import { ChatPage } from '@/pages/ChatPage'
import { ValidationPage } from '@/pages/ValidationPage'
import { DocumentsPage } from '@/pages/DocumentsPage'
import { WorkspacesPage } from '@/pages/WorkspacesPage'
import { SearchPage } from '@/pages/SearchPage'
import { AuditPage } from '@/pages/AuditPage'
import { MonitoringPage } from '@/pages/MonitoringPage'
import { CallbackPage } from '@/pages/CallbackPage'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Point de terminaison du rappel OIDC Authentik */}
          <Route path="callback" element={<CallbackPage />} />

          {/* Routes applicatives protégées */}
          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<HomePage />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="validation" element={<ValidationPage />} />
            <Route path="documents" element={<DocumentsPage />} />
            <Route path="workspaces" element={<WorkspacesPage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="monitoring" element={<MonitoringPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
