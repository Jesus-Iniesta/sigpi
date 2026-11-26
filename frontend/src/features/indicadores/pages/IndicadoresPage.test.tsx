import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import {
  exportarIndicadoresCsv,
  getResumenIndicadores,
  type ResumenIndicadores,
} from '@/api/indicadores'
import { IndicadoresPage } from './IndicadoresPage'

vi.mock('@/api/indicadores', () => ({
  getResumenIndicadores: vi.fn(),
  exportarIndicadoresCsv: vi.fn(),
}))

const getResumenMock = vi.mocked(getResumenIndicadores)
const exportarMock = vi.mocked(exportarIndicadoresCsv)

function buildResumen(
  overrides: Partial<ResumenIndicadores> = {},
): ResumenIndicadores {
  return {
    desde: '2026-10-28',
    hasta: '2026-11-26',
    total: 12,
    por_estatus: { resolved: 7, in_progress: 5 },
    por_prioridad: { P1: 2, P3: 10 },
    por_categoria: { Redes: 8, 'Cuentas y accesos': 4 },
    resueltas_con_sla: 7,
    resueltas_en_tiempo: 6,
    cumplimiento_sla: 85.714,
    tiempo_medio_primera_respuesta_min: 45.4,
    tiempo_medio_resolucion_min: 150,
    abiertas_vencidas: 3,
    por_dia: [
      { fecha: '2026-11-25', total: 4 },
      { fecha: '2026-11-26', total: 8 },
    ],
    ...overrides,
  }
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <IndicadoresPage />
    </QueryClientProvider>,
  )
}

function tarjeta(titulo: string) {
  const region = screen.getByRole('region', { name: 'Tarjetas de indicadores' })
  return within(region).getByText(titulo).parentElement as HTMLElement
}

describe('IndicadoresPage (S5-11)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 10, 26, 10, 0))
    getResumenMock.mockReset()
    exportarMock.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('consulta los últimos 30 días y muestra tarjetas y barras', async () => {
    getResumenMock.mockResolvedValue(buildResumen())
    renderPage()

    await screen.findByRole('region', { name: 'Tarjetas de indicadores' })
    expect(getResumenMock).toHaveBeenCalledWith({
      desde: '2026-10-28',
      hasta: '2026-11-26',
    })
    expect(tarjeta('Total de solicitudes')).toHaveTextContent('12')
    expect(tarjeta('Cumplimiento del SLA')).toHaveTextContent('85.7 %')
    expect(tarjeta('Tiempo medio de primera respuesta')).toHaveTextContent(
      '45 min',
    )
    expect(tarjeta('Tiempo medio de resolución')).toHaveTextContent(
      '2 h 30 min',
    )
    expect(tarjeta('Abiertas vencidas')).toHaveTextContent('3')

    const estatus = screen.getByRole('region', { name: 'Por estatus' })
    expect(within(estatus).getByText('Resuelta')).toBeInTheDocument()
    expect(within(estatus).getByText('En proceso')).toBeInTheDocument()
    const prioridad = screen.getByRole('region', { name: 'Por prioridad' })
    expect(within(prioridad).getByText('P3')).toBeInTheDocument()
    const categoria = screen.getByRole('region', { name: 'Por categoría' })
    expect(within(categoria).getByText('Redes')).toBeInTheDocument()
    const dias = screen.getByRole('region', { name: 'Solicitudes por día' })
    expect(within(dias).getAllByRole('listitem')).toHaveLength(2)
  })

  it('vuelve a consultar al cambiar el rango y con el atajo de 7 días', async () => {
    getResumenMock.mockResolvedValue(buildResumen())
    renderPage()
    await screen.findByRole('region', { name: 'Tarjetas de indicadores' })

    fireEvent.change(screen.getByLabelText('Desde'), {
      target: { value: '2026-11-01' },
    })
    await vi.waitFor(() =>
      expect(getResumenMock).toHaveBeenLastCalledWith({
        desde: '2026-11-01',
        hasta: '2026-11-26',
      }),
    )

    await userEvent.click(screen.getByRole('button', { name: '7 días' }))
    await vi.waitFor(() =>
      expect(getResumenMock).toHaveBeenLastCalledWith({
        desde: '2026-11-20',
        hasta: '2026-11-26',
      }),
    )
  })

  it('avisa de un rango inválido y no consulta', async () => {
    getResumenMock.mockResolvedValue(buildResumen())
    renderPage()
    await screen.findByRole('region', { name: 'Tarjetas de indicadores' })
    getResumenMock.mockClear()

    fireEvent.change(screen.getByLabelText('Desde'), {
      target: { value: '2026-12-01' },
    })

    expect(screen.getByRole('alert')).toHaveTextContent(
      'La fecha «desde» no puede ser posterior a «hasta».',
    )
    expect(getResumenMock).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Exportar CSV' })).toBeDisabled()
  })

  it('«Exportar CSV» descarga el archivo del rango', async () => {
    getResumenMock.mockResolvedValue(buildResumen())
    exportarMock.mockResolvedValue('indicadores_2026-10-28_2026-11-26.csv')
    renderPage()
    await screen.findByRole('region', { name: 'Tarjetas de indicadores' })

    await userEvent.click(screen.getByRole('button', { name: 'Exportar CSV' }))

    expect(exportarMock.mock.calls[0][0]).toEqual({
      desde: '2026-10-28',
      hasta: '2026-11-26',
    })
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Se descargó indicadores_2026-10-28_2026-11-26.csv.',
    )
  })

  it('muestra el error del servidor al exportar', async () => {
    getResumenMock.mockResolvedValue(buildResumen())
    exportarMock.mockRejectedValue(
      new ApiError(403, 'No tienes permiso.', { code: 'forbidden' }),
    )
    renderPage()
    await screen.findByRole('region', { name: 'Tarjetas de indicadores' })

    await userEvent.click(screen.getByRole('button', { name: 'Exportar CSV' }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('muestra el estado vacío cuando el total es 0', async () => {
    getResumenMock.mockResolvedValue(
      buildResumen({
        total: 0,
        por_estatus: {},
        por_prioridad: {},
        por_categoria: {},
        por_dia: [],
      }),
    )
    renderPage()

    expect(
      await screen.findByText('No hay solicitudes registradas en este rango.'),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('region', { name: 'Tarjetas de indicadores' }),
    ).not.toBeInTheDocument()
  })

  it('muestra el error del servidor al consultar', async () => {
    getResumenMock.mockRejectedValue(new ApiError(500, 'Falla interna.'))
    renderPage()

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
