import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createArea,
  createShift,
  getAreas,
  getCatalogOptions,
  getCategories,
  getOrganizationalUnits,
  getShifts,
  getSpecialties,
  getTechnicians,
  type CatalogOptions,
} from '@/api/catalog'
import { CatalogPage } from './catalog-page'

vi.mock('@/api/catalog', () => ({
  getAreas: vi.fn(),
  getCatalogOptions: vi.fn(),
  getCategories: vi.fn(),
  getOrganizationalUnits: vi.fn(),
  getShifts: vi.fn(),
  getSpecialties: vi.fn(),
  getTechnicians: vi.fn(),
  createArea: vi.fn(),
  createCategory: vi.fn(),
  createShift: vi.fn(),
  createSpecialty: vi.fn(),
  updateTechnician: vi.fn(),
}))

const options: CatalogOptions = {
  service_areas: [
    'Soporte a usuarios',
    'Infraestructura y redes',
    'Sistemas y aplicaciones',
    'Laboratorios y aulas',
  ],
  categories: ['Hardware', 'Software', 'Redes', 'Cuentas y accesos'],
  specialties: [
    {
      category: 'Hardware',
      names: [
        'Equipo de cómputo',
        'Impresoras y periféricos',
        'Proyectores y audiovisual',
      ],
    },
    {
      category: 'Redes',
      names: ['Red cableada', 'Red inalámbrica (Wi-Fi)', 'VPN y acceso remoto'],
    },
  ],
  shifts: [
    { name: 'Matutino', start_minute: 420, end_minute: 900 },
    { name: 'Vespertino', start_minute: 780, end_minute: 1260 },
    { name: 'Mixto', start_minute: 540, end_minute: 1020 },
  ],
  max_load: { min: 1, max: 15 },
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <CatalogPage />
    </QueryClientProvider>,
  )
}

async function openCatalogForm(
  user: ReturnType<typeof userEvent.setup>,
  group: string,
) {
  await user.click(
    await screen.findByRole('button', { name: 'Áreas y especialidades' }),
  )
  await user.click(screen.getByRole('button', { name: `Agregar ${group}` }))
  return screen.getByRole('dialog')
}

function optionTexts(select: HTMLElement) {
  return within(select)
    .getAllByRole('option')
    .map((option) => option.textContent)
}

