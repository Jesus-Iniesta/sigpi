import { useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQueries, useQueryClient } from '@tanstack/react-query'
import {
  Clock3,
  FolderTree,
  Layers3,
  Plus,
  Search,
  Settings2,
  SlidersHorizontal,
  UsersRound,
} from 'lucide-react'
import {
  createArea,
  createCategory,
  createShift,
  createSpecialty,
  getAreas,
  getCategories,
  getShifts,
  getSpecialties,
  getTechnicians,
  updateTechnician,
  type Technician,
} from '@/api/catalog'
import { Button } from '@/shared/ui/button'

type CatalogTab = 'technicians' | 'catalog'
type CatalogFormType = 'area' | 'category' | 'specialty' | 'shift'

const supportLevelLabels = {
  level_1: 'Nivel 1',
  level_2: 'Nivel 2',
} as const

function minutesToTime(minutes: number) {
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
}

function timeToMinutes(value: string) {
  const [hours, minutes] = value.split(':').map(Number)
  return hours * 60 + minutes
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

function Modal({
  title,
  description,
  children,
  onClose,
}: {
  title: string
  description: string
  children: React.ReactNode
  onClose: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-20 grid place-items-center bg-[#123b3a]/35 p-5"
      role="presentation"
      onMouseDown={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="catalog-modal-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 id="catalog-modal-title" className="text-xl font-bold">
          {title}
        </h2>
        <p className="mt-1 text-sm text-[#718096]">{description}</p>
        <div className="mt-6">{children}</div>
      </div>
    </div>
  )
}

export function CatalogPage() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<CatalogTab>('technicians')
  const [search, setSearch] = useState('')
  const [editingTechnician, setEditingTechnician] = useState<Technician | null>(
    null,
  )
  const [formType, setFormType] = useState<CatalogFormType | null>(null)
  const [formError, setFormError] = useState('')

  const results = useQueries({
    queries: [
      { queryKey: ['catalog', 'areas'], queryFn: getAreas },
      { queryKey: ['catalog', 'categories'], queryFn: getCategories },
      { queryKey: ['catalog', 'specialties'], queryFn: getSpecialties },
      { queryKey: ['catalog', 'shifts'], queryFn: getShifts },
      { queryKey: ['catalog', 'technicians'], queryFn: getTechnicians },
    ],
  })
  const [
    areasQuery,
    categoriesQuery,
    specialtiesQuery,
    shiftsQuery,
    techniciansQuery,
  ] = results
  const areas = areasQuery.data ?? []
  const categories = categoriesQuery.data ?? []
  const specialties = specialtiesQuery.data ?? []
  const shifts = shiftsQuery.data ?? []
  const technicians = useMemo(
    () => techniciansQuery.data ?? [],
    [techniciansQuery.data],
  )
  const isLoading = results.some((result) => result.isLoading)
  const isError = results.some((result) => result.isError)

  const refreshCatalog = () =>
    queryClient.invalidateQueries({ queryKey: ['catalog'] })

  const technicianMutation = useMutation({
    mutationFn: ({
      technician,
      supportLevel,
      shiftId,
      maxLoad,
      specialtyIds,
    }: {
      technician: Technician
      supportLevel: Technician['support_level']
      shiftId: string
      maxLoad: string
      specialtyIds: string[]
    }) =>
      updateTechnician(technician.id, {
        support_level: supportLevel,
        shift_id: shiftId || null,
        max_load: maxLoad ? Number(maxLoad) : null,
        specialty_ids: specialtyIds,
      }),
    onSuccess: () => {
      void refreshCatalog()
      setEditingTechnician(null)
    },
    onError: (error) =>
      setFormError(
        errorMessage(error, 'No fue posible guardar el perfil técnico.'),
      ),
  })

  const catalogMutations = {
    area: useMutation({ mutationFn: createArea }),
    category: useMutation({ mutationFn: createCategory }),
    specialty: useMutation({ mutationFn: createSpecialty }),
    shift: useMutation({ mutationFn: createShift }),
  }

  const filteredTechnicians = useMemo(() => {
    const normalized = search.trim().toLowerCase()
    if (!normalized) return technicians
    return technicians.filter((technician) =>
      technician.full_name.toLowerCase().includes(normalized),
    )
  }, [search, technicians])

  const closeModal = () => {
    if (
      technicianMutation.isPending ||
      Object.values(catalogMutations).some((mutation) => mutation.isPending)
    ) {
      return
    }
    setEditingTechnician(null)
    setFormType(null)
    setFormError('')
  }

  const handleTechnicianSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    const maxLoad = String(formData.get('max_load') ?? '')
    if (
      maxLoad &&
      (!Number.isInteger(Number(maxLoad)) || Number(maxLoad) < 1)
    ) {
      setFormError('La carga máxima debe ser un entero mayor que cero.')
      return
    }
    setFormError('')
    technicianMutation.mutate({
      technician: editingTechnician!,
      supportLevel:
        (formData.get('support_level') as Technician['support_level']) || null,
      shiftId: String(formData.get('shift_id') ?? ''),
      maxLoad,
      specialtyIds: formData.getAll('specialty_ids').map(String),
    })
  }

  const handleCatalogSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    setFormError('')
    if (formType === 'area') {
      catalogMutations.area.mutate(
        {
          unit_id: String(formData.get('unit_id')),
          name: String(formData.get('name')).trim(),
          description: String(formData.get('description') || '').trim() || null,
        },
        {
          onSuccess: () => {
            void refreshCatalog()
            closeModal()
          },
          onError: (error) =>
            setFormError(errorMessage(error, 'No fue posible crear el área.')),
        },
      )
    } else if (formType === 'category') {
      catalogMutations.category.mutate(
        {
          area_id: String(formData.get('parent_id')),
          name: String(formData.get('name')).trim(),
          description: String(formData.get('description') || '').trim() || null,
        },
        {
          onSuccess: () => {
            void refreshCatalog()
            closeModal()
          },
          onError: (error) =>
            setFormError(
              errorMessage(error, 'No fue posible crear la categoría.'),
            ),
        },
      )
    } else if (formType === 'specialty') {
      catalogMutations.specialty.mutate(
        {
          category_id: String(formData.get('parent_id')),
          name: String(formData.get('name')).trim(),
        },
        {
          onSuccess: () => {
            void refreshCatalog()
            closeModal()
          },
          onError: (error) =>
            setFormError(
              errorMessage(error, 'No fue posible crear la especialidad.'),
            ),
        },
      )
    } else if (formType === 'shift') {
      const start = timeToMinutes(String(formData.get('start')))
      const end = timeToMinutes(String(formData.get('end')))
      if (end <= start) {
        setFormError('El fin del turno debe ser posterior al inicio.')
        return
      }
      catalogMutations.shift.mutate(
        {
          name: String(formData.get('name')).trim(),
          start_minute: start,
          end_minute: end,
        },
        {
          onSuccess: () => {
            void refreshCatalog()
            closeModal()
          },
          onError: (error) =>
            setFormError(errorMessage(error, 'No fue posible crear el turno.')),
        },
      )
    }
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-bold tracking-[0.16em] text-[#0f766e] uppercase">
            Configuración
          </p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Catálogo
          </h1>
          <p className="mt-2 text-[#718096]">
            Administra áreas de soporte, especialidades, turnos y técnicos.
          </p>
        </div>
        {tab === 'catalog' && (
          <Button
            onClick={() => {
              setFormError('')
              setFormType('area')
            }}
          >
            <Plus size={17} />
            Nuevo elemento
          </Button>
        )}
      </section>

      <div className="flex gap-1 border-b border-[#dce6e4]">
        {[
          { key: 'technicians' as const, label: 'Técnicos', icon: UsersRound },
          {
            key: 'catalog' as const,
            label: 'Áreas y especialidades',
            icon: FolderTree,
          },
        ].map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-semibold transition-colors ${tab === key ? 'border-[#0f766e] text-[#0f766e]' : 'border-transparent text-[#718096] hover:text-[#334155]'}`}
          >
            <Icon size={17} />
            {label}
          </button>
        ))}
      </div>

      {isLoading && (
        <p className="rounded-xl border border-[#dce6e4] bg-white p-8 text-center text-sm text-[#718096]">
          Cargando catálogo...
        </p>
      )}
      {isError && (
        <p className="rounded-xl border border-[#f3d4cf] bg-[#fff8f7] p-8 text-center text-sm text-[#b54735]">
          No fue posible cargar el catálogo.
        </p>
      )}

      {!isLoading && !isError && tab === 'technicians' && (
        <>
          <section className="grid gap-4 sm:grid-cols-3">
            {[
              {
                label: 'Técnicos activos',
                value: technicians.filter((technician) => technician.is_active)
                  .length,
                icon: UsersRound,
              },
              {
                label: 'Especialidades',
                value: specialties.length,
                icon: Layers3,
              },
              {
                label: 'Turnos configurados',
                value: shifts.length,
                icon: Clock3,
              },
            ].map(({ label, value, icon: Icon }) => (
              <article
                key={label}
                className="rounded-xl border border-[#dce6e4] bg-white p-5"
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm text-[#718096]">{label}</p>
                  <Icon size={18} className="text-[#0f766e]" />
                </div>
                <p className="mt-3 font-mono text-3xl font-bold">{value}</p>
              </article>
            ))}
          </section>
          <section className="overflow-hidden rounded-xl border border-[#dce6e4] bg-white">
            <div className="border-b border-[#edf2f1] p-4">
              <div className="relative max-w-sm">
                <Search
                  size={16}
                  className="absolute top-1/2 left-3 -translate-y-1/2 text-[#87959c]"
                />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Buscar técnico..."
                  aria-label="Buscar técnico"
                  className="h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] pr-3 pl-9 text-sm outline-none focus:border-[#0f766e]"
                />
              </div>
            </div>
            {filteredTechnicians.length === 0 ? (
              <div className="p-10 text-center">
                <UsersRound className="mx-auto text-[#b7c6c7]" size={28} />
                <p className="mt-3 font-medium">No hay técnicos configurados</p>
                <p className="mt-1 text-sm text-[#87959c]">
                  Los usuarios con perfil técnico aparecerán aquí.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-190 text-left text-sm">
                  <thead className="bg-[#f8faf9] text-xs tracking-wide text-[#87959c] uppercase">
                    <tr>
                      <th className="px-5 py-3 font-semibold">Técnico</th>
                      <th className="px-5 py-3 font-semibold">Nivel</th>
                      <th className="px-5 py-3 font-semibold">Turno</th>
                      <th className="px-5 py-3 font-semibold">
                        Especialidades
                      </th>
                      <th className="px-5 py-3 text-right font-semibold">
                        Acciones
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#edf2f1]">
                    {filteredTechnicians.map((technician) => (
                      <tr key={technician.id} className="hover:bg-[#fbfdfc]">
                        <td className="px-5 py-4 font-semibold text-[#24343d]">
                          {technician.full_name}
                        </td>
                        <td className="px-5 py-4 text-[#52616b]">
                          {technician.support_level
                            ? supportLevelLabels[technician.support_level]
                            : 'Sin asignar'}
                        </td>
                        <td className="px-5 py-4 text-[#52616b]">
                          {shifts.find(
                            (shift) => shift.id === technician.shift_id,
                          )?.name ?? 'Sin asignar'}
                        </td>
                        <td className="px-5 py-4 text-[#52616b]">
                          {technician.specialty_ids
                            .map(
                              (id) =>
                                specialties.find(
                                  (specialty) => specialty.id === id,
                                )?.name,
                            )
                            .filter(Boolean)
                            .join(', ') || 'Sin asignar'}
                        </td>
                        <td className="px-5 py-4 text-right">
                          <Button
                            variant="ghost"
                            onClick={() => {
                              setFormError('')
                              setEditingTechnician(technician)
                            }}
                          >
                            <Settings2 size={16} /> Configurar
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {!isLoading && !isError && tab === 'catalog' && (
        <section className="grid gap-5 xl:grid-cols-2">
          <CatalogGroup
            title="Áreas de servicio"
            count={areas.length}
            icon={FolderTree}
            onAdd={() => {
              setFormError('')
              setFormType('area')
            }}
          >
            {areas.map((area) => (
              <CatalogRow
                key={area.id}
                name={area.name}
                detail={area.description ?? 'Sin descripción'}
              />
            ))}
          </CatalogGroup>
          <CatalogGroup
            title="Categorías"
            count={categories.length}
            icon={Layers3}
            onAdd={() => {
              setFormError('')
              setFormType('category')
            }}
          >
            {categories.map((category) => (
              <CatalogRow
                key={category.id}
                name={category.name}
                detail={
                  areas.find((area) => area.id === category.area_id)?.name ??
                  'Área no disponible'
                }
              />
            ))}
          </CatalogGroup>
          <CatalogGroup
            title="Especialidades"
            count={specialties.length}
            icon={SlidersHorizontal}
            onAdd={() => {
              setFormError('')
              setFormType('specialty')
            }}
          >
            {specialties.map((specialty) => (
              <CatalogRow
                key={specialty.id}
                name={specialty.name}
                detail={
                  categories.find(
                    (category) => category.id === specialty.category_id,
                  )?.name ?? 'Categoría no disponible'
                }
              />
            ))}
          </CatalogGroup>
          <CatalogGroup
            title="Turnos"
            count={shifts.length}
            icon={Clock3}
            onAdd={() => {
              setFormError('')
              setFormType('shift')
            }}
          >
            {shifts.map((shift) => (
              <CatalogRow
                key={shift.id}
                name={shift.name}
                detail={`${minutesToTime(shift.start_minute)} - ${minutesToTime(shift.end_minute)}`}
              />
            ))}
          </CatalogGroup>
        </section>
      )}

      {editingTechnician && (
        <Modal
          title="Configurar técnico"
          description={`Actualiza el perfil operativo de ${editingTechnician.full_name}.`}
          onClose={closeModal}
        >
          <form className="space-y-4" onSubmit={handleTechnicianSubmit}>
            <label className="block text-sm font-medium text-[#334155]">
              Nivel de soporte
              <select
                name="support_level"
                defaultValue={editingTechnician.support_level ?? ''}
                className="mt-1.5 h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3"
              >
                <option value="">Sin asignar</option>
                <option value="level_1">Nivel 1</option>
                <option value="level_2">Nivel 2</option>
              </select>
            </label>
            <label className="block text-sm font-medium text-[#334155]">
              Turno
              <select
                name="shift_id"
                defaultValue={editingTechnician.shift_id ?? ''}
                className="mt-1.5 h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3"
              >
                <option value="">Sin asignar</option>
                {shifts.map((shift) => (
                  <option key={shift.id} value={shift.id}>
                    {shift.name} ({minutesToTime(shift.start_minute)} -{' '}
                    {minutesToTime(shift.end_minute)})
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm font-medium text-[#334155]">
              Carga máxima
              <input
                name="max_load"
                type="number"
                min="1"
                max="50"
                defaultValue={editingTechnician.max_load ?? ''}
                placeholder="Ej. 8"
                className="mt-1.5 h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3"
              />
            </label>
            <fieldset>
              <legend className="text-sm font-medium text-[#334155]">
                Especialidades habilitadas
              </legend>
              <div className="mt-2 max-h-40 space-y-2 overflow-y-auto rounded-lg border border-[#dce6e4] p-3">
                {specialties.map((specialty) => (
                  <label
                    key={specialty.id}
                    className="flex items-center gap-2 text-sm text-[#52616b]"
                  >
                    <input
                      type="checkbox"
                      name="specialty_ids"
                      value={specialty.id}
                      defaultChecked={editingTechnician.specialty_ids.includes(
                        specialty.id,
                      )}
                    />
                    {specialty.name}
                  </label>
                ))}
              </div>
            </fieldset>
            {formError && <p className="text-sm text-[#b54735]">{formError}</p>}
            <div className="flex justify-end gap-3">
              <Button type="button" variant="secondary" onClick={closeModal}>
                Cancelar
              </Button>
              <Button type="submit" disabled={technicianMutation.isPending}>
                {technicianMutation.isPending
                  ? 'Guardando...'
                  : 'Guardar cambios'}
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {formType && (
        <Modal
          title={`Nuevo ${formType === 'area' ? 'área' : formType === 'category' ? 'categoría' : formType === 'specialty' ? 'especialidad' : 'turno'}`}
          description="Completa los datos del nuevo elemento del catálogo."
          onClose={closeModal}
        >
          <form className="space-y-4" onSubmit={handleCatalogSubmit}>
            {formType === 'area' && (
              <label className="block text-sm font-medium text-[#334155]">
                ID de unidad organizacional
                <input
                  required
                  name="unit_id"
                  placeholder="UUID de la unidad"
                  className="mt-1.5 h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3"
                />
              </label>
            )}
            {(formType === 'category' || formType === 'specialty') && (
              <label className="block text-sm font-medium text-[#334155]">
                {formType === 'category' ? 'Área de servicio' : 'Categoría'}
                <select
                  required
                  name="parent_id"
                  className="mt-1.5 h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3"
                >
                  <option value="">Selecciona una opción</option>
                  {(formType === 'category' ? areas : categories).map(
                    (item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ),
                  )}
                </select>
              </label>
            )}
            <label className="block text-sm font-medium text-[#334155]">
              Nombre
              <input
                required
                name="name"
                maxLength={120}
                className="mt-1.5 h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3"
              />
            </label>
            {formType !== 'specialty' && formType !== 'shift' && (
              <label className="block text-sm font-medium text-[#334155]">
                Descripción
                <textarea
                  name="description"
                  maxLength={300}
                  className="mt-1.5 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3 py-2"
                  rows={3}
                />
              </label>
            )}
            {formType === 'shift' && (
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-sm font-medium text-[#334155]">
                  Inicio
                  <input
                    required
                    name="start"
                    type="time"
                    className="mt-1.5 h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3"
                  />
                </label>
                <label className="block text-sm font-medium text-[#334155]">
                  Fin
                  <input
                    required
                    name="end"
                    type="time"
                    className="mt-1.5 h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3"
                  />
                </label>
              </div>
            )}
            {formError && <p className="text-sm text-[#b54735]">{formError}</p>}
            <div className="flex justify-end gap-3">
              <Button type="button" variant="secondary" onClick={closeModal}>
                Cancelar
              </Button>
              <Button
                type="submit"
                disabled={Object.values(catalogMutations).some(
                  (mutation) => mutation.isPending,
                )}
              >
                Guardar
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

function CatalogGroup({
  title,
  count,
  icon: Icon,
  onAdd,
  children,
}: {
  title: string
  count: number
  icon: typeof FolderTree
  onAdd: () => void
  children: React.ReactNode
}) {
  return (
    <article className="overflow-hidden rounded-xl border border-[#dce6e4] bg-white">
      <div className="flex items-center justify-between border-b border-[#edf2f1] p-5">
        <div className="flex items-center gap-3">
          <div className="grid size-9 place-items-center rounded-lg bg-[#d9eee9] text-[#0f766e]">
            <Icon size={18} />
          </div>
          <div>
            <h2 className="font-bold">{title}</h2>
            <p className="text-xs text-[#87959c]">{count} elementos</p>
          </div>
        </div>
        <Button variant="ghost" onClick={onAdd} aria-label={`Agregar ${title}`}>
          <Plus size={17} />
        </Button>
      </div>
      <div className="divide-y divide-[#edf2f1]">{children}</div>
    </article>
  )
}

function CatalogRow({ name, detail }: { name: string; detail: string }) {
  return (
    <div className="px-5 py-4">
      <p className="font-medium text-[#24343d]">{name}</p>
      <p className="mt-1 text-xs text-[#87959c]">{detail}</p>
    </div>
  )
}
