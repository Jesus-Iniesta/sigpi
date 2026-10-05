import { apiFetch } from '@/api/client'
import type { CreateRequestInput, Request } from '@/api/types'

export type { CreateRequestInput, Request }

export function createRequest(input: CreateRequestInput): Promise<Request> {
  return apiFetch<Request>('/solicitudes', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}
