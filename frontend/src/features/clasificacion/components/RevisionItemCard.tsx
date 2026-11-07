import { useState } from 'react'
import type { Category } from '@/api/types'
import type {
  ClassificationSource,
  RevisionItem,
  RevisionResult,
} from '@/api/revision'
import { useGuardarRevision } from '@/features/clasificacion/use-revision'
import {
  PRIORITY_STYLES,
  formatDateTime,
  levelLabel,
} from '@/features/requests/request-labels'
import { getFieldErrors } from '@/shared/lib/error-messages'
import { cn } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/button'
import { ErrorAlert } from '@/shared/ui/error-alert'

const SOURCE_LABELS: Record<ClassificationSource, string> = {
  model: 'Modelo',
  rules: 'Reglas',
  human: 'Revisión humana',
}

const LEVELS = [1, 2, 3] as const

const selectClass =
  'mt-1.5 w-full rounded-lg border border-[#d7e0df] bg-white px-3 py-2.5 text-sm text-[#17212b] focus:border-[#0f766e] focus:ring-2 focus:ring-[#0f766e]/20 focus:outline-none'

type FormErrors = {
  category_id?: string
  justification?: string
}

type RevisionItemCardProps = {
  item: RevisionItem
  categories: Category[]
  onSaved: (item: RevisionItem, result: RevisionResult) => void
}

/** Lista legible de lo que la persona cambió respecto de la propuesta del sistema. */
function changedFields(
  item: RevisionItem,
  categoryId: string,
  urgency: number,
  impact: number,
): string[] {
  const changes: string[] = []
  if (categoryId !== (item.category_id ?? '')) changes.push('categoría')
  if (urgency !== item.urgency) changes.push('urgencia')
  if (impact !== item.impact) changes.push('impacto')
  return changes
}

