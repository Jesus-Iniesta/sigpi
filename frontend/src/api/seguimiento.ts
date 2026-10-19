import { apiFetch } from '@/api/client'
import type { Priority } from '@/api/types'

/*
 * Tipos escritos a mano a partir de los esquemas RequestRead y RequestLogRead del backend.
 * `openapi.ts` todavía no los incluye completos
 * Cuando se regenere con el esquema OpenAPI actual, se pueden reemplazar por `ApiSchemas[...]`.
 */

export type RequestStatus =
  | 'registered'
  | 'pending_verification'
  | 'classified'
  | 'pending_review'
  | 'assigned'
  | 'in_progress'
  | 'waiting'
  | 'escalated'
  | 'resolved'
  | 'closed'
  | 'closed_unverified'

export type RequestChannel = 'portal' | 'phone' | 'in_person'

export type RequestDetail = {
  id: string
  requester_id: string | null
  requester_institutional_id: string | null
  category_id: string | null
  asset_id: string | null
  service_level_version_id: string | null
  related_request_id: string | null
  folio: string
  title: string
  description: string
  physical_location: string
  channel: RequestChannel
  status: RequestStatus
  priority: Priority | null
  urgency: number | null
  impact: number | null
  classification_confidence: number | null
  diagnosis: string | null
  solution: string | null
  resolution_minutes: number | null
  first_response_at: string | null
  resolved_at: string | null
  closed_at: string | null
  created_at: string
  updated_at: string
}

export type RequestLogEntry = {
  id: string
  request_id: string
  author_id: string
  previous_status: RequestStatus | null
  new_status: RequestStatus | null
  action: string
  notes: string | null
  created_at: string
}

export function getRequestDetail(requestId: string): Promise<RequestDetail> {
  return apiFetch<RequestDetail>(`/solicitudes/${requestId}`)
}

/** Entradas de la bitácora, de la más antigua a la más reciente. */
export function getRequestLog(requestId: string): Promise<RequestLogEntry[]> {
  return apiFetch<RequestLogEntry[]>(`/solicitudes/${requestId}/bitacora`)
}
