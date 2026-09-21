import { apiFetch } from '@/api/client'

export type HealthResponse = {
  status: string
  service: string
}

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health')
}
