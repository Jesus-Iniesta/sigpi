import { apiFetch } from '@/api/client'
import type { RequestStatus } from '@/api/seguimiento'

/*
 * Contrato de la asignación de técnicos (S5-03 y S5-12, HU-03.1 y HU-03.3).
 * Tipos escritos a mano: `openapi.ts` aún no incluye estos endpoints. Cuando se regenere
 * con el esquema OpenAPI del backend se pueden reemplazar por `ApiSchemas[...]`.
 */

/** Un concepto del puntaje de un candidato. */
export type ComponentePuntaje = {
  concepto: string
  puntos: number
  detalle: string
}

/** Técnico candidato con su puntaje y el desglose que lo explica. */
export type CandidatoAsignacion = {
  technician_id: string
  full_name: string
  score: number
  active_load: number
  score_breakdown: string
  components: ComponentePuntaje[]
}

/** Asignación vigente tras asignar, con el estatus en que quedó la solicitud. */
export type AsignacionResult = {
  id: string
  request_id: string
  technician_id: string
  score: number | null
  score_breakdown: string | null
  is_automatic: boolean
  assigned_at: string
  unassigned_at: string | null
  request_status: RequestStatus
}

/** Técnico asignado a la solicitud y el desglose del puntaje con el que se eligió. */
export type AsignacionVigente = {
  id: string
  request_id: string
  technician_id: string
  full_name: string
  /** `null` en asignaciones sin puntaje (anteriores al motor de asignación). */
  score: number | null
  score_breakdown: string | null
  /** Vacío si no hay puntaje o el texto no pudo separarse. */
  components: ComponentePuntaje[]
  is_automatic: boolean
  assigned_at: string
}

/** Candidatos para atender la solicitud, ordenados del mejor al peor. */
export function getPropuestaAsignacion(
  requestId: string,
): Promise<CandidatoAsignacion[]> {
  return apiFetch<CandidatoAsignacion[]>(`/asignaciones/${requestId}/propuesta`)
}

/** Asigna la solicitud al técnico elegido. */
export function asignarTecnico(
  requestId: string,
  technicianId: string,
): Promise<AsignacionResult> {
  return apiFetch<AsignacionResult>(`/asignaciones/${requestId}`, {
    method: 'POST',
    body: JSON.stringify({ technician_id: technicianId }),
  })
}

/** Asignación vigente de la solicitud; `null` si todavía no tiene técnico. */
export function getAsignacionVigente(
  requestId: string,
): Promise<AsignacionVigente | null> {
  return apiFetch<AsignacionVigente | null>(`/asignaciones/${requestId}`)
}
