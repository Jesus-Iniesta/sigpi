import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getCategories } from '@/api/catalog'
import {
  getRevisionQueue,
  submitRevision,
  type RevisionInput,
  type RevisionResult,
} from '@/api/revision'

const REVISION_QUEUE_KEY = ['revision', 'cola'] as const

/** Cola de clasificaciones pendientes de revisión (HU-02.2). */
export function useRevisionQueue() {
  return useQuery({
    queryKey: REVISION_QUEUE_KEY,
    queryFn: getRevisionQueue,
  })
}

/** Categorías del catálogo para poder corregir la propuesta; solo las activas. */
export function useRevisionCategories() {
  return useQuery({
    queryKey: ['catalogo', 'categorias'],
    queryFn: async () => (await getCategories()).filter((c) => c.is_active),
  })
}

/**
 * Guarda la revisión de una clasificación. Al terminar, la solicitud sale de la cola
 * porque el servidor la pasa a «Clasificada».
 *
 * `onSaved` se pasa aquí y no a `mutate()`: al refrescarse la cola la tarjeta se
 * desmonta, y TanStack Query no ejecuta los callbacks de `mutate()` de un componente
 * desmontado.
 */
export function useGuardarRevision(
  resultId: string,
  onSaved?: (result: RevisionResult) => void,
) {
  const queryClient = useQueryClient()
  return useMutation<RevisionResult, Error, RevisionInput>({
    mutationFn: (input) => submitRevision(resultId, input),
    onSuccess: (result) => {
      onSaved?.(result)
      return queryClient.invalidateQueries({ queryKey: REVISION_QUEUE_KEY })
    },
  })
}
