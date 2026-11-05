import { apiFetch, apiRequest } from '@/api/client'
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

export const CONTRATO_NOMBRE_POR_DEFECTO = 'contrato.pdf'

export const contratoUrl = (agreementId: string) =>
  `/sla/agreements/${encodeURIComponent(agreementId)}/contrato.pdf`

/**
 * Lee el nombre del archivo de `Content-Disposition` (`filename*` o `filename`).
 * Si el encabezado no llega o no es legible, devuelve `contrato.pdf`.
 */
export function nombreDeContrato(disposition: string | null): string {
  if (!disposition) return CONTRATO_NOMBRE_POR_DEFECTO
  const extendido = /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i.exec(disposition)
  if (extendido) {
    try {
      const nombre = decodeURIComponent(extendido[1].trim().replace(/"/g, ''))
      if (nombre) return nombre
    } catch {
      // Codificación inválida: se intenta con `filename`.
    }
  }
  const simple = /filename\s*=\s*("([^"]*)"|[^;]+)/i.exec(disposition)
  const nombre = (simple?.[2] ?? simple?.[1] ?? '').trim()
  return nombre || CONTRATO_NOMBRE_POR_DEFECTO
}

/**
 * Descarga el contrato en PDF de la versión vigente del acuerdo (COR-06B).
 * Si el servidor responde con error, lanza `ApiError` igual que `apiFetch` (COR-07).
 */
export async function descargarContrato(agreementId: string): Promise<void> {
  const response = await apiRequest(contratoUrl(agreementId))
  const blob = await response.blob()
  const nombre = nombreDeContrato(response.headers.get('Content-Disposition'))

  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombre
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  // Se revoca después del clic para no cancelar la descarga en algunos navegadores.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
