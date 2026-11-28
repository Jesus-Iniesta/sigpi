import type { RequestStatus } from '@/api/seguimiento'

/*
 * Reglas de las acciones de atención (HU-04.1, HU-04.2). Copian las del backend
 * (`backend/app/domain/estados.py` y `backend/app/core/permissions.py`) para
 * mostrar cada botón solo cuando el servidor aceptaría la acción.
 */

const ESTADOS_QUE_PUEDEN_INICIAR: readonly RequestStatus[] = ['assigned']
const ESTADOS_QUE_ADMITEN_DIAGNOSTICO: readonly RequestStatus[] = [
  'assigned',
  'in_progress',
  'waiting',
]
const ESTADOS_QUE_PUEDEN_RESOLVER: readonly RequestStatus[] = [
  'assigned',
  'in_progress',
]

// Roles con requests.update, requests.resolve y requests.close.
export const ROLES_DE_ATENCION = [
  'administrator',
  'service_manager',
  'support_agent',
]

export function puedeIniciar(status: RequestStatus): boolean {
  return ESTADOS_QUE_PUEDEN_INICIAR.includes(status)
}

export function puedeDiagnosticar(status: RequestStatus): boolean {
  return ESTADOS_QUE_ADMITEN_DIAGNOSTICO.includes(status)
}

export function puedeResolver(status: RequestStatus): boolean {
  return ESTADOS_QUE_PUEDEN_RESOLVER.includes(status)
}

export function puedeReanudar(status: RequestStatus): boolean {
  return status === 'waiting'
}

export function puedeCerrar(status: RequestStatus): boolean {
  return status === 'resolved'
}

/** `true` si alguno de los roles puede atender, resolver y cerrar solicitudes. */
export function puedeAtender(roles: string[] | undefined): boolean {
  return roles?.some((role) => ROLES_DE_ATENCION.includes(role)) ?? false
}
