import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getRequestDetail,
  getRequestLog,
  type RequestDetail,
  type RequestLogEntry,
} from '@/api/seguimiento'
import { SolicitudDetallePage } from './SolicitudDetallePage'

vi.mock('@/api/seguimiento', () => ({
  getRequestDetail: vi.fn(),
  getRequestLog: vi.fn(),
}))
vi.mock('@/features/auth/auth-context', () => ({
  useAuth: () => ({
    user: { id: 'tecnico-1', full_name: 'Técnico de prueba', roles: [] },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

const getRequestDetailMock = vi.mocked(getRequestDetail)
const getRequestLogMock = vi.mocked(getRequestLog)

const REQUEST_ID = '11111111-1111-4111-8111-111111111111'

function buildRequest(overrides: Partial<RequestDetail> = {}): RequestDetail {
  return {
    id: REQUEST_ID,
    requester_id: 'solicitante-1',
    requester_institutional_id: 'uaem-local-001',
    category_id: null,
    asset_id: null,
    service_level_version_id: null,
    related_request_id: null,
    folio: 'SIG-0007',
    title: 'No hay conexión a la red',
    description: 'El laboratorio perdió conectividad.',
    physical_location: 'Edificio A, laboratorio 2',
    channel: 'phone',
    status: 'in_progress',
    priority: 'P2',
    urgency: 2,
    impact: 3,
    classification_confidence: null,
    diagnosis: null,
    solution: null,
    resolution_minutes: null,
    first_response_at: '2026-10-17T10:00:00Z',
    resolved_at: null,
    closed_at: null,
    created_at: '2026-10-17T09:00:00Z',
    updated_at: '2026-10-17T10:00:00Z',
    ...overrides,
  }
}

function buildEntry(overrides: Partial<RequestLogEntry> = {}): RequestLogEntry {
  return {
    id: 'log-1',
    request_id: REQUEST_ID,
    author_id: 'tecnico-1',
    previous_status: null,
    new_status: 'registered',
    action: 'Solicitud registrada por teléfono',
    notes: null,
    created_at: '2026-10-17T09:00:00Z',
    ...overrides,
  }
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/solicitudes/${REQUEST_ID}`]}>
        <Routes>
          <Route path="/solicitudes/:id" element={<SolicitudDetallePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const bitacoraRegion = () => screen.getByRole('region', { name: 'Bitácora' })

describe('SolicitudDetallePage: detalle con bitácora (S3-13, HU-04.1)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    getRequestDetailMock.mockResolvedValue(buildRequest())
    getRequestLogMock.mockResolvedValue([buildEntry()])
  })

  it('consulta el detalle y la bitácora con el identificador de la ruta', async () => {
    renderPage()

    await screen.findByRole('heading', { name: 'No hay conexión a la red' })
    expect(getRequestDetailMock).toHaveBeenCalledWith(REQUEST_ID)
    expect(getRequestLogMock).toHaveBeenCalledWith(REQUEST_ID)
  })

  it('muestra el folio, el título, el estado y la prioridad', async () => {
    renderPage()

    expect(
      await screen.findByRole('heading', { name: 'No hay conexión a la red' }),
    ).toBeInTheDocument()
    expect(screen.getByText('SIG-0007')).toBeInTheDocument()
    expect(screen.getByText('En proceso')).toBeInTheDocument()
    expect(screen.getByText('P2')).toBeInTheDocument()
  })

  it('muestra los datos de la solicitud', async () => {
    renderPage()

    const datos = await screen.findByRole('region', {
      name: 'Datos de la solicitud',
    })
    expect(
      within(datos).getByText('El laboratorio perdió conectividad.'),
    ).toBeInTheDocument()
    expect(within(datos).getByText('uaem-local-001')).toBeInTheDocument()
    expect(within(datos).getByText('Teléfono')).toBeInTheDocument()
    expect(
      within(datos).getByText('Edificio A, laboratorio 2'),
    ).toBeInTheDocument()
    expect(within(datos).getByText('Media')).toBeInTheDocument()
    expect(within(datos).getByText('Alta')).toBeInTheDocument()
  })

  it('sin diagnóstico ni solución indica que aún no se registran', async () => {
    renderPage()

    const atencion = await screen.findByRole('region', {
      name: 'Diagnóstico y solución',
    })
    expect(
      within(atencion).getByText('Aún no se registra un diagnóstico.'),
    ).toBeInTheDocument()
    expect(
      within(atencion).getByText('Aún no se registra una solución.'),
    ).toBeInTheDocument()
  })

  it('con solicitud resuelta muestra diagnóstico, solución y tiempo efectivo', async () => {
    getRequestDetailMock.mockResolvedValue(
      buildRequest({
        status: 'resolved',
        diagnosis: 'Cable de red dañado',
        solution: 'Se reemplazó el cable',
        resolution_minutes: 150,
        resolved_at: '2026-10-17T11:30:00Z',
      }),
    )
    renderPage()

    const atencion = await screen.findByRole('region', {
      name: 'Diagnóstico y solución',
    })
    expect(
      within(atencion).getByText('Cable de red dañado'),
    ).toBeInTheDocument()
    expect(
      within(atencion).getByText('Se reemplazó el cable'),
    ).toBeInTheDocument()
    expect(screen.getByText('2 h 30 min')).toBeInTheDocument()
    // «Resuelta» aparece como etiqueta del campo y como estado en el encabezado.
    expect(screen.getAllByText('Resuelta')).toHaveLength(2)
  })

  it('sin prioridad calculada no muestra la etiqueta de prioridad', async () => {
    getRequestDetailMock.mockResolvedValue(
      buildRequest({ priority: null, urgency: null, impact: null }),
    )
    renderPage()

    await screen.findByRole('heading', { name: 'No hay conexión a la red' })
    expect(screen.queryByText('P2')).not.toBeInTheDocument()
    expect(screen.getAllByText('Sin definir')).toHaveLength(2)
  })

  // --- Bitácora ------------------------------------------------------------------

  it('lista las entradas de la bitácora en el orden recibido', async () => {
    getRequestLogMock.mockResolvedValue([
      buildEntry({ id: 'log-1', action: 'Solicitud registrada por teléfono' }),
      buildEntry({
        id: 'log-2',
        action: 'Atención iniciada',
        previous_status: 'assigned',
        new_status: 'in_progress',
      }),
      buildEntry({
        id: 'log-3',
        action: 'Solicitud resuelta',
        previous_status: 'in_progress',
        new_status: 'resolved',
        notes: 'Solución aplicada: se reemplazó el cable.',
      }),
    ])
    renderPage()

    await screen.findByText('Atención iniciada')
    const entradas = within(bitacoraRegion()).getAllByRole('listitem')
    expect(entradas).toHaveLength(3)
    expect(entradas[0]).toHaveTextContent('Solicitud registrada por teléfono')
    expect(entradas[1]).toHaveTextContent('Atención iniciada')
    expect(entradas[1]).toHaveTextContent('Asignada → En proceso')
    expect(entradas[2]).toHaveTextContent('Solicitud resuelta')
    expect(entradas[2]).toHaveTextContent(
      'Solución aplicada: se reemplazó el cable.',
    )
  })

  it('identifica al autor: «Tú» para el usuario actual y un identificador corto para los demás', async () => {
    getRequestLogMock.mockResolvedValue([
      buildEntry({ id: 'log-1', author_id: 'tecnico-1' }),
      buildEntry({
        id: 'log-2',
        author_id: 'abcdef12-0000-4000-8000-000000000000',
      }),
    ])
    renderPage()

    await screen.findAllByRole('listitem')
    const entradas = within(bitacoraRegion()).getAllByRole('listitem')
    expect(entradas[0]).toHaveTextContent('Tú')
    expect(entradas[1]).toHaveTextContent('Usuario abcdef12')
  })

  it('una bitácora sin entradas muestra un mensaje', async () => {
    getRequestLogMock.mockResolvedValue([])
    renderPage()

    expect(
      await screen.findByText(
        'Esta solicitud todavía no tiene entradas en la bitácora.',
      ),
    ).toBeInTheDocument()
  })

  // --- Contingencia: solicitante por verificar ---------------------------------------

  it('una solicitud por verificar muestra el aviso y la nota de la bitácora', async () => {
    getRequestDetailMock.mockResolvedValue(
      buildRequest({
        status: 'pending_verification',
        requester_id: null,
        requester_institutional_id: 'desconocido-999',
      }),
    )
    getRequestLogMock.mockResolvedValue([
      buildEntry({
        new_status: 'pending_verification',
        notes:
          'Solicitante «desconocido-999» por verificar: no aparece en el directorio.',
      }),
    ])
    renderPage()

    expect(await screen.findByRole('note')).toHaveTextContent(
      'quedó por verificar',
    )
    expect(screen.getAllByText('Por verificar').length).toBeGreaterThan(0)
    expect(screen.getByText('desconocido-999')).toBeInTheDocument()
    expect(
      await screen.findByText(/no aparece en el directorio/),
    ).toBeInTheDocument()
  })

  it('una solicitud en otro estado no muestra el aviso de verificación', async () => {
    renderPage()

    await screen.findByRole('heading', { name: 'No hay conexión a la red' })
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  // --- Errores ---------------------------------------------------------------------

  it('si el detalle falla muestra el error y un enlace para volver', async () => {
    getRequestDetailMock.mockRejectedValue(
      new Error('request 11111111 does not exist'),
    )
    renderPage()

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('No se pudo cargar la solicitud.')
    expect(alerta).toHaveTextContent('does not exist')
    expect(
      screen.getByRole('link', { name: /Volver a solicitudes/ }),
    ).toHaveAttribute('href', '/solicitudes')
  })

  it('si solo falla la bitácora, el detalle se sigue mostrando', async () => {
    getRequestLogMock.mockRejectedValue(
      new Error('No tienes permiso para realizar esta acción.'),
    )
    renderPage()

    expect(
      await screen.findByRole('heading', { name: 'No hay conexión a la red' }),
    ).toBeInTheDocument()
    expect(
      await within(bitacoraRegion()).findByRole('alert'),
    ).toHaveTextContent(
      'No se pudo cargar la bitácora. No tienes permiso para realizar esta acción.',
    )
  })

  it('mientras carga muestra un indicador', () => {
    getRequestDetailMock.mockReturnValue(new Promise<RequestDetail>(() => {}))
    renderPage()

    expect(screen.getByRole('status')).toHaveTextContent('Cargando solicitud…')
  })
})
