import { apiFetch } from '@/api/client'

export const priorities = ['P1', 'P2', 'P3', 'P4'] as const

export type Priority = (typeof priorities)[number]

export type SlaAgreement = {
  id: string
  category_id: string | null
  name: string
  is_default: boolean
  is_active: boolean
  created_at: string
}

export type SlaVersion = {
  id: string
  agreement_id: string
  version: number
  priority: Priority
  first_response_minutes: number
  resolution_minutes: number
  valid_from: string
  valid_to: string | null
}

export type SlaAgreementInput = {
  name: string
  category_id?: string | null
  is_default?: boolean
}

export type SlaPriorityTimes = {
  priority: Priority
  first_response_minutes: number
  resolution_minutes: number
}

export type SlaVersionInput = {
  valid_from: string
  times: SlaPriorityTimes[]
}

export type EffectiveSla = {
  agreement_id: string
  agreement_name: string
  version: number
  priority: Priority
  first_response_minutes: number
  resolution_minutes: number
  valid_from: string
  used_default: boolean
  notice: string | null
}

export type EffectiveSlaQuery = {
  priority: Priority
  categoryId?: string
  at?: string
}

export const getSlaAgreements = () =>
  apiFetch<SlaAgreement[]>('/sla/agreements')

export const createSlaAgreement = (input: SlaAgreementInput) =>
  apiFetch<SlaAgreement>('/sla/agreements', {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const getSlaVersions = (agreementId: string) =>
  apiFetch<SlaVersion[]>(`/sla/agreements/${agreementId}/versions`)

export const publishSlaVersion = (
  agreementId: string,
  input: SlaVersionInput,
) =>
  apiFetch<SlaVersion[]>(`/sla/agreements/${agreementId}/versions`, {
    method: 'POST',
    body: JSON.stringify(input),
  })

export function getEffectiveSla({
  priority,
  categoryId,
  at,
}: EffectiveSlaQuery) {
  const params = new URLSearchParams({ priority })
  if (categoryId) params.set('category_id', categoryId)
  if (at) params.set('at', at)
  return apiFetch<EffectiveSla>(`/sla/effective?${params.toString()}`)
}
