import { useState } from 'react'
import { CheckCircle2 } from 'lucide-react'
import type { RevisionItem, RevisionResult } from '@/api/revision'
import { RevisionItemCard } from '@/features/clasificacion/components/RevisionItemCard'
import {
  useRevisionCategories,
  useRevisionQueue,
} from '@/features/clasificacion/use-revision'
import { ErrorAlert } from '@/shared/ui/error-alert'

export function RevisionPage() {
  const queue = useRevisionQueue()
  const categories = useRevisionCategories()
  const [saved, setSaved] = useState<string | null>(null)

  const handleSaved = (item: RevisionItem, result: RevisionResult) => {
    setSaved(
      result.priority
        ? `Revisaste ${item.folio}. Nueva prioridad: ${result.priority}.`
        : `Revisaste ${item.folio}.`,
    )
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="mb-2 text-xs font-bold tracking-[0.16em] text-[#0f766e] uppercase">
          Clasificación
        </p>
        <h1 className="text-3xl font-bold tracking-tight">
          Revisión de clasificaciones
        </h1>
        <p className="mt-2 max-w-2xl text-[#718096]">
          Estas solicitudes quedaron por debajo del umbral de confianza y
          necesitan una persona antes de continuar. Corrige la categoría, la
          urgencia o el impacto si hace falta y explica tu decisión.
        </p>
      </header>

      {saved && (
        <div
          role="status"
          className="flex items-start gap-2 rounded-lg bg-green-50 px-3 py-2.5 text-sm text-green-700"
        >
          <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
          <span>{saved}</span>
        </div>
      )}

      {queue.isPending && (
        <p role="status" className="text-sm text-[#718096]">
          Cargando cola de revisión…
        </p>
      )}

      {queue.isError && (
        <ErrorAlert
          error={queue.error}
          fallback="No se pudo cargar la cola de revisión."
        />
      )}

      {categories.isError && (
        <ErrorAlert
          error={categories.error}
          fallback="No se pudieron cargar las categorías."
        />
      )}

      {queue.isSuccess && queue.data.length === 0 && (
        <p className="rounded-xl border border-dashed border-[#d7e0df] bg-white p-8 text-center text-sm text-[#718096]">
          No hay clasificaciones pendientes de revisión.
        </p>
      )}

      {queue.isSuccess && queue.data.length > 0 && (
        <>
          <p className="text-sm font-medium text-[#52616b]">
            {queue.data.length === 1
              ? '1 clasificación pendiente'
              : `${queue.data.length} clasificaciones pendientes`}
          </p>
          <ul className="space-y-5">
            {queue.data.map((item) => (
              <RevisionItemCard
                key={item.result_id}
                item={item}
                categories={categories.data ?? []}
                onSaved={handleSaved}
              />
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
