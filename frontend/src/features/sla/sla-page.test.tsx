import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getCategories, type Category } from '@/api/catalog'
import {
  createSlaAgreement,
  getEffectiveSla,
  getSlaAgreements,
  getSlaVersions,
  publishSlaVersion,
  type SlaAgreement,
  type SlaVersion,
} from '@/api/sla'
import { SlaPage } from './sla-page'

vi.mock('@/api/sla', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/sla')>()),
  getSlaAgreements: vi.fn(),
  createSlaAgreement: vi.fn(),
  getSlaVersions: vi.fn(),
  publishSlaVersion: vi.fn(),
  getEffectiveSla: vi.fn(),
}))
vi.mock('@/api/catalog', () => ({ getCategories: vi.fn() }))

const getAgreementsMock = vi.mocked(getSlaAgreements)
const createAgreementMock = vi.mocked(createSlaAgreement)
const getVersionsMock = vi.mocked(getSlaVersions)
const publishMock = vi.mocked(publishSlaVersion)
const effectiveMock = vi.mocked(getEffectiveSla)
const categoriesMock = vi.mocked(getCategories)

const category: Category = {
  id: 'cat-1',
  area_id: 'area-1',
  name: 'Conectividad',
  description: null,
  is_active: true,
}

const agreement: SlaAgreement = {
  id: 'ag-1',
  category_id: 'cat-1',
  name: 'Acuerdo de conectividad',
  is_default: false,
  is_active: true,
  created_at: '2026-09-01T08:00:00Z',
}

const defaultAgreement: SlaAgreement = {
  id: 'ag-0',
  category_id: null,
  name: 'Acuerdo predeterminado',
  is_default: true,
  is_active: true,
  created_at: '2026-09-01T08:00:00Z',
}

const v1: SlaVersion = {
  id: 'v1',
  agreement_id: 'ag-1',
  version: 1,
  priority: 'P1',
  first_response_minutes: 15,
  resolution_minutes: 120,
  valid_from: '2026-09-01T08:00:00Z',
  valid_to: null,
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <SlaPage />
    </QueryClientProvider>,
  )
}

