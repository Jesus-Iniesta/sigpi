import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getCategories, type Category } from '@/api/catalog'
import type { User, UserRole } from '@/api/types'
import { AuthContext } from '@/features/auth/auth-context'
import {
  createSlaAgreement,
  getEffectiveSla,
  getSlaAgreements,
  getSlaOptions,
  getSlaVersions,
  publishSlaVersion,
  type SlaAgreement,
  type SlaVersion,
} from '@/api/sla'
import { SlaPage } from './sla-page'

vi.mock('@/api/sla', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/sla')>()),
  getSlaAgreements: vi.fn(),
  getSlaOptions: vi.fn(),
  createSlaAgreement: vi.fn(),
  getSlaVersions: vi.fn(),
  publishSlaVersion: vi.fn(),
  getEffectiveSla: vi.fn(),
}))
vi.mock('@/api/catalog', () => ({ getCategories: vi.fn() }))

const getAgreementsMock = vi.mocked(getSlaAgreements)
const createAgreementMock = vi.mocked(createSlaAgreement)
const getVersionsMock = vi.mocked(getSlaVersions)
const optionsMock = vi.mocked(getSlaOptions)
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
  name: 'Conectividad y redes',
  is_default: false,
  is_active: true,
  created_at: '2026-09-01T08:00:00Z',
}

