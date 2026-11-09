import { apiFetch } from '@/api/client'

/*
 * Contrato de los avisos dentro de la aplicación (S4-05 en el backend, S4-06 aquí).
 * Tipos escritos a mano: `openapi.ts` aún no incluye estos endpoints. Cuando se regenere
 * con el esquema OpenAPI del backend se pueden reemplazar por `ApiSchemas[...]`.
 */

export type ImportanciaAviso = 'normal' | 'high'

/** Un aviso tal como lo muestra la campana. */
export type Aviso = {
  id: string
  request_id: string | null
  request_folio: string | null
  subject: string
  body: string
  importance: ImportanciaAviso
  is_read: boolean
  read_at: string | null
  created_at: string
}

type OpcionesListado = {
  onlyUnread?: boolean
  limit?: number
  offset?: number
}

/** Avisos de la persona en sesión, del más reciente al más antiguo. */
export function getAvisos(opciones: OpcionesListado = {}): Promise<Aviso[]> {
  const params = new URLSearchParams()
  if (opciones.onlyUnread) params.set('only_unread', 'true')
  if (opciones.limit !== undefined) params.set('limit', String(opciones.limit))
  if (opciones.offset !== undefined) {
    params.set('offset', String(opciones.offset))
  }
  const consulta = params.toString()
  return apiFetch<Aviso[]>(`/notificaciones${consulta ? `?${consulta}` : ''}`)
}

/** Número de avisos sin leer: es el contador de la campana. */
export async function getAvisosSinLeer(): Promise<number> {
  const { unread } = await apiFetch<{ unread: number }>(
    '/notificaciones/contador',
  )
  return unread
}

export function marcarAvisoLeido(id: string): Promise<Aviso> {
  return apiFetch<Aviso>(`/notificaciones/${id}/leer`, { method: 'POST' })
}

export function marcarTodosLosAvisosLeidos(): Promise<{ updated: number }> {
  return apiFetch<{ updated: number }>('/notificaciones/leer-todas', {
    method: 'POST',
  })
}
