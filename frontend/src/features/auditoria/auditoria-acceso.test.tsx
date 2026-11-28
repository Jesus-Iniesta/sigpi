import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from '@/App'
import { AppLayout } from '@/routes/app-layout'

const usuario = vi.hoisted(() => ({ roles: ['auditor'] as string[] }))

vi.mock('@/features/auth/auth-context', () => ({
  useAuth: () => ({
    user: {
      id: 'usuario-1',
      full_name: 'Persona de prueba',
      email: 'persona@example.test',
      roles: usuario.roles,
    },
    isLoading: false,
    isAuthenticated: true,
    logout: vi.fn(),
  }),
}))

vi.mock('@/features/notificaciones/components/CampanaAvisos', () => ({
  CampanaAvisos: () => null,
}))
vi.mock('@/features/dashboard/dashboard-page', () => ({
  DashboardPage: () => <p>Inicio</p>,
}))
vi.mock('@/features/auditoria/pages/AuditoriaPage', () => ({
  AuditoriaPage: () => <p>Pantalla de auditoría</p>,
}))

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<p>Inicio</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

function renderApp(ruta: string) {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <App />
    </MemoryRouter>,
  )
}

describe('Acceso a «Auditoría» (S5-21)', () => {
  it.each([['auditor'], ['administrator']])('el rol %s ve el menú', (rol) => {
    usuario.roles = [rol]
    renderLayout()
    expect(screen.getByRole('link', { name: 'Auditoría' })).toHaveAttribute(
      'href',
      '/auditoria',
    )
  })

  it.each([['support_agent'], ['requester'], ['service_manager']])(
    'el rol %s no ve el menú',
    (rol) => {
      usuario.roles = [rol]
      renderLayout()
      expect(
        screen.queryByRole('link', { name: 'Auditoría' }),
      ).not.toBeInTheDocument()
    },
  )

  it('la ruta abre la pantalla para el auditor', async () => {
    usuario.roles = ['auditor']
    renderApp('/auditoria')
    expect(await screen.findByText('Pantalla de auditoría')).toBeInTheDocument()
  })

  it.each([['support_agent'], ['requester']])(
    'la ruta redirige al inicio al rol %s',
    async (rol) => {
      usuario.roles = [rol]
      renderApp('/auditoria')
      expect(await screen.findAllByText('Inicio')).not.toHaveLength(0)
      expect(
        screen.queryByText('Pantalla de auditoría'),
      ).not.toBeInTheDocument()
    },
  )
})
