import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { User, UserRole } from '@/api/types'
import App from '@/App'
import { AuthContext } from '@/features/auth/auth-context'

vi.mock('@/features/clasificador/pages/ClasificadorPage', () => ({
  ClasificadorPage: () => <h1>Pantalla del clasificador</h1>,
}))
vi.mock('@/features/dashboard/dashboard-page', () => ({
  DashboardPage: () => <h1>Resumen de prueba</h1>,
}))
vi.mock('@/features/notificaciones/components/CampanaAvisos', () => ({
  CampanaAvisos: () => null,
}))

function renderApp(roles: UserRole[]) {
  const user = {
    id: 'user-1',
    email: 'persona@sigpi.test',
    full_name: 'Persona de prueba',
    is_active: true,
    roles,
  } as User
  return render(
    <AuthContext.Provider
      value={{
        user,
        isLoading: false,
        isAuthenticated: true,
        sessionExpired: false,
        login: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <MemoryRouter initialEntries={['/clasificador']}>
        <App />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('Acceso a la administración del clasificador (S5-12)', () => {
  it('el administrador ve la ruta y la entrada «Clasificador» del menú', () => {
    renderApp(['administrator'])

    expect(
      screen.getByRole('heading', { name: 'Pantalla del clasificador' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Clasificador' })).toHaveAttribute(
      'href',
      '/clasificador',
    )
  })

  it.each<UserRole>([
    'service_manager',
    'support_agent',
    'classifier',
    'requester',
  ])('%s no ve el menú y la ruta lo regresa al inicio', (role) => {
    renderApp([role])

    expect(
      screen.queryByRole('heading', { name: 'Pantalla del clasificador' }),
    ).not.toBeInTheDocument()
    expect(screen.getByText('Resumen de prueba')).toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: 'Clasificador' }),
    ).not.toBeInTheDocument()
  })
})