export function RevisionItemCard({
  item,
  categories,
  onSaved,
}: RevisionItemCardProps) {
  const [categoryId, setCategoryId] = useState(item.category_id ?? '')
  const [urgency, setUrgency] = useState(item.urgency)
  const [impact, setImpact] = useState(item.impact)
  const [justification, setJustification] = useState('')
  const [errors, setErrors] = useState<FormErrors>({})
  const guardar = useGuardarRevision(item.result_id, (result) =>
    onSaved(item, result),
  )

  const changes = changedFields(item, categoryId, urgency, impact)
  const serverErrors = getFieldErrors(guardar.error)
  const categoryError = errors.category_id ?? serverErrors.category_id
  const justificationError = errors.justification ?? serverErrors.justification
  const hasFieldErrors = Object.keys(serverErrors).length > 0
  const id = item.result_id

  const handleSubmit = () => {
    const nextErrors: FormErrors = {}
    if (!categoryId) nextErrors.category_id = 'Selecciona una categoría.'
    if (!justification.trim()) {
      nextErrors.justification = 'La justificación es obligatoria.'
    }
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return

    guardar.mutate({
      category_id: categoryId,
      urgency,
      impact,
      justification: justification.trim(),
    })
  }

  return (
    <li className="rounded-xl border border-[#dce6e4] bg-white p-6">
      <article aria-labelledby={`revision-${id}`}>
        <header className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div>
            <p className="font-mono text-sm text-[#87959c]">{item.folio}</p>
            <h2 id={`revision-${id}`} className="mt-1 text-lg font-bold">
              {item.title}
            </h2>
            <p className="mt-0.5 text-xs text-[#87959c]">
              Registrada {formatDateTime(item.created_at)}
            </p>
          </div>
          <span className="inline-flex w-fit rounded-md bg-amber-50 px-2 py-1 text-xs font-bold text-amber-800">
            Confianza {Math.round(item.confidence * 100)} %
          </span>
        </header>

        <p className="mt-3 text-sm whitespace-pre-line text-[#52616b]">
          {item.description}
        </p>

        <dl className="mt-4 grid gap-4 rounded-lg bg-[#f5f7f8] p-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-xs font-semibold tracking-wide text-[#87959c] uppercase">
              Categoría propuesta
            </dt>
            <dd className="mt-1 text-[#24343d]">
              {item.category_name ?? 'Sin categoría'}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold tracking-wide text-[#87959c] uppercase">
              Urgencia · Impacto
            </dt>
            <dd className="mt-1 text-[#24343d]">
              {levelLabel(item.urgency)} · {levelLabel(item.impact)}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold tracking-wide text-[#87959c] uppercase">
              Prioridad actual
            </dt>
            <dd className="mt-1">
              {item.priority ? (
                <span
                  className={cn(
                    'inline-flex rounded-md px-2 py-0.5 text-xs font-bold',
                    PRIORITY_STYLES[item.priority],
                  )}
                >
                  {item.priority}
                </span>
              ) : (
                '—'
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold tracking-wide text-[#87959c] uppercase">
              Origen
            </dt>
            <dd className="mt-1 text-[#24343d]">
              {SOURCE_LABELS[item.source]}
              {item.model_version ? ` · ${item.model_version}` : ''}
            </dd>
          </div>
        </dl>

        <form
          noValidate
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            handleSubmit()
          }}
        >
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label
                htmlFor={`categoria-${id}`}
                className="block text-sm font-medium text-[#334155]"
              >
                Categoría
              </label>
              <select
                id={`categoria-${id}`}
                value={categoryId}
                onChange={(event) => setCategoryId(event.target.value)}
                aria-invalid={categoryError ? true : undefined}
                className={cn(selectClass, categoryError && 'border-red-400')}
              >
                <option value="">Selecciona una categoría</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
              {categoryError && (
                <p className="mt-1 text-xs text-red-600">{categoryError}</p>
              )}
            </div>
            <div>
              <label
                htmlFor={`urgencia-${id}`}
                className="block text-sm font-medium text-[#334155]"
              >
                Urgencia
              </label>
              <select
                id={`urgencia-${id}`}
                value={urgency}
                onChange={(event) => setUrgency(Number(event.target.value))}
                className={selectClass}
              >
                {LEVELS.map((level) => (
                  <option key={level} value={level}>
                    {levelLabel(level)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor={`impacto-${id}`}
                className="block text-sm font-medium text-[#334155]"
              >
                Impacto
              </label>
              <select
                id={`impacto-${id}`}
                value={impact}
                onChange={(event) => setImpact(Number(event.target.value))}
                className={selectClass}
              >
                {LEVELS.map((level) => (
                  <option key={level} value={level}>
                    {levelLabel(level)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label
              htmlFor={`justificacion-${id}`}
              className="block text-sm font-medium text-[#334155]"
            >
              Justificación
            </label>
            <textarea
              id={`justificacion-${id}`}
              value={justification}
              onChange={(event) => setJustification(event.target.value)}
              rows={3}
              aria-invalid={justificationError ? true : undefined}
              placeholder={
                changes.length > 0
                  ? 'Explica por qué corriges la propuesta…'
                  : 'Explica por qué confirmas la propuesta…'
              }
              className={cn(
                'mt-1.5 w-full rounded-lg border bg-white px-3 py-2.5 text-sm text-[#17212b] placeholder:text-[#94a3b8] focus:ring-2 focus:outline-none',
                justificationError
                  ? 'border-red-400 focus:ring-red-200'
                  : 'border-[#d7e0df] focus:border-[#0f766e] focus:ring-[#0f766e]/20',
              )}
            />
            {justificationError && (
              <p className="mt-1 text-xs text-red-600">{justificationError}</p>
            )}
            <p className="mt-1 text-xs text-[#87959c]">
              {changes.length > 0
                ? `Cambias: ${changes.join(', ')}. `
                : 'Sin cambios: confirmas la propuesta. '}
              La prioridad se recalcula al guardar.
            </p>
          </div>

          {guardar.isError && !hasFieldErrors && (
            <ErrorAlert error={guardar.error} />
          )}

          <div className="flex justify-end">
            <Button type="submit" disabled={guardar.isPending}>
              {guardar.isPending ? 'Guardando…' : 'Guardar revisión'}
            </Button>
          </div>
        </form>
      </article>
    </li>
  )
}
