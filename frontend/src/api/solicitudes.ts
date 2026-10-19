import { apiFetch } from '@/api/client'
import type { CreateRequestInput, Request, WaitReason } from '@/api/types'

export type { CreateRequestInput, Request }

export function createRequest(input: CreateRequestInput): Promise<Request> {
  return apiFetch<Request>('/solicitudes', {
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
