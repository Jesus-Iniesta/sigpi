import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth } from '@/features/auth/require-auth'
import { LoginPage } from '@/features/auth/login-page'
import { DashboardPage } from '@/features/dashboard/dashboard-page'
import { CatalogPage } from '@/features/catalog/catalog-page'
import { RequestsPage } from '@/features/requests/requests-page'
import { SlaPage } from '@/features/sla/sla-page'
import { UsersPage } from '@/features/users/users-page'
import { AppLayout } from '@/routes/app-layout'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="solicitudes" element={<RequestsPage />} />
          <Route path="catalogo" element={<CatalogPage />} />
          <Route path="sla" element={<SlaPage />} />
          <Route element={<RequireAuth requiredRoles={['administrator']} />}>
            <Route path="usuarios" element={<UsersPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Route>
    </Routes>
  )
}

export default App
