import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import { HomePage } from '@/pages/HomePage'
import { ValidationPage } from '@/pages/ValidationPage'
import { DocumentsPage } from '@/pages/DocumentsPage'
import { WorkspacesPage } from '@/pages/WorkspacesPage'
import { SearchPage } from '@/pages/SearchPage'
import { AuditPage } from '@/pages/AuditPage'
import { MonitoringPage } from '@/pages/MonitoringPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<HomePage />} />
          <Route path="validation" element={<ValidationPage />} />
          <Route path="documents" element={<DocumentsPage />} />
          <Route path="workspaces" element={<WorkspacesPage />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="audit" element={<AuditPage />} />
          <Route path="monitoring" element={<MonitoringPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
