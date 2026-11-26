import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from '@/App'
import { AppLayout } from '@/routes/app-layout'

const usuario = vi.hoisted(() => ({ roles: ['administrator'] as string[] }))

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
vi.mock('@/features/indicadores/pages/IndicadoresPage', () => ({
  IndicadoresPage: () => <p>Pantalla de indicadores</p>,
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

describe('Acceso a «Indicadores» (S5-11)', () => {
  it.each([['administrator'], ['service_manager']])(
    'el rol %s ve el menú y la ruta',
    async (rol) => {
      usuario.roles = [rol]
      renderLayout()
      expect(screen.getByRole('link', { name: 'Indicadores' })).toHaveAttribute(
        'href',
        '/indicadores',
      )
    },
  )

  it.each([['support_agent'], ['requester'], ['auditor']])(
    'el rol %s no ve el menú',
    (rol) => {
      usuario.roles = [rol]
      renderLayout()
      expect(
        screen.queryByRole('link', { name: 'Indicadores' }),
      ).not.toBeInTheDocument()
    },
  )

  it('la ruta abre la pantalla para el jefe de servicio', async () => {
    usuario.roles = ['service_manager']
    renderApp('/indicadores')
    expect(
      await screen.findByText('Pantalla de indicadores'),
    ).toBeInTheDocument()
  })

  it('la ruta redirige al inicio a quien no tiene reports.read', async () => {
    usuario.roles = ['support_agent']
    renderApp('/indicadores')
    expect(await screen.findAllByText('Inicio')).not.toHaveLength(0)
    expect(
      screen.queryByText('Pantalla de indicadores'),
    ).not.toBeInTheDocument()
  })
})
