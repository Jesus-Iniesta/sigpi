import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getAuditoria, type RegistroAuditoria } from '@/api/auditoria'
import { ApiError } from '@/api/client'
import { AuditoriaPage } from './AuditoriaPage'

vi.mock('@/api/auditoria', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/auditoria')>()),
  getAuditoria: vi.fn(),
}))

const auditoriaMock = vi.mocked(getAuditoria)

// Misma forma que `AuditoriaRead` (backend/app/schemas/auditoria.py).
const cambioCategoria: RegistroAuditoria = {
  id: '6f1c2b8e-1d4a-4f0e-9a51-0c8e3a7d2b11',
  actor_id: 'a3e9c2d4-7b61-4c2f-8e15-9d0b6f4a1c22',
  action: 'catalog_category.updated',
  entity_type: 'catalog_category',
  entity_id: '17',
  old_values: { name: 'Redes', is_active: true },
  new_values: { name: 'Redes y telefonía', is_active: false },
  ip_address: '10.0.0.8',
  created_at: '2026-11-25T16:30:00Z',
}

const cambioSistema: RegistroAuditoria = {
  id: '0b7d4e2a-5c3f-4a19-b8e6-2f1a9c7d3e44',
  actor_id: null,
  action: 'sla.recalculated',
  entity_type: 'sla_policy',
  entity_id: 'P1',
  old_values: null,
  new_values: { response_minutes: 30 },
  ip_address: null,
  created_at: '2026-11-26T08:00:00Z',
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <AuditoriaPage />
    </QueryClientProvider>,
  )
}

describe('AuditoriaPage (S5-21, COR-02, COR-03)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    auditoriaMock.mockResolvedValue([cambioCategoria, cambioSistema])
  })

  it('muestra título, columnas y los registros, con «Sistema» si no hay actor', async () => {
    renderPage()

    expect(
      screen.getByRole('heading', { name: 'Auditoría' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'Registro de solo lectura de los cambios administrativos',
      ),
    ).toBeInTheDocument()
    expect(
      await screen.findByText('catalog_category.updated'),
    ).toBeInTheDocument()
    for (const columna of [
      'Fecha',
      'Acción',
      'Entidad',
      'Identificador',
      'Usuario',
      'IP',
    ]) {
      expect(
        screen.getByRole('columnheader', { name: columna }),
      ).toBeInTheDocument()
    }
    expect(screen.getByText(cambioCategoria.actor_id!)).toBeInTheDocument()
    expect(screen.getByText('10.0.0.8')).toBeInTheDocument()
    expect(screen.getByText('Sistema')).toBeInTheDocument()
    expect(auditoriaMock).toHaveBeenCalledWith({})
  })

  it('no ofrece editar ni borrar registros', async () => {
    renderPage()
    await screen.findByText('catalog_category.updated')
    expect(
      screen.queryByRole('button', { name: /editar|eliminar|borrar/i }),
    ).not.toBeInTheDocument()
  })

  it('una fila expandida muestra los valores anteriores y nuevos', async () => {
    const user = userEvent.setup()
    renderPage()

    const fila = (await screen.findByText('catalog_category.updated')).closest(
      'tr',
    )!
    const boton = within(fila).getByRole('button', {
      name: 'Ver valores del cambio',
    })
    expect(boton).toHaveAttribute('aria-expanded', 'false')
    await user.click(boton)

    expect(boton).toHaveAttribute('aria-expanded', 'true')
    const anteriores = screen.getByLabelText('Valores anteriores')
    const nuevos = screen.getByLabelText('Valores nuevos')
    expect(anteriores.textContent).toBe(
      JSON.stringify(cambioCategoria.old_values, null, 2),
    )
    expect(nuevos.textContent).toBe(
      JSON.stringify(cambioCategoria.new_values, null, 2),
    )

    await user.click(
      within(fila).getByRole('button', { name: 'Ocultar valores del cambio' }),
    )
    expect(
      screen.queryByLabelText('Valores anteriores'),
    ).not.toBeInTheDocument()
  })

  it('indica «Sin valores» cuando no hay valores anteriores', async () => {
    const user = userEvent.setup()
    renderPage()
    const fila = (await screen.findByText('sla.recalculated')).closest('tr')!
    await user.click(within(fila).getByRole('button'))
    expect(screen.getByLabelText('Valores anteriores')).toHaveTextContent(
      'Sin valores',
    )
  })

  it('aplica los filtros sin espacios y «Limpiar filtros» los quita', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('catalog_category.updated')

    await user.type(
      screen.getByLabelText('Tipo de entidad'),
      ' catalog_category ',
    )
    await user.type(screen.getByLabelText('Identificador'), '17')
    await user.click(screen.getByRole('button', { name: 'Buscar' }))
    expect(auditoriaMock).toHaveBeenLastCalledWith({
      entity_type: 'catalog_category',
      entity_id: '17',
    })

    await user.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    expect(screen.getByLabelText('Tipo de entidad')).toHaveValue('')
    expect(screen.getByLabelText('Identificador')).toHaveValue('')
    expect(auditoriaMock).toHaveBeenLastCalledWith({})
  })

  it('sugiere los tipos de entidad que aparecen en los datos', async () => {
    const { container } = renderPage()
    await screen.findByText('catalog_category.updated')
    const opciones = Array.from(
      container.querySelectorAll('#auditoria-tipos option'),
    ).map((opcion) => opcion.getAttribute('value'))
    expect(opciones).toEqual(['catalog_category', 'sla_policy'])
  })

  it('muestra el estado vacío', async () => {
    auditoriaMock.mockResolvedValue([])
    renderPage()
    expect(
      await screen.findByText(
        'No hay registros de auditoría con estos filtros.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('muestra el error con ErrorAlert', async () => {
    auditoriaMock.mockRejectedValue(new ApiError(500, 'Falla del servidor'))
    renderPage()
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
