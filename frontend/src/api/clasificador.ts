import { apiFetch } from '@/api/client'

/*
 * Contrato de la administración del clasificador (S5-06, HU-02.2, HU-12.1, HU-12.2).
 * Tipos escritos a mano: `openapi.ts` aún no incluye estos endpoints.
 * Permiso `classification.manage`: solo `administrator`.
 */

export const UMBRAL_MINIMO = 0.5
export const UMBRAL_MAXIMO = 0.95
export const UMBRAL_PASO = 0.05

export type EstadoClasificador = {
  version: string
  umbral: number
  ejemplos: number
  /** Exactitud de categoría entre 0 y 1; `null` si no se midió. */
  exactitud: number | null
  correcciones_pendientes: number
  /** Proporción (0 a 1) de solicitudes recientes enviadas a «Por revisar». */
  proporcion_por_revisar: number | null
  dias_recientes: number
  entrenado_en: string | null
}

export type UmbralResult = {
  umbral_anterior: number
  umbral: number
}

export type ReentrenamientoResult = {
  version: string
  exactitud: number
  ejemplos: number
  correcciones_incorporadas: number
  version_anterior: string
  exactitud_anterior: number | null
  activado: boolean
  mensaje: string
}

export function getEstadoClasificador(): Promise<EstadoClasificador> {
  return apiFetch<EstadoClasificador>('/clasificador/estado')
}

export function guardarUmbral(umbral: number): Promise<UmbralResult> {
  return apiFetch<UmbralResult>('/clasificador/umbral', {
    method: 'PUT',
    body: JSON.stringify({ umbral }),
  })
}

export function reentrenarClasificador(): Promise<ReentrenamientoResult> {
  return apiFetch<ReentrenamientoResult>('/clasificador/reentrenar', {
    method: 'POST',
  })
}
