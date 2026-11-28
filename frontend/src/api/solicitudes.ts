import { apiFetch } from '@/api/client'

import type { RequestChannel, RequestStatus } from '@/api/seguimiento'
import type {
  AssistedChannel,
  CreateAssistedRequestInput,
  CreateRequestInput,
  Priority,
  Request,
  WaitReason,
} from '@/api/types'

export type {
  AssistedChannel,
  CreateAssistedRequestInput,
  CreateRequestInput,
  Request,
}

export function createRequest(input: CreateRequestInput): Promise<Request> {
  return apiFetch<Request>('/solicitudes', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function createAssistedRequest(
  input: CreateAssistedRequestInput,
): Promise<Request> {
  return apiFetch<Request>('/solicitudes/asistido', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function putRequestOnHold(
  requestId: string,
  reason: WaitReason,
  detail: string | null,
): Promise<Request> {
  return apiFetch<Request>(`/solicitudes/${requestId}/espera`, {
    method: 'POST',
    body: JSON.stringify({ reason, detail }),
  })
}

/** Reanuda una solicitud en espera; vuelve a «En atención» (HU-04.2). */
export function reanudarSolicitud(requestId: string): Promise<Request> {
  return apiFetch<Request>(`/solicitudes/${requestId}/reanudar`, {
    method: 'POST',
  })
}

/*
 * Listado de solicitudes (`GET /solicitudes`). Tipos escritos a mano porque `openapi.ts`
 * todavía no incluye este endpoint; se pueden reemplazar al regenerarlo.
 */
export type RequestSummary = {
  id: string
  folio: string
  title: string
  status: RequestStatus
  priority: Priority | null
  category_id: string | null
  created_at: string
  updated_at: string
  physical_location: string
  channel: RequestChannel
  requester_institutional_id: string | null
  category_name: string | null
  requester_name: string | null
}

export type RequestPage = {
  items: RequestSummary[]
  total: number
  limit: number
  offset: number
}

export type ListRequestsParams = {
  q?: string
  status?: RequestStatus | ''
  priority?: Priority | ''
  limit?: number
  offset?: number
}

export function listRequests(
  params: ListRequestsParams = {},
): Promise<RequestPage> {
  const query = new URLSearchParams()
  if (params.q?.trim()) query.set('q', params.q.trim())
  if (params.status) query.set('status', params.status)
  if (params.priority) query.set('priority', params.priority)
  if (params.limit !== undefined) query.set('limit', String(params.limit))
  if (params.offset !== undefined) query.set('offset', String(params.offset))
  const suffix = query.toString()
  return apiFetch<RequestPage>(
    suffix ? `/solicitudes?${suffix}` : '/solicitudes',
  )
}