describe('SlaPage: configuración de SLA (S2-14, HU-08.1)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    categoriesMock.mockResolvedValue([category])
    getAgreementsMock.mockResolvedValue([agreement])
    getVersionsMock.mockResolvedValue([v1])
  })

  it('muestra los acuerdos y el histórico de versiones del seleccionado', async () => {
    renderPage()

    expect(
      await screen.findByRole('heading', { name: 'Acuerdo de conectividad' }),
    ).toBeInTheDocument()
    expect(await screen.findByText('v1')).toBeInTheDocument()
    expect(screen.getByText('15 min')).toBeInTheDocument()
    expect(screen.getByText('2 h')).toBeInTheDocument()
    expect(screen.getByText('Vigente')).toBeInTheDocument()
  })

  it('muestra el estado vacío cuando no hay acuerdos', async () => {
    getAgreementsMock.mockResolvedValue([])

    renderPage()

    expect(
      await screen.findByText('No hay acuerdos configurados'),
    ).toBeInTheDocument()
  })

  it('AC2: rechaza una resolución menor o igual a la primera respuesta', async () => {
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nueva versión/i }))
    const resolution = screen.getByLabelText('Resolución (P1)')
    await user.clear(resolution)
    await user.type(resolution, '10')
    await user.click(screen.getByRole('button', { name: 'Publicar versión' }))

    expect(
      await screen.findByText(/La resolución debe ser mayor/),
    ).toBeInTheDocument()
    expect(publishMock).not.toHaveBeenCalled()
  })

  it('AC2: rechaza una resolución igual a la primera respuesta', async () => {
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nueva versión/i }))
    const resolution = screen.getByLabelText('Resolución (P1)')
    await user.clear(resolution)
    await user.type(resolution, '15')
    await user.click(screen.getByRole('button', { name: 'Publicar versión' }))

    expect(
      await screen.findByText(/La resolución debe ser mayor/),
    ).toBeInTheDocument()
    expect(publishMock).not.toHaveBeenCalled()
  })

  it('AC2: exige incluir al menos una prioridad', async () => {
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nueva versión/i }))
    await user.click(screen.getByLabelText('Incluir P1'))
    await user.click(screen.getByRole('button', { name: 'Publicar versión' }))

    expect(
      await screen.findByText('Incluye al menos una prioridad.'),
    ).toBeInTheDocument()
    expect(publishMock).not.toHaveBeenCalled()
  })

  it('AC1: publica una versión nueva con su fecha de entrada en vigor', async () => {
    publishMock.mockResolvedValue([{ ...v1, id: 'v2', version: 2 }])
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nueva versión/i }))
    fireEvent.change(screen.getByLabelText('Entrada en vigor'), {
      target: { value: '2026-11-01T08:00' },
    })
    const first = screen.getByLabelText('Primera respuesta (P1)')
    const resolution = screen.getByLabelText('Resolución (P1)')
    await user.clear(first)
    await user.type(first, '10')
    await user.clear(resolution)
    await user.type(resolution, '60')
    await user.click(screen.getByRole('button', { name: 'Publicar versión' }))

    await waitFor(() => expect(publishMock).toHaveBeenCalledTimes(1))
    expect(publishMock.mock.calls[0][0]).toBe('ag-1')
    expect(publishMock.mock.calls[0][1]).toEqual({
      valid_from: new Date('2026-11-01T08:00').toISOString(),
      times: [
        { priority: 'P1', first_response_minutes: 10, resolution_minutes: 60 },
      ],
    })
    await waitFor(() =>
      expect(
        screen.queryByRole('heading', { name: 'Nueva versión' }),
      ).not.toBeInTheDocument(),
    )
  })

  it('crea un acuerdo por categoría', async () => {
    createAgreementMock.mockResolvedValue({ ...agreement, id: 'ag-2' })
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nuevo acuerdo/i }))
    await user.type(screen.getByLabelText('Nombre del acuerdo'), 'Redes')
    await user.selectOptions(screen.getByLabelText('Categoría'), 'cat-1')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => expect(createAgreementMock).toHaveBeenCalledTimes(1))
    expect(createAgreementMock.mock.calls[0][0]).toEqual({
      name: 'Redes',
      category_id: 'cat-1',
      is_default: false,
    })
  })

  it('crea el acuerdo predeterminado sin categoría', async () => {
    createAgreementMock.mockResolvedValue(defaultAgreement)
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nuevo acuerdo/i }))
    await user.type(
      screen.getByLabelText('Nombre del acuerdo'),
      'Acuerdo predeterminado',
    )
    await user.selectOptions(screen.getByLabelText('Alcance'), 'default')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => expect(createAgreementMock).toHaveBeenCalledTimes(1))
    expect(createAgreementMock.mock.calls[0][0]).toEqual({
      name: 'Acuerdo predeterminado',
      is_default: true,
    })
  })

  it('muestra el error del servidor cuando el acuerdo ya existe', async () => {
    createAgreementMock.mockRejectedValue(
      new Error('La categoría ya tiene un acuerdo activo.'),
    )
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nuevo acuerdo/i }))
    await user.type(screen.getByLabelText('Nombre del acuerdo'), 'Redes')
    await user.selectOptions(screen.getByLabelText('Categoría'), 'cat-1')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(
      await screen.findByText('La categoría ya tiene un acuerdo activo.'),
    ).toBeInTheDocument()
  })

  it('AC3: avisa cuando se aplica el acuerdo predeterminado', async () => {
    effectiveMock.mockResolvedValue({
      agreement_id: 'ag-0',
      agreement_name: 'Acuerdo predeterminado',
      version: 1,
      priority: 'P3',
      first_response_minutes: 60,
      resolution_minutes: 480,
      valid_from: '2026-09-01T08:00:00Z',
      used_default: true,
      notice:
        'No hay acuerdo configurado para la categoría y la prioridad P3; se aplicó el acuerdo predeterminado.',
    })
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.selectOptions(
      screen.getByLabelText('Categoría de consulta'),
      'cat-1',
    )
    await user.selectOptions(
      screen.getByLabelText('Prioridad de consulta'),
      'P3',
    )
    await user.click(screen.getByRole('button', { name: /consultar/i }))

    expect(await screen.findByRole('status')).toHaveTextContent(
      /se aplicó el acuerdo predeterminado/,
    )
    expect(effectiveMock.mock.calls[0][0]).toEqual({
      priority: 'P3',
      categoryId: 'cat-1',
    })
    expect(screen.getByText('8 h')).toBeInTheDocument()
  })

  it('no muestra aviso cuando el acuerdo es propio de la categoría', async () => {
    effectiveMock.mockResolvedValue({
      agreement_id: 'ag-1',
      agreement_name: 'Acuerdo de conectividad',
      version: 1,
      priority: 'P1',
      first_response_minutes: 15,
      resolution_minutes: 120,
      valid_from: '2026-09-01T08:00:00Z',
      used_default: false,
      notice: null,
    })
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /consultar/i }))

    expect(
      await screen.findByText('v1', { selector: 'dd' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
