import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getEstadoClasificador,
  guardarUmbral,
  reentrenarClasificador,
  type EstadoClasificador,
} from '@/api/clasificador'
import { ApiError } from '@/api/client'
import { ClasificadorPage } from './ClasificadorPage'

vi.mock('@/api/clasificador', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/clasificador')>()),
  getEstadoClasificador: vi.fn(),
  guardarUmbral: vi.fn(),
  reentrenarClasificador: vi.fn(),
}))

const estadoMock = vi.mocked(getEstadoClasificador)
const umbralMock = vi.mocked(guardarUmbral)
const reentrenarMock = vi.mocked(reentrenarClasificador)

const estado: EstadoClasificador = {
  version: 'v3',
  umbral: 0.7,
  ejemplos: 260,
  exactitud: 0.677,
  correcciones_pendientes: 4,
  proporcion_por_revisar: 0.25,
  dias_recientes: 30,
  entrenado_en: '2026-11-25T10:00:00Z',
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ClasificadorPage />
    </QueryClientProvider>,
  )
}

describe('ClasificadorPage (S5-12, HU-02.2, HU-12.1, HU-12.2)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    estadoMock.mockResolvedValue(estado)
  })

  it('muestra el estado del clasificador con la exactitud en porcentaje', async () => {
    renderPage()

    expect(await screen.findByText('v3')).toBeInTheDocument()
    expect(screen.getByText('260')).toBeInTheDocument()
    expect(screen.getByText('67.7 %')).toBeInTheDocument()
    expect(screen.getByText('25.0 %')).toBeInTheDocument()
    expect(screen.getByText(/últimos 30 días/)).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
  })

  it('muestra «Sin medir» si no hay exactitud medida', async () => {
    estadoMock.mockResolvedValueOnce({
      ...estado,
      exactitud: null,
      proporcion_por_revisar: null,
    })
    renderPage()
    expect(await screen.findAllByText('Sin medir')).toHaveLength(2)
  })

  it('muestra un error con ErrorAlert si no carga el estado', async () => {
    estadoMock.mockRejectedValue(new ApiError(500, 'Falla del servidor'))
    renderPage()
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('guarda el umbral elegido y confirma el cambio «de X a Y»', async () => {
    umbralMock.mockResolvedValue({ umbral_anterior: 0.7, umbral: 0.85 })
    renderPage()
    const deslizador = await screen.findByRole('slider', { name: 'Umbral' })
    expect(deslizador).toHaveAttribute('min', '0.5')
    expect(deslizador).toHaveAttribute('max', '0.95')
    expect(deslizador).toHaveAttribute('step', '0.05')

    fireEvent.change(deslizador, { target: { value: '0.85' } })
    expect(screen.getByRole('spinbutton', { name: 'Valor' })).toHaveValue(0.85)
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: 'Guardar umbral' }))

    expect(umbralMock).toHaveBeenCalledWith(0.85, expect.anything())
    expect(
      await screen.findByText(/Umbral actualizado de 0\.70 a 0\.85/),
    ).toBeInTheDocument()
    expect(screen.getByText(/más solicitudes a revisión/)).toBeInTheDocument()
  })

  it('muestra el 422 del umbral con ErrorAlert', async () => {
    umbralMock.mockRejectedValue(
      new ApiError(422, 'El umbral debe estar entre 0.50 y 0.95.'),
    )
    renderPage()
    const valor = await screen.findByRole('spinbutton', { name: 'Valor' })
    fireEvent.change(valor, { target: { value: '0.99' } })
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: 'Guardar umbral' }))

    expect(umbralMock).toHaveBeenCalledWith(0.99, expect.anything())
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('reentrenar pide confirmación y muestra la versión activada', async () => {
    reentrenarMock.mockResolvedValue({
      version: 'v4',
      exactitud: 0.72,
      ejemplos: 264,
      correcciones_incorporadas: 4,
      version_anterior: 'v3',
      exactitud_anterior: 0.677,
      activado: true,
      mensaje: 'La versión nueva mejora la exactitud y quedó activa.',
    })
    renderPage()
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: 'Reentrenar modelo' }),
    )

    expect(reentrenarMock).not.toHaveBeenCalled()
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Sí, reentrenar' }))

    expect(await screen.findByText('Versión v4 activada')).toBeInTheDocument()
    expect(
      screen.getByText('La versión nueva mejora la exactitud y quedó activa.'),
    ).toBeInTheDocument()
    expect(screen.getByText('72.0 %')).toBeInTheDocument()
    expect(screen.getByText('Exactitud anterior (v3)')).toBeInTheDocument()
    await waitFor(() => expect(estadoMock).toHaveBeenCalledTimes(2))
  })

  it('reentrenar muestra cuando la versión nueva no se activó', async () => {
    reentrenarMock.mockResolvedValue({
      version: 'v4',
      exactitud: 0.6,
      ejemplos: 264,
      correcciones_incorporadas: 4,
      version_anterior: 'v3',
      exactitud_anterior: 0.677,
      activado: false,
      mensaje: 'La exactitud empeoró; se conserva la versión v3.',
    })
    renderPage()
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: 'Reentrenar modelo' }),
    )
    await user.click(screen.getByRole('button', { name: 'Sí, reentrenar' }))

    expect(
      await screen.findByText('Versión v4 no activada'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('La exactitud empeoró; se conserva la versión v3.'),
    ).toBeInTheDocument()
    expect(screen.getByText('60.0 %')).toBeInTheDocument()
  })

  it('cancelar la confirmación no reentrena', async () => {
    renderPage()
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: 'Reentrenar modelo' }),
    )
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(reentrenarMock).not.toHaveBeenCalled()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })
})
