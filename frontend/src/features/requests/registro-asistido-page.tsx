import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AlertCircle, ArrowLeft, CheckCircle2, Search } from 'lucide-react'
import { getCategories } from '@/api/catalog'
import {
  createAssistedRequest,
  type AssistedChannel,
  type Request,
} from '@/api/solicitudes'
import { getUsers, type User } from '@/api/usuarios'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'

type FormErrors = {
  requester?: string
  channel?: string
  title?: string
  description?: string
  physical_location?: string
}

const channelOptions: { value: AssistedChannel; label: string }[] = [
  { value: 'phone', label: 'Teléfono' },
  { value: 'in_person', label: 'Presencial' },
]

const MAX_RESULTS = 5

const inputClass =
  'mt-1.5 w-full rounded-lg border bg-white px-3 py-2.5 text-sm text-[#17212b] placeholder:text-[#94a3b8] focus:ring-2 focus:outline-none'
const inputOk =
  'border-[#d7e0df] focus:border-[#0f766e] focus:ring-[#0f766e]/20'
const inputError = 'border-red-400 focus:ring-red-200'

function filterRequesters(users: User[], term: string): User[] {
  const query = term.trim().toLowerCase()
  if (!query) return []
  return users
    .filter(
      (user) =>
        user.is_active &&
        [user.full_name, user.institutional_id, user.email].some((field) =>
          field.toLowerCase().includes(query),
        ),
    )
    .slice(0, MAX_RESULTS)
}

function validate(values: {
  requester: User | null
  channel: AssistedChannel | ''
  title: string
  description: string
  physicalLocation: string
}): FormErrors {
  const errors: FormErrors = {}
  if (!values.requester) errors.requester = 'Selecciona al solicitante.'
  if (!values.channel) errors.channel = 'Selecciona el canal de origen.'
  if (!values.title.trim()) errors.title = 'El título es obligatorio.'
  if (!values.description.trim())
    errors.description = 'La descripción es obligatoria.'
  if (!values.physicalLocation.trim())
    errors.physical_location = 'La ubicación física es obligatoria.'
  return errors
}

