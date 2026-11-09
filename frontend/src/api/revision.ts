import { apiFetch } from '@/api/client'
import type { Priority } from '@/api/types'
import type { RequestStatus } from '@/api/seguimiento'

/*
 * Contrato de la revisión de clasificaciones (S4-14, S4-16 y S4-15).
 * Tipos escritos a mano: `openapi.ts` aún no incluye estos endpoints. Cuando se regenere
 * con el esquema OpenAPI del backend se pueden reemplazar por `ApiSchemas[...]`.
 */

export type ClassificationSource = 'model' | 'rules' | 'human'

/** Una clasificación de baja confianza que espera revisión humana. */
export type RevisionItem = {
  result_id: string
  request_id: string
  folio: string
  title: string
  description: string
  created_at: string
  category_id: string | null
  category_name: string | null
  urgency: number
  impact: number
  priority: Priority | null
  /** Entre 0 y 1. */
  confidence: number
  source: ClassificationSource
  model_version: string | null
}

/** Lo que decide la persona revisora; la prioridad la recalcula el servidor (RN-05). */
export type RevisionInput = {
  category_id: string
  urgency: number
  impact: number
  justification: string
}

export type RevisionResult = {
  request_id: string
  status: RequestStatus
  priority: Priority | null
}

/** Solicitudes en cola de revisión (la ruta definitiva la consolida S5-04). */
export function getRevisionQueue(): Promise<RevisionItem[]> {
  return apiFetch<RevisionItem[]>('/revision/cola')
}

/** Guarda la revisión de una clasificación y la guarda como ejemplo de reentrenamiento. */
export function submitRevision(
  resultId: string,
  input: RevisionInput,
): Promise<RevisionResult> {
  return apiFetch<RevisionResult>(`/revision/${resultId}/correccion`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}
