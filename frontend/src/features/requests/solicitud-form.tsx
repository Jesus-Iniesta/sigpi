import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, X } from 'lucide-react'
import { getCategories } from '@/api/catalog'
import { useAuth } from '@/features/auth/auth-context'
import { useCrearSolicitud } from './use-crear-solicitud'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'

type SolicitudFormProps = {
  onClose: () => void
}

type FormErrors = {
  title?: string
  description?: string
  physical_location?: string
}

type FieldName = keyof FormErrors

const REQUIRED_MESSAGES: Record<FieldName, string> = {
  title: 'El título es obligatorio.',
  description: 'La descripción es obligatoria.',
  physical_location: 'La ubicación física es obligatoria.',
}

function validateField(name: FieldName, value: string): string | undefined {
  return value.trim() ? undefined : REQUIRED_MESSAGES[name]
}

function validate(
  title: string,
  description: string,
  physicalLocation: string,
): FormErrors {
  const values = {
    title,
    description,
    physical_location: physicalLocation,
  }
  const errors: FormErrors = {}
  for (const name of Object.keys(values) as FieldName[]) {
    const message = validateField(name, values[name])
    if (message) errors[name] = message
  }
  return errors
}

export function SolicitudForm({ onClose }: SolicitudFormProps) {
  const { user } = useAuth()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [physicalLocation, setPhysicalLocation] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [urgency, setUrgency] = useState('')
  const [impact, setImpact] = useState('')
  const [errors, setErrors] = useState<FormErrors>({})

  const { data: categories } = useQuery({
    queryKey: ['catalog', 'categories'],
    queryFn: getCategories,
  })

  const { crear, solicitud, isPending, error: apiError } = useCrearSolicitud()

  // Validación en línea: al salir de un campo se valida; si ya tenía error,
  // se vuelve a validar mientras el usuario escribe.
  const checkField = (name: FieldName, value: string) => {
    setErrors((current) => ({ ...current, [name]: validateField(name, value) }))
  }
  const onFieldChange = (
    name: FieldName,
    value: string,
    setValue: (value: string) => void,
  ) => {
    setValue(value)
    if (errors[name]) checkField(name, value)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const validationErrors = validate(title, description, physicalLocation)
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) return

    crear({
      requester_id: user!.id,
      category_id: categoryId || null,
      title: title.trim(),
      description: description.trim(),
      physical_location: physicalLocation.trim(),
      channel: 'portal',
      urgency: urgency ? Number(urgency) : null,
      impact: impact ? Number(impact) : null,
    })
  }

  const isUnauthenticated =
    apiError !== null && /sesión|autorizado|401/i.test(apiError)

  if (solicitud) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div
          role="status"
          className="w-full max-w-md rounded-xl bg-white p-6 text-center shadow-xl"
        >
          <CheckCircle2 size={40} className="mx-auto text-green-600" />
          <h2 className="mt-3 text-lg font-bold text-[#17212b]">
            Solicitud registrada correctamente
          </h2>
          <p className="mt-2 text-sm text-[#52616b]">
            Guarda tu folio para dar seguimiento a la solicitud.
          </p>
          <p className="mt-4 rounded-lg bg-[#f0f6f5] px-4 py-3 font-mono text-xl font-bold text-[#0f766e]">
            {solicitud.folio}
          </p>
          <div className="mt-6 flex justify-center">
            <Button type="button" onClick={onClose}>
              Cerrar
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-[#edf2f1] px-6 py-4">
          <h2 className="text-lg font-bold text-[#17212b]">Nueva solicitud</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-[#87959c] hover:bg-[#e7efee] hover:text-[#17212b]"
            aria-label="Cerrar"
          >
            <X size={18} />
          </button>
        </div>

        <form
          onSubmit={handleSubmit}
          className="space-y-4 px-6 py-5"
          noValidate
        >
          <div>
            <label
              htmlFor="solicitud-title"
              className="block text-sm font-medium text-[#334155]"
            >
              Título
            </label>
            <input
              id="solicitud-title"
              type="text"
              value={title}
              onChange={(e) => onFieldChange('title', e.target.value, setTitle)}
              onBlur={(e) => checkField('title', e.target.value)}
              placeholder="Ej. No hay conexión a la red"
              className={cn(
                'mt-1.5 w-full rounded-lg border bg-white px-3 py-2.5 text-sm text-[#17212b] placeholder:text-[#94a3b8] focus:ring-2 focus:outline-none',
                errors.title
                  ? 'border-red-400 focus:ring-red-200'
                  : 'border-[#d7e0df] focus:border-[#0f766e] focus:ring-[#0f766e]/20',
              )}
            />
            {errors.title && (
              <p className="mt-1 text-xs text-red-600">{errors.title}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="solicitud-description"
              className="block text-sm font-medium text-[#334155]"
            >
              Descripción
            </label>
            <textarea
              id="solicitud-description"
              value={description}
              onChange={(e) =>
                onFieldChange('description', e.target.value, setDescription)
              }
              onBlur={(e) => checkField('description', e.target.value)}
              rows={3}
              placeholder="Describe el problema con detalle…"
              className={cn(
                'mt-1.5 w-full rounded-lg border bg-white px-3 py-2.5 text-sm text-[#17212b] placeholder:text-[#94a3b8] focus:ring-2 focus:outline-none',
                errors.description
                  ? 'border-red-400 focus:ring-red-200'
                  : 'border-[#d7e0df] focus:border-[#0f766e] focus:ring-[#0f766e]/20',
              )}
            />
            {errors.description && (
              <p className="mt-1 text-xs text-red-600">{errors.description}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="solicitud-location"
              className="block text-sm font-medium text-[#334155]"
            >
              Ubicación física
            </label>
            <input
              id="solicitud-location"
              type="text"
              value={physicalLocation}
              onChange={(e) =>
                onFieldChange(
                  'physical_location',
                  e.target.value,
                  setPhysicalLocation,
                )
              }
              onBlur={(e) => checkField('physical_location', e.target.value)}
              placeholder="Ej. Edificio A, laboratorio 2"
              className={cn(
                'mt-1.5 w-full rounded-lg border bg-white px-3 py-2.5 text-sm text-[#17212b] placeholder:text-[#94a3b8] focus:ring-2 focus:outline-none',
                errors.physical_location
                  ? 'border-red-400 focus:ring-red-200'
                  : 'border-[#d7e0df] focus:border-[#0f766e] focus:ring-[#0f766e]/20',
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
                htmlFor="solicitud-category"
                className="block text-sm font-medium text-[#334155]"
              >
                Categoría
              </label>
              <select
                id="solicitud-category"
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-[#d7e0df] bg-white px-3 py-2.5 text-sm text-[#17212b] focus:border-[#0f766e] focus:ring-2 focus:ring-[#0f766e]/20 focus:outline-none"
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
                htmlFor="solicitud-urgency"
                className="block text-sm font-medium text-[#334155]"
              >
                Urgencia
              </label>
              <select
                id="solicitud-urgency"
                value={urgency}
                onChange={(e) => setUrgency(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-[#d7e0df] bg-white px-3 py-2.5 text-sm text-[#17212b] focus:border-[#0f766e] focus:ring-2 focus:ring-[#0f766e]/20 focus:outline-none"
              >
                <option value="">—</option>
                <option value="1">1</option>
                <option value="2">2</option>
                <option value="3">3</option>
              </select>
            </div>
            <div>
              <label
                htmlFor="solicitud-impact"
                className="block text-sm font-medium text-[#334155]"
              >
                Impacto
              </label>
              <select
                id="solicitud-impact"
                value={impact}
                onChange={(e) => setImpact(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-[#d7e0df] bg-white px-3 py-2.5 text-sm text-[#17212b] focus:border-[#0f766e] focus:ring-2 focus:ring-[#0f766e]/20 focus:outline-none"
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
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Enviando…' : 'Enviar'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
