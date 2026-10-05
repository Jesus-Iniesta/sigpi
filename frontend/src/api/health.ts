import { apiFetch } from '@/api/client'
import type { HealthResponse } from '@/api/types'

export type { HealthResponse }

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health')
}
