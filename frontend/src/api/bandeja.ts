import { apiFetch } from '@/api/client'
import type { RequestStatus } from '@/api/seguimiento'
import type { Priority } from '@/api/types'

/*
 * Contrato de la bandeja de solicitudes asignadas (S5-04, HU-04.6).
 * Tipos escritos a mano: `openapi.ts` aún no incluye este endpoint.
 */

/** Renglón de la bandeja: la solicitud y el avance de su reloj del SLA. */
export type BandejaElemento = {
  request_id: string
  folio: string
  titulo: string
  estatus: RequestStatus
  prioridad: Priority | null
  categoria: string | null
  fecha_registro: string
  fecha_compromiso: string | null
  /** Entre 0 y 100; `null` si la solicitud aún no tiene SLA. */
  porcentaje_consumido: number | null
  en_riesgo: boolean
}

export type BandejaParams = {
  estatus?: RequestStatus | ''
  prioridad?: Priority | ''
  /** Solo para quien puede asignar (jefe o administrador). */
  todas?: boolean
}

/** Solicitudes asignadas a la persona, o a todo el equipo con `todas`. */
export function getBandeja(
  params: BandejaParams = {},
): Promise<BandejaElemento[]> {
  const query = new URLSearchParams()
  if (params.estatus) query.set('estatus', params.estatus)
  if (params.prioridad) query.set('prioridad', params.prioridad)
  if (params.todas) query.set('todas', 'true')
  const suffix = query.toString()
  return apiFetch<BandejaElemento[]>(suffix ? `/bandeja?${suffix}` : '/bandeja')
}
