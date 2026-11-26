import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import {
  asignarTecnico,
  getPropuestaAsignacion,
  type AsignacionResult,
  type CandidatoAsignacion,
} from '@/api/asignaciones'
import type { RequestStatus } from '@/api/seguimiento'
import { AsignarTecnicoPanel } from './AsignarTecnicoPanel'

vi.mock('@/api/asignaciones', () => ({
  getPropuestaAsignacion: vi.fn(),
  asignarTecnico: vi.fn(),
}))

const authState = vi.hoisted(() => ({ roles: ['support_agent'] as string[] }))
vi.mock('@/features/auth/auth-context', () => ({
  useAuth: () => ({
    user: { id: 'usuario-1', full_name: 'Persona', roles: authState.roles },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

const getPropuestaMock = vi.mocked(getPropuestaAsignacion)
const asignarMock = vi.mocked(asignarTecnico)

const REQUEST_ID = '11111111-1111-4111-8111-111111111111'

const CANDIDATOS: CandidatoAsignacion[] = [
  {
    technician_id: 'tec-1',
    full_name: 'Ana López',
    score: 85,
    active_load: 1,
    score_breakdown: 'Especialidad +50; carga -5',
    components: [
      { concepto: 'Especialidad', puntos: 50, detalle: 'Atiende Redes' },
      { concepto: 'Carga', puntos: -5, detalle: '1 solicitud activa' },
    ],
  },
  {
    technician_id: 'tec-2',
    full_name: 'Bruno Díaz',
    score: 40,
    active_load: 4,
    score_breakdown: 'Carga -20',
    components: [
      { concepto: 'Carga', puntos: -20, detalle: '4 solicitudes activas' },
    ],
  },
]

function renderPanel(status: RequestStatus = 'classified') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
  render(
    <QueryClientProvider client={queryClient}>
      <AsignarTecnicoPanel requestId={REQUEST_ID} status={status} />
    </QueryClientProvider>,
  )
  return { invalidateSpy }
}

beforeEach(() => {
  vi.clearAllMocks()
  authState.roles = ['support_agent']
})

describe('AsignarTecnicoPanel', () => {
  it('propone candidatos con puntaje y desglose, y marca el sugerido', async () => {
    getPropuestaMock.mockResolvedValue(CANDIDATOS)
    const user = userEvent.setup()
    renderPanel()

    expect(getPropuestaMock).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /proponer técnico/i }))

    const lista = await screen.findByRole('list', { name: 'Candidatos' })
    expect(getPropuestaMock).toHaveBeenCalledWith(REQUEST_ID)
    const items = within(lista).getAllByRole('listitem', { name: /./ })
    expect(items).toHaveLength(2)

    const ana = screen.getByRole('listitem', { name: 'Ana López' })
    expect(within(ana).getByText('Sugerido')).toBeInTheDocument()
    expect(within(ana).getByText(/Puntaje:/)).toHaveTextContent(
      'Puntaje: 85 · Carga actual: 1 solicitud',
    )
    expect(within(ana).getByText(/Atiende Redes/)).toHaveTextContent(
      'Especialidad (+50 pts): Atiende Redes',
    )

    const bruno = screen.getByRole('listitem', { name: 'Bruno Díaz' })
    expect(within(bruno).queryByText('Sugerido')).not.toBeInTheDocument()
    expect(within(bruno).getByText(/4 solicitudes activas/)).toHaveTextContent(
      'Carga (-20 pts): 4 solicitudes activas',
    )
  })

  it('asigna al técnico elegido tras confirmar y refresca el detalle', async () => {
    getPropuestaMock.mockResolvedValue(CANDIDATOS)
    asignarMock.mockResolvedValue({
      id: 'asig-1',
      request_id: REQUEST_ID,
      technician_id: 'tec-2',
      score: 40,
      score_breakdown: 'Carga -20',
      is_automatic: false,
      assigned_at: '2026-11-25T10:00:00Z',
      unassigned_at: null,
      request_status: 'assigned',
    } satisfies AsignacionResult)
    const user = userEvent.setup()
    const { invalidateSpy } = renderPanel()

    await user.click(screen.getByRole('button', { name: /proponer técnico/i }))
    const bruno = await screen.findByRole('listitem', { name: 'Bruno Díaz' })
    await user.click(within(bruno).getByRole('button', { name: 'Asignar' }))

    expect(asignarMock).not.toHaveBeenCalled()
    expect(
      within(bruno).getByText('¿Asignar a Bruno Díaz?'),
    ).toBeInTheDocument()
    await user.click(within(bruno).getByRole('button', { name: 'Confirmar' }))

    expect(asignarMock).toHaveBeenCalledWith(REQUEST_ID, 'tec-2')
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Solicitud asignada a Bruno Díaz.',
    )
    expect(
      screen.queryByRole('list', { name: 'Candidatos' }),
    ).not.toBeInTheDocument()
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['solicitudes', REQUEST_ID],
    })
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['solicitudes', 'lista'],
    })
  })

  it('muestra el estado vacío si no hay candidatos', async () => {
    getPropuestaMock.mockResolvedValue([])
    const user = userEvent.setup()
    renderPanel()

    await user.click(screen.getByRole('button', { name: /proponer técnico/i }))

    expect(
      await screen.findByText(
        'No hay técnicos disponibles para esta categoría.',
      ),
    ).toBeInTheDocument()
  })

  it('muestra el error del servidor con ErrorAlert', async () => {
    getPropuestaMock.mockResolvedValue(CANDIDATOS)
    asignarMock.mockRejectedValue(
      new ApiError(422, 'El técnico indicado está inactivo o no es técnico.', {
        code: 'technician_unavailable',
      }),
    )
    const user = userEvent.setup()
    renderPanel()

    await user.click(screen.getByRole('button', { name: /proponer técnico/i }))
    const ana = await screen.findByRole('listitem', { name: 'Ana López' })
    await user.click(within(ana).getByRole('button', { name: 'Asignar' }))
    await user.click(within(ana).getByRole('button', { name: 'Confirmar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'El técnico indicado está inactivo o no es técnico.',
    )
  })

  it('muestra el error al cargar la propuesta', async () => {
    getPropuestaMock.mockRejectedValue(
      new ApiError(404, 'La solicitud no existe.', { code: 'not_found' }),
    )
    const user = userEvent.setup()
    renderPanel()

    await user.click(screen.getByRole('button', { name: /proponer técnico/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'La solicitud no existe.',
    )
  })

  it('no aparece para el solicitante', () => {
    authState.roles = ['requester']
    renderPanel()

    expect(
      screen.queryByRole('heading', { name: 'Asignar técnico' }),
    ).not.toBeInTheDocument()
  })

  it.each<RequestStatus>(['resolved', 'closed', 'closed_unverified'])(
    'no aparece cuando la solicitud está %s',
    (status) => {
      renderPanel(status)

      expect(
        screen.queryByRole('heading', { name: 'Asignar técnico' }),
      ).not.toBeInTheDocument()
    },
  )

  it('aparece para un jefe de servicio con la solicitud abierta', () => {
    authState.roles = ['service_manager']
    renderPanel('assigned')

    expect(
      screen.getByRole('heading', { name: 'Asignar técnico' }),
    ).toBeInTheDocument()
  })
})
