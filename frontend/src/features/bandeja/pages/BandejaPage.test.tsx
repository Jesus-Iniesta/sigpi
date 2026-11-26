import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { getBandeja, type BandejaElemento } from '@/api/bandeja'
import { BANDEJA_REFRESCO_MS } from '../use-bandeja'
import { BandejaPage } from './BandejaPage'

const sesion = vi.hoisted(() => ({ roles: ['support_agent'] as string[] }))

vi.mock('@/features/auth/auth-context', () => ({
  useAuth: () => ({
    user: {
      id: 'usuario-1',
      full_name: 'Tomás Técnico',
      email: 'tomas@example.test',
      roles: sesion.roles,
    },
  }),
}))

vi.mock('@/api/bandeja', () => ({ getBandeja: vi.fn() }))

const getBandejaMock = vi.mocked(getBandeja)

function construirElemento(
  sobrescribir: Partial<BandejaElemento> = {},
): BandejaElemento {
  return {
    request_id: '3f2b9c1e-0000-4000-8000-000000000001',
    folio: 'SIG-0001',
    titulo: 'Sin red en el laboratorio',
    estatus: 'in_progress',
    prioridad: 'P2',
    categoria: 'Redes',
    fecha_registro: '2026-11-20T08:00:00Z',
    fecha_compromiso: '2026-11-20T16:00:00Z',
    porcentaje_consumido: 42.5,
    en_riesgo: false,
    ...sobrescribir,
  }
}

function renderizar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <BandejaPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return queryClient
}

function ultimaConsulta() {
  return getBandejaMock.mock.lastCall?.[0]
}

describe('BandejaPage: «Mi bandeja» del técnico (S5-10)', () => {
  beforeEach(() => {
    sesion.roles = ['support_agent']
    getBandejaMock.mockReset()
    getBandejaMock.mockResolvedValue([
      construirElemento(),
      construirElemento({
        request_id: '3f2b9c1e-0000-4000-8000-000000000002',
        folio: 'SIG-0002',
        titulo: 'Proyector sin imagen',
        estatus: 'assigned',
        prioridad: 'P1',
        porcentaje_consumido: 83.3,
        en_riesgo: true,
      }),
    ])
  })

  it('muestra las asignadas con prioridad, compromiso y barra de tiempo consumido', async () => {
    renderizar()

    const fila = (await screen.findByText('Sin red en el laboratorio')).closest(
      'tr',
    )!
    expect(within(fila).getByText('P2')).toBeInTheDocument()
    expect(within(fila).getByText('En proceso')).toBeInTheDocument()
    expect(within(fila).getByText('Redes')).toBeInTheDocument()
    expect(within(fila).getByText(/2026/)).toBeInTheDocument()
    const barra = within(fila).getByRole('progressbar', {
      name: 'Tiempo consumido de SIG-0001',
    })
    expect(barra).toHaveAttribute('aria-valuenow', '43')
    expect(within(fila).getByText('43 %')).toBeInTheDocument()
  })

  it('el folio enlaza al detalle de la solicitud con su request_id', async () => {
    renderizar()

    const enlace = await screen.findByRole('link', { name: 'SIG-0001' })
    expect(enlace).toHaveAttribute(
      'href',
      '/solicitudes/3f2b9c1e-0000-4000-8000-000000000001',
    )
  })

  it('resalta con «En riesgo» solo las filas en riesgo', async () => {
    renderizar()

    const enRiesgo = (await screen.findByText('Proyector sin imagen')).closest(
      'tr',
    )!
    const normal = screen.getByText('Sin red en el laboratorio').closest('tr')!
    expect(within(enRiesgo).getByText('En riesgo')).toBeInTheDocument()
    expect(enRiesgo).toHaveAttribute('data-en-riesgo', 'true')
    expect(within(normal).queryByText('En riesgo')).not.toBeInTheDocument()
    expect(normal).not.toHaveAttribute('data-en-riesgo')
  })

  it('los filtros envían estatus y prioridad al endpoint', async () => {
    const user = userEvent.setup()
    renderizar()
    await screen.findByText('Sin red en el laboratorio')
    expect(ultimaConsulta()).toEqual({
      estatus: '',
      prioridad: '',
      todas: false,
    })

    await user.selectOptions(
      screen.getByLabelText('Filtrar por estatus'),
      'waiting',
    )
    await waitFor(() =>
      expect(ultimaConsulta()).toMatchObject({ estatus: 'waiting' }),
    )

    await user.selectOptions(
      screen.getByLabelText('Filtrar por prioridad'),
      'P1',
    )
    await waitFor(() =>
      expect(ultimaConsulta()).toEqual({
        estatus: 'waiting',
        prioridad: 'P1',
        todas: false,
      }),
    )
  })

  it('el técnico no ve el interruptor «Ver todo el equipo»', async () => {
    renderizar()
    await screen.findByText('Sin red en el laboratorio')

    expect(
      screen.queryByRole('switch', { name: 'Ver todo el equipo' }),
    ).not.toBeInTheDocument()
  })

  it.each(['service_manager', 'administrator'])(
    '%s ve el interruptor y al activarlo envía todas=true',
    async (rol) => {
      sesion.roles = [rol]
      const user = userEvent.setup()
      renderizar()
      await screen.findByText('Sin red en el laboratorio')

      await user.click(
        screen.getByRole('switch', { name: 'Ver todo el equipo' }),
      )

      await waitFor(() =>
        expect(ultimaConsulta()).toMatchObject({ todas: true }),
      )
    },
  )

  it('sin solicitudes muestra el estado vacío', async () => {
    getBandejaMock.mockResolvedValue([])
    renderizar()

    expect(
      await screen.findByText('No tienes solicitudes asignadas'),
    ).toBeInTheDocument()
  })

  it('un error del servidor se muestra con ErrorAlert', async () => {
    getBandejaMock.mockRejectedValue(
      new ApiError(500, 'Error del servidor al cargar la bandeja.'),
    )
    renderizar()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'No fue posible cargar la bandeja.',
    )
  })

  it('se actualiza sola cada 60 segundos', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      renderizar()
      await screen.findByText('Sin red en el laboratorio')
      expect(getBandejaMock).toHaveBeenCalledTimes(1)

      await vi.advanceTimersByTimeAsync(BANDEJA_REFRESCO_MS - 1_000)
      expect(getBandejaMock).toHaveBeenCalledTimes(1)

      await vi.advanceTimersByTimeAsync(1_000)
      await waitFor(() => expect(getBandejaMock).toHaveBeenCalledTimes(2))
    } finally {
      vi.useRealTimers()
    }
  })
})