export function RegistroAsistidoPage() {
  const [search, setSearch] = useState('')
  const [requester, setRequester] = useState<User | null>(null)
  const [channel, setChannel] = useState<AssistedChannel | ''>('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [physicalLocation, setPhysicalLocation] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [urgency, setUrgency] = useState('')
  const [impact, setImpact] = useState('')
  const [errors, setErrors] = useState<FormErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [created, setCreated] = useState<Request | null>(null)

  const usersQuery = useQuery({ queryKey: ['users'], queryFn: getUsers })
  const { data: categories } = useQuery({
    queryKey: ['catalog', 'categories'],
    queryFn: getCategories,
  })

  const matches = useMemo(
    () => filterRequesters(usersQuery.data ?? [], search),
    [usersQuery.data, search],
  )

  const createMutation = useMutation({
    mutationFn: createAssistedRequest,
    onSuccess: (request) => setCreated(request),
    onError: (error: Error) => setApiError(error.message),
  })

  const resetForm = () => {
    setSearch('')
    setRequester(null)
    setChannel('')
    setTitle('')
    setDescription('')
    setPhysicalLocation('')
    setCategoryId('')
    setUrgency('')
    setImpact('')
    setErrors({})
    setApiError(null)
    setCreated(null)
    createMutation.reset()
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setApiError(null)

    const validationErrors = validate({
      requester,
      channel,
      title,
      description,
      physicalLocation,
    })
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) return

    createMutation.mutate({
      requester_id: requester!.id,
      category_id: categoryId || null,
      title: title.trim(),
      description: description.trim(),
      physical_location: physicalLocation.trim(),
      channel: channel as AssistedChannel,
      urgency: urgency ? Number(urgency) : null,
      impact: impact ? Number(impact) : null,
    })
  }

  const isUnauthenticated =
    apiError !== null && /sesión|autorizado|401/i.test(apiError)

  if (created) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <div
          role="status"
          className="rounded-xl border border-green-200 bg-green-50 p-6"
        >
          <div className="flex items-start gap-3">
            <CheckCircle2
              size={22}
              className="mt-0.5 shrink-0 text-green-700"
            />
            <div>
              <h1 className="text-xl font-bold text-green-900">
                Solicitud registrada correctamente.
              </h1>
              <p className="mt-2 text-sm text-green-800">
                Folio:{' '}
                <span className="font-mono text-base font-bold">
                  {created.folio}
                </span>
              </p>
              <p className="mt-1 text-sm text-green-800">
                Solicitante: {requester?.full_name}. Dale el folio para que
                pueda dar seguimiento.
              </p>
            </div>
          </div>
        </div>
        <div className="flex gap-3">
          <Button onClick={resetForm}>Registrar otra solicitud</Button>
          <Link
            to="/solicitudes"
            className="inline-flex min-h-10 items-center rounded-lg border border-[#d7e0df] bg-white px-4 text-sm font-semibold text-[#334155] hover:bg-[#eef5f4]"
          >
            Ir a solicitudes
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <section>
        <Link
          to="/solicitudes"
          className="mb-3 inline-flex items-center gap-1.5 text-sm font-medium text-[#0f766e] hover:underline"
        >
          <ArrowLeft size={14} />
          Volver a solicitudes
        </Link>
        <p className="mb-2 text-xs font-bold tracking-[0.16em] text-[#0f766e] uppercase">
          Gestion operativa
        </p>
        <h1 className="text-3xl font-bold tracking-tight">Registro asistido</h1>
        <p className="mt-2 text-[#718096]">
          Captura una solicitud recibida por teléfono o de forma presencial en
          nombre del solicitante.
        </p>
      </section>

      <form
        onSubmit={handleSubmit}
        noValidate
        className="space-y-5 rounded-xl border border-[#dce6e4] bg-white p-6"
      >
        <div>
          <label
            htmlFor="asistido-search"
            className="block text-sm font-medium text-[#334155]"
          >
            Buscar solicitante
          </label>
          {requester ? (
            <div className="mt-1.5 flex items-center justify-between rounded-lg border border-[#0f766e] bg-[#eef8f6] px-3 py-2.5">
              <div className="text-sm">
                <p className="font-semibold text-[#17212b]">
                  {requester.full_name}
                </p>
                <p className="text-xs text-[#52616b]">
                  {requester.institutional_id} · {requester.email}
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setRequester(null)
                  setSearch('')
                }}
              >
                Cambiar
              </Button>
            </div>
          ) : (
            <>
              <div className="relative mt-1.5">
                <Search
                  size={16}
                  className="absolute top-1/2 left-3 -translate-y-1/2 text-[#87959c]"
                />
                <input
                  id="asistido-search"
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Nombre, matrícula o correo"
                  className={cn(
                    inputClass,
                    'mt-0 pl-9',
                    errors.requester ? inputError : inputOk,
                  )}
                />
              </div>
              {usersQuery.isError && (
                <p className="mt-1 text-xs text-red-600">
                  No se pudo cargar la lista de usuarios.
                </p>
              )}
              {search.trim() && matches.length > 0 && (
                <ul className="mt-2 divide-y divide-[#edf2f1] overflow-hidden rounded-lg border border-[#d7e0df]">
                  {matches.map((user) => (
                    <li key={user.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setRequester(user)
                          setErrors((prev) => ({
                            ...prev,
                            requester: undefined,
                          }))
                        }}
                        className="block w-full px-3 py-2.5 text-left text-sm hover:bg-[#f5f7f8]"
                      >
                        <span className="font-medium text-[#17212b]">
                          {user.full_name}
                        </span>
                        <span className="block text-xs text-[#52616b]">
                          {user.institutional_id} · {user.email}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {search.trim() &&
                matches.length === 0 &&
                usersQuery.isSuccess && (
                  <p className="mt-2 text-sm text-[#718096]">
                    No se encontró ningún solicitante con ese dato.
                  </p>
                )}
            </>
          )}
          {errors.requester && (
            <p className="mt-1 text-xs text-red-600">{errors.requester}</p>
          )}
        </div>

        <fieldset>
          <legend className="block text-sm font-medium text-[#334155]">
            Canal de origen
          </legend>
          <div className="mt-1.5 flex gap-6">
            {channelOptions.map((option) => (
              <label
                key={option.value}
                className="flex items-center gap-2 text-sm text-[#17212b]"
              >
                <input
                  type="radio"
                  name="asistido-channel"
                  value={option.value}
                  checked={channel === option.value}
                  onChange={() => setChannel(option.value)}
                  className="accent-[#0f766e]"
                />
                {option.label}
              </label>
            ))}
          </div>
          {errors.channel && (
            <p className="mt-1 text-xs text-red-600">{errors.channel}</p>
          )}
        </fieldset>

        <div>
          <label
            htmlFor="asistido-title"
            className="block text-sm font-medium text-[#334155]"
          >
            Título
          </label>
          <input
            id="asistido-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Ej. No hay conexión a la red"
            className={cn(inputClass, errors.title ? inputError : inputOk)}
          />
          {errors.title && (
            <p className="mt-1 text-xs text-red-600">{errors.title}</p>
          )}
        </div>

        <div>
          <label
            htmlFor="asistido-description"
            className="block text-sm font-medium text-[#334155]"
          >
            Descripción
          </label>
          <textarea
            id="asistido-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Describe el problema con detalle…"
            className={cn(
              inputClass,
              errors.description ? inputError : inputOk,
            )}
          />
          {errors.description && (
            <p className="mt-1 text-xs text-red-600">{errors.description}</p>
          )}
        </div>

        <div>
          <label
            htmlFor="asistido-location"
            className="block text-sm font-medium text-[#334155]"
          >
            Ubicación física
          </label>
          <input
            id="asistido-location"
            type="text"
            value={physicalLocation}
            onChange={(e) => setPhysicalLocation(e.target.value)}
            placeholder="Ej. Edificio A, laboratorio 2"
            className={cn(
              inputClass,
              errors.physical_location ? inputError : inputOk,
            )}
          />
          {errors.physical_location && (
            <p className="mt-1 text-xs text-red-600">
              {errors.physical_location}
            </p>
          )}
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label
              htmlFor="asistido-category"
              className="block text-sm font-medium text-[#334155]"
            >
              Categoría
            </label>
            <select
              id="asistido-category"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              className={cn(inputClass, inputOk)}
            >
              <option value="">Sin categoría</option>
              {categories?.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="asistido-urgency"
              className="block text-sm font-medium text-[#334155]"
            >
              Urgencia
            </label>
            <select
              id="asistido-urgency"
              value={urgency}
              onChange={(e) => setUrgency(e.target.value)}
              className={cn(inputClass, inputOk)}
            >
              <option value="">—</option>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
            </select>
          </div>
          <div>
            <label
              htmlFor="asistido-impact"
              className="block text-sm font-medium text-[#334155]"
            >
              Impacto
            </label>
            <select
              id="asistido-impact"
              value={impact}
              onChange={(e) => setImpact(e.target.value)}
              className={cn(inputClass, inputOk)}
            >
              <option value="">—</option>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
            </select>
          </div>
        </div>

        {isUnauthenticated && (
          <div className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <span>Tu sesión ha expirado. Inicia sesión nuevamente.</span>
          </div>
        )}

        {apiError && !isUnauthenticated && (
          <div className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <span>{apiError}</span>
          </div>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="secondary" onClick={resetForm}>
            Limpiar
          </Button>
          <Button type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending ? 'Registrando…' : 'Registrar solicitud'}
          </Button>
        </div>
      </form>
    </div>
  )
}
