import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import {
  listRequests,
  type RequestPage,
  type RequestSummary,
} from '@/api/solicitudes'
import { RequestsPage } from './requests-page'

const sesion = vi.hoisted(() => ({ roles: ['administrator'] as string[] }))

vi.mock('@/features/auth/auth-context', () => ({
  useAuth: () => ({
    user: {
      id: 'usuario-1',
      full_name: 'Persona de prueba',
      email: 'persona@example.test',
      roles: sesion.roles,
    },
  }),
}))

vi.mock('@/api/solicitudes', () => ({
  listRequests: vi.fn(),
  putRequestOnHold: vi.fn(),
  createRequest: vi.fn(),
}))

const listRequestsMock = vi.mocked(listRequests)

function construirSolicitud(
  sobrescribir: Partial<RequestSummary> = {},
): RequestSummary {
  return {
    id: '3f2b9c1e-0000-4000-8000-000000000001',
    folio: 'SIG-0001',
    title: 'Sin red en el laboratorio',
    status: 'classified',
    priority: 'P2',
    category_id: 'cat-1',
    created_at: '2026-11-10T10:00:00Z',
    updated_at: '2026-11-10T10:00:00Z',
    physical_location: 'Edificio B',
    channel: 'portal',
    requester_institutional_id: null,
    category_name: 'Redes',
    requester_name: 'Sara Solicitante',
    ...sobrescribir,
  }
}

function construirPagina(items: RequestSummary[]): RequestPage {
  return { items, total: items.length, limit: 10, offset: 0 }
}

function renderizar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RequestsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RequestsPage: listado de solicitudes', () => {
  beforeEach(() => {
    sesion.roles = ['administrator']
    listRequestsMock.mockReset()
    listRequestsMock.mockResolvedValue(construirPagina([construirSolicitud()]))
  })

  it('muestra las solicitudes de la API y enlaza el detalle con el id (UUID)', async () => {
    renderizar()

    const enlace = await screen.findByRole('link', {
      name: 'Sin red en el laboratorio',
    })
    expect(enlace).toHaveAttribute(
      'href',
      '/solicitudes/3f2b9c1e-0000-4000-8000-000000000001',
    )
    expect(screen.getByText('SIG-0001')).toBeInTheDocument()
    expect(screen.getByText('Redes')).toBeInTheDocument()
    expect(screen.getByText('Sara Solicitante')).toBeInTheDocument()
    expect(screen.getByText('Mostrando 1–1 de 1')).toBeInTheDocument()
  })

  it('al solicitante le enlaza «Mis solicitudes» por folio y no le ofrece acciones', async () => {
    sesion.roles = ['requester']
    renderizar()

    const enlace = await screen.findByRole('link', {
      name: 'Sin red en el laboratorio',
    })
    expect(enlace).toHaveAttribute('href', '/mis-solicitudes/SIG-0001')
    expect(
      screen.queryByRole('columnheader', { name: 'Acciones' }),
    ).not.toBeInTheDocument()
  })

  it('ofrece «Marcar en espera» solo en solicitudes asignadas o en proceso', async () => {
    listRequestsMock.mockResolvedValue(
      construirPagina([
        construirSolicitud({ id: 'a', folio: 'SIG-0001', status: 'assigned' }),
        construirSolicitud({ id: 'b', folio: 'SIG-0002', status: 'resolved' }),
      ]),
    )
    renderizar()

    await screen.findByText('SIG-0002')
    expect(
      screen.getAllByRole('button', { name: 'Marcar en espera' }),
    ).toHaveLength(1)
  })

  it('envía la búsqueda al servidor al dejar de escribir y vuelve a la primera página', async () => {
    const user = userEvent.setup()
    renderizar()
    await screen.findByText('SIG-0001')

    await user.type(screen.getByLabelText('Buscar solicitudes'), 'red')

    await waitFor(() =>
      expect(listRequestsMock).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'red', offset: 0 }),
      ),
    )
  })

  it('filtra por estatus y por prioridad', async () => {
    const user = userEvent.setup()
    renderizar()
    await screen.findByText('SIG-0001')

    await user.selectOptions(
      screen.getByLabelText('Filtrar por estatus'),
      'resolved',
    )
    await user.selectOptions(
      screen.getByLabelText('Filtrar por prioridad'),
      'P1',
    )

    await waitFor(() =>
      expect(listRequestsMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: 'resolved', priority: 'P1' }),
      ),
    )
  })

  it('avisa cuando no hay coincidencias', async () => {
    listRequestsMock.mockResolvedValue(construirPagina([]))
    renderizar()

    expect(
      await screen.findByText('No hay solicitudes que coincidan.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Sin resultados')).toBeInTheDocument()
  })

  it('muestra el error cuando falla la carga', async () => {
    listRequestsMock.mockRejectedValue(new ApiError(500, 'Error interno'))
    renderizar()

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
