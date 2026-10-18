import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getCategories, type Category } from '@/api/catalog'
import { createRequest } from '@/api/solicitudes'
import { SolicitudForm } from './solicitud-form'

vi.mock('@/api/solicitudes', () => ({ createRequest: vi.fn() }))
vi.mock('@/api/catalog', () => ({ getCategories: vi.fn() }))
vi.mock('@/features/auth/auth-context', () => ({
  useAuth: () => ({
    user: {
      id: 'user-1',
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
    },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

const createRequestMock = vi.mocked(createRequest)
const getCategoriesMock = vi.mocked(getCategories)

const category: Category = {
  id: 'cat-1',
  area_id: 'area-1',
  name: 'Conectividad',
  description: null,
  is_active: true,
}

function renderForm(onClose = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <SolicitudForm onClose={onClose} />
    </QueryClientProvider>,
  )
  return onClose
}

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(
    screen.getByLabelText('Título'),
    'No hay conexión a la red',
  )
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

describe('SolicitudForm: alta de solicitudes (S3-05, HU-01.1)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    getCategoriesMock.mockResolvedValue([category])
  })

  // --- AC1: alta válida ------------------------------------------------------

  it('AC1: alta válida envía los datos correctos y cierra el formulario', async () => {
    createRequestMock.mockResolvedValue({
      id: 'req-1',
      requester_id: 'user-1',
      category_id: 'cat-1',
      asset_id: null,
      service_level_version_id: null,
      related_request_id: null,
      folio: 'SIG-0001',
      title: 'No hay conexión a la red',
      description: 'El laboratorio perdió conectividad.',
      physical_location: 'Edificio A, laboratorio 2',
      channel: 'portal',
      status: 'registered',
      priority: null,
      urgency: 2,
      impact: 1,
      classification_confidence: null,
      first_response_at: null,
      resolved_at: null,
      closed_at: null,
      created_at: '2026-10-17T12:00:00Z',
      updated_at: '2026-10-17T12:00:00Z',
    })
    const onClose = renderForm()

    const user = userEvent.setup()
    await fillValidForm(user)
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    await waitFor(() => expect(createRequestMock).toHaveBeenCalledTimes(1))
    expect(createRequestMock.mock.calls[0][0]).toEqual({
      requester_id: 'user-1',
      category_id: 'cat-1',
      title: 'No hay conexión a la red',
      description: 'El laboratorio perdió conectividad.',
      physical_location: 'Edificio A, laboratorio 2',
      channel: 'portal',
      urgency: 2,
      impact: 1,
    })
    expect(onClose).toHaveBeenCalled()
  })

  it('AC1: alta válida sin categoría ni urgencia envía null', async () => {
    createRequestMock.mockResolvedValue({
      id: 'req-2',
      requester_id: 'user-1',
      category_id: null,
      asset_id: null,
      service_level_version_id: null,
      related_request_id: null,
      folio: 'SIG-0002',
      title: 'Falla de impresora',
      description: 'La impresora del piso 3 no imprime.',
      physical_location: 'Edificio B, piso 3',
      channel: 'portal',
      status: 'registered',
      priority: null,
      urgency: null,
      impact: null,
      classification_confidence: null,
      first_response_at: null,
      resolved_at: null,
      closed_at: null,
      created_at: '2026-10-17T12:00:00Z',
      updated_at: '2026-10-17T12:00:00Z',
    })
    renderForm()

    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Título'), 'Falla de impresora')
    await user.type(
      screen.getByLabelText('Descripción'),
      'La impresora del piso 3 no imprime.',
    )
    await user.type(
      screen.getByLabelText('Ubicación física'),
      'Edificio B, piso 3',
    )
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    await waitFor(() => expect(createRequestMock).toHaveBeenCalledTimes(1))
    expect(createRequestMock.mock.calls[0][0]).toMatchObject({
      category_id: null,
      urgency: null,
      impact: null,
    })
  })

  // --- AC2: campos incompletos -----------------------------------------------

  it('AC2: campos vacíos muestra errores y no envía', async () => {
    renderForm()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(
      await screen.findByText('El título es obligatorio.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('La descripción es obligatoria.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('La ubicación física es obligatoria.'),
    ).toBeInTheDocument()
    expect(createRequestMock).not.toHaveBeenCalled()
  })

  it('AC2: al enviar vacío y luego llenar título, persisten los otros errores', async () => {
    renderForm()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Enviar' }))
    await screen.findByText('El título es obligatorio.')

    await user.type(screen.getByLabelText('Título'), 'Prueba')
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(screen.queryByText('El título es obligatorio.')).not.toBeInTheDocument()
    expect(
      screen.getByText('La descripción es obligatoria.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('La ubicación física es obligatoria.'),
    ).toBeInTheDocument()
    expect(createRequestMock).not.toHaveBeenCalled()
  })

  // --- AC3: credenciales inválidas -------------------------------------------

  it('AC3: error 401 muestra mensaje de sesión expirada y no cierra el formulario', async () => {
    createRequestMock.mockRejectedValue(
      new Error('Debes iniciar sesión para continuar.'),
    )
    const onClose = renderForm()

    const user = userEvent.setup()
    await fillValidForm(user)
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(
      await screen.findByText(
        'Tu sesión ha expirado. Inicia sesión nuevamente.',
      ),
    ).toBeInTheDocument()
    expect(createRequestMock).toHaveBeenCalledTimes(1)
    expect(onClose).not.toHaveBeenCalled()
    // El formulario sigue visible
    expect(screen.getByLabelText('Título')).toBeInTheDocument()
  })

  it('AC3: otro error del servidor muestra el mensaje original', async () => {
    createRequestMock.mockRejectedValue(
      new Error('El solicitante no está activo.'),
    )
    renderForm()

    const user = userEvent.setup()
    await fillValidForm(user)
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(
      await screen.findByText('El solicitante no está activo.'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('Tu sesión ha expirado.'),
    ).not.toBeInTheDocument()
  })
})
