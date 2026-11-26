import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth } from '@/features/auth/require-auth'
import { LoginPage } from '@/features/auth/login-page'
import { BandejaPage } from '@/features/bandeja/pages/BandejaPage'
import { DashboardPage } from '@/features/dashboard/dashboard-page'
import { CatalogPage } from '@/features/catalog/catalog-page'
import { RevisionPage } from '@/features/clasificacion/pages/RevisionPage'
import { ClasificadorPage } from '@/features/clasificador/pages/ClasificadorPage'
import { RegistroAsistidoPage } from '@/features/requests/registro-asistido-page'
import { RequestsPage } from '@/features/requests/requests-page'
import { SolicitudDetallePage } from '@/features/requests/pages/SolicitudDetallePage'
import { MiSolicitudPage } from '@/features/solicitudes/pages/MiSolicitudPage'
import { MisSolicitudesPage } from '@/features/solicitudes/pages/MisSolicitudesPage'
import { SlaPage } from '@/features/sla/sla-page'
import { UsersPage } from '@/features/users/users-page'
import { IndicadoresPage } from '@/features/indicadores/pages/IndicadoresPage'
import { AppLayout } from '@/routes/app-layout'

const staffRoles = ['administrator', 'service_manager', 'support_agent']
// Roles con el permiso classification.review (backend/app/core/permissions.py).
const reviewRoles = [
  'administrator',
  'service_manager',
  'classifier',
  'support_agent',
]
// Único rol con el permiso requests.view_own (S4-01).
const requesterRoles = ['requester']
// Roles con el permiso catalog.read (backend/app/core/permissions.py).
const catalogRoles = [
  'administrator',
  'service_manager',
  'support_agent',
  'classifier',
  'auditor',
]
// Roles con el permiso reports.read (S5-11).
const reportsRoles = ['administrator', 'service_manager']

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="solicitudes" element={<RequestsPage />} />
          <Route element={<RequireAuth requiredRoles={staffRoles} />}>
            <Route
              path="solicitudes/asistido"
              element={<RegistroAsistidoPage />}
            />
            <Route path="solicitudes/:id" element={<SolicitudDetallePage />} />
            <Route path="bandeja" element={<BandejaPage />} />
          </Route>
          <Route element={<RequireAuth requiredRoles={reviewRoles} />}>
            <Route path="clasificacion/revision" element={<RevisionPage />} />
          </Route>
          <Route element={<RequireAuth requiredRoles={requesterRoles} />}>
            <Route path="mis-solicitudes" element={<MisSolicitudesPage />} />
            <Route
              path="mis-solicitudes/:folio"
              element={<MiSolicitudPage />}
            />
          </Route>
          <Route element={<RequireAuth requiredRoles={catalogRoles} />}>
            <Route path="catalogo" element={<CatalogPage />} />
          </Route>
          {/* /sla queda abierto a todo usuario autenticado: el solicitante
              descarga ahí el contrato del acuerdo de servicio. */}
          <Route path="sla" element={<SlaPage />} />
          <Route element={<RequireAuth requiredRoles={['administrator']} />}>
            <Route path="usuarios" element={<UsersPage />} />
            <Route path="clasificador" element={<ClasificadorPage />} />
          </Route>
          <Route element={<RequireAuth requiredRoles={reportsRoles} />}>
            <Route path="indicadores" element={<IndicadoresPage />} />
          </Route>
        </Route>
      </Route>

      {/* Fallback: redirige al dashboard */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