const defaultAgreement: SlaAgreement = {
  id: 'ag-0',
  category_id: null,
  name: 'Acuerdo general de servicio',
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

const generalP1: SlaVersion = {
  ...v1,
  id: 'g1',
  agreement_id: 'ag-0',
  first_response_minutes: 30,
  resolution_minutes: 240,
}

const generalP3: SlaVersion = {
  ...v1,
  id: 'g3',
  agreement_id: 'ag-0',
  priority: 'P3',
  first_response_minutes: 60,
  resolution_minutes: 480,
}

const serviceTypes = [
  'Soporte a equipo de cómputo y periféricos',
  'Soporte de software y aplicaciones',
  'Conectividad y redes',
  'Cuentas y accesos institucionales',
]

function makeUser(roles: UserRole[]): User {
  return {
    id: 'user-1',
    email: 'persona@sigpi.test',
    full_name: 'Persona de prueba',
    is_active: true,
    roles,
  } as User
}

function renderPage(roles: UserRole[] = ['administrator']) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <AuthContext.Provider
      value={{
        user: makeUser(roles),
        isLoading: false,
        isAuthenticated: true,
        sessionExpired: false,
        login: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <QueryClientProvider client={queryClient}>
        <SlaPage />
      </QueryClientProvider>
    </AuthContext.Provider>,
  )
}

describe('SlaPage: configuración de Tickets (S2-14, COR-05, HU-08.1)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    categoriesMock.mockResolvedValue([category])
    getAgreementsMock.mockResolvedValue([agreement])
    getVersionsMock.mockResolvedValue([v1])
    optionsMock.mockResolvedValue({
      default_name: 'Acuerdo general de servicio',
      service_types: serviceTypes,
    })
  })

  it('COR-05: no muestra «SLA» como texto visible y titula la página «Tickets»', async () => {
    const { container } = renderPage()
    await screen.findByText('v1')

    expect(
      screen.getByRole('heading', { level: 1, name: 'Tickets' }),
    ).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/\bSLA\b/)

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nuevo acuerdo/i }))
    expect(container.textContent).not.toMatch(/\bSLA\b/)
  })

  it('COR-05: el nombre del acuerdo se elige de los tipos de servicio', async () => {
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nuevo acuerdo/i }))
    const name = screen.getByLabelText('Nombre del acuerdo')

    expect(name.tagName).toBe('SELECT')
    await waitFor(() => expect(name).toBeEnabled())
    expect(
      screen.getAllByRole('option').map((option) => option.textContent),
    ).toEqual(expect.arrayContaining(serviceTypes))
  })

  it('COR-05: el predeterminado muestra el nombre fijo y deshabilitado', async () => {
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nuevo acuerdo/i }))
    await user.selectOptions(screen.getByLabelText('Alcance'), 'default')

    const name = screen.getByLabelText('Nombre del acuerdo')
    expect(name).toBeDisabled()
    expect(name).toHaveDisplayValue('Acuerdo general de servicio')
  })

  it('COR-05: exige elegir un tipo de servicio', async () => {
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nuevo acuerdo/i }))
    await user.selectOptions(screen.getByLabelText('Categoría'), 'cat-1')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(
      await screen.findByText('Selecciona el tipo de servicio del acuerdo.'),
    ).toBeInTheDocument()
    expect(createAgreementMock).not.toHaveBeenCalled()
  })

  it('COR-05: precarga los tiempos del acuerdo general en una versión nueva', async () => {
    getAgreementsMock.mockResolvedValue([agreement, defaultAgreement])
    getVersionsMock.mockImplementation(async (agreementId) =>
      agreementId === 'ag-0' ? [generalP1, generalP3] : [v1],
    )
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await waitFor(() => expect(getVersionsMock).toHaveBeenCalledWith('ag-0'))
    await user.click(screen.getByRole('button', { name: /nueva versión/i }))
    await user.click(
      screen.getByRole('button', { name: 'Usar tiempos del acuerdo general' }),
    )

    expect(screen.getByLabelText('Primera respuesta (P1)')).toHaveValue(30)
    expect(screen.getByLabelText('Resolución (P1)')).toHaveValue(240)
    expect(screen.getByLabelText('Incluir P3')).toBeChecked()
    expect(screen.getByLabelText('Resolución (P3)')).toHaveValue(480)
    expect(screen.getByLabelText('Incluir P2')).not.toBeChecked()
  })

  it('COR-05: no ofrece tiempos de referencia si no hay acuerdo general', async () => {
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nueva versión/i }))

    expect(
      screen.queryByRole('button', {
        name: 'Usar tiempos del acuerdo general',
      }),
    ).not.toBeInTheDocument()
  })

  it('muestra los acuerdos y el histórico de versiones del seleccionado', async () => {
    renderPage()

    expect(
      await screen.findByRole('heading', { name: 'Conectividad y redes' }),
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
    await user.selectOptions(
      await screen.findByRole('combobox', { name: 'Nombre del acuerdo' }),
      'Conectividad y redes',
    )
    await user.selectOptions(screen.getByLabelText('Categoría'), 'cat-1')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => expect(createAgreementMock).toHaveBeenCalledTimes(1))
    expect(createAgreementMock.mock.calls[0][0]).toEqual({
      name: 'Conectividad y redes',
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
    await user.selectOptions(screen.getByLabelText('Alcance'), 'default')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => expect(createAgreementMock).toHaveBeenCalledTimes(1))
    expect(createAgreementMock.mock.calls[0][0]).toEqual({ is_default: true })
  })

  it('muestra el error del servidor cuando el acuerdo ya existe', async () => {
    createAgreementMock.mockRejectedValue(
      new Error('La categoría ya tiene un acuerdo activo.'),
    )
    renderPage()
    await screen.findByText('v1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /nuevo acuerdo/i }))
    await user.selectOptions(
      await screen.findByRole('combobox', { name: 'Nombre del acuerdo' }),
      'Conectividad y redes',
    )
    await user.selectOptions(screen.getByLabelText('Categoría'), 'cat-1')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(
      await screen.findByText('La categoría ya tiene un acuerdo activo.'),
    ).toBeInTheDocument()
  })

  it('AC3: avisa cuando se aplica el acuerdo predeterminado', async () => {
    effectiveMock.mockResolvedValue({
      agreement_id: 'ag-0',
      agreement_name: 'Acuerdo general de servicio',
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
      agreement_name: 'Conectividad y redes',
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

  describe('COR-06B: descarga del contrato en PDF', () => {
    const contractButton = { name: 'Descargar contrato (PDF)' }
    let fetchMock: ReturnType<typeof vi.fn>
    let createUrlMock: ReturnType<typeof vi.fn>
    let clickSpy: ReturnType<typeof vi.spyOn>
    let downloadedName: string | null

    beforeEach(() => {
      fetchMock = vi.fn()
      vi.stubGlobal('fetch', fetchMock)
      createUrlMock = vi.fn(() => 'blob:contrato')
      URL.createObjectURL = createUrlMock as typeof URL.createObjectURL
      URL.revokeObjectURL = vi.fn()
      downloadedName = null
      clickSpy = vi
        .spyOn(HTMLAnchorElement.prototype, 'click')
        .mockImplementation(function (this: HTMLAnchorElement) {
          downloadedName = this.download
        })
    })

    afterEach(() => {
      clickSpy.mockRestore()
      vi.unstubAllGlobals()
    })

    function pdfResponse(headers: Record<string, string> = {}) {
      // Cuerpo como texto: el Blob de jsdom no tiene `stream()` y el Response de Node 22 lo exige.
      return new Response('%PDF-1.4', {
        status: 200,
        headers: { 'Content-Type': 'application/pdf', ...headers },
      })
    }

    it.each<UserRole>(['administrator', 'requester'])(
      'muestra el botón para %s',
      async (role) => {
        renderPage([role])
        await screen.findByText('v1')

        expect(screen.getByRole('button', contractButton)).toBeInTheDocument()
      },
    )

    it('no muestra el botón para support_agent', async () => {
      renderPage(['support_agent'])
      await screen.findByText('v1')

      expect(
        screen.queryByRole('button', contractButton),
      ).not.toBeInTheDocument()
    })

    it('descarga el PDF del acuerdo seleccionado con la URL correcta', async () => {
      let resolveFetch: (response: Response) => void = () => {}
      fetchMock.mockReturnValue(
        new Promise<Response>((resolve) => {
          resolveFetch = resolve
        }),
      )
      renderPage(['administrator'])
      await screen.findByText('v1')

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', contractButton))

      const generating = await screen.findByRole('button', {
        name: 'Generando…',
      })
      expect(generating).toBeDisabled()
      expect(fetchMock).toHaveBeenCalledTimes(1)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('http://localhost:8000/sla/agreements/ag-1/contrato.pdf')
      expect(init.credentials).toBe('include')

      resolveFetch(
        pdfResponse({
          'Content-Disposition':
            'attachment; filename="contrato-conectividad-y-redes-v1.pdf"',
        }),
      )

      await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1))
      expect(createUrlMock).toHaveBeenCalledWith(
        expect.objectContaining({ size: 8, type: 'application/pdf' }),
      )
      expect(downloadedName).toBe('contrato-conectividad-y-redes-v1.pdf')
      expect(await screen.findByRole('button', contractButton)).toBeEnabled()
    })

    it('usa contrato.pdf si no puede leer Content-Disposition', async () => {
      fetchMock.mockResolvedValue(pdfResponse())
      renderPage(['administrator'])
      await screen.findByText('v1')

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', contractButton))

      await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1))
      expect(downloadedName).toBe('contrato.pdf')
    })

    it('muestra el mensaje del servidor si no hay versión vigente', async () => {
      fetchMock.mockResolvedValue(
        new Response(
          JSON.stringify({
            detail:
              'El acuerdo no tiene una versión vigente; publica una antes de generar el contrato.',
            code: 'sla_without_current_version',
            request_id: 'req-123',
          }),
          { status: 422, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      renderPage(['administrator'])
      await screen.findByText('v1')

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', contractButton))

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'El acuerdo no tiene una versión vigente; publica una antes de generar el contrato.',
      )
      expect(createUrlMock).not.toHaveBeenCalled()
      expect(clickSpy).not.toHaveBeenCalled()
    })
  })
})