describe('CatalogPage con opciones predefinidas', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getCatalogOptions).mockResolvedValue(options)
    vi.mocked(getOrganizationalUnits).mockResolvedValue([
      { id: 'unit-1', name: 'Soporte técnico', unit_type: 'dept', code: 'SPT' },
    ])
    vi.mocked(getAreas).mockResolvedValue([
      {
        id: 'area-1',
        unit_id: 'unit-1',
        name: 'Soporte a usuarios',
        description: null,
        is_active: true,
      },
    ])
    vi.mocked(getCategories).mockResolvedValue([
      {
        id: 'cat-hw',
        area_id: 'area-1',
        name: 'Hardware',
        description: null,
        is_active: true,
      },
      {
        id: 'cat-red',
        area_id: 'area-1',
        name: 'Redes',
        description: null,
        is_active: true,
      },
    ])
    vi.mocked(getSpecialties).mockResolvedValue([
      {
        id: 'esp-1',
        category_id: 'cat-red',
        name: 'Red cableada',
        is_active: true,
      },
    ])
    vi.mocked(getShifts).mockResolvedValue([
      {
        id: 'shift-1',
        name: 'Matutino',
        start_minute: 420,
        end_minute: 900,
        is_active: true,
      },
    ])
    vi.mocked(getTechnicians).mockResolvedValue([
      {
        id: 'tec-1',
        full_name: 'Carlos Rodríguez López',
        support_level: 'level_1',
        shift_id: null,
        max_load: 8,
        is_active: true,
        specialty_ids: [],
      },
    ])
  })

  it.each(['Áreas de servicio', 'Categorías', 'Especialidades', 'Turnos'])(
    'el formulario de %s no tiene campo de nombre libre',
    async (group) => {
      const user = userEvent.setup()
      renderPage()

      const dialog = await openCatalogForm(user, group)

      expect(dialog.querySelector('input[name="name"]')).toBeNull()
      expect(within(dialog).getByLabelText('Nombre').tagName).toBe('SELECT')
      // El único texto libre que queda es la descripción (áreas y categorías).
      const textboxes = within(dialog).queryAllByRole('textbox')
      expect(
        textboxes.every((box) => box.getAttribute('name') === 'description'),
      ).toBe(true)
    },
  )

  it('marca como «ya registrada» las áreas que ya existen', async () => {
    const user = userEvent.setup()
    renderPage()

    const dialog = await openCatalogForm(user, 'Áreas de servicio')
    const name = within(dialog).getByLabelText('Nombre')

    const registered = within(name).getByRole('option', {
      name: 'Soporte a usuarios (ya registrada)',
    })
    expect(registered).toBeDisabled()
    expect(
      within(name).getByRole('option', { name: 'Laboratorios y aulas' }),
    ).toBeEnabled()
  })

  it('envía el área elegida de la lista', async () => {
    vi.mocked(createArea).mockResolvedValue({
      id: 'area-2',
      unit_id: 'unit-1',
      name: 'Laboratorios y aulas',
      description: 'Aulas',
      is_active: true,
    })
    const user = userEvent.setup()
    renderPage()

    const dialog = await openCatalogForm(user, 'Áreas de servicio')
    await user.selectOptions(
      within(dialog).getByLabelText(/Unidad organizacional/),
      'unit-1',
    )
    await user.selectOptions(
      within(dialog).getByLabelText('Nombre'),
      'Laboratorios y aulas',
    )
    await user.type(within(dialog).getByLabelText('Descripción'), '  Aulas  ')
    await user.click(within(dialog).getByRole('button', { name: 'Guardar' }))

    await waitFor(() => expect(createArea).toHaveBeenCalled())
    expect(vi.mocked(createArea).mock.calls[0][0]).toEqual({
      unit_id: 'unit-1',
      name: 'Laboratorios y aulas',
      description: 'Aulas',
    })
  })

  it('filtra las especialidades según la categoría elegida', async () => {
    const user = userEvent.setup()
    renderPage()

    const dialog = await openCatalogForm(user, 'Especialidades')
    const name = within(dialog).getByLabelText('Nombre')
    expect(name).toBeDisabled()

    await user.selectOptions(
      within(dialog).getByLabelText('Categoría'),
      'cat-red',
    )
    expect(optionTexts(name)).toEqual([
      'Selecciona una opción',
      'Red cableada (ya registrada)',
      'Red inalámbrica (Wi-Fi)',
      'VPN y acceso remoto',
    ])
    expect(
      within(name).getByRole('option', {
        name: 'Red cableada (ya registrada)',
      }),
    ).toBeDisabled()

    await user.selectOptions(
      within(dialog).getByLabelText('Categoría'),
      'cat-hw',
    )
    expect(optionTexts(name)).toEqual([
      'Selecciona una opción',
      'Equipo de cómputo',
      'Impresoras y periféricos',
      'Proyectores y audiovisual',
    ])
  })

  it('muestra el horario del turno como texto de solo lectura', async () => {
    vi.mocked(createShift).mockResolvedValue({
      id: 'shift-2',
      name: 'Vespertino',
      start_minute: 780,
      end_minute: 1260,
      is_active: true,
    })
    const user = userEvent.setup()
    renderPage()

    const dialog = await openCatalogForm(user, 'Turnos')
    expect(dialog.querySelector('input[type="time"]')).toBeNull()
    expect(
      within(dialog).getByRole('option', { name: 'Matutino (ya registrada)' }),
    ).toBeDisabled()

    await user.selectOptions(
      within(dialog).getByLabelText('Nombre'),
      'Vespertino',
    )
    expect(
      within(dialog).getByLabelText('Horario del turno'),
    ).toHaveTextContent('13:00 - 21:00')

    await user.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(createShift).toHaveBeenCalled())
    expect(vi.mocked(createShift).mock.calls[0][0]).toEqual({
      name: 'Vespertino',
    })
  })

  it('la carga máxima del técnico es un selector de 1 a 15', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Configurar/ }))
    const maxLoad = within(screen.getByRole('dialog')).getByLabelText(
      'Carga máxima',
    )

    expect(maxLoad.tagName).toBe('SELECT')
    expect(optionTexts(maxLoad)).toEqual([
      'Sin asignar',
      ...Array.from({ length: 15 }, (_, index) => String(index + 1)),
    ])
    expect(maxLoad).toHaveValue('8')
  })
})
