import { useState } from 'react'
import { Clock, Plus, Search, ShieldCheck } from 'lucide-react'
import type { Category } from '@/api/catalog'
import {
  priorities,
  type EffectiveSla,
  type Priority,
  type SlaAgreement,
  type SlaAgreementInput,
  type SlaVersion,
  type SlaVersionInput,
} from '@/api/sla'
import { Button } from '@/shared/ui/button'
import {
  useCreateSlaAgreement,
  useEffectiveSlaLookup,
  usePublishSlaVersion,
  useSlaAgreements,
  useSlaCategories,
  useSlaVersions,
} from './use-sla'

const inputClass =
  'mt-1.5 h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3 outline-none focus:border-[#0f766e]'

function formatMinutes(minutes: number) {
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('es-MX', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function toLocalInput(date: Date) {
  const offset = date.getTimezoneOffset() * 60000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : ''
}

// ---------------------------------------------------------------------------
// Nuevo acuerdo
// ---------------------------------------------------------------------------
function AgreementDialog({
  categories,
  isSaving,
  serverError,
  onClose,
  onSubmit,
}: {
  categories: Category[]
  isSaving: boolean
  serverError: string
  onClose: () => void
  onSubmit: (input: SlaAgreementInput) => void
}) {
  const [name, setName] = useState('')
  const [kind, setKind] = useState<'default' | 'category'>('category')
  const [categoryId, setCategoryId] = useState('')
  const [error, setError] = useState('')

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!name.trim()) {
      setError('Escribe el nombre del acuerdo.')
      return
    }
    if (kind === 'category' && !categoryId) {
      setError('Selecciona la categoría del acuerdo.')
      return
    }
    setError('')
    onSubmit(
      kind === 'default'
        ? { name: name.trim(), is_default: true }
        : { name: name.trim(), category_id: categoryId },
    )
  }

  return (
    <div
      className="fixed inset-0 z-20 grid place-items-center bg-[#123b3a]/35 p-5"
      role="presentation"
      onMouseDown={onClose}
    >
      <form
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
        onSubmit={submit}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 className="text-xl font-bold">Nuevo acuerdo</h2>
        <p className="mt-1 text-sm text-[#718096]">
          Define un acuerdo para una categoría o el predeterminado.
        </p>
        <div className="mt-6 space-y-4">
          <label className="block text-sm font-medium text-[#334155]">
            Nombre del acuerdo
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className={inputClass}
              disabled={isSaving}
            />
          </label>
          <label className="block text-sm font-medium text-[#334155]">
            Alcance
            <select
              value={kind}
              onChange={(event) =>
                setKind(event.target.value as 'default' | 'category')
              }
              className={inputClass}
              disabled={isSaving}
            >
              <option value="category">Por categoría</option>
              <option value="default">Predeterminado</option>
            </select>
          </label>
          {kind === 'category' && (
            <label className="block text-sm font-medium text-[#334155]">
              Categoría
              <select
                value={categoryId}
                onChange={(event) => setCategoryId(event.target.value)}
                className={inputClass}
                disabled={isSaving}
              >
                <option value="">Selecciona una categoría</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        {(error || serverError) && (
          <p className="mt-4 text-sm text-[#b54735]">{error || serverError}</p>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={isSaving}
          >
            Cancelar
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? 'Guardando...' : 'Guardar'}
          </Button>
        </div>
      </form>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Nueva versión
// ---------------------------------------------------------------------------
type RowState = { include: boolean; first: string; resolution: string }
type RowsState = Record<Priority, RowState>

function initialRows(current: SlaVersion[]): RowsState {
  const rows = {} as RowsState
  for (const priority of priorities) {
    const open = current.find(
      (version) => version.priority === priority && version.valid_to === null,
    )
    rows[priority] = {
      include: Boolean(open),
      first: open ? String(open.first_response_minutes) : '',
      resolution: open ? String(open.resolution_minutes) : '',
    }
  }
  return rows
}

function validateRows(rows: RowsState) {
  const errors: Partial<Record<Priority, string>> = {}
  let included = 0
  for (const priority of priorities) {
    const row = rows[priority]
    if (!row.include) continue
    included += 1
    const first = Number(row.first)
    const resolution = Number(row.resolution)
    if (
      !Number.isInteger(first) ||
      !Number.isInteger(resolution) ||
      first <= 0 ||
      resolution <= 0
    ) {
      errors[priority] = 'Escribe tiempos enteros mayores que cero.'
    } else if (resolution <= first) {
      errors[priority] =
        'La resolución debe ser mayor que la primera respuesta.'
    }
  }
  return { errors, included }
}

function VersionDialog({
  initialValidFrom,
  current,
  isSaving,
  serverError,
  onClose,
  onSubmit,
}: {
  initialValidFrom: string
  current: SlaVersion[]
  isSaving: boolean
  serverError: string
  onClose: () => void
  onSubmit: (input: SlaVersionInput) => void
}) {
  const [validFrom, setValidFrom] = useState(initialValidFrom)
  const [rows, setRows] = useState<RowsState>(() => initialRows(current))
  const [rowErrors, setRowErrors] = useState<Partial<Record<Priority, string>>>(
    {},
  )
  const [error, setError] = useState('')

  const updateRow = (priority: Priority, change: Partial<RowState>) =>
    setRows((state) => ({
      ...state,
      [priority]: { ...state[priority], ...change },
    }))

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const { errors, included } = validateRows(rows)
    setRowErrors(errors)
    if (!validFrom) {
      setError('Indica la fecha de entrada en vigor.')
      return
    }
    if (included === 0) {
      setError('Incluye al menos una prioridad.')
      return
    }
    if (Object.keys(errors).length > 0) {
      setError('Corrige las inconsistencias señaladas.')
      return
    }
    setError('')
    onSubmit({
      valid_from: new Date(validFrom).toISOString(),
      times: priorities
        .filter((priority) => rows[priority].include)
        .map((priority) => ({
          priority,
          first_response_minutes: Number(rows[priority].first),
          resolution_minutes: Number(rows[priority].resolution),
        })),
    })
  }

  return (
    <div
      className="fixed inset-0 z-20 grid place-items-center bg-[#123b3a]/35 p-5"
      role="presentation"
      onMouseDown={onClose}
    >
      <form
        className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl"
        onSubmit={submit}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 className="text-xl font-bold">Nueva versión</h2>
        <p className="mt-1 text-sm text-[#718096]">
          Los tiempos se expresan en minutos. La versión anterior se conserva en
          el histórico.
        </p>
        <label className="mt-6 block text-sm font-medium text-[#334155]">
          Entrada en vigor
          <input
            type="datetime-local"
            value={validFrom}
            onChange={(event) => setValidFrom(event.target.value)}
            className={inputClass}
            disabled={isSaving}
          />
        </label>
        <div className="mt-5 space-y-3">
          {priorities.map((priority) => {
            const row = rows[priority]
            return (
              <div key={priority}>
                <div className="grid grid-cols-[auto_1fr_1fr] items-end gap-3">
                  <label className="flex h-10 items-center gap-2 text-sm font-semibold text-[#334155]">
                    <input
                      type="checkbox"
                      checked={row.include}
                      onChange={(event) =>
                        updateRow(priority, { include: event.target.checked })
                      }
                      aria-label={`Incluir ${priority}`}
                      disabled={isSaving}
                    />
                    {priority}
                  </label>
                  <label className="block text-xs font-medium text-[#718096]">
                    Primera respuesta ({priority})
                    <input
                      type="number"
                      min="1"
                      value={row.first}
                      onChange={(event) =>
                        updateRow(priority, { first: event.target.value })
                      }
                      className={inputClass}
                      disabled={isSaving || !row.include}
                    />
                  </label>
                  <label className="block text-xs font-medium text-[#718096]">
                    Resolución ({priority})
                    <input
                      type="number"
                      min="1"
                      value={row.resolution}
                      onChange={(event) =>
                        updateRow(priority, { resolution: event.target.value })
                      }
                      className={inputClass}
                      disabled={isSaving || !row.include}
                    />
                  </label>
                </div>
                {rowErrors[priority] && (
                  <p className="mt-1 text-xs text-[#b54735]">
                    {priority}: {rowErrors[priority]}
                  </p>
                )}
              </div>
            )
          })}
        </div>
        {(error || serverError) && (
          <p className="mt-4 text-sm text-[#b54735]">{error || serverError}</p>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={isSaving}
          >
            Cancelar
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? 'Guardando...' : 'Publicar versión'}
          </Button>
        </div>
      </form>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Consulta del acuerdo vigente (AC3: aviso cuando se aplica el predeterminado)
// ---------------------------------------------------------------------------
function EffectiveLookup({ categories }: { categories: Category[] }) {
  const lookup = useEffectiveSlaLookup()
  const [categoryId, setCategoryId] = useState('')
  const [priority, setPriority] = useState<Priority>('P1')
  const result: EffectiveSla | undefined = lookup.data

  return (
    <section className="rounded-xl border border-[#dce6e4] bg-white p-5">
      <h2 className="text-lg font-bold">Consultar acuerdo vigente</h2>
      <p className="mt-1 text-sm text-[#718096]">
        Muestra el acuerdo que aplica a una categoría y prioridad. Si no hay
        acuerdo propio, se aplica el predeterminado.
      </p>
      <div className="mt-4 grid gap-4 sm:grid-cols-[1fr_9rem_auto] sm:items-end">
        <label className="block text-sm font-medium text-[#334155]">
          Categoría de consulta
          <select
            value={categoryId}
            onChange={(event) => setCategoryId(event.target.value)}
            className={inputClass}
          >
            <option value="">Sin categoría</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm font-medium text-[#334155]">
          Prioridad de consulta
          <select
            value={priority}
            onChange={(event) => setPriority(event.target.value as Priority)}
            className={inputClass}
          >
            {priorities.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <Button
          type="button"
          variant="secondary"
          disabled={lookup.isPending}
          onClick={() =>
            lookup.mutate({ priority, categoryId: categoryId || undefined })
          }
        >
          <Search size={16} />
          Consultar
        </Button>
      </div>
      {lookup.isError && (
        <p className="mt-4 text-sm text-[#b54735]">
          {errorMessage(lookup.error)}
        </p>
      )}
      {result && (
        <div className="mt-4 space-y-3">
          {result.notice && (
            <p
              role="status"
              className="rounded-lg border border-[#ecd9a8] bg-[#fff8e6] px-4 py-3 text-sm text-[#7a5b13]"
            >
              {result.notice}
            </p>
          )}
          <dl className="grid gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-[#87959c]">Acuerdo</dt>
              <dd className="font-semibold">{result.agreement_name}</dd>
            </div>
            <div>
              <dt className="text-[#87959c]">Versión</dt>
              <dd className="font-semibold">v{result.version}</dd>
            </div>
            <div>
              <dt className="text-[#87959c]">Primera respuesta</dt>
              <dd className="font-semibold">
                {formatMinutes(result.first_response_minutes)}
              </dd>
            </div>
            <div>
              <dt className="text-[#87959c]">Resolución</dt>
              <dd className="font-semibold">
                {formatMinutes(result.resolution_minutes)}
              </dd>
            </div>
          </dl>
        </div>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Pantalla
// ---------------------------------------------------------------------------
export function SlaPage() {
  const agreementsQuery = useSlaAgreements()
  const categoriesQuery = useSlaCategories()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [now] = useState(() => Date.now())
  const [showAgreementForm, setShowAgreementForm] = useState(false)
  const [versionForm, setVersionForm] = useState<{
    validFrom: string
    current: SlaVersion[]
  } | null>(null)

  const agreements: SlaAgreement[] = agreementsQuery.data ?? []
  const categories: Category[] = categoriesQuery.data ?? []
  const selected =
    agreements.find((agreement) => agreement.id === selectedId) ?? agreements[0]

  const versionsQuery = useSlaVersions(selected?.id)
  const versions: SlaVersion[] = versionsQuery.data ?? []
  const createAgreement = useCreateSlaAgreement()
  const publishVersion = usePublishSlaVersion(selected?.id)

  const categoryName = (agreement: SlaAgreement) =>
    agreement.is_default
      ? 'Predeterminado'
      : (categories.find((category) => category.id === agreement.category_id)
          ?.name ?? 'Categoría')

  const openAgreementForm = () => {
    createAgreement.reset()
    setShowAgreementForm(true)
  }

  const openVersionForm = () => {
    publishVersion.reset()
    const tomorrow = new Date()
    tomorrow.setDate(tomorrow.getDate() + 1)
    tomorrow.setHours(8, 0, 0, 0)
    setVersionForm({ validFrom: toLocalInput(tomorrow), current: versions })
  }

  const versionStatus = (version: SlaVersion) => {
    if (version.valid_to) return `Cerrada el ${formatDate(version.valid_to)}`
    return new Date(version.valid_from).getTime() > now
      ? 'Programada'
      : 'Vigente'
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-bold tracking-[0.16em] text-[#0f766e] uppercase">
            Configuración
          </p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Acuerdos de nivel de servicio
          </h1>
          <p className="mt-2 text-[#718096]">
            Define y versiona los tiempos de primera respuesta y de resolución
            por categoría y prioridad.
          </p>
        </div>
        <Button onClick={openAgreementForm}>
          <Plus size={17} />
          Nuevo acuerdo
        </Button>
      </section>

      {agreementsQuery.isLoading && (
        <p className="p-8 text-center text-sm text-[#718096]">
          Cargando acuerdos...
        </p>
      )}
      {agreementsQuery.isError && (
        <p className="p-8 text-center text-sm text-[#b54735]">
          No fue posible cargar los acuerdos.
        </p>
      )}

      {!agreementsQuery.isLoading &&
        !agreementsQuery.isError &&
        agreements.length === 0 && (
          <div className="rounded-xl border border-[#dce6e4] bg-white p-10 text-center">
            <ShieldCheck className="mx-auto text-[#b7c6c7]" size={28} />
            <p className="mt-3 font-medium">No hay acuerdos configurados</p>
            <p className="mt-1 text-sm text-[#87959c]">
              Crea el acuerdo predeterminado o uno por categoría.
            </p>
          </div>
        )}

      {agreements.length > 0 && selected && (
        <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
          <section className="space-y-2" aria-label="Acuerdos">
            {agreements.map((agreement) => (
              <button
                key={agreement.id}
                type="button"
                onClick={() => setSelectedId(agreement.id)}
                aria-pressed={agreement.id === selected.id}
                className={
                  agreement.id === selected.id
                    ? 'w-full rounded-xl border border-[#0f766e] bg-[#eef7f5] p-4 text-left'
                    : 'w-full rounded-xl border border-[#dce6e4] bg-white p-4 text-left hover:bg-[#fbfdfc]'
                }
              >
                <p className="font-semibold text-[#24343d]">{agreement.name}</p>
                <p className="mt-1 text-xs text-[#87959c]">
                  {categoryName(agreement)}
                </p>
              </button>
            ))}
          </section>

          <section className="overflow-hidden rounded-xl border border-[#dce6e4] bg-white">
            <div className="flex flex-col gap-3 border-b border-[#edf2f1] p-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-lg font-bold">{selected.name}</h2>
                <p className="mt-1 text-sm text-[#87959c]">
                  {categoryName(selected)} · Histórico de versiones
                </p>
              </div>
              <Button variant="secondary" onClick={openVersionForm}>
                <Clock size={16} />
                Nueva versión
              </Button>
            </div>
            {versionsQuery.isLoading && (
              <p className="p-8 text-center text-sm text-[#718096]">
                Cargando versiones...
              </p>
            )}
            {versionsQuery.isError && (
              <p className="p-8 text-center text-sm text-[#b54735]">
                No fue posible cargar las versiones.
              </p>
            )}
            {!versionsQuery.isLoading &&
              !versionsQuery.isError &&
              versions.length === 0 && (
                <p className="p-8 text-center text-sm text-[#87959c]">
                  Este acuerdo aún no tiene versiones. Publica la primera.
                </p>
              )}
            {versions.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full min-w-170 text-left text-sm">
                  <thead className="bg-[#f8faf9] text-xs tracking-wide text-[#87959c] uppercase">
                    <tr>
                      <th className="px-5 py-3 font-semibold">Versión</th>
                      <th className="px-5 py-3 font-semibold">Prioridad</th>
                      <th className="px-5 py-3 font-semibold">
                        Primera respuesta
                      </th>
                      <th className="px-5 py-3 font-semibold">Resolución</th>
                      <th className="px-5 py-3 font-semibold">
                        Entra en vigor
                      </th>
                      <th className="px-5 py-3 font-semibold">Estado</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#edf2f1]">
                    {versions.map((version) => (
                      <tr key={version.id}>
                        <td className="px-5 py-3 font-mono">
                          v{version.version}
                        </td>
                        <td className="px-5 py-3 font-semibold">
                          {version.priority}
                        </td>
                        <td className="px-5 py-3">
                          {formatMinutes(version.first_response_minutes)}
                        </td>
                        <td className="px-5 py-3">
                          {formatMinutes(version.resolution_minutes)}
                        </td>
                        <td className="px-5 py-3 text-[#52616b]">
                          {formatDate(version.valid_from)}
                        </td>
                        <td className="px-5 py-3 text-[#52616b]">
                          {versionStatus(version)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}

      <EffectiveLookup categories={categories} />

      {showAgreementForm && (
        <AgreementDialog
          categories={categories}
          isSaving={createAgreement.isPending}
          serverError={errorMessage(createAgreement.error)}
          onClose={() =>
            !createAgreement.isPending && setShowAgreementForm(false)
          }
          onSubmit={(input) =>
            createAgreement.mutate(input, {
              onSuccess: (created) => {
                setSelectedId(created.id)
                setShowAgreementForm(false)
              },
            })
          }
        />
      )}

      {versionForm && selected && (
        <VersionDialog
          initialValidFrom={versionForm.validFrom}
          current={versionForm.current}
          isSaving={publishVersion.isPending}
          serverError={errorMessage(publishVersion.error)}
          onClose={() => !publishVersion.isPending && setVersionForm(null)}
          onSubmit={(input) =>
            publishVersion.mutate(input, {
              onSuccess: () => setVersionForm(null),
            })
          }
        />
      )}
    </div>
  )
}
