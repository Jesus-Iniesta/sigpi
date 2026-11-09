import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { getCategories } from '@/api/catalog'
import {
  getRevisionQueue,
  submitRevision,
  type RevisionItem,
} from '@/api/revision'
import { RevisionPage } from './RevisionPage'

vi.mock('@/api/revision', () => ({
  getRevisionQueue: vi.fn(),
  submitRevision: vi.fn(),
}))
vi.mock('@/api/catalog', () => ({
  getCategories: vi.fn(),
}))

const getRevisionQueueMock = vi.mocked(getRevisionQueue)
const submitRevisionMock = vi.mocked(submitRevision)
const getCategoriesMock = vi.mocked(getCategories)

const RESULT_ID = '22222222-2222-4222-8222-222222222222'

function buildItem(overrides: Partial<RevisionItem> = {}): RevisionItem {
  return {
    result_id: RESULT_ID,
    request_id: 'req-1',
    folio: 'SIG-0012',
    title: 'No puedo entrar a mi correo',
    description: 'Dice que mi contraseña es incorrecta.',
    created_at: '2026-10-20T09:00:00Z',
    category_id: 'cat-1',
    category_name: 'Redes',
    urgency: 2,
    impact: 2,
    priority: 'P3',
    confidence: 0.62,
    source: 'model',
    model_version: 'clasificador-v1',
    ...overrides,
  }
}

const CATEGORIES = [
  {
    id: 'cat-1',
    area_id: 'a-1',
    name: 'Redes',
    description: null,
    is_active: true,
  },
  {
    id: 'cat-2',
    area_id: 'a-1',
    name: 'Cuentas y accesos',
    description: null,
    is_active: true,
  },
  {
    id: 'cat-3',
    area_id: 'a-1',
    name: 'Obsoleta',
    description: null,
    is_active: false,
  },
]

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <RevisionPage />
    </QueryClientProvider>,
  )
}

describe('RevisionPage: revisión de clasificaciones (S4-15, HU-02.2)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    getCategoriesMock.mockResolvedValue(CATEGORIES)
  })

  it('muestra la propuesta del sistema con su confianza y origen', async () => {
    getRevisionQueueMock.mockResolvedValue([buildItem()])
    renderPage()

    expect(await screen.findByText('SIG-0012')).toBeInTheDocument()
    expect(screen.getByText('No puedo entrar a mi correo')).toBeInTheDocument()
    expect(screen.getByText('Confianza 62 %')).toBeInTheDocument()
    expect(screen.getByText('Modelo · clasificador-v1')).toBeInTheDocument()
    expect(screen.getByText('1 clasificación pendiente')).toBeInTheDocument()
  })

  it('ofrece solo las categorías activas y parte de la propuesta', async () => {
    getRevisionQueueMock.mockResolvedValue([buildItem()])
    renderPage()

    const categoria = await screen.findByLabelText('Categoría')
    expect(
      await screen.findByRole('option', { name: 'Cuentas y accesos' }),
    ).toBeInTheDocument()
    expect(categoria).toHaveValue('cat-1')
    expect(screen.queryByRole('option', { name: 'Obsoleta' })).toBeNull()
    expect(screen.getByLabelText('Urgencia')).toHaveValue('2')
    expect(screen.getByLabelText('Impacto')).toHaveValue('2')
  })

  it('muestra un mensaje cuando no hay nada por revisar', async () => {
    getRevisionQueueMock.mockResolvedValue([])
    renderPage()

    expect(
      await screen.findByText('No hay clasificaciones pendientes de revisión.'),
    ).toBeInTheDocument()
  })

  it('exige la justificación y no envía nada sin ella', async () => {
    getRevisionQueueMock.mockResolvedValue([buildItem()])
    renderPage()
    const user = userEvent.setup()

    await user.click(
      await screen.findByRole('button', { name: 'Guardar revisión' }),
    )

    expect(
      screen.getByText('La justificación es obligatoria.'),
    ).toBeInTheDocument()
    expect(submitRevisionMock).not.toHaveBeenCalled()
  })

  it('avisa qué cambió respecto de la propuesta', async () => {
    getRevisionQueueMock.mockResolvedValue([buildItem()])
    renderPage()
    const user = userEvent.setup()

    expect(await screen.findByText(/Sin cambios/)).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Urgencia'), '3')

    expect(screen.getByText(/Cambias: urgencia\./)).toBeInTheDocument()
  })

  it('guarda la corrección con su justificación y saca la solicitud de la cola', async () => {
    getRevisionQueueMock
      .mockResolvedValueOnce([buildItem()])
      .mockResolvedValueOnce([])
    submitRevisionMock.mockResolvedValue({
      request_id: 'req-1',
      status: 'classified',
      priority: 'P2',
    })
    renderPage()
    const user = userEvent.setup()

    await screen.findByText('SIG-0012')
    await screen.findByRole('option', { name: 'Cuentas y accesos' })
    await user.selectOptions(screen.getByLabelText('Categoría'), 'cat-2')
    await user.selectOptions(screen.getByLabelText('Urgencia'), '3')
    await user.type(
      screen.getByLabelText('Justificación'),
      '  Es un problema de cuenta, no de red.  ',
    )
    await user.click(screen.getByRole('button', { name: 'Guardar revisión' }))

    expect(submitRevisionMock).toHaveBeenCalledWith(RESULT_ID, {
      category_id: 'cat-2',
      urgency: 3,
      impact: 2,
      justification: 'Es un problema de cuenta, no de red.',
    })
    expect(
      await screen.findByText('Revisaste SIG-0012. Nueva prioridad: P2.'),
    ).toBeInTheDocument()
    expect(
      await screen.findByText('No hay clasificaciones pendientes de revisión.'),
    ).toBeInTheDocument()
  })

  it('muestra el error del servidor y conserva lo escrito', async () => {
    getRevisionQueueMock.mockResolvedValue([buildItem()])
    submitRevisionMock.mockRejectedValue(
      new ApiError(409, 'La solicitud ya fue revisada por otra persona.', {
        code: 'conflict',
      }),
    )
    renderPage()
    const user = userEvent.setup()

    await screen.findByText('SIG-0012')
    await user.type(
      screen.getByLabelText('Justificación'),
      'Confirmo la propuesta.',
    )
    await user.click(screen.getByRole('button', { name: 'Guardar revisión' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'La solicitud ya fue revisada por otra persona.',
    )
    expect(screen.getByLabelText('Justificación')).toHaveValue(
      'Confirmo la propuesta.',
    )
  })
})
