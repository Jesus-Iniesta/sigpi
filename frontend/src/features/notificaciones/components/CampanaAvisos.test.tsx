import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import {
  getAvisos,
  getAvisosSinLeer,
  marcarAvisoLeido,
  marcarTodosLosAvisosLeidos,
  type Aviso,
} from '@/api/notificaciones'
import { CampanaAvisos } from './CampanaAvisos'

vi.mock('@/api/notificaciones', () => ({
  getAvisos: vi.fn(),
  getAvisosSinLeer: vi.fn(),
  marcarAvisoLeido: vi.fn(),
  marcarTodosLosAvisosLeidos: vi.fn(),
}))

const getAvisosMock = vi.mocked(getAvisos)
const getAvisosSinLeerMock = vi.mocked(getAvisosSinLeer)
const marcarAvisoLeidoMock = vi.mocked(marcarAvisoLeido)
const marcarTodosMock = vi.mocked(marcarTodosLosAvisosLeidos)

function construirAviso(sobrescribir: Partial<Aviso> = {}): Aviso {
  return {
    id: 'aviso-1',
    request_id: 'req-1',
    request_folio: 'SIG-0012',
    subject: 'Tu solicitud fue asignada',
    body: 'Se asignó al técnico Luis Pérez; fecha compromiso 12/11.',
    importance: 'normal',
    is_read: false,
    read_at: null,
    created_at: '2026-11-07T10:00:00Z',
    ...sobrescribir,
  }
}

function renderizar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <CampanaAvisos />
    </QueryClientProvider>,
  )
}

describe('CampanaAvisos (S4-06, HU-07.1)', () => {
  beforeEach(() => {
    getAvisosSinLeerMock.mockResolvedValue(0)
    getAvisosMock.mockResolvedValue([])
    marcarAvisoLeidoMock.mockResolvedValue(construirAviso({ is_read: true }))
    marcarTodosMock.mockResolvedValue({ updated: 0 })
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  it('muestra en la campana el número de avisos sin leer', async () => {
    getAvisosSinLeerMock.mockResolvedValue(3)
    renderizar()

    expect(
      await screen.findByRole('button', { name: 'Avisos, 3 sin leer' }),
    ).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('no muestra contador cuando no hay avisos sin leer', async () => {
    renderizar()

    expect(
      await screen.findByRole('button', { name: 'Avisos' }),
    ).toBeInTheDocument()
    await waitFor(() => expect(getAvisosSinLeerMock).toHaveBeenCalled())
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })

  it('limita el contador a 99+', async () => {
    getAvisosSinLeerMock.mockResolvedValue(250)
    renderizar()

    expect(await screen.findByText('99+')).toBeInTheDocument()
  })

  it('no consulta la lista hasta abrir la campana', async () => {
    getAvisosSinLeerMock.mockResolvedValue(1)
    renderizar()

    await screen.findByRole('button', { name: 'Avisos, 1 sin leer' })
    expect(getAvisosMock).not.toHaveBeenCalled()
  })

  it('lista los avisos con folio y marca los de alta importancia', async () => {
    getAvisosSinLeerMock.mockResolvedValue(2)
    getAvisosMock.mockResolvedValue([
      construirAviso(),
      construirAviso({
        id: 'aviso-2',
        subject: 'Riesgo de incumplir el tiempo comprometido',
        importance: 'high',
        request_folio: 'SIG-0015',
      }),
    ])
    const usuario = userEvent.setup()
    renderizar()

    await usuario.click(
      await screen.findByRole('button', { name: 'Avisos, 2 sin leer' }),
    )

    expect(
      await screen.findByText('Tu solicitud fue asignada'),
    ).toBeInTheDocument()
    expect(screen.getByText(/SIG-0012/)).toBeInTheDocument()
    expect(
      screen.getByText('Riesgo de incumplir el tiempo comprometido'),
    ).toBeInTheDocument()
    expect(screen.getAllByText('Importante')).toHaveLength(1)
  })

  it('muestra un mensaje cuando no hay avisos', async () => {
    const usuario = userEvent.setup()
    renderizar()

    await usuario.click(await screen.findByRole('button', { name: 'Avisos' }))

    expect(await screen.findByText('No tienes avisos.')).toBeInTheDocument()
  })

  it('marca un aviso como leído y vuelve a consultar el contador', async () => {
    getAvisosSinLeerMock.mockResolvedValue(1)
    getAvisosMock.mockResolvedValue([construirAviso()])
    const usuario = userEvent.setup()
    renderizar()

    await usuario.click(
      await screen.findByRole('button', { name: 'Avisos, 1 sin leer' }),
    )
    getAvisosSinLeerMock.mockResolvedValue(0)
    await usuario.click(
      await screen.findByRole('button', {
        name: 'Marcar como leído: Tu solicitud fue asignada',
      }),
    )

    expect(marcarAvisoLeidoMock).toHaveBeenCalledWith('aviso-1')
    expect(
      await screen.findByRole('button', { name: 'Avisos' }),
    ).toBeInTheDocument()
  })

  it('marca todos los avisos como leídos', async () => {
    getAvisosSinLeerMock.mockResolvedValue(2)
    getAvisosMock.mockResolvedValue([
      construirAviso(),
      construirAviso({ id: 'aviso-2', subject: 'Otro aviso' }),
    ])
    const usuario = userEvent.setup()
    renderizar()

    await usuario.click(
      await screen.findByRole('button', { name: 'Avisos, 2 sin leer' }),
    )
    await usuario.click(
      await screen.findByRole('button', { name: /Marcar todos como leídos/ }),
    )

    expect(marcarTodosMock).toHaveBeenCalledTimes(1)
  })

  it('deshabilita «marcar todos» si no hay avisos sin leer', async () => {
    const usuario = userEvent.setup()
    renderizar()

    await usuario.click(await screen.findByRole('button', { name: 'Avisos' }))

    expect(
      await screen.findByRole('button', { name: /Marcar todos como leídos/ }),
    ).toBeDisabled()
  })

  it('muestra el error si no se pueden cargar los avisos', async () => {
    getAvisosMock.mockRejectedValue(new ApiError(500, 'Error del servidor'))
    const usuario = userEvent.setup()
    renderizar()

    await usuario.click(await screen.findByRole('button', { name: 'Avisos' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'No se pudieron cargar los avisos.',
    )
  })

  it('cierra la lista con la tecla Escape', async () => {
    const usuario = userEvent.setup()
    renderizar()

    await usuario.click(await screen.findByRole('button', { name: 'Avisos' }))
    expect(
      await screen.findByRole('region', { name: 'Lista de avisos' }),
    ).toBeInTheDocument()

    await usuario.keyboard('{Escape}')

    expect(
      screen.queryByRole('region', { name: 'Lista de avisos' }),
    ).not.toBeInTheDocument()
  })

  it('consulta el contador de forma periódica (en menos de un minuto)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderizar()

    await waitFor(() => expect(getAvisosSinLeerMock).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(30_000)

    await waitFor(() =>
      expect(getAvisosSinLeerMock.mock.calls.length).toBeGreaterThanOrEqual(2),
    )
  })
})
