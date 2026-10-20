import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getCategories, type Category } from '@/api/catalog'
import { createAssistedRequest, type Request } from '@/api/solicitudes'
import { getUsers, type User } from '@/api/usuarios'
import { RegistroAsistidoPage } from './registro-asistido-page'

vi.mock('@/api/solicitudes', () => ({ createAssistedRequest: vi.fn() }))
vi.mock('@/api/catalog', () => ({ getCategories: vi.fn() }))
vi.mock('@/api/usuarios', () => ({ getUsers: vi.fn() }))

const createAssistedMock = vi.mocked(createAssistedRequest)
const getUsersMock = vi.mocked(getUsers)
const getCategoriesMock = vi.mocked(getCategories)

const ana: User = {
  id: 'user-ana',
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

const category: Category = {
  id: 'cat-1',
  area_id: 'area-1',
  name: 'Conectividad',
  description: null,
  is_active: true,
}

const createdRequest: Request = {
  id: 'req-1',
  requester_id: 'user-ana',
  category_id: 'cat-1',
  asset_id: null,
  service_level_version_id: null,
  related_request_id: null,
  folio: 'SIG-0007',
  title: 'No hay conexión a la red',
  description: 'El laboratorio perdió conectividad.',
  physical_location: 'Edificio A, laboratorio 2',
  channel: 'phone',
  status: 'registered',
  priority: null,
  urgency: 2,
  impact: 1,
  classification_confidence: null,
  first_response_at: null,
  resolved_at: null,
  closed_at: null,
  created_at: '2026-10-18T12:00:00Z',
  updated_at: '2026-10-18T12:00:00Z',
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RegistroAsistidoPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function selectRequester(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Buscar solicitante'), 'ana')
  await user.click(await screen.findByRole('button', { name: /Ana Martínez/ }))
}

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await selectRequester(user)
  await user.click(screen.getByLabelText('Teléfono'))
  await user.type(screen.getByLabelText('Título'), 'No hay conexión a la red')
  await user.type(
    screen.getByLabelText('Descripción'),
    'El laboratorio perdió conectividad.',
  )
  await user.type(
    screen.getByLabelText('Ubicación física'),
    'Edificio A, laboratorio 2',
  )
  await user.selectOptions(screen.getByLabelText('Categoría'), 'cat-1')
  await user.selectOptions(screen.getByLabelText('Urgencia'), '2')
  await user.selectOptions(screen.getByLabelText('Impacto'), '1')
}

describe('RegistroAsistidoPage: registro asistido (S3-09, HU-01.3)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    getUsersMock.mockResolvedValue([ana])
    getCategoriesMock.mockResolvedValue([category])
  })

  it('busca al solicitante por nombre y lo muestra para elegirlo', async () => {
    renderPage()
    const user = userEvent.setup()

    await selectRequester(user)

    expect(screen.getByText(/uaem2026001/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cambiar' })).toBeInTheDocument()
  })

  it('avisa cuando no hay ningún solicitante con ese dato', async () => {
    renderPage()
    const user = userEvent.setup()

    await user.type(screen.getByLabelText('Buscar solicitante'), 'zzz')

    expect(
      await screen.findByText(
        'No se encontró ningún solicitante con ese dato.',
      ),
    ).toBeInTheDocument()
  })

  it('envía el registro con el solicitante elegido y el canal de origen', async () => {
    createAssistedMock.mockResolvedValue(createdRequest)
    renderPage()
    const user = userEvent.setup()

    await fillValidForm(user)
    await user.click(
      screen.getByRole('button', { name: 'Registrar solicitud' }),
    )

    await waitFor(() => expect(createAssistedMock).toHaveBeenCalledTimes(1))
    expect(createAssistedMock.mock.calls[0][0]).toEqual({
      requester_id: 'user-ana',
      category_id: 'cat-1',
      title: 'No hay conexión a la red',
      description: 'El laboratorio perdió conectividad.',
      physical_location: 'Edificio A, laboratorio 2',
      channel: 'phone',
      urgency: 2,
      impact: 1,
    })
  })

  it('permite elegir el canal presencial', async () => {
    createAssistedMock.mockResolvedValue({
      ...createdRequest,
      channel: 'in_person',
    })
    renderPage()
    const user = userEvent.setup()

    await fillValidForm(user)
    await user.click(screen.getByLabelText('Presencial'))
    await user.click(
      screen.getByRole('button', { name: 'Registrar solicitud' }),
    )

    await waitFor(() => expect(createAssistedMock).toHaveBeenCalledTimes(1))
    expect(createAssistedMock.mock.calls[0][0]).toMatchObject({
      channel: 'in_person',
    })
  })

  it('muestra el folio como acuse tras registrar', async () => {
    createAssistedMock.mockResolvedValue(createdRequest)
    renderPage()
    const user = userEvent.setup()

    await fillValidForm(user)
    await user.click(
      screen.getByRole('button', { name: 'Registrar solicitud' }),
    )

    expect(
      await screen.findByText('Solicitud registrada correctamente.'),
    ).toBeInTheDocument()
    expect(screen.getByText('SIG-0007')).toBeInTheDocument()
  })

  it('sin llenar nada muestra todos los errores y no envía', async () => {
    renderPage()
    const user = userEvent.setup()

    await user.click(
      screen.getByRole('button', { name: 'Registrar solicitud' }),
    )

    expect(
      await screen.findByText('Selecciona al solicitante.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Selecciona el canal de origen.'),
    ).toBeInTheDocument()
    expect(screen.getByText('El título es obligatorio.')).toBeInTheDocument()
    expect(
      screen.getByText('La descripción es obligatoria.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('La ubicación física es obligatoria.'),
    ).toBeInTheDocument()
    expect(createAssistedMock).not.toHaveBeenCalled()
  })

  it('muestra el mensaje del servidor si el registro falla', async () => {
    createAssistedMock.mockRejectedValue(
      new Error('No tienes permiso para realizar esta acción.'),
    )
    renderPage()
    const user = userEvent.setup()

    await fillValidForm(user)
    await user.click(
      screen.getByRole('button', { name: 'Registrar solicitud' }),
    )

    expect(
      await screen.findByText('No tienes permiso para realizar esta acción.'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Título')).toBeInTheDocument()
  })

  it('"Registrar otra solicitud" regresa al formulario vacío', async () => {
    createAssistedMock.mockResolvedValue(createdRequest)
    renderPage()
    const user = userEvent.setup()

    await fillValidForm(user)
    await user.click(
      screen.getByRole('button', { name: 'Registrar solicitud' }),
    )
    await user.click(
      await screen.findByRole('button', { name: 'Registrar otra solicitud' }),
    )

    expect(screen.getByLabelText('Título')).toHaveValue('')
    expect(screen.getByLabelText('Buscar solicitante')).toBeInTheDocument()
  })
})
