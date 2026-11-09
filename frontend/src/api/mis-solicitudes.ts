import { apiFetch } from '@/api/client'
import type { RequestStatus } from '@/api/seguimiento'
import type { Priority } from '@/api/types'

/*
 * Consulta del solicitante por folio (S4-01 en el backend, S4-02 aquí).
 * Tipos escritos a mano a partir de `backend/app/schemas/mis_solicitudes.py`: `openapi.ts`
 * aún no incluye estos endpoints. Cuando se regenere se pueden reemplazar por `ApiSchemas[...]`.
 */

/** Renglón de la lista «Mis solicitudes». */
export type MiSolicitudResumen = {
  folio: string
  title: string
  status: RequestStatus
  priority: Priority | null
  created_at: string
}

/** Entrada resumida de la bitácora (sin las notas internas del técnico). */
export type MiSolicitudBitacoraEntrada = {
  action: string
  new_status: RequestStatus | null
  created_at: string
}

export type MiSolicitudDetalle = {
  folio: string
  title: string
  status: RequestStatus
  priority: Priority | null
  category: string | null
  due_at: string | null
  technician: string | null
  created_at: string
  resolved_at: string | null
  closed_at: string | null
  log: MiSolicitudBitacoraEntrada[]
}

/** Solicitudes de la persona en sesión, de la más reciente a la más antigua. */
export function getMisSolicitudes(): Promise<MiSolicitudResumen[]> {
  return apiFetch<MiSolicitudResumen[]>('/mis-solicitudes')
}

/** Detalle de una solicitud propia. Responde 404 si el folio no existe o no es suyo. */
export function getMiSolicitud(folio: string): Promise<MiSolicitudDetalle> {
  return apiFetch<MiSolicitudDetalle>(
    `/mis-solicitudes/${encodeURIComponent(folio)}`,
  )
}

/** Confirma que la solución funcionó; la solicitud pasa a «Cerrada». */
export function confirmarMiSolicitud(
  folio: string,
  notes: string | null = null,
): Promise<MiSolicitudDetalle> {
  return apiFetch<MiSolicitudDetalle>(
    `/mis-solicitudes/${encodeURIComponent(folio)}/confirmar`,
    { method: 'POST', body: JSON.stringify({ notes }) },
  )
}
