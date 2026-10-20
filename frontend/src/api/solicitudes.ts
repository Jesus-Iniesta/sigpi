import { apiFetch } from '@/api/client'

import type {
  AssistedChannel,
  CreateAssistedRequestInput,
  CreateRequestInput,
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
