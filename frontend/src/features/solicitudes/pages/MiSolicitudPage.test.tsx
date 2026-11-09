import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import {
  confirmarMiSolicitud,
  getMiSolicitud,
  type MiSolicitudDetalle,
} from '@/api/mis-solicitudes'
import { MiSolicitudPage } from './MiSolicitudPage'

vi.mock('@/api/mis-solicitudes', () => ({
  getMisSolicitudes: vi.fn(),
  getMiSolicitud: vi.fn(),
  confirmarMiSolicitud: vi.fn(),
}))

const getMiSolicitudMock = vi.mocked(getMiSolicitud)
const confirmarMock = vi.mocked(confirmarMiSolicitud)

function buildDetalle(
  overrides: Partial<MiSolicitudDetalle> = {},
): MiSolicitudDetalle {
  return {
    folio: 'SIG-0007',
    title: 'No hay conexión a la red',
    status: 'resolved',
    priority: 'P2',
    category: 'Redes',
    due_at: '2026-10-18T09:00:00Z',
    technician: 'Ana Técnica',
    created_at: '2026-10-17T09:00:00Z',
    resolved_at: '2026-10-17T12:00:00Z',
    closed_at: null,
    log: [
      {
        action: 'Solicitud registrada',
        new_status: 'registered',
        created_at: '2026-10-17T09:00:00Z',
      },
      {
        action: 'Solicitud resuelta',
        new_status: 'resolved',
        created_at: '2026-10-17T12:00:00Z',
      },
    ],
    ...overrides,
  }
}

function renderPage(folio = 'SIG-0007') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/mis-solicitudes/${folio}`]}>
        <Routes>
          <Route path="/mis-solicitudes/:folio" element={<MiSolicitudPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MiSolicitudPage (S4-02)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('muestra estatus legible, datos y la línea de tiempo', async () => {
    getMiSolicitudMock.mockResolvedValue(
      buildDetalle({ status: 'in_progress' }),
    )
    renderPage()

    expect(await screen.findByTestId('estatus')).toHaveTextContent('En proceso')
    expect(screen.getByText('Ana Técnica')).toBeInTheDocument()
    expect(screen.getByText('Redes')).toBeInTheDocument()
    const linea = screen.getByRole('list')
    expect(within(linea).getAllByRole('listitem')).toHaveLength(2)
    expect(within(linea).getByText('Solicitud resuelta')).toBeInTheDocument()
  })

  it('no ofrece confirmar si la solicitud no está «Resuelta»', async () => {
    getMiSolicitudMock.mockResolvedValue(
      buildDetalle({ status: 'in_progress' }),
    )
    renderPage()

    await screen.findByTestId('estatus')
    expect(
      screen.queryByRole('button', { name: /Confirmar solución/ }),
    ).not.toBeInTheDocument()
  })

  it('confirma la solución con diálogo y la vista pasa a «Cerrada»', async () => {
    getMiSolicitudMock.mockResolvedValue(buildDetalle())
    confirmarMock.mockResolvedValue(
      buildDetalle({ status: 'closed', closed_at: '2026-10-17T13:00:00Z' }),
    )
    renderPage()

    expect(await screen.findByTestId('estatus')).toHaveTextContent('Resuelta')
    await userEvent.click(
      screen.getByRole('button', { name: /Confirmar solución/ }),
    )

    const dialogo = screen.getByRole('dialog', {
      name: '¿Confirmas la solución?',
    })
    expect(confirmarMock).not.toHaveBeenCalled()
    await userEvent.click(
      within(dialogo).getByRole('button', { name: 'Sí, confirmar' }),
    )

    expect(confirmarMock).toHaveBeenCalledWith('SIG-0007')
    expect(await screen.findByTestId('estatus')).toHaveTextContent('Cerrada')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /Confirmar solución/ }),
    ).not.toBeInTheDocument()
  })

  it('cancelar el diálogo no confirma', async () => {
    getMiSolicitudMock.mockResolvedValue(buildDetalle())
    renderPage()

    await userEvent.click(
      await screen.findByRole('button', { name: /Confirmar solución/ }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(confirmarMock).not.toHaveBeenCalled()
    expect(screen.getByTestId('estatus')).toHaveTextContent('Resuelta')
  })

  it('un error al confirmar se muestra en el diálogo', async () => {
    getMiSolicitudMock.mockResolvedValue(buildDetalle())
    confirmarMock.mockRejectedValue(
      new ApiError(422, 'Solo se puede confirmar una solicitud resuelta.', {
        code: 'business_rule_violation',
      }),
    )
    renderPage()

    await userEvent.click(
      await screen.findByRole('button', { name: /Confirmar solución/ }),
    )
    const dialogo = screen.getByRole('dialog')
    await userEvent.click(
      within(dialogo).getByRole('button', { name: 'Sí, confirmar' }),
    )

    expect(await within(dialogo).findByRole('alert')).toHaveTextContent(
      'Solo se puede confirmar una solicitud resuelta.',
    )
  })

  it('un 404 muestra «No encontramos esa solicitud»', async () => {
    getMiSolicitudMock.mockRejectedValue(
      new ApiError(404, 'No encontramos una solicitud tuya con ese folio.', {
        code: 'not_found',
      }),
    )
    renderPage('SIG-9999')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'No encontramos esa solicitud',
    )
    expect(getMiSolicitudMock).toHaveBeenCalledWith('SIG-9999')
  })
})
