import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createUser, getUsers, type User } from '@/api/usuarios'
import { UsersPage } from './users-page'

vi.mock('@/api/usuarios', () => ({
  getUsers: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  deactivateUser: vi.fn(),
}))

const getUsersMock = vi.mocked(getUsers)
const createUserMock = vi.mocked(createUser)

const ana: User = {
  id: '11111111-1111-1111-1111-111111111111',
  institutional_id: 'uaem2026001',
  full_name: 'Ana Martínez Soto',
  email: 'amartinez@uaemex.mx',
  user_type: 'student',
  support_level: null,
  is_active: true,
  max_load: null,
  roles: ['requester'],
  created_at: '2026-10-01T12:00:00Z',
  updated_at: '2026-10-01T12:00:00Z',
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <UsersPage />
    </QueryClientProvider>,
  )
}

async function abrirFormularioDeAlta() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /nuevo usuario/i }))
  return user
}

describe('UsersPage: alta de cuentas (S2-06, HU-10.1)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('muestra las cuentas que devuelve la API', async () => {
    getUsersMock.mockResolvedValue([ana])

    renderPage()

    expect(await screen.findByText('Ana Martínez Soto')).toBeInTheDocument()
    expect(screen.getByText(/uaem2026001/)).toBeInTheDocument()
    expect(screen.getByText('Solicitante')).toBeInTheDocument()
  })

  it('muestra el estado vacío cuando no hay cuentas registradas', async () => {
    getUsersMock.mockResolvedValue([])

    renderPage()

    expect(
      await screen.findByText('No hay usuarios que mostrar'),
    ).toBeInTheDocument()
  })

  it('alta válida: envía la cuenta, cierra el formulario y recarga la lista', async () => {
    getUsersMock.mockResolvedValueOnce([]).mockResolvedValue([ana])
    createUserMock.mockResolvedValue(ana)
    renderPage()
    await screen.findByText('No hay usuarios que mostrar')

    const user = await abrirFormularioDeAlta()
    await user.type(
      screen.getByPlaceholderText('Ej. uaem2026001'),
      'uaem2026001',
    )
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => expect(createUserMock).toHaveBeenCalledTimes(1))
    expect(createUserMock.mock.calls[0][0]).toEqual({
      institutional_id: 'uaem2026001',
      role: 'requester',
      max_load: null,
    })
    expect(await screen.findByText('Ana Martínez Soto')).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Nuevo usuario' }),
    ).not.toBeInTheDocument()
  })

  it('alta válida: envía la carga máxima como número', async () => {
    getUsersMock.mockResolvedValue([])
    createUserMock.mockResolvedValue(ana)
    renderPage()
    await screen.findByText('No hay usuarios que mostrar')

    const user = await abrirFormularioDeAlta()
    await user.type(
      screen.getByPlaceholderText('Ej. uaem2026001'),
      'uaem2026001',
    )
    await user.type(screen.getByPlaceholderText('Sin límite'), '5')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => expect(createUserMock).toHaveBeenCalledTimes(1))
    expect(createUserMock.mock.calls[0][0]).toMatchObject({ max_load: 5 })
  })

  it('cuenta no reconocida: muestra el mensaje del directorio y conserva el formulario', async () => {
    getUsersMock.mockResolvedValue([])
    createUserMock.mockRejectedValue(
      new Error(
        'El directorio institucional no reconoce la cuenta cuenta-inexistente.',
      ),
    )
    renderPage()
    await screen.findByText('No hay usuarios que mostrar')

    const user = await abrirFormularioDeAlta()
    await user.type(
      screen.getByPlaceholderText('Ej. uaem2026001'),
      'cuenta-inexistente',
    )
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(
      await screen.findByText(/no reconoce la cuenta cuenta-inexistente/),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Nuevo usuario' }),
    ).toBeInTheDocument()
    expect(getUsersMock).toHaveBeenCalledTimes(1)
  })
})
