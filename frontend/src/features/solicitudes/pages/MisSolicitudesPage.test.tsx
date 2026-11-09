import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import {
  getMiSolicitud,
  getMisSolicitudes,
  type MiSolicitudDetalle,
} from '@/api/mis-solicitudes'
import { MiSolicitudPage } from './MiSolicitudPage'
import { MisSolicitudesPage } from './MisSolicitudesPage'

vi.mock('@/api/mis-solicitudes', () => ({
  getMisSolicitudes: vi.fn(),
  getMiSolicitud: vi.fn(),
  confirmarMiSolicitud: vi.fn(),
}))

const getMisSolicitudesMock = vi.mocked(getMisSolicitudes)
const getMiSolicitudMock = vi.mocked(getMiSolicitud)

const DETALLE: MiSolicitudDetalle = {
  folio: 'SIG-0007',
  title: 'No hay conexión a la red',
  status: 'in_progress',
  priority: 'P2',
  category: 'Redes',
  due_at: '2026-10-18T09:00:00Z',
  technician: 'Ana Técnica',
  created_at: '2026-10-17T09:00:00Z',
  resolved_at: null,
  closed_at: null,
  log: [
    {
      action: 'Atención iniciada',
      new_status: 'in_progress',
      created_at: '2026-10-17T10:00:00Z',
    },
  ],
}

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/mis-solicitudes']}>
        <Routes>
          <Route path="/mis-solicitudes" element={<MisSolicitudesPage />} />
          <Route path="/mis-solicitudes/:folio" element={<MiSolicitudPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MisSolicitudesPage (S4-02)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('muestra la lista del solicitante y entra al detalle por folio', async () => {
    getMisSolicitudesMock.mockResolvedValue([
      {
        folio: 'SIG-0007',
        title: 'No hay conexión a la red',
        status: 'in_progress',
        priority: 'P2',
        created_at: '2026-10-17T09:00:00Z',
      },
    ])
    getMiSolicitudMock.mockResolvedValue(DETALLE)
    renderApp()

    const enlace = await screen.findByRole('link', {
      name: /SIG-0007.*No hay conexión a la red/,
    })
    expect(enlace).toHaveTextContent('En proceso')

    await userEvent.click(enlace)

    expect(
      await screen.findByRole('heading', { name: 'No hay conexión a la red' }),
    ).toBeInTheDocument()
    expect(getMiSolicitudMock).toHaveBeenCalledWith('SIG-0007')
    expect(screen.getByText('Ana Técnica')).toBeInTheDocument()
    expect(screen.getByText('Redes')).toBeInTheDocument()
    expect(screen.getByText('Atención iniciada')).toBeInTheDocument()
  })

  it('el buscador lleva al detalle del folio escrito', async () => {
    getMisSolicitudesMock.mockResolvedValue([])
    getMiSolicitudMock.mockResolvedValue(DETALLE)
    renderApp()

    expect(
      await screen.findByText('Todavía no has registrado solicitudes.'),
    ).toBeInTheDocument()
    await userEvent.type(
      screen.getByLabelText('Buscar por folio'),
      '  SIG-0007 ',
    )
    await userEvent.click(screen.getByRole('button', { name: /Buscar/ }))

    expect(
      await screen.findByRole('heading', { name: 'No hay conexión a la red' }),
    ).toBeInTheDocument()
    expect(getMiSolicitudMock).toHaveBeenCalledWith('SIG-0007')
  })

  it('muestra el error de carga con ErrorAlert', async () => {
    getMisSolicitudesMock.mockRejectedValue(
      new ApiError(500, 'Error interno', {
        code: 'internal_error',
        requestId: 'req-123',
      }),
    )
    renderApp()

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('Ocurrió un error interno')
    expect(alerta).toHaveTextContent('req-123')
  })
})
