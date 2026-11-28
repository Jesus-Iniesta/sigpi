import { apiFetch } from '@/api/client'

/*
 * Contrato de la bitácora de auditoría (S2-08, HU-10.3).
 * Refleja `AuditoriaRead` de `backend/app/schemas/auditoria.py`; la bitácora es
 * de solo lectura, así que aquí no hay funciones de escritura.
 */

export type RegistroAuditoria = {
  id: string
  /** Usuario que hizo el cambio; `null` si lo hizo el sistema. */
  actor_id: string | null
  action: string
  entity_type: string
  entity_id: string
  old_values: Record<string, unknown> | null
  new_values: Record<string, unknown> | null
  ip_address: string | null
  /** Fecha ISO 8601. */
  created_at: string
}

export type FiltrosAuditoria = {
  entity_type?: string
  entity_id?: string
}

/** Arma la cadena de consulta sin los filtros vacíos o solo con espacios. */
export function auditoriaQuery(filtros: FiltrosAuditoria): string {
  const params = new URLSearchParams()
  for (const clave of ['entity_type', 'entity_id'] as const) {
    const valor = filtros[clave]?.trim()
    if (valor) params.set(clave, valor)
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

export function getAuditoria(
  filtros: FiltrosAuditoria = {},
): Promise<RegistroAuditoria[]> {
  return apiFetch<RegistroAuditoria[]>(`/auditoria${auditoriaQuery(filtros)}`)
}
