import { apiFetch } from '@/api/client'
import type {
  CreateSlaAgreementInput,
  CreateSlaVersionInput,
  EffectiveSla,
  Priority,
  SlaAgreement,
  SlaVersion,
} from '@/api/types'

export const priorities = [
  'P1',
  'P2',
  'P3',
  'P4',
] as const satisfies readonly Priority[]

export type { EffectiveSla, Priority, SlaAgreement, SlaVersion }

// openapi.ts aún no refleja COR-05: `name` es opcional (el predeterminado lo asigna el
// servidor) y existe `GET /sla/options`. Se tipan aquí hasta regenerarlo.
export type SlaAgreementInput = Omit<CreateSlaAgreementInput, 'name'> & {
  name?: string | null
}
export type SlaOptions = {
  default_name: string
  service_types: string[]
}
export type SlaPriorityTimes = CreateSlaVersionInput['times'][number]
export type SlaVersionInput = CreateSlaVersionInput
export type EffectiveSlaQuery = {
  priority: Priority
  categoryId?: string
  at?: string
}

export const getSlaOptions = (): Promise<SlaOptions> =>
  apiFetch<SlaOptions>('/sla/options')

export const getSlaAgreements = (): Promise<SlaAgreement[]> =>
  apiFetch<SlaAgreement[]>('/sla/agreements')

export const createSlaAgreement = (
  input: SlaAgreementInput,
): Promise<SlaAgreement> =>
  apiFetch<SlaAgreement>('/sla/agreements', {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const getSlaVersions = (
  agreementId: string,
  priority?: Priority,
): Promise<SlaVersion[]> => {
  const query = priority ? `?priority=${encodeURIComponent(priority)}` : ''
  return apiFetch<SlaVersion[]>(
    `/sla/agreements/${agreementId}/versions${query}`,
  )
}

export const publishSlaVersion = (
  agreementId: string,
  input: SlaVersionInput,
): Promise<SlaVersion[]> =>
  apiFetch<SlaVersion[]>(`/sla/agreements/${agreementId}/versions`, {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const createSlaVersion = publishSlaVersion

export function getEffectiveSla({
  priority,
  categoryId,
  at,
}: EffectiveSlaQuery): Promise<EffectiveSla> {
  const params = new URLSearchParams({ priority })
  if (categoryId) params.set('category_id', categoryId)
  if (at) params.set('at', at)
  return apiFetch<EffectiveSla>(`/sla/effective?${params.toString()}`)
}
